from __future__ import annotations

from dataclasses import replace
import unittest

from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.repair_apply_request import (
    RepairApplyRequest,
    RepairApplyRequestBuilder,
    RepairApplyRequestResult,
)
from app.agent.repair_policy import (
    RepairPolicy,
    RepairProposal,
)
from app.agent.repair_result_verifier import (
    RepairVerificationResult,
)


class TestRepairApplyRequest(
    unittest.TestCase
):

    def setUp(self):
        self.decision = (
            RepairPolicy().evaluate(
                RepairProposal(
                    summary="Repair sample.",
                    rationale=(
                        "Verified isolated repair."
                    ),
                    target_files=(
                        "app/agent/sample.py",
                    ),
                    permission_level=(
                        PermissionLevel.SAFE
                    ),
                )
            )
        )

        self.verification = (
            RepairVerificationResult(
                evidence_verified=True,
                eligible_for_apply_review=True,
                reason="verified",
                source_head=(
                    "a" * 40
                ),
                validation_digest=(
                    "b" * 64
                ),
                changed_files=(
                    "app/agent/sample.py",
                ),
                executed_files=(
                    "app/agent/sample.py",
                ),
                test_files=(
                    "app/agent/test_sample.py",
                ),
                tests_run=2,
                evidence_digest=(
                    "c" * 64
                ),
            )
        )

    def build(
        self,
        *,
        decision=None,
        verification=None,
    ):
        return (
            RepairApplyRequestBuilder()
            .build(
                decision=(
                    decision
                    if decision is not None
                    else self.decision
                ),
                verification=(
                    verification
                    if verification is not None
                    else self.verification
                ),
            )
        )

    def test_safe_repair_still_requires_explicit_approval(
        self
    ):
        self.assertFalse(
            self.decision
            .requires_human_approval
        )

        result = self.build()

        self.assertTrue(
            result.ready_for_confirmation,
            result.reason,
        )

        self.assertIsNotNone(
            result.request
        )

        self.assertTrue(
            result.request
            .requires_explicit_human_approval
        )

    def test_confirmation_arguments_bind_exact_repair(
        self
    ):
        result = self.build()

        arguments = (
            result.request
            .confirmation_arguments()
        )

        self.assertEqual(
            arguments["action"],
            "apply_verified_repair",
        )

        self.assertEqual(
            arguments["source_head"],
            self.verification.source_head,
        )

        self.assertEqual(
            arguments["evidence_digest"],
            self.verification.evidence_digest,
        )

        self.assertEqual(
            arguments["changed_files"],
            [
                "app/agent/sample.py",
            ],
        )

        self.assertEqual(
            arguments["request_digest"],
            result.request.request_digest,
        )

    def test_request_digest_is_deterministic(
        self
    ):
        first = self.build()
        second = self.build()

        self.assertEqual(
            first.request.request_digest,
            second.request.request_digest,
        )

    def test_changed_evidence_changes_request_digest(
        self
    ):
        first = self.build()

        changed = replace(
            self.verification,
            evidence_digest=(
                "d" * 64
            ),
        )

        second = self.build(
            verification=changed
        )

        self.assertNotEqual(
            first.request.request_digest,
            second.request.request_digest,
        )

    def test_unverified_evidence_is_rejected(
        self
    ):
        verification = replace(
            self.verification,
            evidence_verified=False,
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_apply_ineligible_evidence_is_rejected(
        self
    ):
        verification = replace(
            self.verification,
            eligible_for_apply_review=False,
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_automatic_apply_decision_is_rejected(
        self
    ):
        decision = replace(
            self.decision,
            automatic_main_checkout_apply=True,
        )

        result = self.build(
            decision=decision
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_malformed_source_head_is_rejected(
        self
    ):
        verification = replace(
            self.verification,
            source_head="not-a-head",
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_malformed_validation_digest_is_rejected(
        self
    ):
        verification = replace(
            self.verification,
            validation_digest=(
                "x" * 64
            ),
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_malformed_evidence_digest_is_rejected(
        self
    ):
        verification = replace(
            self.verification,
            evidence_digest=(
                "x" * 64
            ),
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_file_outside_original_scope_is_rejected(
        self
    ):
        verification = replace(
            self.verification,
            changed_files=(
                "app/agent/other.py",
            ),
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_duplicate_changed_files_are_rejected(
        self
    ):
        verification = replace(
            self.verification,
            changed_files=(
                "app/agent/sample.py",
                "app/agent/sample.py",
            ),
        )

        result = self.build(
            verification=verification
        )

        self.assertFalse(
            result.ready_for_confirmation
        )

    def test_request_is_immutable(
        self
    ):
        request = RepairApplyRequest(
            source_head=(
                "a" * 40
            ),
            validation_digest=(
                "b" * 64
            ),
            evidence_digest=(
                "c" * 64
            ),
            changed_files=(
                "app/agent/sample.py",
            ),
            request_digest=(
                "d" * 64
            ),
        )

        with self.assertRaises(
            Exception
        ):
            request.source_head = "changed"

    def test_result_is_immutable(
        self
    ):
        result = RepairApplyRequestResult(
            ready_for_confirmation=False,
            reason="blocked",
        )

        with self.assertRaises(
            Exception
        ):
            result.ready_for_confirmation = True


if __name__ == "__main__":
    unittest.main()
