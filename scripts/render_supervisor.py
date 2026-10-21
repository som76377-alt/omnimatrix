"""Supervise the loopback-only FreeLLMAPI sidecar and Omnitrix Render server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / ".tools" / "node" / "bin" / "node"
GATEWAY_ROOT = ROOT / ".tools" / "freellmapi"
GATEWAY_ENTRY = GATEWAY_ROOT / "server" / "dist" / "index.js"
GATEWAY_DB = GATEWAY_ROOT / "server" / "data" / "freeapi.db"
GATEWAY_PORT = 3001
API_KEY_PREFIX = "freellmapi-"

ROUTE_SPECS = (
    ("google", "gemini-3.6-flash", "GEMINI_API_KEY", "Omnitrix Gemini primary"),
    ("google", "gemini-3.5-flash-lite", "GEMINI_API_KEY_1", "Omnitrix Gemini secondary"),
    ("openrouter", "minimax/minimax-m3.1-flash:free", "OPENROUTER_API_KEY", "Omnitrix OpenRouter primary"),
    ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", "OPENROUTER_API_KEY_1", "Omnitrix OpenRouter secondary"),
    ("groq", "openai/gpt-oss-120b", "GROQ_API_KEY", "Omnitrix Groq primary"),
    ("groq", "openai/gpt-oss-20b", "GROQ_API_KEY_1", "Omnitrix Groq secondary"),
)


def _groq_free_confirmed(env: dict[str, str]) -> bool:
    return env.get("GROQ_FREE_QUOTA_CONFIRMED", "").strip().lower() == "true"


def _configured_routes(env: dict[str, str]) -> list[tuple[str, str, str, str]]:
    """Return only model/key pairs explicitly present in the environment."""
    routes = []
    for platform, model_id, key_env, label in ROUTE_SPECS:
        if not env.get(key_env, "").strip():
            continue
        if platform == "groq" and not _groq_free_confirmed(env):
            continue
        routes.append((platform, model_id, key_env, label))
    return routes


def _declarative_config(env: dict[str, str]) -> tuple[dict[str, object], list[tuple[str, str, str, str]]]:
    """Build boot config in memory; never persist or print raw provider credentials."""
    routes = _configured_routes(env)
    keys = []
    seen: set[tuple[str, str]] = set()
    for platform, _model_id, key_env, label in routes:
        identity = (platform, key_env)
        if identity in seen:
            continue
        seen.add(identity)
        keys.append({
            "platform": platform,
            "key": env[key_env],
            "label": key_env.lower().replace("_api_key", "").replace("_", "-"),
            "enabled": True,
        })
    models = [
        {
            "platform": platform,
            "modelId": model_id,
            "displayName": label,
            "enabled": True,
            "fallbackEnabled": True,
            "supportsTools": platform in {"openrouter", "groq"},
        }
        for platform, model_id, _key_env, label in routes
    ]
    return {
        "keys": keys,
        "models": models,
        "routing": {"strategy": "balanced", "keySelectionStrategy": "auto"},
    }, routes


def _apply_gateway_policy(
    db_path: Path,
    unified_api_key: str,
    routes: list[tuple[str, str, str, str]],
) -> int:
    """Reset gateway model eligibility to an explicit allowlist of the owner's free-quota routes."""
    if not unified_api_key.startswith(API_KEY_PREFIX) or len(unified_api_key) < 32:
        raise RuntimeError("Gateway API credential has an invalid format.")
    if not db_path.is_file():
        raise RuntimeError("Gateway database was not initialized.")
    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        required = {"settings", "models", "fallback_config"}
        if not required.issubset(tables):
            raise RuntimeError("Gateway database schema is not ready.")
        cursor = conn.execute(
            "UPDATE settings SET value = ? WHERE key = 'unified_api_key'",
            (unified_api_key,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("Gateway unified API key setting is missing or ambiguous.")

        # Fail closed first. Catalog routing must never see unrelated models, paid
        # candidates, or keyless endpoints as an available choice for auto:balanced.
        conn.execute("UPDATE models SET enabled = 0")
        conn.execute("UPDATE fallback_config SET enabled = 0")

        priority = conn.execute(
            "SELECT COALESCE(MAX(priority), 0) FROM fallback_config"
        ).fetchone()[0]
        enabled_rows = 0
        for platform, model_id, _key_env, _label in routes:
            rows = conn.execute(
                "SELECT id FROM models WHERE platform = ? AND model_id = ?",
                (platform, model_id),
            ).fetchall()
            for (model_db_id,) in rows:
                conn.execute("UPDATE models SET enabled = 1 WHERE id = ?", (model_db_id,))
                chain = conn.execute(
                    "SELECT 1 FROM fallback_config WHERE model_db_id = ?",
                    (model_db_id,),
                ).fetchone()
                if chain:
                    conn.execute(
                        "UPDATE fallback_config SET enabled = 1 WHERE model_db_id = ?",
                        (model_db_id,),
                    )
                else:
                    priority += 1
                    conn.execute(
                        "INSERT INTO fallback_config (model_db_id, priority, enabled) VALUES (?, ?, 1)",
                        (model_db_id, priority),
                    )
                enabled_rows += 1

        if enabled_rows == 0:
            # Persist the safe empty allowlist before failing, rather than rolling
            # back the disable-all step in the exception handler.
            conn.commit()
            raise RuntimeError("No configured free-quota routes exist in the gateway model catalog.")
        unexpected = conn.execute(
            "SELECT COUNT(*) FROM models WHERE enabled = 1 AND NOT (" +
            " OR ".join("(platform = ? AND model_id = ?)" for _ in routes) + ")",
            tuple(value for platform, model_id, _key_env, _label in routes for value in (platform, model_id)),
        ).fetchone()[0] if routes else 0
        if unexpected:
            raise RuntimeError("Gateway model allowlist verification failed.")
        unexpected_fallbacks = conn.execute(
            "SELECT COUNT(*) FROM fallback_config WHERE enabled = 1 AND model_db_id NOT IN "
            "(SELECT id FROM models WHERE enabled = 1)"
        ).fetchone()[0]
        if unexpected_fallbacks:
            raise RuntimeError("Gateway fallback-chain allowlist verification failed.")
        conn.commit()
        return enabled_rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _wait_for_gateway(process: subprocess.Popen[bytes], timeout_seconds: float = 50.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    url = f"http://127.0.0.1:{GATEWAY_PORT}/api/ping"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Gateway process exited during startup.")
        try:
            with urlopen(url, timeout=1.5) as response:
                if 200 <= response.status < 300:
                    return
        except (OSError, URLError, TimeoutError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Gateway did not become healthy before the startup deadline.")


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)


def _start_gateway(env: dict[str, str]) -> tuple[subprocess.Popen[bytes], int] | None:
    enabled = env.get("OMNITRIX_ENABLE_FREELLMAPI_GATEWAY", "").strip().lower() == "true"
    if not enabled:
        return None
    if not NODE.is_file() or not GATEWAY_ENTRY.is_file():
        print("Gateway disabled: pinned FreeLLMAPI build is unavailable.", flush=True)
        return None
    api_key = env.get("FREELLMAPI_API_KEY", "").strip()
    encryption_key = env.get("FREELLMAPI_ENCRYPTION_KEY", "").strip()
    if not api_key or not encryption_key:
        print("Gateway disabled: required gateway secrets are not configured.", flush=True)
        return None
    if len(encryption_key) != 64 or any(char not in "0123456789abcdefABCDEF" for char in encryption_key):
        print("Gateway disabled: gateway encryption-key format is invalid.", flush=True)
        return None

    config, routes = _declarative_config(env)
    if not routes:
        print("Gateway disabled: no configured free-quota model routes are eligible.", flush=True)
        return None
    sidecar_env = env.copy()
    allowed_ids = {"auto:balanced"}
    for platform, model_id, _key_env, _label in routes:
        allowed_ids.add(model_id)
        allowed_ids.add(f"{platform}/{model_id}")
    # Pass exact identity allowlist to Omnitrix as well. A gateway response that
    # claims a model outside this set is rejected rather than trusted.
    env["FREELLMAPI_ALLOWED_MODEL_IDS"] = ",".join(sorted(allowed_ids))
    env.setdefault("FREELLMAPI_BASE_URL", f"http://127.0.0.1:{GATEWAY_PORT}/v1")
    sidecar_env.update({
        "NODE_ENV": "production",
        "HOST": "127.0.0.1",
        "PORT": str(GATEWAY_PORT),
        "ENCRYPTION_KEY": encryption_key,
        "FREEAPI_DB_PATH": str(GATEWAY_DB),
        "FREEAPI_CONFIG_JSON": json.dumps(config, separators=(",", ":"), ensure_ascii=False),
        # Keep the catalogue static for this pinned experiment. The SQLite
        # allowlist is reapplied from declarative startup config on every boot.
        "CATALOG_SYNC_DISABLED": "1",
        "FREELLMAPI_UPDATE_CHECK": "off",
    })
    GATEWAY_DB.parent.mkdir(parents=True, exist_ok=True)
    process: subprocess.Popen[bytes] | None = None
    try:
        # Discard raw sidecar logs: only safe status messages should reach Render logs.
        process = subprocess.Popen(
            [str(NODE), str(GATEWAY_ENTRY)],
            cwd=str(GATEWAY_ROOT),
            env=sidecar_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for_gateway(process)
        enabled_count = _apply_gateway_policy(GATEWAY_DB, api_key, routes)
        print(
            f"FreeLLMAPI loopback gateway ready; allowlisted model rows: {enabled_count}.",
            flush=True,
        )
        return process, enabled_count
    except Exception as exc:
        _terminate(process)
        # Do not make Omnitrix unavailable when the optional gateway fails.
        print(
            f"FreeLLMAPI disabled safely ({type(exc).__name__}); using direct model routes.",
            flush=True,
        )
        return None


def main() -> int:
    env = os.environ.copy()
    gateway: subprocess.Popen[bytes] | None = None
    gateway_result = _start_gateway(env)
    use_gateway = gateway_result is not None
    if use_gateway:
        gateway = gateway_result[0]
        config_path = "config/mobile.models.freellmapi.json"
        env["OMNITRIX_AGENT_CONFIG"] = "config/agents.freellmapi.json"
    else:
        config_path = "config/mobile.models.json"
        env.pop("OMNITRIX_AGENT_CONFIG", None)

    server = subprocess.Popen(
        [
            sys.executable, "-m", "interfaces.web.server",
            "--host", "0.0.0.0",
            "--port", env.get("PORT", "8000"),
            "--config", config_path,
            "--workspace-root", ".",
            "--allow-public-chat",
            "--allow-free-quota",
        ],
        cwd=str(ROOT),
        env=env,
    )
    def shutdown(_signum: int, _frame: object) -> None:
        _terminate(server)
        _terminate(gateway)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        return server.wait()
    finally:
        _terminate(gateway)


if __name__ == "__main__":
    raise SystemExit(main())
