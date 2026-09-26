import unittest

from types import SimpleNamespace

from app.agent.goal_plan import (
    GoalStep,
)
from app.agent.kuma_mission_executor import (
    KumaMissionExecutor,
)
from app.agent.mission_result import (
    MissionExecutionResult,
)


class TestKumaMissionExecutor(unittest.TestCase):

    def test_delegates_to_kuma_agent(self):

        step = GoalStep(
            id="build",
            objective="Build the application.",
        )

        expected = MissionExecutionResult(
            success=True,
            step_id="build",
            capability="filesystem",
            tool_name="open_file",
            result="DONE",
            verified=True,
        )

        class FakeKuma:

            def execute_mission_step(
                self,
                received_step,
            ):
                self.received = received_step
                return expected

        kuma = FakeKuma()

        executor = KumaMissionExecutor(
            kuma
        )

        result = executor.execute(
            step
        )

        self.assertIs(
            result,
            expected,
        )

        self.assertIs(
            kuma.received,
            step,
        )

    def test_missing_kuma_method_is_rejected(self):

        step = GoalStep(
            id="build",
            objective="Build the application.",
        )

        executor = KumaMissionExecutor(
            SimpleNamespace()
        )

        result = executor.execute(
            step
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "execute_mission_step",
            result.error,
        )

    def test_invalid_kuma_result_is_rejected(self):

        step = GoalStep(
            id="build",
            objective="Build the application.",
        )

        class FakeKuma:

            def execute_mission_step(
                self,
                received_step,
            ):
                return "not a mission result"

        executor = KumaMissionExecutor(
            FakeKuma()
        )

        result = executor.execute(
            step
        )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "invalid",
            result.error.lower(),
        )


if __name__ == "__main__":
    unittest.main()