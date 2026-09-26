import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.kuma_agent import KumaAgent
from app.agent.kuma_mission_executor import KumaMissionExecutor
from app.agent.mission_controller import MissionController
from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)


class FakePersistence:

    def __init__(self):
        self.items = {}

    def save(self, mission):
        self.items[mission.mission_id] = MissionState.from_json(
            mission.to_json()
        )

    def load(self, mission_id):
        mission = self.items.get(mission_id)

        if mission is None:
            return None

        return MissionState.from_json(
            mission.to_json()
        )


class TestRestartResumeIdempotency(unittest.TestCase):

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

        plan.add_step(step)
        plan.current_step_id = step.id

        mission = MissionState.create(
            plan.goal
        )

        mission.plan = plan
        mission.status = MissionStatus.PAUSED
        mission.current_step_id = step.id
        mission.last_evidence = "PARTIAL_STATE_VERIFIED"
        mission.remaining_objective = "Perform only unfinished work."
        mission.continuation_guard_known = True
        mission.continuation_guard_tool = "continuation_test"
        mission.continuation_guard_arguments = {
            "target": "old"
        }
        mission.continuation_guard_capability = (
            "continuation_capability"
        )

        return mission

    def response_for(self, target):
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

    def make_kuma(self, tool):
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
                    "name": "continuation_capability",
                    "description": "test continuation",
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

    def test_inflight_barrier_survives_json_round_trip(self):
        mission = self.make_mission()
        mission.continuation_execution_inflight = True

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertTrue(
            restored.continuation_execution_inflight
        )

    def test_controller_restores_inflight_barrier(self):
        mission = self.make_mission()
        mission.continuation_execution_inflight = True

        controller = MissionController.from_mission_state(
            mission
        )

        self.assertTrue(
            controller.task_state.continuation_execution_inflight
        )

    def test_repeated_resume_of_inflight_state_executes_nothing(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        mission.continuation_execution_inflight = True
        persistence.save(mission)

        calls = []

        def tool(target=""):
            calls.append(target)
            return "SHOULD_NOT_RUN"

        kuma = self.make_kuma(tool)

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "In-flight restart must not call the model."
            ),
        ):
            first = kuma.resume_mission(
                mission.mission_id
            )
            second = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(calls, [])
        self.assertFalse(first.success)
        self.assertFalse(second.success)
        self.assertEqual(first.recovery_action, "escalate")
        self.assertEqual(second.recovery_action, "escalate")
        self.assertTrue(
            restored.continuation_execution_inflight
        )
        self.assertEqual(
            restored.action_history,
            [],
        )

    def test_execution_intent_is_persisted_before_tool_runs(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)

        observed = []

        def tool(target=""):
            snapshot = persistence.load(
                mission.mission_id
            )
            observed.append(
                snapshot.continuation_execution_inflight
            )
            return "CONTINUED_OK"

        kuma = self.make_kuma(tool)

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            return_value=self.response_for("new"),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(
            observed,
            [True],
        )
        self.assertTrue(result.success)
        self.assertFalse(result.completed)
        self.assertFalse(
            restored.continuation_execution_inflight
        )
        self.assertTrue(
            restored.continuation_verification_pending
        )
        self.assertEqual(
            len(restored.action_history),
            1,
        )

    def test_crash_after_intent_leaves_restart_barrier(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        persistence.save(mission)

        kuma = self.make_kuma(
            lambda target="": "UNUSED"
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.KumaMissionExecutor.execute",
            side_effect=RuntimeError(
                "simulated process crash"
            ),
        ):
            with self.assertRaises(RuntimeError):
                kuma.resume_mission(
                    mission.mission_id
                )

        crashed = persistence.load(
            mission.mission_id
        )

        self.assertTrue(
            crashed.continuation_execution_inflight
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "Restart must not plan another continuation."
            ),
        ), patch.object(
            KumaMissionExecutor,
            "execute",
            side_effect=AssertionError(
                "Restart must not execute again."
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertFalse(result.success)
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )
        self.assertTrue(
            persistence.load(
                mission.mission_id
            ).continuation_execution_inflight
        )

    def test_completed_terminal_mission_stays_idempotent(self):
        mission = self.make_mission()

        step = mission.plan.get_step(
            "continue"
        )

        step.status = StepStatus.COMPLETED
        mission.plan.current_step_id = ""
        mission.current_step_id = ""
        mission.remaining_objective = ""
        mission.continuation_guard_known = False
        mission.continuation_guard_tool = ""
        mission.continuation_guard_arguments = {}
        mission.continuation_guard_capability = ""
        mission.continuation_execution_inflight = False
        mission.status = MissionStatus.COMPLETED

        persistence = FakePersistence()
        persistence.save(mission)

        calls = []

        kuma = self.make_kuma(
            lambda target="": calls.append(target)
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "Completed mission must not call the model."
            ),
        ):
            first = kuma.resume_mission(
                mission.mission_id
            )
            second = kuma.resume_mission(
                mission.mission_id
            )

        self.assertTrue(first.completed)
        self.assertTrue(second.completed)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
