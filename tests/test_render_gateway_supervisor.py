import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.render_supervisor import _apply_gateway_policy, _declarative_config


class RenderGatewaySupervisorTests(unittest.TestCase):
    def test_config_contains_only_present_provider_keys_and_gates_groq(self):
        env = {
            "GEMINI_API_KEY": "gemini-secret-one",
            "OPENROUTER_API_KEY_1": "openrouter-secret-two",
            "GROQ_API_KEY": "groq-secret-one",
            "GROQ_API_KEY_1": "groq-secret-two",
            "GROQ_FREE_QUOTA_CONFIRMED": "false",
        }
        config, routes = _declarative_config(env)
        self.assertEqual({item[0] for item in routes}, {"google", "openrouter"})
        self.assertEqual(len(config["keys"]), 2)
        self.assertTrue(all(item["platform"] != "groq" for item in config["keys"]))
        self.assertEqual(len(config["models"]), 2)
        serialized = json.dumps(config)
        self.assertIn("gemini-secret-one", serialized)
        self.assertNotIn("groq-secret-one", serialized)

    def test_groq_routes_are_included_only_after_explicit_free_quota_confirmation(self):
        env = {
            "GROQ_API_KEY": "groq-secret-one",
            "GROQ_API_KEY_1": "groq-secret-two",
            "GROQ_FREE_QUOTA_CONFIRMED": "true",
        }
        config, routes = _declarative_config(env)
        self.assertEqual(len(routes), 2)
        self.assertEqual({route[0] for route in routes}, {"groq"})
        self.assertEqual(len(config["keys"]), 2)

    def _make_database(self, path: Path):
        with sqlite3.connect(path) as conn:
            conn.executescript("""
                CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO settings VALUES ('unified_api_key', 'temporary-key');
                CREATE TABLE models (
                    id INTEGER PRIMARY KEY,
                    platform TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE fallback_config (
                    model_db_id INTEGER PRIMARY KEY,
                    priority INTEGER NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO models VALUES (1, 'google', 'gemini-3.6-flash', 1);
                INSERT INTO models VALUES (2, 'groq', 'openai/gpt-oss-120b', 1);
                INSERT INTO models VALUES (3, 'openrouter', 'some/paid-model', 1);
                INSERT INTO fallback_config VALUES (1, 1, 1);
                INSERT INTO fallback_config VALUES (2, 2, 1);
                INSERT INTO fallback_config VALUES (3, 3, 1);
            """)

    def test_gateway_enables_only_the_explicit_allowlist_and_sets_stable_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gateway.db"
            self._make_database(path)
            key = "freellmapi-" + "a" * 48
            routes = [("google", "gemini-3.6-flash", "GEMINI_API_KEY", "primary")]
            enabled = _apply_gateway_policy(path, key, routes)
            self.assertEqual(enabled, 1)
            with sqlite3.connect(path) as conn:
                self.assertEqual(
                    conn.execute("SELECT platform, model_id FROM models WHERE enabled = 1").fetchall(),
                    [("google", "gemini-3.6-flash")],
                )
                self.assertEqual(
                    conn.execute("SELECT model_db_id FROM fallback_config WHERE enabled = 1").fetchall(),
                    [(1,)],
                )
                self.assertEqual(
                    conn.execute("SELECT value FROM settings WHERE key='unified_api_key'").fetchone()[0],
                    key,
                )

    def test_unknown_free_routes_fail_closed_with_all_catalog_models_disabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "gateway.db"
            self._make_database(path)
            key = "freellmapi-" + "b" * 48
            routes = [("google", "not-in-catalog", "GEMINI_API_KEY", "missing")]
            with self.assertRaisesRegex(RuntimeError, "No configured free-quota routes"):
                _apply_gateway_policy(path, key, routes)
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM models WHERE enabled = 1").fetchone()[0], 0)
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM fallback_config WHERE enabled = 1").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
