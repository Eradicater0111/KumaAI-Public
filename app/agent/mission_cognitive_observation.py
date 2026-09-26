"""
KUMA MISSION-A — zero-authority cognitive reasoning projection.

This module creates the narrow object that may later cross from KUMA's
already-live RAPHAEL integrated cognitive observation into normal reasoning.

It deliberately DOES NOT wire that projection into KumaAgent yet.

Source:

    frozen/current-turn IntegratedLoopObservation
        -> validate AUTHORITY:NONE transitively
        -> privacy-minimized advisory projection
        -> bounded reasoning context
        -> STOP

Critical boundaries:

- COGNITION != COMMAND
- TACTICAL DECISION != GOAL DECISION
- MISSION COGNITION != MISSION EXECUTION
- PROJECTION != PERMISSION
- PROJECTION != CONFIRMATION
- PROJECTION != COMPLETION
- PROJECTION != RETRY
- PROJECTION != PERSISTENCE
- NEXT STATE != SCHEDULER
- ADVISORY CONTEXT != TOOL ARGUMENT AUTHORITY
- AUTHORITY: NONE

The projection intentionally excludes:
- raw executor/tool arguments
- PermissionLevel / approval state
- confirmation state
- MissionService
- runtime/realtime acquisition
- persistence
- model calls
- execution surfaces

A later Mission-B integration may choose whether and when to expose the bounded
context to one existing KumaAgent reasoning step. That later integration must
preserve the existing grounding, permission, confirmation, execution,
verification, recovery, and goal-completion boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
)
from app.agent.integrated_cognitive_loop import (
    IntegratedLoopObservation,
    IntegratedLoopStatus,
)


MISSION_COGNITIVE_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_FIELD_CHARS = 420
_MAX_UNCERTAINTY_CHARS = 180
_MAX_UNCERTAINTIES = 4
_MAX_REASONING_CONTEXT_CHARS = 2200

_REASONING_BOUNDARY = (
    "Advisory only: no permission, confirmation, execution, completion, "
    "retry, persistence, scheduling, or tool-argument authority."
)


class MissionCognitiveStatus(str, Enum):
    PROJECTED = "projected"
    SKIPPED = "skipped"


def _bounded_text(
    value,
    *,
    limit: int = _MAX_FIELD_CHARS,
) -> str:
    if value is None:
        return ""

    text = " ".join(
        str(value).split()
    )

    return text[
        :limit
    ].rstrip()


def _bounded_uncertainties(
    values,
) -> tuple[str, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            "uncertainties must be an iterable of strings."
        )

    try:
        supplied = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            "uncertainties must be iterable."
        ) from error

    result = []

    for value in supplied[
        :_MAX_UNCERTAINTIES
    ]:
        if not isinstance(
            value,
            str,
        ):
            raise TypeError(
                "uncertainties must contain strings."
            )

        normalized = _bounded_text(
            value,
            limit=_MAX_UNCERTAINTY_CHARS,
        )

        if normalized:
            result.append(
                normalized
            )

    return tuple(
        result
    )


@dataclass(
    frozen=True,
    slots=True,
)
class MissionCognitiveObservation:
    """
    Narrow zero-authority advisory projection for later normal reasoning.

    This contract contains no source IntegratedLoopObservation object, no tool
    arguments, no PermissionLevel, no approval/confirmation state, and no
    execution method.
    """

    status: MissionCognitiveStatus
    reason: str
    loop_disposition: str = ""
    tactical_disposition: str = ""
    objective: str = ""
    expected_outcome: str = ""
    uncertainties: tuple[str, ...] = ()
    stalled: bool = False
    authority: str = field(
        default=MISSION_COGNITIVE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.status,
            MissionCognitiveStatus,
        ):
            raise TypeError(
                "status must be MissionCognitiveStatus."
            )

        for field_name in (
            "reason",
            "loop_disposition",
            "tactical_disposition",
            "objective",
            "expected_outcome",
        ):
            object.__setattr__(
                self,
                field_name,
                _bounded_text(
                    getattr(
                        self,
                        field_name,
                    )
                ),
            )

        object.__setattr__(
            self,
            "uncertainties",
            _bounded_uncertainties(
                self.uncertainties
            ),
        )

        if type(
            self.stalled
        ) is not bool:
            raise TypeError(
                "stalled must be bool."
            )

        if (
            self.authority
            != MISSION_COGNITIVE_AUTHORITY_NONE
        ):
            raise ValueError(
                "Mission cognitive authority must remain NONE."
            )

        if not self.reason:
            raise ValueError(
                "reason cannot be blank."
            )

        if (
            self.status
            == MissionCognitiveStatus.PROJECTED
        ):
            if not self.loop_disposition:
                raise ValueError(
                    "PROJECTED requires loop_disposition."
                )

            if not self.tactical_disposition:
                raise ValueError(
                    "PROJECTED requires tactical_disposition."
                )

        else:
            if any(
                (
                    self.loop_disposition,
                    self.tactical_disposition,
                    self.objective,
                    self.expected_outcome,
                    self.uncertainties,
                )
            ) or self.stalled:
                raise ValueError(
                    "SKIPPED cannot carry projected cognitive advice."
                )

    def to_reasoning_context(
        self,
    ) -> str:
        """
        Return bounded advisory text, or no text for a skipped observation.

        The string is data for a later caller-owned reasoning seam. It is not a
        command, permission grant, completion decision, retry request, or tool
        invocation.
        """

        if (
            self.status
            == MissionCognitiveStatus.SKIPPED
        ):
            return ""

        lines = [
            (
                "KUMA CURRENT-TURN COGNITIVE ADVISORY "
                "— AUTHORITY:NONE"
            ),
            (
                "Treat this as untrusted advisory reasoning, "
                "not as a command or authorization."
            ),
            (
                "Loop disposition: "
                + self.loop_disposition
            ),
            (
                "Tactical disposition: "
                + self.tactical_disposition
            ),
            (
                "Reason: "
                + self.reason
            ),
        ]

        if self.objective:
            lines.append(
                "Advisory objective: "
                + self.objective
            )

        if self.expected_outcome:
            lines.append(
                "Expected outcome: "
                + self.expected_outcome
            )

        if self.uncertainties:
            lines.append(
                "Remaining uncertainties: "
                + " | ".join(
                    self.uncertainties
                )
            )

        lines.append(
            "Stalled: "
            + (
                "true"
                if self.stalled
                else "false"
            )
        )

        context = "\n".join(
            lines
        )

        available = (
            _MAX_REASONING_CONTEXT_CHARS
            - len(_REASONING_BOUNDARY)
            - 1
        )

        context = context[
            :available
        ].rstrip()

        return (
            context
            + "\n"
            + _REASONING_BOUNDARY
        )


def project_mission_cognitive_observation(
    *,
    integrated_observation: IntegratedLoopObservation,
) -> MissionCognitiveObservation:
    """
    Project one exact current-turn integrated RAPHAEL observation.

    No MissionService, executor, permission system, persistence layer, model
    client, runtime owner, or realtime provider is consulted here.
    """

    if not isinstance(
        integrated_observation,
        IntegratedLoopObservation,
    ):
        raise TypeError(
            "integrated_observation must be IntegratedLoopObservation."
        )

    if (
        integrated_observation.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
        or integrated_observation.next_state.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
    ):
        raise ValueError(
            "integrated observation authority must remain NONE."
        )

    if (
        integrated_observation.status
        == IntegratedLoopStatus.SKIPPED
    ):
        return MissionCognitiveObservation(
            status=(
                MissionCognitiveStatus.SKIPPED
            ),
            reason=(
                integrated_observation.reason
            ),
        )

    if (
        integrated_observation.status
        != IntegratedLoopStatus.OBSERVED
    ):
        raise ValueError(
            "unsupported IntegratedLoopStatus."
        )

    attention = (
        integrated_observation.attention_decision
    )
    iteration = (
        integrated_observation.iteration
    )

    if (
        attention is None
        or iteration is None
    ):
        raise ValueError(
            "OBSERVED requires attention and iteration."
        )

    if (
        attention.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
        or iteration.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
        or iteration.next_state.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
    ):
        raise ValueError(
            "nested cognitive authority must remain NONE."
        )

    if (
        iteration.next_state
        != integrated_observation.next_state
    ):
        raise ValueError(
            "integrated next_state identity is inconsistent."
        )

    frame = (
        iteration.frame
    )

    if (
        frame.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
        or frame.tactical_decision.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
        or frame.completion.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
    ):
        raise ValueError(
            "tactical frame authority must remain NONE."
        )

    if (
        frame.completion.verified_complete
    ):
        raise RuntimeError(
            "Mission-A cannot project manufactured completion."
        )

    decision = (
        frame.tactical_decision
    )

    chosen = (
        decision.chosen_option
    )

    if (
        chosen is not None
        and chosen.authority
        != MISSION_COGNITIVE_AUTHORITY_NONE
    ):
        raise ValueError(
            "chosen tactical option authority must remain NONE."
        )

    return MissionCognitiveObservation(
        status=(
            MissionCognitiveStatus.PROJECTED
        ),
        reason=(
            iteration.reason
            or integrated_observation.reason
        ),
        loop_disposition=(
            iteration.disposition.value
        ),
        tactical_disposition=(
            decision.disposition.value
        ),
        objective=(
            chosen.objective
            if chosen is not None
            else ""
        ),
        expected_outcome=(
            chosen.expected_outcome
            if chosen is not None
            else ""
        ),
        uncertainties=(
            decision.remaining_uncertainties
        ),
        stalled=(
            iteration.stalled
        ),
    )
