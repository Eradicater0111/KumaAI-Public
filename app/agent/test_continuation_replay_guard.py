import unittest

from app.agent.continuation_replay_guard import (
    ContinuationReplayGuard,
)


class TestContinuationReplayGuard(unittest.TestCase):

    def setUp(self):
        self.guard = ContinuationReplayGuard()

    def test_exact_tool_and_arguments_are_blocked(self):

        decision = self.guard.assess(
            proposed_tool="write_value",
            proposed_arguments={
                "path": "a.txt",
                "value": "hello",
            },
            previous_known=True,
            previous_tool="write_value",
            previous_arguments={
                "path": "a.txt",
                "value": "hello",
            },
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertTrue(
            decision.exact_replay
        )

    def test_same_tool_with_different_arguments_is_allowed(self):

        decision = self.guard.assess(
            proposed_tool="write_value",
            proposed_arguments={
                "path": "b.txt",
            },
            previous_known=True,
            previous_tool="write_value",
            previous_arguments={
                "path": "a.txt",
            },
        )

        self.assertTrue(
            decision.allowed
        )

        self.assertFalse(
            decision.exact_replay
        )

    def test_different_tool_is_allowed(self):

        decision = self.guard.assess(
            proposed_tool="verify_value",
            proposed_arguments={
                "path": "a.txt",
            },
            previous_known=True,
            previous_tool="write_value",
            previous_arguments={
                "path": "a.txt",
            },
        )

        self.assertTrue(
            decision.allowed
        )

    def test_unknown_previous_operation_fails_closed(self):

        decision = self.guard.assess(
            proposed_tool="verify_value",
            proposed_arguments={},
            previous_known=False,
            previous_tool="",
            previous_arguments={},
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertFalse(
            decision.exact_replay
        )

        self.assertIn(
            "provenance",
            decision.reason.lower(),
        )


if __name__ == "__main__":
    unittest.main()
