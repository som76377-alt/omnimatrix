import os
from pathlib import Path
import tempfile
import unittest

from core.tools.implementations.cline_coding import ClineCodingTool
from core.tools.bootstrap import build_tool_registry


class ClineCodingToolTests(unittest.TestCase):
    def test_registry_requires_explicit_enablement_and_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            default_registry = build_tool_registry()
            self.assertFalse(default_registry.has("cline.coding"))
            with self.assertRaises(ValueError):
                build_tool_registry(enable_cline=True)
            enabled_registry = build_tool_registry(directory, enable_cline=True)
            self.assertTrue(enabled_registry.has("cline.coding"))
            self.assertEqual(enabled_registry.get("cline.coding").capabilities,
                             frozenset({"coding.execute"}))

    def test_missing_cli_reports_actionable_unavailable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = ClineCodingTool(directory, executable=None)
            tool._executable = None
            result = tool.execute(task="Fix the parser and add tests", mode="implement")
        self.assertFalse(result.success)
        self.assertIn("not installed", result.error)
        self.assertFalse(result.metadata["available"])

    def test_rejects_invalid_mode_and_timeout_before_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = ClineCodingTool(directory, executable="/fake/cline")
            bad_mode = tool.execute(task="Fix the parser and add tests", mode="deploy")
            bad_timeout = tool.execute(task="Fix the parser and add tests", mode="implement",
                                       timeout_seconds=99999)
        self.assertFalse(bad_mode.success)
        self.assertFalse(bad_timeout.success)

    def test_fake_cline_edits_isolated_copy_and_changes_are_applied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            source = root / "sample.py"
            source.write_text("before = True\n", encoding="utf-8")
            fake_cline = Path(directory) / "fake-cline"
            fake_cline.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                "import sys\n"
                "prompt = sys.argv[-1]\n"
                "assert 'Shared intent, constraints, and context' in prompt\n"
                "assert 'reasoning specialist found the edge case' in prompt\n"
                "assert 'parser returns 400 for malformed input' in prompt\n"
                "assert 'core/parser.py' in prompt\n"
                "Path('sample.py').write_text('after = True\\n', encoding='utf-8')\n"
                "print('{\\\"type\\\":\\\"run_result\\\",\\\"text\\\":\\\"implemented and tested\\\"}')\n",
                encoding="utf-8",
            )
            fake_cline.chmod(0o755)
            tool = ClineCodingTool(root, executable=str(fake_cline))
            result = tool.execute(
                task="Update sample.py and report what changed",
                context="Shared context from Omnitrix planning",
                related_agent_findings=["The reasoning specialist found the edge case"],
                acceptance_criteria=["parser returns 400 for malformed input"],
                files_in_scope=["core/parser.py"],
                mode="implement", timeout_seconds=30,
            )
            self.assertTrue(result.success, result.error)
            self.assertEqual(source.read_text(encoding="utf-8"), "after = True\n")
            self.assertTrue(result.metadata["changes_applied"])
            self.assertEqual(result.metadata["changed_files"], ["sample.py"])
            self.assertIn("not an OS-level sandbox", result.metadata["warning"])

    def test_workspace_allowlist_is_enforced_before_cline_sees_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            (root / "core").mkdir(parents=True)
            (root / "private").mkdir()
            (root / "core" / "safe.py").write_text("safe = True\\n", encoding="utf-8")
            (root / "private" / "not_for_cline.py").write_text("private = True\\n", encoding="utf-8")
            tool = ClineCodingTool(root, executable="/fake/cline", allowed_paths=("core",))
            with tempfile.TemporaryDirectory() as copied:
                tool._copy_workspace(Path(copied))
                self.assertTrue((Path(copied) / "core" / "safe.py").exists())
                self.assertFalse((Path(copied) / "private" / "not_for_cline.py").exists())

    def test_rejects_malformed_shared_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = ClineCodingTool(directory, executable="/fake/cline")
            result = tool.execute(
                task="Update the parser and add tests",
                related_agent_findings="this must be a list",
                mode="plan",
            )
        self.assertFalse(result.success)
        self.assertIn("related_agent_findings", result.error)

    def test_secret_files_are_not_copied_to_task_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            root.mkdir()
            (root / "safe.py").write_text("print('safe')\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
            (root / "api_key.txt").write_text("SECRET=value\n", encoding="utf-8")
            tool = ClineCodingTool(root, executable="/fake/cline")
            with tempfile.TemporaryDirectory() as copied:
                count = tool._copy_workspace(Path(copied))
                self.assertTrue((Path(copied) / "safe.py").exists())
                self.assertFalse((Path(copied) / ".env").exists())
                self.assertFalse((Path(copied) / "api_key.txt").exists())
                self.assertGreater(count, 0)


if __name__ == "__main__":
    unittest.main()
