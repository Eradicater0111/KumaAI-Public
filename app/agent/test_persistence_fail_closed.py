import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.kuma_agent import KumaAgent
from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)


class FailingPersistence:
    """
    In-memory durable store with deterministic save failures.

    A failed save occurs before replacing the previously durable
    snapshot, which lets these tests prove that the earlier
    write-ahead inflight barrier remains authoritative.
    """

    def __init__(self):
        self.items = {}
        self.save_calls = 0
        self.fail_on_save_calls = set()

    def save(self, mission):
        self.save_calls += 1

        if self.save_calls in self.fail_on_save_calls:
            raise RuntimeError(
                "simulated persistence failure"
            )

        self.items[mission.mission_id] = (
            MissionState.from_json(
                mission.to_json()
            )
        )

    def load(self, mission_id):
        mission = self.items.get(
            mission_id
        )

        if mission is None:
            return None

        return MissionState.from_json(
            mission.to_json()
        )


class TestPersistenceFailClosed(unittest.TestCase):

    def make_mission(self):
        plan = GoalPlan(
            goal="Continue exactly once."
        )

        step = GoalStep(
            id="continue",
            objective="Finish the original step.",
            status=StepStatus.IN_PROGRESS,
            required_capabilities=[
                "continuation_capability"
            ],
            success_criteria=[
                "Original step is complete."
            ],
            verification_requirements=[
                "Verify original end-state."
            ],
        )

        plan.add_step(
            step
        )
        plan.current_step_id = (
            step.id
        )

        mission = MissionState.create(
            plan.goal
        )

        mission.plan = plan
        mission.status = (
            MissionStatus.PAUSED
        )
        mission.current_step_id = (
            step.id
        )
        mission.last_evidence = (
            "PARTIAL_STATE_VERIFIED"
        )
        mission.remaining_objective = (
            "Perform only unfinished work."
        )
        mission.continuation_guard_known = True
        mission.continuation_guard_tool = (
            "continuation_test"
        )
        mission.continuation_guard_arguments = {
            "target": "old"
        }
        mission.continuation_guard_capability = (
            "continuation_capability"
        )

        return mission

    @staticmethod
    def response_for(target):
        return SimpleNamespace(
            message=SimpleNamespace(
                content="",
                tool_calls=[
                    SimpleNamespace(
                        function=SimpleNamespace(
                            name="continuation_test",
                            arguments={
                                "target": target,
                            },
                        )
                    )
                ],
            )
        )

    @staticmethod
    def make_kuma(tool):
        kuma = KumaAgent(
            model="test-model",
            tool_registry={
                "continuation_test": tool,
            },
        )

        kuma.capability_registry.register(
            type(
                "Capability",
                (),
                {
                    "name": (
                        "continuation_capability"
                    ),
                    "description": (
                        "test continuation"
                    ),
                    "tools": (
                        "continuation_test",
                    ),
                    "platform": "macos",
                    "risk_level": "normal",
                    "tags": (),
                },
            )()
        )

        return kuma

    def test_write_ahead_save_failure_prevents_tool_execution(
        self,
    ):
        persistence = (
            FailingPersistence()
        )
        mission = self.make_mission()

        # Initial durable PAUSED mission.
        persistence.save(
            mission
        )

        # The next save is the continuation write-ahead
        # inflight barrier. Fail it before any model/tool work.
        persistence.fail_on_save_calls = {
            2
        }

        tool_calls = []

        def tool(target=""):
            tool_calls.append(
                target
            )
            return "SHOULD_NOT_RUN"

        kuma = self.make_kuma(
            tool
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "Failed write-ahead persistence must "
                "prevent model/tool execution."
            ),
        ):

            with self.assertRaisesRegex(
                RuntimeError,
                "simulated persistence failure",
            ):
                kuma.resume_mission(
                    mission.mission_id
                )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            tool_calls,
            [],
        )
        self.assertFalse(
            restored.continuation_execution_inflight
        )
        self.assertEqual(
            restored.action_history,
            [],
        )

    def test_post_execution_save_failure_preserves_durable_inflight_barrier(
        self,
    ):
        persistence = (
            FailingPersistence()
        )
        mission = self.make_mission()

        # Save #1: initial mission.
        persistence.save(
            mission
        )

        # Save #2: inflight=True write-ahead barrier succeeds.
        # Save #3: classified post-execution state fails.
        persistence.fail_on_save_calls = {
            3
        }

        tool_calls = []

        def tool(target=""):
            tool_calls.append(
                target
            )
            return "CONTINUED_OK"

        kuma = self.make_kuma(
            tool
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            return_value=self.response_for(
                "new"
            ),
        ):

            with self.assertRaisesRegex(
                RuntimeError,
                "simulated persistence failure",
            ):
                kuma.resume_mission(
                    mission.mission_id
                )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            tool_calls,
            [
                "new",
            ],
        )
        self.assertTrue(
            restored.continuation_execution_inflight
        )
        self.assertEqual(
            restored.action_history,
            [],
        )
        self.assertEqual(
            restored.remaining_objective,
            "Perform only unfinished work.",
        )

    def test_restart_after_post_execution_save_failure_never_replays(
        self,
    ):
        persistence = (
            FailingPersistence()
        )
        mission = self.make_mission()

        persistence.save(
            mission
        )
        persistence.fail_on_save_calls = {
            3
        }

        tool_calls = []

        def tool(target=""):
            tool_calls.append(
                target
            )
            return "CONTINUED_OK"

        kuma = self.make_kuma(
            tool
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            return_value=self.response_for(
                "new"
            ),
        ):

            with self.assertRaisesRegex(
                RuntimeError,
                "simulated persistence failure",
            ):
                kuma.resume_mission(
                    mission.mission_id
                )

        # Persistence is healthy again for the simulated restart.
        persistence.fail_on_save_calls = set()

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "Restart from durable inflight state "
                "must not call the model."
            ),
        ):
            restarted = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            tool_calls,
            [
                "new",
            ],
        )
        self.assertFalse(
            restarted.success
        )
        self.assertEqual(
            restarted.recovery_action,
            "escalate",
        )
        self.assertTrue(
            restored.continuation_execution_inflight
        )
        self.assertEqual(
            restored.action_history,
            [],
        )


if __name__ == "__main__":
    unittest.main()
