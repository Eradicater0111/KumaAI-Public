from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class RecoveryAction(str, Enum):
    NONE = "none"
    RETRY = "retry"
    REPAIR_ARGUMENTS = "repair_arguments"
    ALTERNATIVE_CAPABILITY = "alternative_capability"
    RESUME = "resume"
    ESCALATE = "escalate"


class FailureType(str, Enum):
    NONE = "none"
    TRANSIENT = "transient"
    INVALID_ARGUMENTS = "invalid_arguments"
    TOOL_FAILURE = "tool_failure"
    VERIFICATION_FAILURE = "verification_failure"
    PERMISSION_DENIED = "permission_denied"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    MISSION_INTERRUPTED = "mission_interrupted"
    AGENT_CONTRACT_FAILURE = "agent_contract_failure"
    UNKNOWN = "unknown"

@dataclass(frozen=True)
class RecoveryDiagnosis:
    """
    Structured explanation of a failure before policy decides
    whether automatic recovery is allowed.

    Diagnosis does not execute recovery and does not grant
    permissions.
    """

    failure_type: FailureType
    summary: str
    likely_cause: str
    confidence: float
    recommended_action: RecoveryAction
    state_may_have_changed: bool
    affected_tool: str = ""

    def __post_init__(self):
        confidence = float(self.confidence)

        if not 0.0 <= confidence <= 1.0:
            raise ValueError(
                "RecoveryDiagnosis confidence must be between 0.0 and 1.0."
            )

        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class RecoveryDecision:
    failure_type: FailureType
    action: RecoveryAction
    reason: str
    retryable: bool = False


