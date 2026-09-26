"""
KUMA-INTEGRATION-1C — live zero-authority Raphael handoff observation.

This adapter connects the already-frozen Integration-1B shadow action
evaluation to the already-frozen RAPHAEL-1F execution bridge.

The connection is observational. It never authorizes or blocks KUMA:

    existing KUMA current-request gate result
        +
    Integration-1B ShadowActionEvaluation
        +
    exact current request / normalized arguments / current tool set
        ↓
    frozen RaphaelExecutionBridge.prepare(...)
        ↓
    HandoffAssessment
        ↓
    ShadowHandoffObservation
    AUTHORITY:NONE
        ↓
    STOP

KUMA's existing permission, confirmation, GUI authority, executor and
verification pipelines remain unchanged and authoritative.

Critical boundaries:

- HANDOFF != APPROVAL
- FORWARD_TO_KUMA != PERMISSION
- GUI_AUTHORITY_REQUIRED != EXECUTION
- REJECTED != RAPHAEL BECOMING A SAFETY AUTHORITY
- CURRENT-REQUEST GROUNDING != DANGEROUS APPROVAL
- BRIDGE ASSESSMENT != EXECUTOR INPUT

The adapter intentionally consumes the boolean result of KUMA's already-run
current-request gate instead of calling stateful clarification logic again.
The boolean is rebound to the exact request, tool identity and argument digest
before it is exposed to the frozen bridge as its pure grounding predicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalSituation,
)
from app.agent.shadow_action_evaluation import (
    ShadowActionEvaluation,
    ShadowActionStatus,
    arguments_digest,
)
from app.agent.tactical_execution_bridge import (
    HandoffAssessment,
    RaphaelExecutionBridge,
)


SHADOW_HANDOFF_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)


class ShadowHandoffStatus(str, Enum):
    ASSESSED = "assessed"
    SKIPPED = "skipped"


@dataclass(
    frozen=True,
    slots=True,
)
class ShadowHandoffObservation:
    """
    Immutable zero-authority observation of the frozen 1F bridge.

    A SKIPPED observation carries no bridge assessment. An ASSESSED
    observation carries exactly one frozen HandoffAssessment, which itself
    remains AUTHORITY:NONE.
    """

    status: ShadowHandoffStatus
    tool_name: str
    arguments_digest: str
    reason: str
    assessment: HandoffAssessment | None = None
    authority: str = field(
        default=SHADOW_HANDOFF_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.status,
            ShadowHandoffStatus,
        ):
            raise TypeError(
                "status must be ShadowHandoffStatus."
            )

        if (
            type(
                self.tool_name
            ) is not str
            or not self.tool_name.strip()
        ):
            raise ValueError(
                "tool_name must be a nonblank string."
            )

        object.__setattr__(
            self,
            "tool_name",
            self.tool_name.strip(),
        )

        if (
            type(
                self.arguments_digest
            ) is not str
            or len(
                self.arguments_digest
            ) != 64
            or any(
                character
                not in "0123456789abcdef"
                for character
                in self.arguments_digest
            )
        ):
            raise ValueError(
                "arguments_digest must be a lowercase SHA-256 digest."
            )

        if type(
            self.reason
        ) is not str:
            raise TypeError(
                "reason must be a string."
            )

        normalized_reason = " ".join(
            self.reason.split()
        )

        if not normalized_reason:
            raise ValueError(
                "reason cannot be blank."
            )

        object.__setattr__(
            self,
            "reason",
            normalized_reason,
        )

        if (
            self.assessment is not None
            and not isinstance(
                self.assessment,
                HandoffAssessment,
            )
        ):
            raise TypeError(
                "assessment must be HandoffAssessment or None."
            )

        if (
            self.assessment is not None
            and self.assessment.authority
            != SHADOW_HANDOFF_AUTHORITY_NONE
        ):
            raise ValueError(
                "bridge assessment authority must remain NONE."
            )

        if (
            self.status
            == ShadowHandoffStatus.ASSESSED
        ):
            if self.assessment is None:
                raise ValueError(
                    "ASSESSED observation requires a bridge assessment."
                )

        elif self.assessment is not None:
            raise ValueError(
                "SKIPPED observation cannot carry a bridge assessment."
            )


def _normalized_request(
    current_request: str,
) -> str:
    if type(
        current_request
    ) is not str:
        raise TypeError(
            "current_request must be a string."
        )

    normalized = current_request.strip()

    if not normalized:
        raise ValueError(
            "current_request cannot be blank."
        )

    return normalized


def observe_shadow_handoff(
    *,
    situation: TacticalSituation,
    action_evaluation: ShadowActionEvaluation,
    current_request: str,
    arguments: Mapping[str, Any],
    available_tool_names: Iterable[str],
    current_request_grounded: bool,
) -> ShadowHandoffObservation:
    """
    Observe frozen RAPHAEL-1F against one already-evaluated model proposal.

    No returned value from this function is an authorization decision for
    KUMA. The caller must not branch its live permission/execution behavior on
    this observation.
    """

    if not isinstance(
        situation,
        TacticalSituation,
    ):
        raise TypeError(
            "situation must be TacticalSituation."
        )

    if (
        situation.authority
        != SHADOW_HANDOFF_AUTHORITY_NONE
    ):
        raise ValueError(
            "TacticalSituation authority must remain NONE."
        )

    if not isinstance(
        action_evaluation,
        ShadowActionEvaluation,
    ):
        raise TypeError(
            "action_evaluation must be ShadowActionEvaluation."
        )

    if (
        action_evaluation.authority
        != SHADOW_HANDOFF_AUTHORITY_NONE
    ):
        raise ValueError(
            "ShadowActionEvaluation authority must remain NONE."
        )

    if type(
        current_request_grounded
    ) is not bool:
        raise TypeError(
            "current_request_grounded must be bool."
        )

    request = _normalized_request(
        current_request
    )

    digest = arguments_digest(
        arguments
    )

    if (
        digest
        != action_evaluation.arguments_digest
    ):
        return ShadowHandoffObservation(
            status=ShadowHandoffStatus.SKIPPED,
            tool_name=action_evaluation.tool_name,
            arguments_digest=digest,
            reason=(
                "The current normalized arguments no longer match the "
                "Integration-1B evaluation digest."
            ),
        )

    if (
        action_evaluation.status
        != ShadowActionStatus.EVALUATED
        or action_evaluation.candidate is None
        or action_evaluation.decision is None
    ):
        return ShadowHandoffObservation(
            status=ShadowHandoffStatus.SKIPPED,
            tool_name=action_evaluation.tool_name,
            arguments_digest=digest,
            reason=(
                "Integration-1B did not produce a complete tactical candidate "
                "and decision for bridge observation."
            ),
        )

    expected_tool = (
        action_evaluation.tool_name
    )

    expected_digest = digest
    expected_request = request
    grounded_result = (
        current_request_grounded
    )

    def bound_current_request_authorizer(
        callback_request: str,
        callback_tool_name: str,
        callback_arguments: dict[str, Any],
    ) -> bool:
        """
        Pure exact-binding adapter around KUMA's already-run grounding result.

        This cannot create dangerous approval. It can only return the captured
        grounding result when the bridge presents the exact same request,
        tool identity and argument digest.
        """

        try:
            return (
                grounded_result
                and callback_request
                == expected_request
                and callback_tool_name
                == expected_tool
                and arguments_digest(
                    callback_arguments
                )
                == expected_digest
            )
        except Exception:
            return False

    bridge = RaphaelExecutionBridge(
        capability_registry=(
            create_default_capability_registry()
        ),
        current_request_authorizer=(
            bound_current_request_authorizer
        ),
    )

    assessment = bridge.prepare(
        situation=situation,
        decision=action_evaluation.decision,
        candidate=action_evaluation.candidate,
        current_request=request,
        arguments=arguments,
        available_tool_names=available_tool_names,
    )

    return ShadowHandoffObservation(
        status=ShadowHandoffStatus.ASSESSED,
        tool_name=expected_tool,
        arguments_digest=digest,
        reason=(
            "Frozen RAPHAEL-1F assessed the Integration-1B proposal. "
            "The assessment is observational and cannot alter KUMA authority."
        ),
        assessment=assessment,
    )
