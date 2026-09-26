from __future__ import annotations

from dataclasses import dataclass

from app.agent.recovery_state_verifier import (
    StateVerificationResult,
)


@dataclass(frozen=True)
class ObjectiveVerificationResult:
    """
    Observation about whether a mission objective is satisfied.

    This object carries evidence only.

    It does not execute tools, mutate state, grant permission,
    or authorize a recovery action.
    """

    known: bool
    satisfied: bool | None
    summary: str
    evidence: str = ""
    contract_failure: bool = False

    def __post_init__(self) -> None:
        self.validate_contract()

    def validate_contract(self) -> None:
        if type(self.known) is not bool:
            raise ValueError(
                "ObjectiveVerificationResult.known must be boolean."
            )

        if (
            self.satisfied is not None
            and type(self.satisfied) is not bool
        ):
            raise ValueError(
                "ObjectiveVerificationResult.satisfied must be "
                "boolean or None."
            )

        if type(self.contract_failure) is not bool:
            raise ValueError(
                "ObjectiveVerificationResult.contract_failure must be boolean."
            )

        if not isinstance(self.summary, str):
            raise ValueError(
                "ObjectiveVerificationResult.summary must be a string."
            )

        if not isinstance(self.evidence, str):
            raise ValueError(
                "ObjectiveVerificationResult.evidence must be a string."
            )

        if self.known and self.satisfied is None:
            raise ValueError(
                "Known objective verification requires an explicit "
                "satisfied value."
            )

        if not self.known and self.satisfied is not None:
            raise ValueError(
                "Unknown objective verification cannot claim satisfaction."
            )

        if self.contract_failure and self.known:
            raise ValueError(
                "Verifier contract failure cannot report a known objective."
            )


class ObjectiveVerifier:
    """
    Conservative mission-objective verification boundary.

    The base implementation does not infer completion from natural
    language or from a tool name.

    Concrete deterministic objective verifiers can be added as KUMA
    gains real capabilities with observable end-state contracts.
    """

    def verify(
        self,
        *,
        objective: str,
        success_criteria: list[str] | None = None,
        verification_requirements: list[str] | None = None,
        tool_name: str = "",
        arguments: dict | None = None,
        state: StateVerificationResult | None = None,
    ) -> ObjectiveVerificationResult:
        objective = str(objective or "").strip()

        if not objective:
            return ObjectiveVerificationResult(
                known=False,
                satisfied=None,
                summary=(
                    "The mission objective is missing and cannot "
                    "be verified."
                ),
                evidence="",
            )

        if state is None or not state.known:
            return ObjectiveVerificationResult(
                known=False,
                satisfied=None,
                summary=(
                    "The mission objective cannot be verified "
                    "because the current state is unknown."
                ),
                evidence=(
                    state.evidence
                    if state is not None
                    else ""
                ),
            )

        return ObjectiveVerificationResult(
            known=False,
            satisfied=None,
            summary=(
                "No deterministic objective verifier is registered "
                "for this mission step."
            ),
            evidence=state.evidence,
        )


def safe_verify_objective(
    verifier,
    *,
    objective: str,
    success_criteria: list[str] | None = None,
    verification_requirements: list[str] | None = None,
    tool_name: str = "",
    arguments: dict | None = None,
    state: StateVerificationResult | None = None,
) -> ObjectiveVerificationResult:
    # A broken objective verifier can never become completion authority.
    state_evidence = (
        state.evidence
        if isinstance(state, StateVerificationResult)
        else ""
    )

    try:
        verification = verifier.verify(
            objective=objective,
            success_criteria=success_criteria,
            verification_requirements=verification_requirements,
            tool_name=tool_name,
            arguments=arguments,
            state=state,
        )

        if not isinstance(verification, ObjectiveVerificationResult):
            raise TypeError(
                "Objective verifier returned an invalid result type."
            )

        verification.validate_contract()
        return verification

    except Exception as error:
        return ObjectiveVerificationResult(
            known=False,
            satisfied=None,
            summary=(
                "Objective verifier failed closed because its result "
                "contract could not be trusted. "
                f"Failure type: {type(error).__name__}."
            ),
            evidence=state_evidence,
            contract_failure=True,
        )
