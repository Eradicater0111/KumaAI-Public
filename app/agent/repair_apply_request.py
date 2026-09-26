from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from app.agent.repair_policy import (
    RepairDecision,
)
from app.agent.repair_result_verifier import (
    RepairVerificationResult,
)


@dataclass(frozen=True)
class RepairApplyRequest:
    """
    Immutable request describing exactly one verified repair that
    may be presented to the human for main-checkout approval.

    This object is inert:
    - it writes no files
    - it executes no commands
    - it performs no Git mutation
    - it is not approval
    - it never authorizes automatic application
    """

    source_head: str
    validation_digest: str
    evidence_digest: str
    changed_files: tuple[str, ...]
    request_digest: str
    requires_explicit_human_approval: bool = True

    def confirmation_arguments(
        self,
    ) -> dict[str, object]:
        """
        Exact arguments intended for KumaAgent.request_confirmation().

        The confirmation UI therefore sees the same repair identity
        that the future apply executor will verify.
        """

        return {
            "action": (
                "apply_verified_repair"
            ),
            "source_head": (
                self.source_head
            ),
            "validation_digest": (
                self.validation_digest
            ),
            "evidence_digest": (
                self.evidence_digest
            ),
            "changed_files": list(
                self.changed_files
            ),
            "request_digest": (
                self.request_digest
            ),
        }


@dataclass(frozen=True)
class RepairApplyRequestResult:
    ready_for_confirmation: bool
    reason: str
    request: RepairApplyRequest | None = None


class RepairApplyRequestBuilder:
    """
    First 6C.7 boundary.

    Convert verified 6C.6 evidence into one canonical repair request
    suitable for explicit human confirmation.

    Main-checkout application ALWAYS requires explicit human approval,
    regardless of the proposal's earlier PermissionLevel.

    This class performs no I/O.
    """

    _ACTION = (
        "apply_verified_repair"
    )

    @staticmethod
    def _reject(
        reason: str,
    ) -> RepairApplyRequestResult:
        return RepairApplyRequestResult(
            ready_for_confirmation=False,
            reason=reason,
            request=None,
        )

    @staticmethod
    def _valid_hex(
        value: object,
        lengths: set[int],
    ) -> bool:
        if (
            type(value) is not str
            or len(value) not in lengths
        ):
            return False

        return all(
            character
            in "0123456789abcdef"
            for character in value
        )

    @staticmethod
    def _valid_target(
        target: object,
    ) -> bool:
        if (
            type(target) is not str
            or not target
            or "\\" in target
            or target.startswith("/")
            or not target.endswith(".py")
        ):
            return False

        parts = target.split(
            "/"
        )

        if (
            not parts
            or parts[0] != "app"
        ):
            return False

        if any(
            part in {
                "",
                ".",
                "..",
                ".git",
                ".venv",
                "venv",
                "env",
                ".env",
            }
            or part.startswith(
                ".env."
            )
            for part in parts
        ):
            return False

        return True

    @staticmethod
    def _request_digest(
        *,
        source_head: str,
        validation_digest: str,
        evidence_digest: str,
        changed_files: tuple[str, ...],
    ) -> str:
        payload = {
            "version": 1,
            "action": (
                RepairApplyRequestBuilder
                ._ACTION
            ),
            "source_head": (
                source_head
            ),
            "validation_digest": (
                validation_digest
            ),
            "evidence_digest": (
                evidence_digest
            ),
            "changed_files": list(
                changed_files
            ),
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            encoded
        ).hexdigest()

    def build(
        self,
        *,
        decision: RepairDecision,
        verification: RepairVerificationResult,
    ) -> RepairApplyRequestResult:
        if not isinstance(
            decision,
            RepairDecision,
        ):
            return self._reject(
                "Repair decision contract is invalid."
            )

        if not isinstance(
            verification,
            RepairVerificationResult,
        ):
            return self._reject(
                "Repair verification contract is invalid."
            )

        if (
            decision
            .eligible_for_isolated_evaluation
            is not True
        ):
            return self._reject(
                "Repair decision is not eligible."
            )

        if (
            decision
            .automatic_main_checkout_apply
            is not False
        ):
            return self._reject(
                "Repair decision illegally claims "
                "automatic main-checkout authority."
            )

        if (
            verification
            .evidence_verified
            is not True
        ):
            return self._reject(
                "Repair evidence has not been verified."
            )

        if (
            verification
            .eligible_for_apply_review
            is not True
        ):
            return self._reject(
                "Repair is not eligible for apply review."
            )

        if not self._valid_hex(
            verification.source_head,
            {
                40,
                64,
            },
        ):
            return self._reject(
                "Repair source HEAD evidence is malformed."
            )

        if not self._valid_hex(
            verification.validation_digest,
            {
                64,
            },
        ):
            return self._reject(
                "Repair validation digest is malformed."
            )

        if not self._valid_hex(
            verification.evidence_digest,
            {
                64,
            },
        ):
            return self._reject(
                "Repair evidence digest is malformed."
            )

        changed_files = (
            verification.changed_files
        )

        if (
            type(changed_files) is not tuple
            or not changed_files
        ):
            return self._reject(
                "Repair contains no immutable changed-file scope."
            )

        if (
            len(
                set(
                    changed_files
                )
            )
            != len(
                changed_files
            )
        ):
            return self._reject(
                "Repair contains duplicate changed files."
            )

        if any(
            not self._valid_target(
                target
            )
            for target in changed_files
        ):
            return self._reject(
                "Repair contains an unsafe changed-file path."
            )

        approved_scope = (
            decision
            .normalized_target_files
        )

        if (
            type(approved_scope) is not tuple
            or not approved_scope
        ):
            return self._reject(
                "Repair decision has no immutable target scope."
            )

        if any(
            target
            not in approved_scope
            for target in changed_files
        ):
            return self._reject(
                "Verified repair exceeds the originally "
                "approved repair target scope."
            )

        request_digest = (
            self._request_digest(
                source_head=(
                    verification.source_head
                ),
                validation_digest=(
                    verification
                    .validation_digest
                ),
                evidence_digest=(
                    verification
                    .evidence_digest
                ),
                changed_files=(
                    changed_files
                ),
            )
        )

        request = RepairApplyRequest(
            source_head=(
                verification.source_head
            ),
            validation_digest=(
                verification.validation_digest
            ),
            evidence_digest=(
                verification.evidence_digest
            ),
            changed_files=(
                changed_files
            ),
            request_digest=(
                request_digest
            ),
            requires_explicit_human_approval=True,
        )

        return RepairApplyRequestResult(
            ready_for_confirmation=True,
            reason=(
                "Verified repair is ready to be presented "
                "for explicit human confirmation. This "
                "request grants no main-checkout mutation "
                "authority by itself."
            ),
            request=request,
        )
