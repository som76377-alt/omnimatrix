import os
import tempfile
import unittest
from pathlib import Path

from core.tools.bootstrap import build_tool_registry
from core.tools.executor import ToolExecutor
from core.tools.permissions import ToolPermission
from core.tools.request import ToolRequest
from core.tools.implementations.workspace_inspect import (
    WorkspaceInspectTool,
    supports_secure_workspace_inspection,
)


@unittest.skipUnless(
    supports_secure_workspace_inspection(),
    "Secure descriptor-relative workspace access is unavailable on this OS",
)
class WorkspaceInspectToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()
        self.tool = WorkspaceInspectTool(self.root)

    def tearDown(self):
        self.tool.close()
        self.temp.cleanup()

    def execute(self, operation, path):
        return self.tool.execute(operation=operation, path=path)

    def test_reads_utf8_text_file_with_untrusted_metadata(self):
        (self.root / "notes.txt").write_text("hello Omnitrix", encoding="utf-8")
        result = self.execute("read", "notes.txt")
        self.assertTrue(result.success)
        self.assertEqual(result.output["content"], "hello Omnitrix")
        self.assertTrue(result.output["read_only"])
        self.assertTrue(result.output["untrusted_content"])

    def test_lists_only_one_directory_and_hides_dotfiles(self):
        (self.root / "main.py").write_text("pass", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=do-not-read", encoding="utf-8")
        (self.root / ".hidden").mkdir()
        result = self.execute("list", ".")
        self.assertTrue(result.success)
        names = {item["name"] for item in result.output["entries"]}
        self.assertIn("main.py", names)
        self.assertNotIn(".env", names)
        self.assertNotIn(".hidden", names)

    def test_denies_sensitive_paths(self):
        for name in (".env", ".env.local", "credentials.json", "api_token.txt", "private.key"):
            (self.root / name).write_text("private", encoding="utf-8")
            result = self.execute("read", name)
            self.assertFalse(result.success, name)

    def test_denies_parent_and_absolute_path_traversal(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        for path in ("../outside.txt", str(outside), "/etc/passwd"):
            result = self.execute("read", path)
            self.assertFalse(result.success, path)

    def test_denies_symlink_even_when_target_is_inside_workspace(self):
        target = self.root / "actual.txt"
        target.write_text("content", encoding="utf-8")
        link = self.root / "linked.txt"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable in this environment")
        result = self.execute("read", "linked.txt")
        self.assertFalse(result.success)

    def test_denies_symlink_to_outside_workspace(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        link = self.root / "escape.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks are unavailable in this environment")
        result = self.execute("read", "escape.txt")
        self.assertFalse(result.success)


    def test_pinned_root_handle_resists_workspace_path_replacement(self):
        (self.root / "inside.txt").write_text("pinned workspace", encoding="utf-8")
        attacker_root = Path(self.temp.name) / "attacker"
        attacker_root.mkdir()
        (attacker_root / "outside.txt").write_text("outside secret", encoding="utf-8")
        moved_root = Path(self.temp.name) / "workspace-original"
        self.root.rename(moved_root)
        try:
            self.root.symlink_to(attacker_root, target_is_directory=True)
        except (OSError, NotImplementedError):
            moved_root.rename(self.root)
            self.skipTest("Directory symlinks are unavailable in this environment")

        inside = self.execute("read", "inside.txt")
        outside = self.execute("read", "outside.txt")
        self.assertTrue(inside.success)
        self.assertEqual(inside.output["content"], "pinned workspace")
        self.assertFalse(outside.success)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO files are unavailable")
    def test_read_does_not_block_on_fifo(self):
        os.mkfifo(self.root / "pipe.txt")
        result = self.execute("read", "pipe.txt")
        self.assertFalse(result.success)


    def test_denies_binary_and_oversized_files(self):
        (self.root / "binary.bin").write_bytes(b"hello\x00world")
        (self.root / "large.txt").write_bytes(b"x" * (64 * 1024 + 1))
        self.assertFalse(self.execute("read", "binary.bin").success)
        self.assertFalse(self.execute("read", "large.txt").success)

    def test_denies_directory_read_and_file_listing(self):
        (self.root / "folder").mkdir()
        (self.root / "text.txt").write_text("text", encoding="utf-8")
        self.assertFalse(self.execute("read", "folder").success)
        self.assertFalse(self.execute("list", "text.txt").success)

    def test_workspace_access_requires_explicit_capability(self):
        registry = build_tool_registry(self.root)
        executor = ToolExecutor(registry)
        request = ToolRequest("workspace.inspect", {"operation": "list", "path": "."})
        denied = executor.execute(request, ToolPermission.from_capabilities(set()))
        self.assertFalse(denied.success)
        allowed = executor.execute(
            request, ToolPermission.from_capabilities({"workspace.read"})
        )
        self.assertTrue(allowed.success)

    def test_tool_is_registered_but_not_implicitly_authorized(self):
        registry = build_tool_registry(self.root)
        self.assertTrue(registry.has("workspace.inspect"))
        self.assertEqual(registry.get("workspace.inspect").capabilities, frozenset({"workspace.read"}))


if __name__ == "__main__":
    unittest.main()
