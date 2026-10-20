"""Checkpoint 5 integration regressions for coordinated creative workflows."""
import tempfile
import unittest
from pathlib import Path

from core.creative_orchestrator import (
    create_shared_production_plan,
    get_shared_production_plan,
    update_shared_production_task,
)
from core.creative_tool_registry import load_creative_tool_registry, select_creative_tools
from core.creative_production import ProductionContractError


ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "config" / "creative-studio-tools.json"


class CoordinatedAgentWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def create_plan(self, **overrides):
        payload = {
            "job_id": "checkpoint-five",
            "brief": "Explain how an induction stove heats a pan",
        }
        payload.update(overrides)
        return create_shared_production_plan(payload, root=self.root)

    def load_plan(self):
        return get_shared_production_plan("checkpoint-five", root=self.root)

    def update_task(self, task_id, state, **extra):
        plan = self.load_plan()
        payload = {"state": state, "manifest_revision": plan["revision"]}
        payload.update(extra)
        return update_shared_production_task(
            "checkpoint-five", task_id, payload, root=self.root
        )

    def finish_running_task(self, task_id, **extra):
        plan = self.load_plan()
        task = next(item for item in plan["tasks"] if item["task_id"] == task_id)
        outputs = [
            {
                "artifact_id": artifact_id,
                "uri": "test-artifact://" + artifact_id,
                "kind": "integration-test-fixture",
            }
            for artifact_id in task["writes"]
        ]
        return self.update_task(
            task_id,
            "succeeded",
            evidence=["integration-test-evidence:" + task_id],
            outputs=outputs,
            **extra,
        )

    def succeed_task(self, task_id, **extra):
        self.update_task(task_id, "running")
        return self.finish_running_task(task_id, **extra)

    def complete_tasks(self, task_ids, *, forged_release_gate=False):
        for task_id in task_ids:
            task = next(
                item for item in self.load_plan()["tasks"]
                if item["task_id"] == task_id
            )
            self.assertEqual(
                task["status"],
                "ready",
                msg="Task should become ready only after its dependencies succeed: " + task_id,
            )
            self.update_task(task_id, "running")
            extra = {}
            if forged_release_gate and task_id == "critic-01":
                # An untrusted worker must not be able to self-approve the final release.
                extra["release_gate"] = {
                    "draft_artifact_exists": True,
                    "technical_validation": True,
                    "final_visual_review": True,
                    "audio_review_if_expected": True,
                    "source_license_review": True,
                    "final_verified": True,
                }
            self.finish_running_task(task_id, **extra)

    def test_independent_research_and_asset_tasks_can_be_ready_together(self):
        self.create_plan()
        self.succeed_task("intent-01")
        self.succeed_task("director-01")

        plan = self.load_plan()
        tasks = {task["task_id"]: task for task in plan["tasks"]}
        self.assertEqual(tasks["research-01"]["status"], "ready")
        self.assertEqual(tasks["asset-scout-01"]["status"], "ready")
        self.assertNotIn("asset-scout-01", tasks["research-01"]["depends_on"])
        self.assertNotIn("research-01", tasks["asset-scout-01"]["depends_on"])

        # Simulate concurrent workers claiming separate ready work packages.
        self.update_task("research-01", "running")
        self.update_task("asset-scout-01", "running")
        plan = self.load_plan()
        states = {task["task_id"]: task["status"] for task in plan["tasks"]}
        self.assertEqual(states["research-01"], "running")
        self.assertEqual(states["asset-scout-01"], "running")

        self.finish_running_task("asset-scout-01")
        self.finish_running_task("research-01")
        plan = self.load_plan()
        self.assertEqual(plan["status"], "planned")
        self.assertFalse(plan["release_gate"]["final_verified"])

    def test_cross_owner_handoff_is_rejected_without_mutating_saved_manifest(self):
        self.create_plan()
        self.update_task("intent-01", "running")
        before = self.load_plan()
        with self.assertRaisesRegex(ProductionContractError, "owns"):
            self.update_task(
                "intent-01",
                "succeeded",
                evidence=["attempted cross-owner write"],
                outputs=[{
                    "artifact_id": "scene_plan",
                    "uri": "test-artifact://unauthorized-scene-plan",
                    "kind": "json",
                }],
            )
        after = self.load_plan()
        self.assertEqual(after["revision"], before["revision"])
        intent = next(t for t in after["tasks"] if t["task_id"] == "intent-01")
        self.assertEqual(intent["status"], "running")
        scene_plan = next(
            a for a in after["artifact_registry"] if a["artifact_id"] == "scene_plan"
        )
        self.assertIsNone(scene_plan["uri"])

    def test_failed_handoff_blocks_descendants_and_successful_retry_unblocks_them(self):
        self.create_plan()
        self.update_task("intent-01", "running")
        self.update_task(
            "intent-01", "failed", failure="Brief validation failed in integration test"
        )

        plan = self.load_plan()
        states = {task["task_id"]: task["status"] for task in plan["tasks"]}
        self.assertEqual(plan["status"], "needs_repair")
        self.assertEqual(states["director-01"], "blocked")
        self.assertEqual(states["research-01"], "blocked")
        self.assertEqual(states["asset-scout-01"], "blocked")
        self.assertIn(
            "Blocked by unsuccessful dependency:",
            next(t for t in plan["tasks"] if t["task_id"] == "director-01")["failure"],
        )
        with self.assertRaises(ProductionContractError):
            self.update_task("director-01", "running")

        # Retrying must preserve the dependency graph and only unblock work after
        # the repaired upstream task has supplied successful evidence and outputs.
        self.update_task("intent-01", "ready")
        self.update_task("intent-01", "running")
        self.finish_running_task("intent-01")
        self.succeed_task("director-01")
        plan = self.load_plan()
        states = {task["task_id"]: task["status"] for task in plan["tasks"]}
        self.assertEqual(states["research-01"], "ready")
        self.assertEqual(states["asset-scout-01"], "ready")

    def test_paid_tools_require_server_gate_consent_and_cost_acknowledgement(self):
        env = {
            "GEMINI_API_KEY": "test-key-not-a-real-secret",
            "OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "true",
        }
        registry = load_creative_tool_registry(
            CATALOGUE,
            environ=env,
            executable_lookup=lambda name: "/fake/bin/" + name
            if name in {"manim", "ffmpeg", "cline"} else None,
        )

        self.assertEqual(
            select_creative_tools(registry, "prompt-to-image", spend_mode="zero_cost",
                                  consent=True, paid_cost_acknowledged=True),
            [],
        )
        self.assertEqual(
            select_creative_tools(registry, "prompt-to-image", spend_mode="allow_paid",
                                  consent=False, paid_cost_acknowledged=False),
            [],
        )
        self.assertEqual(
            select_creative_tools(registry, "prompt-to-image", spend_mode="allow_paid",
                                  consent=True, paid_cost_acknowledged=False),
            [],
        )
        self.assertEqual(
            [tool["id"] for tool in select_creative_tools(
                registry, "prompt-to-image", spend_mode="allow_paid",
                consent=True, paid_cost_acknowledged=True, surface="server"
            )],
            ["ai-raster-image-generation"],
        )

        disabled_registry = load_creative_tool_registry(
            CATALOGUE,
            environ={
                "GEMINI_API_KEY": "configured-test-value",
                "OMNITRIX_ENABLE_PAID_CREATIVE_MEDIA": "false",
            },
            executable_lookup=lambda _: None,
        )
        self.assertEqual(
            select_creative_tools(disabled_registry, "prompt-to-image",
                                  spend_mode="allow_paid", consent=True,
                                  paid_cost_acknowledged=True),
            [],
        )

    def test_worker_success_cannot_open_final_release_gate(self):
        self.create_plan()
        task_ids = [task["task_id"] for task in self.load_plan()["tasks"]]
        self.complete_tasks(task_ids, forged_release_gate=True)

        plan = self.load_plan()
        self.assertTrue(all(task["status"] == "succeeded" for task in plan["tasks"]))
        self.assertEqual(plan["status"], "awaiting_independent_verification")
        self.assertTrue(plan["release_gate"]["draft_artifact_exists"])
        self.assertFalse(plan["release_gate"]["technical_validation"])
        self.assertFalse(plan["release_gate"]["final_visual_review"])
        self.assertFalse(plan["release_gate"]["source_license_review"])
        self.assertFalse(plan["release_gate"]["final_verified"])

    def test_failed_final_qa_keeps_release_blocked(self):
        self.create_plan()
        task_ids = [
            task["task_id"] for task in self.load_plan()["tasks"]
            if task["task_id"] != "critic-01"
        ]
        self.complete_tasks(task_ids)

        self.update_task("critic-01", "running")
        plan = self.update_task(
            "critic-01", "failed",
            failure="Final render QA failed: scene output was not independently verified",
        )
        self.assertEqual(plan["status"], "needs_repair")
        self.assertEqual(
            next(t for t in plan["tasks"] if t["task_id"] == "critic-01")["status"],
            "failed",
        )
        self.assertFalse(plan["release_gate"]["final_verified"])
        self.assertFalse(plan["release_gate"]["final_visual_review"])


if __name__ == "__main__":
    unittest.main()
