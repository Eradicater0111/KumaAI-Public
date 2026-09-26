import math
import unittest

from app.agent.continuation_replay_guard import (
    ContinuationReplayGuard,
)


class TestReplayGuardAdversarial(unittest.TestCase):

    def setUp(self):
        self.guard = ContinuationReplayGuard()

    def assess(
        self,
        *,
        proposed,
        previous,
        proposed_tool="write_value",
        previous_tool="write_value",
        previous_known=True,
    ):
        return self.guard.assess(
            proposed_tool=proposed_tool,
            proposed_arguments=proposed,
            previous_known=previous_known,
            previous_tool=previous_tool,
            previous_arguments=previous,
        )

    def test_dictionary_key_order_cannot_bypass_replay_block(self):
        decision = self.assess(
            proposed={"a": 1, "b": 2},
            previous={"b": 2, "a": 1},
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.exact_replay)

    def test_nested_dictionary_order_cannot_bypass_replay_block(self):
        decision = self.assess(
            proposed={
                "outer": {
                    "a": 1,
                    "b": [2, 3],
                }
            },
            previous={
                "outer": {
                    "b": [2, 3],
                    "a": 1,
                }
            },
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.exact_replay)

    def test_numeric_equivalent_bool_and_int_block_conservatively(self):
        decision = self.assess(
            proposed={"value": True},
            previous={"value": 1},
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.exact_replay)

    def test_numeric_equivalent_int_and_float_block_conservatively(self):
        decision = self.assess(
            proposed={"value": 1.0},
            previous={"value": 1},
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.exact_replay)

    def test_string_false_is_not_coerced_into_known_provenance(self):
        decision = self.guard.assess(
            proposed_tool="write_value",
            proposed_arguments={},
            previous_known="false",
            previous_tool="write_value",
            previous_arguments={},
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)
        self.assertIn(
            "malformed",
            decision.reason.lower(),
        )

    def test_missing_previous_arguments_fail_closed(self):
        decision = self.guard.assess(
            proposed_tool="write_value",
            proposed_arguments={},
            previous_known=True,
            previous_tool="write_value",
            previous_arguments=None,
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)

    def test_list_of_pairs_is_not_coerced_into_dictionary(self):
        decision = self.guard.assess(
            proposed_tool="write_value",
            proposed_arguments={"path": "a.txt"},
            previous_known=True,
            previous_tool="write_value",
            previous_arguments=[
                ("path", "a.txt"),
            ],
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)

    def test_non_string_argument_key_fails_closed(self):
        decision = self.assess(
            proposed={"value": "x"},
            previous={1: "x"},
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)

    def test_nan_cannot_create_unstable_replay_identity(self):
        decision = self.assess(
            proposed={"value": math.nan},
            previous={"value": math.nan},
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)
        self.assertIn(
            "non-finite",
            decision.reason.lower(),
        )

    def test_cyclic_arguments_fail_closed(self):
        cyclic = {}
        cyclic["self"] = cyclic

        decision = self.assess(
            proposed={"value": "safe"},
            previous=cyclic,
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)
        self.assertIn(
            "cycle",
            decision.reason.lower(),
        )

    def test_non_dictionary_context_fails_closed(self):
        decision = self.guard.assess_context(
            proposed_tool="write_value",
            proposed_arguments={},
            context="not-a-dictionary",
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)
        self.assertIn(
            "malformed",
            decision.reason.lower(),
        )

    def test_missing_context_field_fails_closed(self):
        decision = self.guard.assess_context(
            proposed_tool="write_value",
            proposed_arguments={},
            context={
                "known": True,
                "tool": "write_value",
            },
        )
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.exact_replay)
        self.assertIn(
            "missing",
            decision.reason.lower(),
        )

    def test_unicode_canonical_equivalent_strings_are_replay(self):
        composed = "\u00e9"
        decomposed = "e\u0301"

        decision = self.assess(
            proposed={"value": composed},
            previous={"value": decomposed},
        )
        self.assertFalse(decision.allowed)
        self.assertTrue(decision.exact_replay)


if __name__ == "__main__":
    unittest.main()
