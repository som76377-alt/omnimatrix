#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
TOKEN_FILE="/tmp/omnitrix-studio-runtime-token"
LOG_FILE="/tmp/omnitrix-studio.log"
PID_FILE="/tmp/omnitrix-studio-supervisor.pid"

if [[ -s "$PID_FILE" ]]; then
  existing_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "$existing_pid" =~ ^[0-9]+$ ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "Omnitrix Studio supervisor is already running (PID $existing_pid)."
    echo "Runtime access token (keep private; paste into the Omnitrix Android app): $(cat "$TOKEN_FILE")"
    echo "Logs: tail -f $LOG_FILE"
    exit 0
  fi
fi

if [[ ! -s "$TOKEN_FILE" ]]; then
  umask 077
  python -c 'import secrets; print(secrets.token_urlsafe(32))' > "$TOKEN_FILE"
fi
chmod 600 "$TOKEN_FILE"
TOKEN="$(cat "$TOKEN_FILE")"

# Prefer the real multi-provider profile when a runtime credential is present.
# GitHub Actions secrets do not automatically become Codespaces environment variables;
# configure Codespaces secrets separately or explicitly set OMNITRIX_MODEL_CONFIG.
if [[ -n "${OMNITRIX_MODEL_CONFIG:-}" ]]; then
  MODEL_CONFIG="$OMNITRIX_MODEL_CONFIG"
elif [[ -f config/mobile.models.json && ( -n "${GEMINI_API_KEY:-}" || -n "${GEMINI_API_KEY_1:-}" || -n "${OPENROUTER_API_KEY:-}" || -n "${OPENROUTER_API_KEY_1:-}" || -n "${GROQ_API_KEY:-}" || -n "${GROQ_API_KEY_1:-}" ) ]]; then
  MODEL_CONFIG="config/mobile.models.json"
else
  MODEL_CONFIG="config/demo.models.json"
fi

# This supervisor restarts the server after the safe main-branch fast-forward
# updater exits the process. No shell text is accepted from the browser.
nohup bash -c '
  set +e
  token="$1"
  model_config="$2"
  while true; do
    python -m interfaces.web.server \
      --host 0.0.0.0 \
      --port 8000 \
      --config "$model_config" \
      --workspace-root . \
      --allow-workspace-read \
      --allow-workspace-write \
      --enable-cline-coding \
      --workspace-allow core \
      --workspace-allow interfaces \
      --workspace-allow tests \
      --workspace-allow docs \
      --workspace-allow config \
      --workspace-allow webapp \
      --workspace-allow android \
      --workspace-allow README.md \
      --allow-test-run \
      --auto-sync-main \
      --auto-sync-interval 60 \
      --access-token "$token"
    exit_code=$?
    if [[ "$exit_code" -eq 0 ]]; then
      exit 0
    fi
    sleep 2
  done
' omnitrix-studio-supervisor "$TOKEN" "$MODEL_CONFIG" </dev/null > "$LOG_FILE" 2>&1 &
echo "$!" > "$PID_FILE"
chmod 600 "$PID_FILE" "$LOG_FILE" 2>/dev/null || true

echo "OMNITRIX STUDIO STARTING on Codespaces port 8000."
echo "Model profile selected: $MODEL_CONFIG"
echo "Runtime access token (keep private; paste into the Omnitrix Android app): $TOKEN"
echo "Server log: tail -f $LOG_FILE"
echo "The app will fast-forward a clean checkout of main when GitHub changes arrive."
echo "Cline CLI is installed by the devcontainer. First use: run cline auth once in the Codespaces terminal to configure its model provider."
if [[ "$MODEL_CONFIG" == "config/demo.models.json" ]]; then
  echo "DEMO MODE: specialist routing is simulated/offline. Add GEMINI_API_KEY or OPENROUTER_API_KEY as a Codespaces secret, or set OMNITRIX_MODEL_CONFIG, to enable real-model orchestration."
fi
