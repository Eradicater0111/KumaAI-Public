from __future__ import annotations

from dataclasses import dataclass

from app.agent.recovery_manager import (
    FailureType,
    RecoveryAction,
    RecoveryDecision,
    RecoveryDiagnosis,
)


@dataclass(frozen=True)
class RecoveryPolicy:
    """
    Bounded policy for deciding whether a diagnosed failure
    may be automatically recovered.

    This layer does not execute recovery actions.
    It only enforces safety and retry limits.
    """

    max_retries: int = 2

    def decide(
        self,
        diagnosis: RecoveryDiagnosis,
        attempts: int = 0,
        *,
        dangerous: bool = False,
    ) -> RecoveryDecision:

        attempts = max(0, int(attempts))

        # -------------------------------------------------
        # NO FAILURE
        # -------------------------------------------------

        if diagnosis.failure_type == FailureType.NONE:
            return RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=RecoveryAction.NONE,
                reason=diagnosis.summary,
                retryable=False,
            )

        # -------------------------------------------------
        # DANGEROUS ACTIONS
        # -------------------------------------------------

        # Recovery must never turn a dangerous operation
        # into an autonomous retry loop.
        if dangerous:
            return RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=RecoveryAction.ESCALATE,
                reason=(
                    "Automatic recovery is disabled for "
                    "dangerous actions."
                ),
                retryable=False,
            )

        # -------------------------------------------------
        # PERMISSION
        # -------------------------------------------------

        if diagnosis.failure_type == FailureType.PERMISSION_DENIED:
            return RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=RecoveryAction.ESCALATE,
                reason=(
                    "Permission denial cannot be bypassed "
                    "by automatic recovery."
                ),
                retryable=False,
            )

        # -------------------------------------------------
        # RETRYABLE FAILURES
        # -------------------------------------------------

        if diagnosis.recommended_action == RecoveryAction.RETRY:

            if attempts >= self.max_retries:
                return RecoveryDecision(
                    failure_type=diagnosis.failure_type,
                    action=RecoveryAction.ESCALATE,
                    reason="Recovery retry limit reached.",
                    retryable=False,
                )

            return RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=RecoveryAction.RETRY,
                reason=(
                    f"Safe bounded retry "
                    f"{attempts + 1}/{self.max_retries}."
                ),
                retryable=True,
            )

        # -------------------------------------------------
        # ARGUMENT REPAIR
        # -------------------------------------------------

        if (
            diagnosis.recommended_action
            == RecoveryAction.REPAIR_ARGUMENTS
        ):
            return RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=RecoveryAction.REPAIR_ARGUMENTS,
                reason=(
                    "Arguments may be repaired only through "
                    "the existing normalization and validation "
                    "pipeline."
                ),
                retryable=False,
            )

        # -------------------------------------------------
        # ALTERNATIVE CAPABILITY
        # -------------------------------------------------

        if (
            diagnosis.recommended_action
            == RecoveryAction.ALTERNATIVE_CAPABILITY
        ):
            return RecoveryDecision(
                failure_type=diagnosis.failure_type,
                action=RecoveryAction.ALTERNATIVE_CAPABILITY,
                reason=(
                    "An alternative may be selected only from "
                    "already registered and authorized capabilities."
                ),
                retryable=False,
            )

        # -------------------------------------------------
        # EVERYTHING ELSE ESCALATES
        # -------------------------------------------------

        return RecoveryDecision(
            failure_type=diagnosis.failure_type,
            action=RecoveryAction.ESCALATE,
            reason=(
                "Failure is not currently eligible for "
                "automatic recovery."
            ),
            retryable=False,
        )