class RecoveryManager:
    """
    KUMA's first recovery layer.

    This component only diagnoses failures and recommends a
    bounded recovery action. It does not execute repairs,
    modify source code, or bypass permissions.
    """

    @staticmethod
    def _operation_may_have_changed_state(
        *,
        tool_name: str,
        verified: bool,
        error_text: str,
        result: Any,
    ) -> bool:
        """
        Estimate whether the failed operation may already have
        changed system state.

        This is intentionally conservative.

        Read-only operations are treated as non-mutating unless
        there is explicit evidence otherwise. Mutating operations
        are treated as state-changing when execution may have
        started.
        """

        tool = str(tool_name or "").strip().lower()

        read_only_tools = {
            "list_files",
            "open_file",
            "inspect_system",
            "analyze_screen",
            "recall",
        }

        if tool in read_only_tools:
            return False

        if not error_text and verified:
            return False

        # Explicit evidence that the operation began or partially
        # completed means we must assume state may have changed.
        partial_execution_markers = (
            "started",
            "executed",
            "completed",
            "partially",
            "partial",
            "after execution",
            "after running",
        )

        if any(
            marker in error_text
            for marker in partial_execution_markers
        ):
            return True

        # A successful tool result that failed verification means
        # the operation may have changed state even though KUMA
        # could not verify the intended final condition.
        if result is not None and not verified:
            return True

        # For unknown or mutating tools, fail closed.
        return True

    def diagnose(
        self,
        *,
        error: str | None = None,
        verified: bool = True,
        tool_name: str = "",
        result: Any = None,
    ) -> RecoveryDiagnosis:

        error_text = str(error or "").strip().lower()

        state_may_have_changed = (
            self._operation_may_have_changed_state(
                tool_name=tool_name,
                verified=verified,
                error_text=error_text,
                result=result,
            )
        )

        if not error_text and verified:
            return RecoveryDiagnosis(
                failure_type=FailureType.NONE,
                summary="No failure detected.",
                likely_cause="Execution completed without a detected failure.",
                confidence=1.0,
                recommended_action=RecoveryAction.NONE,
                state_may_have_changed=False,
                affected_tool=tool_name,
            )

        if "confirmation required" in error_text:
            return RecoveryDiagnosis(
                failure_type=FailureType.PERMISSION_DENIED,
                summary="Permission is required for the requested action.",
                likely_cause=(
                    "The tool or operation requires explicit authorization."
                ),
                confidence=0.99,
                recommended_action=RecoveryAction.ESCALATE,
                state_may_have_changed=False,
                affected_tool=tool_name,
            )

        if "denied" in error_text and "permission" in error_text:
            return RecoveryDiagnosis(
                failure_type=FailureType.PERMISSION_DENIED,
                summary="Permission was denied.",
                likely_cause=(
                    "The operation was blocked by the permission system."
                ),
                confidence=0.99,
                recommended_action=RecoveryAction.ESCALATE,
                state_may_have_changed=False,
                affected_tool=tool_name,
            )

        if (
            "invalid" in error_text
            and "argument" in error_text
        ) or "arguments could not be normalized" in error_text:
            return RecoveryDiagnosis(
                failure_type=FailureType.INVALID_ARGUMENTS,
                summary="The tool received invalid arguments.",
                likely_cause=(
                    "The supplied arguments do not satisfy the tool contract."
                ),
                confidence=0.96,
                recommended_action=RecoveryAction.REPAIR_ARGUMENTS,
                state_may_have_changed=False,
                affected_tool=tool_name,
            )

        if (
            "unknown tool" in error_text
            or "no registered tools" in error_text
            or "not permitted" in error_text
        ):
            return RecoveryDiagnosis(
                failure_type=FailureType.CAPABILITY_UNAVAILABLE,
                summary="The requested capability is unavailable.",
                likely_cause=(
                    "The requested tool is missing, unavailable, "
                    "or outside the authorized capability set."
                ),
                confidence=0.95,
                recommended_action=RecoveryAction.ALTERNATIVE_CAPABILITY,
                state_may_have_changed=False,
                affected_tool=tool_name,
            )

        if "invalid mission execution result" in error_text:
            return RecoveryDiagnosis(
                failure_type=FailureType.AGENT_CONTRACT_FAILURE,
                summary="The agent returned an invalid execution result.",
                likely_cause=(
                    "The agent violated the MissionExecutionResult contract."
                ),
                confidence=0.99,
                recommended_action=RecoveryAction.ESCALATE,
                state_may_have_changed=False,
                affected_tool=tool_name,
            )

        # -------------------------------------------------
        # TRANSIENT FAILURE
        # -------------------------------------------------
        #
        # Specific failure evidence must be evaluated before
        # the generic verification-failure fallback.
        # -------------------------------------------------

        transient_markers = (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "temporary failure",
            "connection reset",
            "connection refused",
            "busy",
            "try again",
        )

        if any(
            marker in error_text
            for marker in transient_markers
        ):
            return RecoveryDiagnosis(
                failure_type=FailureType.TRANSIENT,
                summary=(
                    "The operation appears to have "
                    "failed transiently."
                ),
                likely_cause=(
                    "The failure matches a known temporary "
                    "availability or connectivity pattern."
                ),
                confidence=0.88,
                recommended_action=RecoveryAction.RETRY,
                state_may_have_changed=(
                    state_may_have_changed
                ),
                affected_tool=tool_name,
            )

        # -------------------------------------------------
        # VERIFICATION FAILURE
        # -------------------------------------------------

        if not verified:
            return RecoveryDiagnosis(
                failure_type=FailureType.VERIFICATION_FAILURE,
                summary=(
                    "Execution completed but verification failed."
                ),
                likely_cause=(
                    "The observed result did not provide "
                    "sufficient evidence that the intended "
                    "outcome occurred."
                ),
                confidence=0.90,
                recommended_action=RecoveryAction.RETRY,
                state_may_have_changed=(
                    state_may_have_changed
                ),
                affected_tool=tool_name,
            )

        if error_text:
            return RecoveryDiagnosis(
                failure_type=FailureType.TOOL_FAILURE,
                summary=f"Tool '{tool_name}' failed.",
                likely_cause=(
                    "The failure could not be classified as safely "
                    "recoverable."
                ),
                confidence=0.65,
                recommended_action=RecoveryAction.ESCALATE,
                state_may_have_changed=state_may_have_changed,
                affected_tool=tool_name,
            )

        return RecoveryDiagnosis(
            failure_type=FailureType.UNKNOWN,
            summary="The failure could not be classified safely.",
            likely_cause=(
                "Available evidence was insufficient to determine "
                "a safe recovery path."
            ),
            confidence=0.35,
            recommended_action=RecoveryAction.ESCALATE,
            state_may_have_changed=True,
            affected_tool=tool_name,
        )
