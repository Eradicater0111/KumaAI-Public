import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.kuma_agent import KumaAgent
from app.agent.mission_controller import MissionController
from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)
from app.agent.mission_service import (
    MAX_RECOVERY_CONTINUATION_CYCLES,
)
from app.agent.task_state import TaskState


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


class TestRecoveryLivelockGuard(unittest.TestCase):

    def make_mission(self):
        plan = GoalPlan(
            goal="Finish without livelock."
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
        mission.remaining_objective = "Perform unfinished work."
        mission.continuation_guard_known = True
        mission.continuation_guard_tool = "continuation_test"
        mission.continuation_guard_arguments = {
            "target": "old"
        }
        mission.continuation_guard_capability = (
            "continuation_capability"
        )

        return mission

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

    def test_counter_defaults_to_zero(self):
        state = TaskState(
            goal="g"
        )

        self.assertEqual(
            state.recovery_continuation_cycles,
            0,
        )

    def test_increment_method_counts_completed_cycles(self):
        state = TaskState(
            goal="g"
        )

        self.assertEqual(
            state.increment_recovery_continuation_cycles(),
            1,
        )
        self.assertEqual(
            state.increment_recovery_continuation_cycles(),
            2,
        )

    def test_counter_survives_json_round_trip(self):
        mission = self.make_mission()
        mission.recovery_continuation_cycles = 2

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertEqual(
            restored.recovery_continuation_cycles,
            2,
        )

    def test_controller_restores_counter(self):
        mission = self.make_mission()
        mission.recovery_continuation_cycles = 2

        controller = MissionController.from_mission_state(
            mission
        )

        self.assertEqual(
            controller.task_state.recovery_continuation_cycles,
            2,
        )

    def test_counter_rejects_string(self):
        mission = self.make_mission()
        data = mission.to_dict()
        data["recovery_continuation_cycles"] = "3"

        with self.assertRaises(ValueError):
            MissionState.from_dict(data)

    def test_counter_rejects_float(self):
        mission = self.make_mission()
        data = mission.to_dict()
        data["recovery_continuation_cycles"] = 3.0

        with self.assertRaises(ValueError):
            MissionState.from_dict(data)

    def test_counter_rejects_bool(self):
        mission = self.make_mission()
        data = mission.to_dict()
        data["recovery_continuation_cycles"] = True

        with self.assertRaises(ValueError):
            MissionState.from_dict(data)

    def test_counter_rejects_negative_integer(self):
        mission = self.make_mission()
        data = mission.to_dict()
        data["recovery_continuation_cycles"] = -1

        with self.assertRaises(ValueError):
            MissionState.from_dict(data)

    def test_completion_resets_counter(self):
        mission = self.make_mission()
        mission.recovery_continuation_cycles = 2

        controller = MissionController.from_mission_state(
            mission
        )

        completed = (
            controller
            .complete_current_step_from_verification(
                result="COMPLETE",
                evidence="COMPLETE_EVIDENCE",
                reason="Verified.",
            )
        )

        self.assertTrue(completed)
        self.assertEqual(
            controller.task_state.recovery_continuation_cycles,
            0,
        )

    def test_budget_exhaustion_blocks_before_model_or_tool(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        mission.recovery_continuation_cycles = (
            MAX_RECOVERY_CONTINUATION_CYCLES
        )
        persistence.save(mission)

        tool_calls = []

        def tool(target=""):
            tool_calls.append(target)
            return "SHOULD_NOT_RUN"

        kuma = self.make_kuma(tool)

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            side_effect=AssertionError(
                "Livelock budget exhaustion must block "
                "the continuation model call."
            ),
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        restored = persistence.load(
            mission.mission_id
        )

        self.assertEqual(tool_calls, [])
        self.assertFalse(result.success)
        self.assertEqual(
            result.recovery_action,
            "escalate",
        )
        self.assertEqual(
            restored.recovery_continuation_cycles,
            MAX_RECOVERY_CONTINUATION_CYCLES,
        )
        self.assertEqual(
            restored.remaining_objective,
            "Perform unfinished work.",
        )

    def test_below_budget_still_allows_one_continuation(self):
        persistence = FakePersistence()
        mission = self.make_mission()
        mission.recovery_continuation_cycles = (
            MAX_RECOVERY_CONTINUATION_CYCLES - 1
        )
        persistence.save(mission)

        tool_calls = []

        def tool(target=""):
            tool_calls.append(target)
            return "CONTINUED_OK"

        kuma = self.make_kuma(tool)

        response = SimpleNamespace(
            message=SimpleNamespace(
                content="",
                tool_calls=[
                    SimpleNamespace(
                        function=SimpleNamespace(
                            name="continuation_test",
                            arguments={
                                "target": "new",
                            },
                        )
                    )
                ],
            )
        )

        with patch(
            "app.agent.mission_service.MissionPersistence",
            return_value=persistence,
        ), patch(
            "app.agent.mission_service.chat",
            return_value=response,
        ):
            result = kuma.resume_mission(
                mission.mission_id
            )

        self.assertEqual(
            tool_calls,
            ["new"],
        )
        self.assertTrue(
            result.success
        )


if __name__ == "__main__":
    unittest.main()
