import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from core.application import ChatApplication
from core.orchestrator.omnitrix import Omnitrix
from core.tools.bootstrap import build_tool_registry
from core.tools.permissions import ToolPermission
from interfaces.web.server import StudioRuntime


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "demo.models.json"


class SafeMainSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.remote = self.base / "origin.git"
        self.seed = self.base / "seed"
        self.checkout = self.base / "checkout"
        self.producer = self.base / "producer"
        self.workspace = self.base / "runtime-workspace"
        self.workspace.mkdir()
        (self.workspace / "note.txt").write_text("test workspace", encoding="utf-8")

        self.git_env = dict(os.environ)
        self.git_env["GIT_CONFIG_NOSYSTEM"] = "1"
        self.git_env["GIT_CONFIG_GLOBAL"] = os.devnull
        self.git_env["GIT_TERMINAL_PROMPT"] = "0"

        self.git(self.base, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.base, "init", "--initial-branch=main", str(self.seed))
        self.git(self.seed, "config", "user.name", "Omnitrix Test")
        self.git(self.seed, "config", "user.email", "omnitrix-test@example.invalid")
        (self.seed / "README.md").write_text("initial revision\n", encoding="utf-8")
        self.git(self.seed, "add", "README.md")
        self.git(self.seed, "commit", "-m", "initial")
        self.git(self.seed, "remote", "add", "origin", str(self.remote))
        self.git(self.seed, "push", "-u", "origin", "main")
        self.git(self.base, "clone", str(self.remote), str(self.checkout))
        self.make_producer()
        self.runtime, self.workspace_tool = self.make_runtime(self.checkout)

    def tearDown(self):
        self.workspace_tool.close()
        self.temp.cleanup()

    def git(self, cwd, *args):
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=self.git_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"git {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}",
        )
        return result.stdout.strip()

    def make_producer(self):
        self.git(self.base, "clone", str(self.remote), str(self.producer))
        self.git(self.producer, "config", "user.name", "Omnitrix Test")
        self.git(self.producer, "config", "user.email", "omnitrix-test@example.invalid")

    def push_remote_change(self, name="upstream.txt"):
        (self.producer / name).write_text("from GitHub main\n", encoding="utf-8")
        self.git(self.producer, "add", name)
        self.git(self.producer, "commit", "-m", "upstream change")
        self.git(self.producer, "push", "origin", "main")
        return self.git(self.producer, "rev-parse", "HEAD")

    def make_runtime(self, code_root):
        registry = build_tool_registry(self.workspace)
        omnitrix = Omnitrix.from_config(
            CONFIG,
            tool_registry=registry,
            tool_permission=ToolPermission.from_capabilities({"calculation"}),
        )
        return (
            StudioRuntime(
                root=self.workspace,
                code_root=code_root,
                config_path=CONFIG,
                app=ChatApplication(omnitrix),
                omnitrix=omnitrix,
                workspace_tool=registry.get("workspace.inspect"),
                access_token="sync-test-token",
                workspace_read_enabled=False,
                allowed_paths=None,
                tests_enabled=False,
                auto_sync_main=True,
                auto_sync_interval_seconds=30,
            ),
            registry.get("workspace.inspect"),
        )

    def test_clean_main_fast_forwards_to_origin_main_without_reset(self):
        expected = self.push_remote_change()
        changed = self.runtime.check_for_updates()
        actual = self.git(self.checkout, "rev-parse", "HEAD")
        dirty = self.git(self.checkout, "status", "--porcelain")
        self.assertTrue(changed)
        self.assertEqual(actual, expected)
        self.assertEqual(dirty, "")
        self.assertEqual(self.runtime.sync_status, "updated")
        self.assertTrue(self.runtime.sync_restart_pending)

    def test_dirty_checkout_is_never_modified_by_auto_sync(self):
        local_file = self.checkout / "uncommitted-notes.txt"
        local_file.write_text("keep these local edits", encoding="utf-8")
        before = self.git(self.checkout, "rev-parse", "HEAD")
        self.push_remote_change()
        changed = self.runtime.check_for_updates()
        after = self.git(self.checkout, "rev-parse", "HEAD")
        self.assertFalse(changed)
        self.assertEqual(before, after)
        self.assertEqual(local_file.read_text(encoding="utf-8"), "keep these local edits")
        self.assertEqual(self.runtime.sync_status, "deferred_dirty")

    def test_non_main_branch_is_not_auto_updated(self):
        self.git(self.checkout, "checkout", "-b", "user-experiment")
        before = self.git(self.checkout, "rev-parse", "HEAD")
        self.push_remote_change()
        changed = self.runtime.check_for_updates()
        after = self.git(self.checkout, "rev-parse", "HEAD")
        self.assertFalse(changed)
        self.assertEqual(before, after)
        self.assertEqual(self.runtime.sync_status, "deferred_not_main")

    def test_auto_sync_is_off_by_default_for_general_runtime(self):
        self.runtime.auto_sync_main = False
        before = self.git(self.checkout, "rev-parse", "HEAD")
        self.push_remote_change()
        self.assertFalse(self.runtime.check_for_updates())
        self.assertEqual(self.git(self.checkout, "rev-parse", "HEAD"), before)
        self.assertEqual(self.runtime.sync_status, "disabled")


if __name__ == "__main__":
    unittest.main()
