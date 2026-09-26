import unittest

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
    StepStatus,
)
from app.agent.mission_controller import (
    MissionController,
)


class TestMissionController(unittest.TestCase):

    def make_plan(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="requirements",
                objective="Define requirements.",
            )
        )

        plan.add_step(
            GoalStep(
                id="architecture",
                objective="Design architecture.",
                dependencies=["requirements"],
            )
        )

        plan.add_step(
            GoalStep(
                id="implementation",
                objective="Implement the application.",
                dependencies=["architecture"],
            )
        )

        return plan

    def test_plan_can_be_attached(self):

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            self.make_plan()
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        self.assertIsNotNone(
            controller.next_step()
        )

        self.assertEqual(
            controller.next_step().id,
            "requirements",
        )

    def test_controller_can_be_restored_from_mission_state(self):

        from app.agent.mission_state import (
            MissionState,
        )

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="first",
                objective="Perform the first action.",
            )
        )

        plan.add_step(
            GoalStep(
                id="second",
                objective="Perform the second action.",
                dependencies=[
                    "first"
                ],
            )
        )

        plan.steps[0].status = (
            StepStatus.COMPLETED
        )

        plan.current_step_id = ""

        mission = MissionState.create(
            "Build an application."
        )

        mission.plan = plan

        mission.completed_step_ids = [
            "first"
        ]

        mission.last_evidence = (
            "FIRST_VERIFIED"
        )

        restored = (
            MissionController
            .from_mission_state(
                mission
            )
        )

        self.assertEqual(
            restored.task_state.goal,
            "Build an application.",
        )

        self.assertEqual(
            restored.plan.current_step_id,
            "",
        )

        self.assertEqual(
            restored.plan.get_step(
                "first"
            ).status,
            StepStatus.COMPLETED,
        )

        self.assertEqual(
            restored.next_step().id,
            "second",
        )

        self.assertEqual(
            restored.task_state.last_evidence,
            "FIRST_VERIFIED",
        )

    def test_restore_rejects_missing_plan(self):

        from app.agent.mission_state import (
            MissionState,
        )

        mission = MissionState.create(
            "Build an application."
        )

        with self.assertRaises(ValueError):
            MissionController.from_mission_state(
                mission
            )

    def test_restore_rejects_goal_mismatch(self):

        from app.agent.mission_state import (
            MissionState,
        )

        plan = GoalPlan(
            goal="Different goal."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build it.",
            )
        )

        mission = MissionState.create(
            "Build an application."
        )

        mission.plan = plan

        with self.assertRaises(ValueError):
            MissionController.from_mission_state(
                mission
            )

    def test_begin_next_step(self):

        controller = MissionController(
            goal="Build an application."
        )

        plan = self.make_plan()

        valid, error = controller.set_plan(
            plan
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        step = controller.begin_next_step()

        self.assertIsNotNone(step)
        self.assertEqual(
            step.id,
            "requirements",
        )

        self.assertEqual(
            step.status,
            StepStatus.IN_PROGRESS,
        )

        self.assertEqual(
            controller.plan.current_step_id,
            "requirements",
        )

    def test_completed_step_unlocks_dependent_step(self):

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            self.make_plan()
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        controller.begin_next_step()

        completed = controller.complete_current_step(
            "Requirements completed."
        )

        self.assertTrue(completed)

        next_step = controller.next_step()

        self.assertIsNotNone(next_step)
        self.assertEqual(
            next_step.id,
            "architecture",
        )

    def test_failed_step_is_recorded(self):

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            self.make_plan()
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        controller.begin_next_step()

        failed = controller.fail_current_step(
            "Requirements could not be determined."
        )

        self.assertTrue(failed)

        step = controller.plan.get_step(
            "requirements"
        )

        self.assertEqual(
            step.status,
            StepStatus.FAILED,
        )

        self.assertIn(
            "Requirements could not be determined.",
            controller.task_state.failures,
        )

    def test_complete_plan_marks_task_finished(self):

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            self.make_plan()
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        controller.begin_next_step()
        controller.complete_current_step(
            "Requirements complete."
        )

        controller.begin_next_step()
        controller.complete_current_step(
            "Architecture complete."
        )

        controller.begin_next_step()
        controller.complete_current_step(
            "Implementation complete."
        )

        self.assertTrue(
            controller.is_complete()
        )

        controller.mark_complete()

        self.assertTrue(
            controller.task_state.finished
        )

    def test_plan_goal_must_match_mission_goal(self):

        controller = MissionController(
            goal="Build an application."
        )

        plan = GoalPlan(
            goal="Build a website."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build it.",
            )
        )

        valid, error = controller.set_plan(
            plan
        )

        self.assertFalse(valid)
        self.assertIn(
            "goal does not match",
            error.lower(),
        )

    def test_completed_step_clears_current_step(self):

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            self.make_plan()
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        step = controller.begin_next_step()

        self.assertEqual(
            step.id,
            "requirements",
        )

        completed = controller.complete_current_step(
            "Requirements completed."
        )

        self.assertTrue(completed)

        self.assertIsNone(
            controller.current_step()
        )

        self.assertEqual(
            controller.plan.current_step_id,
            "",
        )

        self.assertEqual(
            controller.plan.get_step(
                "requirements"
            ).status,
            StepStatus.COMPLETED,
        )


    def test_preserve_current_step_for_resume(self):

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            self.make_plan()
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        step = controller.begin_next_step()

        preserved = (
            controller
            .preserve_current_step_for_resume(
                reason="Verified partial state.",
                evidence="PARTIAL_VERIFIED",
                tool_name="mutating_test_tool",
                arguments={
                    "target": "example",
                },
                capability="test_capability",
            )
        )

        self.assertTrue(
            preserved
        )

        self.assertEqual(
            step.status,
            StepStatus.IN_PROGRESS,
        )

        self.assertEqual(
            controller.plan.current_step_id,
            step.id,
        )

        self.assertEqual(
            controller.task_state.last_evidence,
            "PARTIAL_VERIFIED",
        )

        self.assertEqual(
            controller.task_state.remaining_objective,
            "",
        )

        self.assertEqual(
            step.reason,
            "Verified partial state.",
        )

        self.assertTrue(
            controller.task_state.continuation_guard_known
        )

        self.assertEqual(
            controller.task_state.continuation_guard_tool,
            "mutating_test_tool",
        )

        self.assertEqual(
            controller.task_state.continuation_guard_arguments,
            {
                "target": "example",
            },
        )

        self.assertEqual(
            controller.task_state.continuation_guard_capability,
            "test_capability",
        )


    def test_restore_prefers_persisted_remaining_objective(self):

        from app.agent.mission_state import (
            MissionState,
            MissionStatus,
        )

        plan = self.make_plan()

        step = plan.get_step(
            "requirements"
        )

        step.status = (
            StepStatus.IN_PROGRESS
        )

        plan.current_step_id = (
            step.id
        )

        mission = MissionState.create(
            "Build an application."
        )

        mission.plan = plan

        mission.status = (
            MissionStatus.PAUSED
        )

        mission.current_step_id = (
            step.id
        )

        mission.remaining_objective = (
            "Verify only the unfinished requirements."
        )

        restored = (
            MissionController
            .from_mission_state(
                mission
            )
        )

        self.assertEqual(
            restored.task_state.remaining_objective,
            (
                "Verify only the unfinished "
                "requirements."
            ),
        )

        self.assertEqual(
            restored.plan.current_step_id,
            step.id,
        )

        self.assertEqual(
            restored.current_step().status,
            StepStatus.IN_PROGRESS,
        )


    def test_restore_preserves_continuation_guard_provenance(self):

        from app.agent.mission_state import (
            MissionState,
            MissionStatus,
        )

        plan = self.make_plan()

        step = plan.get_step(
            "requirements"
        )

        step.status = StepStatus.IN_PROGRESS
        plan.current_step_id = step.id

        mission = MissionState.create(
            "Build an application."
        )

        mission.plan = plan
        mission.status = MissionStatus.PAUSED
        mission.current_step_id = step.id

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

        restored = (
            MissionController
            .from_mission_state(
                mission
            )
        )

        self.assertTrue(
            restored.task_state.continuation_guard_known
        )

        self.assertEqual(
            restored.task_state.continuation_guard_tool,
            "mutating_test_tool",
        )

        self.assertEqual(
            restored.task_state.continuation_guard_arguments,
            {
                "target": "example",
            },
        )



if __name__ == "__main__":
    unittest.main()