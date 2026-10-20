"""Shared production orchestration, ownership, revision and handoff tests."""
import tempfile
import unittest
from pathlib import Path

from core.creative_orchestrator import (
    create_shared_production_plan,
    get_shared_production_plan,
    update_shared_production_task,
)
from core.creative_production import ProductionContractError


class SharedCreativeOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, **extra):
        payload = {"job_id": "job-test", "brief": "Explain induction stove heating", **extra}
        return create_shared_production_plan(payload, root=self.root)

    def test_creates_one_manifest_with_shared_scene_plan_and_dependency_graph(self):
        plan = self.create()
        self.assertEqual(plan["scenes"][0]["renderer"], "manim")
        self.assertEqual(plan["tasks"][0]["task_id"], "intent-01")
        self.assertIn("scene_plan", [a["artifact_id"] for a in plan["artifact_registry"]])
        self.assertEqual(plan["coordination_contract"]["single_source_of_truth"], True)
        saved = get_shared_production_plan("job-test", root=self.root)
        self.assertEqual(saved["job_id"], "job-test")
        self.assertEqual(saved["revision"], 1)

    def test_scene_asset_references_must_exist_and_asset_ids_are_unique(self):
        with self.assertRaisesRegex(ProductionContractError, "unique"):
            self.create(assets=[{"asset_id": "coil", "kind": "image"}, {"asset_id": "coil", "kind": "image"}])
        with self.assertRaisesRegex(ProductionContractError, "existing"):
            self.create(scenes=[{"scene_id": "s1", "purpose": "coil", "asset_refs": ["missing"]}])

    def test_duplicate_job_id_does_not_overwrite_existing_manifest(self):
        self.create()
        with self.assertRaisesRegex(ProductionContractError, "already exists"):
            self.create()

    def test_tasks_cannot_start_before_dependencies_and_revision_must_match(self):
        self.create()
        with self.assertRaisesRegex(ProductionContractError, "dependencies"):
            update_shared_production_task("job-test", "director-01",
                {"state": "ready", "manifest_revision": 1}, root=self.root)
        with self.assertRaisesRegex(ProductionContractError, "revision mismatch"):
            update_shared_production_task("job-test", "intent-01",
                {"state": "running", "manifest_revision": 99}, root=self.root)
        plan = update_shared_production_task("job-test", "intent-01",
            {"state": "running", "manifest_revision": 1}, root=self.root)
        self.assertEqual(plan["tasks"][0]["status"], "running")
        self.assertEqual(plan["revision"], 2)

    def test_success_requires_owned_outputs_and_concrete_evidence(self):
        self.create()
        update_shared_production_task("job-test", "intent-01",
            {"state": "running", "manifest_revision": 1}, root=self.root)
        with self.assertRaisesRegex(ProductionContractError, "evidence"):
            update_shared_production_task("job-test", "intent-01",
                {"state": "succeeded", "manifest_revision": 2, "evidence": [], "outputs": [{"artifact_id": "job_brief", "uri": "artifact://brief"}]}, root=self.root)
        with self.assertRaisesRegex(ProductionContractError, "owns"):
            update_shared_production_task("job-test", "intent-01",
                {"state": "succeeded", "manifest_revision": 2, "evidence": ["brief written"], "outputs": [{"artifact_id": "scene_plan", "uri": "artifact://scene"}]}, root=self.root)
        plan = update_shared_production_task("job-test", "intent-01",
            {"state": "succeeded", "manifest_revision": 2, "evidence": ["brief artifact emitted"], "outputs": [{"artifact_id": "job_brief", "uri": "artifact://brief", "kind": "json"}]}, root=self.root)
        self.assertEqual(plan["tasks"][0]["status"], "succeeded")
        self.assertEqual(plan["tasks"][1]["status"], "ready")
        artifact = next(a for a in plan["artifact_registry"] if a["artifact_id"] == "job_brief")
        self.assertFalse(artifact["verified"])
        self.assertEqual(artifact["verification_status"], "reported-unverified")

    def test_graphics_overlay_is_opt_in_and_does_not_duplicate_manim_core_visuals(self):
        plan = self.create(scenes=[
            {"scene_id": "science", "purpose": "Induction coil field", "renderer": "manim", "needs_overlays": True},
            {"scene_id": "title", "purpose": "Opening title", "renderer": "canvas-2d", "needs_overlays": True},
        ])
        task_ids = {task["task_id"] for task in plan["tasks"]}
        self.assertNotIn("graphics-science", task_ids)
        self.assertIn("graphics-title", task_ids)
        render = next(task for task in plan["tasks"] if task["task_id"] == "render-science")
        self.assertIn("research-01", render["depends_on"])
        self.assertIn("asset-scout-01", render["depends_on"])

    def test_blender_and_independent_qa_are_not_claimed_available(self):
        plan = self.create(scenes=[{"scene_id": "model", "purpose": "3D camera orbit", "renderer": "blender"}])
        self.assertIn("not integrated", next(s for s in plan["scenes"] if s["scene_id"] == "model")["runtime_note"])
        self.assertFalse(plan["release_gate"]["final_verified"])
        self.assertFalse(plan["coordination_contract"]["no_automatic_tool_execution"] is False)

    def test_successful_worker_reports_never_mark_final_output_verified(self):
        plan = self.create()
        update_shared_production_task("job-test", "intent-01",
            {"state": "running", "manifest_revision": 1}, root=self.root)
        plan = update_shared_production_task("job-test", "intent-01",
            {"state": "succeeded", "manifest_revision": 2, "evidence": ["brief"], "outputs": [{"artifact_id": "job_brief", "uri": "artifact://brief"}]}, root=self.root)
        self.assertFalse(plan["release_gate"]["final_verified"])
        self.assertEqual(plan["status"], "planned")


if __name__ == "__main__":
    unittest.main()
