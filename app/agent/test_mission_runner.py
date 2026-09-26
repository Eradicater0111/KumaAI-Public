import unittest

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.mission_controller import (
    MissionController,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)
from app.agent.mission_runner import (
    MissionRunner,
)


class TestMissionRunner(unittest.TestCase):

    def make_controller(self):

        plan = GoalPlan(
            goal="Build an application."
        )

        plan.add_step(
            GoalStep(
                id="build",
                objective="Build the application.",
            )
        )

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            plan
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        return controller

    def test_successful_step_is_completed(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                tool_name="execute_command",
                arguments={
                    "command": "echo hello"
                },
                result="hello",
                verification="Command completed successfully.",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertTrue(
            result.completed
        )

        self.assertTrue(
            controller.is_complete()
        )

        action = (
            controller
            .task_state
            .action_history[0]
        )

        self.assertEqual(
            action["tool"],
            "execute_command",
        )

        self.assertEqual(
            action["arguments"],
            {"command": "echo hello"},
        )

    def test_state_callback_runs_on_step_start_and_completion(self):

        controller = self.make_controller()

        events = []

        def execute(step):
            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                tool_name="execute_command",
                result="done",
            )

        def on_state_change(controller):
            events.append(
                controller.current_step().id
                if controller.current_step()
                else "completed"
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
            on_state_change=on_state_change,
        )

        runner.run_next_step()

        self.assertEqual(
            events,
            [
                "build",
                "completed",
            ],
        )

    def test_state_callback_runs_on_failure(self):

        controller = self.make_controller()

        events = []

        def execute(step):
            return MissionExecutionResult(
                success=False,
                verified=False,
                step_id=step.id,
                error="Build failed.",
            )

        def on_state_change(controller):
            events.append(
                controller.current_step()
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
            on_state_change=on_state_change,
        )

        runner.run_next_step()

        self.assertEqual(
            len(events),
            2,
        )

        self.assertIsNotNone(
            events[0]
            or events[1]
        )

    def test_failed_step_is_recorded(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=False,
                verified=False,
                step_id=step.id,
                error="Build failed.",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Build failed.",
            controller.task_state.failures,
        )

        self.assertFalse(
            controller.is_complete()
        )

    def test_unverified_result_does_not_complete_step(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=True,
                verified=False,
                step_id=step.id,
                tool_name="execute_command",
                result="maybe worked",
                verification="Could not verify.",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertFalse(
            result.completed
        )

        step = controller.plan.get_step(
            "build"
        )

        self.assertEqual(
            step.status.value,
            "failed",
        )

    def test_callback_exception_is_failure(self):

        controller = self.make_controller()

        def execute(step):
            raise RuntimeError(
                "executor crashed"
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "executor crashed",
            result.error,
        )

    def test_invalid_callback_result_is_rejected(self):

        controller = self.make_controller()

        def execute(step):
            return "not a mission result"

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "invalid result",
            result.error.lower(),
        )

    def test_completed_mission_is_marked_finished(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                tool_name="execute_command",
                result="done",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        runner.run_next_step()

        self.assertTrue(
            runner.mission_complete()
        )

        self.assertTrue(
            controller.task_state.finished
        )

    def test_run_mission_executes_all_steps_in_order(self):

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
                id="implementation",
                objective="Implement the application.",
                dependencies=[
                    "requirements"
                ],
            )
        )

        controller = MissionController(
            goal="Build an application."
        )

        valid, error = controller.set_plan(
            plan
        )

        self.assertTrue(valid)
        self.assertIsNone(error)

        calls = []

        def execute(step):

            calls.append(step.id)

            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                capability="filesystem",
                tool_name="open_file",
                arguments={
                    "step": step.id
                },
                result=f"{step.id} completed.",
                verification="Verified.",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_mission()

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            calls,
            [
                "requirements",
                "implementation",
            ],
        )

        self.assertTrue(
            controller.is_complete()
        )

        self.assertTrue(
            controller.task_state.finished
        )

    def test_successful_execution_preserves_capability(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=True,
                verified=True,
                step_id=step.id,
                capability="filesystem",
                tool_name="open_file",
                arguments={
                    "path": "calculator.py"
                },
                result="FILE_CONTENT",
                verification="File verified.",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertTrue(
            result.completed
        )

        self.assertEqual(
            result.capability,
            "filesystem",
        )

        self.assertEqual(
            result.tool_name,
            "open_file",
        )

    def test_failure_does_not_mark_step_complete(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=False,
                verified=False,
                step_id=step.id,
                capability="filesystem",
                tool_name="open_file",
                error="File could not be created.",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertFalse(
            result.completed
        )

        self.assertEqual(
            controller.plan.get_step(
                "build"
            ).status.value,
            "failed",
        )

    def test_resume_recovery_preserves_step_in_progress(self):

        controller = self.make_controller()

        calls = []

        def execute(step):

            calls.append(step.id)

            return MissionExecutionResult(
                success=False,
                verified=False,
                step_id=step.id,
                tool_name="test_mutating_tool",
                arguments={
                    "target": "example",
                },
                result="partial execution",
                recovery_action="resume",
                recovery_reason=(
                    "Verified partial state remains."
                ),
                recovery_evidence=(
                    "STATE: verified-partial-state"
                ),
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        step = controller.plan.get_step(
            "build"
        )

        self.assertFalse(
            result.completed
        )

        self.assertEqual(
            result.recovery_action,
            "resume",
        )

        self.assertEqual(
            calls,
            ["build"],
        )

        self.assertEqual(
            step.status.value,
            "in_progress",
        )

        self.assertEqual(
            controller.plan.current_step_id,
            "build",
        )

        self.assertEqual(
            controller.task_state.failures,
            [],
        )

        self.assertEqual(
            controller.task_state.last_evidence,
            "STATE: verified-partial-state",
        )

        self.assertTrue(
            controller.task_state.continuation_guard_known
        )

        self.assertEqual(
            controller.task_state.continuation_guard_tool,
            "test_mutating_tool",
        )

        self.assertEqual(
            controller.task_state.continuation_guard_arguments,
            {
                "target": "example",
            },
        )

    def test_resume_without_evidence_fails_closed(self):

        controller = self.make_controller()

        def execute(step):

            return MissionExecutionResult(
                success=False,
                verified=False,
                step_id=step.id,
                recovery_action="resume",
                recovery_reason="Partial state claimed.",
                recovery_evidence="",
            )

        runner = MissionRunner(
            controller=controller,
            execute_step=execute,
        )

        result = runner.run_next_step()

        self.assertEqual(
            result.recovery_action,
            "escalate",
        )

        self.assertEqual(
            controller.plan.get_step(
                "build"
            ).status.value,
            "failed",
        )

        self.assertIn(
            "lacked verified",
            result.error.lower(),
        )



if __name__ == "__main__":
    unittest.main()