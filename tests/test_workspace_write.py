import hashlib
import tempfile
import unittest
from pathlib import Path

from interfaces.web.server import write_workspace_file


class WorkspaceWriteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "notes.txt").write_text("before", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def test_atomically_replaces_existing_allowlisted_text_file(self):
        result = write_workspace_file(
            self.root, "notes.txt", "after", self.digest("before"), ["notes.txt"]
        )
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "after")
        self.assertEqual(result["previous_sha256"], self.digest("before"))
        self.assertEqual(result["sha256"], self.digest("after"))
        self.assertEqual(result["write_mode"], "atomic_existing_file_only")

    def test_rejects_stale_hash_without_overwriting(self):
        with self.assertRaisesRegex(RuntimeError, "changed since it was opened"):
            write_workspace_file(self.root, "notes.txt", "lost update", self.digest("older"), ["notes.txt"])
        self.assertEqual((self.root / "notes.txt").read_text(encoding="utf-8"), "before")

    def test_rejects_paths_outside_allowlist(self):
        with self.assertRaises(PermissionError):
            write_workspace_file(self.root, "notes.txt", "after", self.digest("before"), ["src"])

    def test_rejects_traversal_and_hidden_files(self):
        for path in ("../notes.txt", ".env", "folder/../notes.txt", "secrets.json"):
            with self.subTest(path=path):
                with self.assertRaises((ValueError, PermissionError)):
                    write_workspace_file(self.root, path, "after", self.digest("before"), None)

    def test_rejects_new_files_and_binary_content(self):
        with self.assertRaises(ValueError):
            write_workspace_file(self.root, "new.txt", "new", self.digest(""), None)
        with self.assertRaises(ValueError):
            write_workspace_file(self.root, "notes.txt", "bad\x00text", self.digest("before"), None)


if __name__ == "__main__":
    unittest.main()
