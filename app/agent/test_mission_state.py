import unittest

from app.agent.mission_state import (
    MissionState,
    MissionStatus,
)


class TestMissionState(unittest.TestCase):

    def test_create_generates_mission_id(self):

        mission = MissionState.create(
            "Build a calculator."
        )

        self.assertTrue(
            mission.mission_id.startswith("M-")
        )

        self.assertEqual(
            mission.goal,
            "Build a calculator.",
        )

        self.assertEqual(
            mission.status,
            MissionStatus.PLANNED,
        )

    def test_empty_goal_is_rejected(self):

        with self.assertRaises(ValueError):
            MissionState.create("")

    def test_step_completion_is_recorded(self):

        mission = MissionState.create(
            "Build an application."
        )

        mission.start()
        mission.set_current_step(
            "implementation"
        )

        mission.complete_step(
            "implementation"
        )

        self.assertIn(
            "implementation",
            mission.completed_step_ids,
        )

        self.assertEqual(
            mission.current_step_id,
            "",
        )

    def test_failure_changes_status(self):

        mission = MissionState.create(
            "Build an application."
        )

        mission.start()
        mission.set_current_step(
            "implementation"
        )

        mission.fail_step(
            "implementation",
            "Compilation failed.",
        )

        self.assertEqual(
            mission.status,
            MissionStatus.FAILED,
        )

        self.assertIn(
            "implementation",
            mission.failed_step_ids,
        )

        self.assertIn(
            "Compilation failed.",
            mission.failures,
        )

    def test_verified_action_updates_evidence(self):

        mission = MissionState.create(
            "Inspect the system."
        )

        mission.add_action(
            tool_name="inspect_system",
            arguments={},
            result="SYSTEM_OK",
            verified=True,
            capability="system_inspection",
        )

        self.assertEqual(
            mission.last_evidence,
            "SYSTEM_OK",
        )

        self.assertEqual(
            mission.action_history[0]["tool"],
            "inspect_system",
        )

        self.assertEqual(
            mission.action_history[0]["capability"],
            "system_inspection",
        )

    def test_plan_survives_json_round_trip(self):

        from app.agent.goal_plan import (
            GoalPlan,
            GoalStep,
        )

        mission = MissionState.create(
            "Build an application."
        )

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build the application.",
                success_criteria=[
                    "Application exists."
                ],
                verification_requirements=[
                    "Check the application."
                ],
                artifacts=[
                    "app.py"
                ],
            )
        )

        mission.plan = plan

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertIsNotNone(
            restored.plan
        )

        self.assertEqual(
            restored.plan.goal,
            "Build an application.",
        )

        self.assertEqual(
            restored.plan.steps[0].id,
            "build",
        )

    def test_json_round_trip(self):

        mission = MissionState.create(
            "Build an application."
        )

        mission.start()
        mission.set_current_step(
            "build"
        )
        mission.add_observation(
            "Source directory inspected."
        )
        mission.add_artifact(
            "calculator.py"
        )

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertEqual(
            restored.mission_id,
            mission.mission_id,
        )

        self.assertEqual(
            restored.goal,
            mission.goal,
        )

        self.assertEqual(
            restored.status,
            mission.status,
        )

        self.assertEqual(
            restored.current_step_id,
            mission.current_step_id,
        )

        self.assertEqual(
            restored.observations,
            mission.observations,
        )

        self.assertEqual(
            restored.artifacts,
            mission.artifacts,
        )

    def test_remaining_objective_survives_json_round_trip(self):

        mission = MissionState.create(
            "Build an application."
        )

        mission.remaining_objective = (
            "Verify the unfinished configuration."
        )

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertEqual(
            restored.remaining_objective,
            (
                "Verify the unfinished "
                "configuration."
            ),
        )


    def test_continuation_guard_survives_json_round_trip(self):

        mission = MissionState.create(
            "Continue safely."
        )

        mission.continuation_guard_known = True

        mission.continuation_guard_tool = (
            "mutating_test_tool"
        )

        mission.continuation_guard_arguments = {
            "target": "example",
        }

        mission.continuation_guard_capability = (
            "test_capability"
        )

        restored = MissionState.from_json(
            mission.to_json()
        )

        self.assertTrue(
            restored.continuation_guard_known
        )

        self.assertEqual(
            restored.continuation_guard_tool,
            "mutating_test_tool",
        )

        self.assertEqual(
            restored.continuation_guard_arguments,
            {
                "target": "example",
            },
        )

        self.assertEqual(
            restored.continuation_guard_capability,
            "test_capability",
        )



if __name__ == "__main__":
    unittest.main()