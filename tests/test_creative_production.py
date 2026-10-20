import tempfile
import unittest
from pathlib import Path

from core.creative_production import CreativeProductionManifest, ProductionContractError


class CreativeProductionManifestTests(unittest.TestCase):
    def test_dependency_blocks_until_upstream_succeeds(self):
        manifest = CreativeProductionManifest("job-1", "Explain induction")
        manifest.add_task("research", "researcher", "Verify mechanism", writes=["research.json"])
        manifest.add_task("graphics", "graphics_engineer", "Draw coil", depends_on=["research"], reads=["research.json"], writes=["coil.mp4"])
        self.assertEqual(manifest.tasks["research"].status, "ready")
        with self.assertRaises(ProductionContractError):
            manifest.set_task_state("graphics", "running")
        manifest.register_artifact("research.json", kind="json", owner_task_id="research", uri="artifact://research.json")
        manifest.set_task_state("research", "succeeded", evidence=["source-reviewed"])
        self.assertEqual(manifest.tasks["graphics"].status, "ready")
        manifest.register_artifact("coil.mp4", kind="video", owner_task_id="graphics", uri="artifact://coil.mp4")
        manifest.set_task_state("graphics", "running")
        manifest.set_task_state("graphics", "succeeded", evidence=["rendered-output"])

    def test_duplicate_writers_are_rejected(self):
        manifest = CreativeProductionManifest("job-2", "Test")
        manifest.add_task("one", "coder", "Create shared asset", writes=["shared.png"])
        with self.assertRaises(ProductionContractError):
            manifest.add_task("two", "editor", "Create duplicate", writes=["shared.png"])

    def test_unknown_dependencies_and_artifacts_are_rejected(self):
        manifest = CreativeProductionManifest("job-3", "Test")
        with self.assertRaises(ProductionContractError):
            manifest.add_task("later", "editor", "Bad dependency", depends_on=["missing"])
        with self.assertRaises(ProductionContractError):
            manifest.add_task("later", "editor", "Bad input", reads=["missing.png"])

    def test_persistence_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            manifest = CreativeProductionManifest("job-4", "Test", output_path=path)
            manifest.add_task("research", "researcher", "Research", writes=["research.json"])
            self.assertTrue(path.exists())
            self.assertEqual(len(manifest.fingerprint()), 64)


if __name__ == "__main__":
    unittest.main()
