from __future__ import annotations

from dataclasses import dataclass

from app.agent.objective_verifier import (
    ObjectiveVerificationResult,
)
from app.agent.recovery_manager import (
    FailureType,
    RecoveryAction,
    RecoveryDecision,
    RecoveryDiagnosis,
)
from app.agent.recovery_state_verifier import (
    StateVerificationResult,
)


@dataclass(frozen=True)
class RecoveryStrategy:
    """
    Evidence-aware recovery recommendation.

    A strategy is advisory only.

    It does not:
        - execute tools
        - modify state
        - bypass permissions
        - authorize dangerous actions
        - replan the mission
    """

    action: RecoveryAction
    reason: str
    automatic: bool = False


class RecoveryStrategyAdvisor:
    """
    Combine diagnosis, policy, state evidence, and objective
    evidence into one conservative recovery recommendation.

    This layer may make recovery stricter than RecoveryPolicy.

    It must never weaken an existing safety boundary.
    """

    def assess(
        self,
        *,
        diagnosis: RecoveryDiagnosis,
        policy_decision: RecoveryDecision,
        state_verification: StateVerificationResult | None = None,
        objective_verification: ObjectiveVerificationResult | None = None,
        dangerous: bool = False,
    ) -> RecoveryStrategy:

        # -------------------------------------------------
        # VERIFIER CONTRACT FAILURE
        # -------------------------------------------------

        if (
            state_verification is not None
            and getattr(
                state_verification,
                "contract_failure",
                False,
            )
        ):
            return RecoveryStrategy(
                action=RecoveryAction.ESCALATE,
                reason=(
                    "State verification contract failed. "
                    "Automatic recovery is disabled."
                ),
                automatic=False,
            )

        if (
            objective_verification is not None
            and getattr(
                objective_verification,
                "contract_failure",
                False,
            )
        ):
            return RecoveryStrategy(
                action=RecoveryAction.ESCALATE,
                reason=(
                    "Objective verification contract failed. "
                    "Automatic recovery is disabled."
                ),
                automatic=False,
            )

        # -------------------------------------------------
        # DANGEROUS ACTION
        # -------------------------------------------------

        if dangerous:
            return RecoveryStrategy(
                action=RecoveryAction.ESCALATE,
                reason=(
                    "Dangerous operations cannot receive an "
                    "automatic recovery strategy."
                ),
                automatic=False,
            )

        # -------------------------------------------------
        # PERMISSION FAILURE
        # -------------------------------------------------

        if diagnosis.failure_type == FailureType.PERMISSION_DENIED:
            return RecoveryStrategy(
                action=RecoveryAction.ESCALATE,
                reason=(
                    "Permission failures require authorization "
                    "and cannot be recovered automatically."
                ),
                automatic=False,
            )

        # -------------------------------------------------
        # OBJECTIVE ALREADY SATISFIED
        # -------------------------------------------------

        if (
            objective_verification is not None
            and objective_verification.known
            and objective_verification.satisfied
        ):
            return RecoveryStrategy(
                action=RecoveryAction.NONE,
                reason=(
                    "Independent objective evidence indicates "
                    "that the mission step is already satisfied."
                ),
                automatic=False,
            )

        # -------------------------------------------------
        # OPERATION MAY HAVE CHANGED STATE
        # -------------------------------------------------

        if diagnosis.state_may_have_changed:

            if (
                state_verification is None
                or not state_verification.known
            ):
                return RecoveryStrategy(
                    action=RecoveryAction.ESCALATE,
                    reason=(
                        "System state is unknown after an operation "
                        "that may have changed it."
                    ),
                    automatic=False,
                )

            if state_verification.state_changed:

                if (
                    objective_verification is not None
                    and objective_verification.known
                    and objective_verification.satisfied is False
                ):
                    return RecoveryStrategy(
                        action=RecoveryAction.RESUME,
                        reason=(
                            "Partial state change is known and the "
                            "objective remains unsatisfied. Recovery "
                            "should continue from verified state "
                            "rather than blindly repeating the "
                            "original operation."
                        ),
                        automatic=False,
                    )

                return RecoveryStrategy(
                    action=RecoveryAction.ESCALATE,
                    reason=(
                        "System state changed, but the objective "
                        "status is not known safely."
                    ),
                    automatic=False,
                )

        # -------------------------------------------------
        # ARGUMENT REPAIR
        # -------------------------------------------------

        if policy_decision.action == RecoveryAction.REPAIR_ARGUMENTS:
            return RecoveryStrategy(
                action=RecoveryAction.REPAIR_ARGUMENTS,
                reason=policy_decision.reason,
                automatic=False,
            )

        # -------------------------------------------------
        # ALTERNATIVE CAPABILITY
        # -------------------------------------------------

        if (
            policy_decision.action
            == RecoveryAction.ALTERNATIVE_CAPABILITY
        ):
            return RecoveryStrategy(
                action=RecoveryAction.ALTERNATIVE_CAPABILITY,
                reason=policy_decision.reason,
                automatic=False,
            )

        # -------------------------------------------------
        # SAFE BOUNDED RETRY
        # -------------------------------------------------

        if policy_decision.action == RecoveryAction.RETRY:
            return RecoveryStrategy(
                action=RecoveryAction.RETRY,
                reason=policy_decision.reason,
                automatic=bool(
                    policy_decision.retryable
                ),
            )

        # -------------------------------------------------
        # DEFAULT TO EXISTING POLICY
        # -------------------------------------------------

        return RecoveryStrategy(
            action=policy_decision.action,
            reason=policy_decision.reason,
            automatic=False,
        )
