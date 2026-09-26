import unittest

from app.agent.permissions import PermissionLevel
from app.agent.repair_policy import (
    RepairDecision,
    RepairPolicy,
    RepairProposal,
)


class TestRepairPolicy(unittest.TestCase):

    def make_proposal(
        self,
        *,
        summary="Fix deterministic bug.",
        rationale="Observed failure evidence supports the repair.",
        target_files=("app/agent/example.py",),
        permission_level=PermissionLevel.SAFE,
    ):
        return RepairProposal(
            summary=summary,
            rationale=rationale,
            target_files=target_files,
            permission_level=permission_level,
        )

    def test_safe_proposal_is_evaluation_only(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal()
        )

        self.assertTrue(
            decision.eligible_for_isolated_evaluation
        )
        self.assertFalse(
            decision.automatic_main_checkout_apply
        )
        self.assertFalse(
            decision.requires_human_approval
        )

    def test_user_authorized_proposal_requires_approval(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                permission_level=(
                    PermissionLevel.USER_AUTHORIZED
                )
            )
        )

        self.assertTrue(
            decision.eligible_for_isolated_evaluation
        )
        self.assertFalse(
            decision.automatic_main_checkout_apply
        )
        self.assertTrue(
            decision.requires_human_approval
        )

    def test_dangerous_proposal_requires_approval(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                permission_level=PermissionLevel.DANGEROUS
            )
        )

        self.assertTrue(
            decision.eligible_for_isolated_evaluation
        )
        self.assertFalse(
            decision.automatic_main_checkout_apply
        )
        self.assertTrue(
            decision.requires_human_approval
        )

    def test_invalid_contract_fails_closed(self):
        decision = RepairPolicy().evaluate(
            object()
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )
        self.assertFalse(
            decision.automatic_main_checkout_apply
        )
        self.assertTrue(
            decision.requires_human_approval
        )

    def test_empty_summary_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                summary="   "
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_empty_rationale_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                rationale=""
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_empty_target_scope_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=()
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_file_scope_is_bounded(self):
        policy = RepairPolicy(
            max_target_files=2
        )

        decision = policy.evaluate(
            self.make_proposal(
                target_files=(
                    "app/agent/a.py",
                    "app/agent/b.py",
                    "app/agent/c.py",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_absolute_path_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "/tmp/evil.py",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_parent_traversal_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "app/agent/../evil.py",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_outside_app_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "scripts/repair.py",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_non_python_target_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "app/agent/config.json",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_duplicate_target_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "app/agent/a.py",
                    "app/agent/a.py",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_mutable_target_list_is_rejected(self):
        proposal = RepairProposal(
            summary="Fix.",
            rationale="Evidence.",
            target_files=["app/agent/a.py"],
            permission_level=PermissionLevel.SAFE,
        )

        decision = RepairPolicy().evaluate(
            proposal
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_invalid_permission_level_is_rejected(self):
        proposal = RepairProposal(
            summary="Fix.",
            rationale="Evidence.",
            target_files=("app/agent/a.py",),
            permission_level="safe",
        )

        decision = RepairPolicy().evaluate(
            proposal
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_backslash_path_is_rejected(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "app\\agent\\a.py",
                )
            )
        )

        self.assertFalse(
            decision.eligible_for_isolated_evaluation
        )

    def test_normalized_targets_are_returned(self):
        decision = RepairPolicy().evaluate(
            self.make_proposal(
                target_files=(
                    "  app/agent/a.py  ",
                    "app/tools/b.py",
                )
            )
        )

        self.assertEqual(
            decision.normalized_target_files,
            (
                "app/agent/a.py",
                "app/tools/b.py",
            ),
        )

    def test_decision_contract_is_frozen_data(self):
        decision = RepairDecision(
            eligible_for_isolated_evaluation=False,
            automatic_main_checkout_apply=False,
            requires_human_approval=True,
            reason="Blocked.",
        )

        with self.assertRaises(Exception):
            decision.reason = "Changed."


if __name__ == "__main__":
    unittest.main()
