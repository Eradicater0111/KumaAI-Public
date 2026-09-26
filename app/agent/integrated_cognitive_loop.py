
"""
KUMA-INTEGRATION-1F — bounded integrated cognitive-loop adapter.

This adapter binds already-produced Integration-1A/1B state to frozen
RAPHAEL-1J attention and one frozen RAPHAEL-1K cognitive iteration.

It deliberately does not own KUMA's real loop. KumaAgent remains the caller and
the sole owner of model calls, grounding, permission, confirmation, execution,
verification, recovery, and request completion.

Pipeline:

    caller-owned WorldStateSnapshot/TacticalSituation
        + caller-owned ShadowActionEvaluation
        + caller-supplied RealtimeSignal snapshot
        + caller-owned TacticalLoopState
        -> frozen ProactiveAttentionEngine.decide(...)
        -> TacticalLoopFrame
        -> ContinuousTacticalLoop.evaluate_iteration(...)
        -> zero-authority observation + next caller-owned loop state
        -> STOP

Critical boundaries:

- LOOP ITERATION != EXECUTION
- ACTION_CANDIDATE != AUTHORIZATION
- WAIT_FOR_EVIDENCE != POLL
- BLOCKED != KUMA CONTROL-FLOW OVERRIDE
- ATTENTION != COMMAND
- COMPLETION != INFERRED FROM TOOL SUCCESS
- VERIFIED TOOL RESULT != VERIFIED OVERALL GOAL COMPLETION
- NEXT STATE != BACKGROUND SCHEDULER

This module never manufactures VerifiedLoopCompletion. Positive completion must
remain externally established by a later owner with a legitimate completion
contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable

from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
)
from app.agent.proactive_attention import (
    AttentionContext,
    AttentionCue,
    AttentionDecision,
    ProactiveAttentionEngine,
)
from app.agent.shadow_action_evaluation import (
    ShadowActionEvaluation,
    ShadowActionStatus,
)
from app.agent.shadow_cognition import (
    ShadowCognitionResult,
)
from app.agent.tactical_loop import (
    ContinuousTacticalLoop,
    TacticalLoopFrame,
    TacticalLoopIteration,
    TacticalLoopState,
    VerifiedLoopCompletion,
)
from app.realtime.change_detection import (
    RealtimeSignal,
)


INTEGRATED_LOOP_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

_MAX_TEXT_CHARS = 600
_MAX_EVENT_IDS = 32
_MAX_SIGNALS = 32


class IntegratedLoopStatus(str, Enum):
    OBSERVED = "observed"
    SKIPPED = "skipped"


def _bounded_text(
    value,
    *,
    limit: int = _MAX_TEXT_CHARS,
) -> str:
    if value is None:
        return ""

    text = " ".join(
        str(value).split()
    )

    return text[
        :limit
    ].rstrip()


def _event_ids(
    values: Iterable[str],
    *,
    field_name: str,
) -> tuple[str, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            f"{field_name} must be an iterable of event IDs."
        )

    try:
        items = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            f"{field_name} must be iterable."
        ) from error

    if len(items) > _MAX_EVENT_IDS:
        raise ValueError(
            f"{field_name} exceed the bounded item limit."
        )

    normalized = []

    for value in items:
        if type(value) is not str:
            raise TypeError(
                f"{field_name} values must be strings."
            )

        event_id = value.strip()

        if (
            len(event_id) != 64
            or any(
                character
                not in "0123456789abcdef"
                for character
                in event_id
            )
        ):
            raise ValueError(
                f"{field_name} values must be lowercase SHA-256 digests."
            )

        normalized.append(
            event_id
        )

    return tuple(
        dict.fromkeys(
            normalized
        )
    )


def _signals(
    values: Iterable[RealtimeSignal],
) -> tuple[RealtimeSignal, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            "signals must be an iterable of RealtimeSignal values."
        )

    try:
        items = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            "signals must be iterable."
        ) from error

    if len(items) > _MAX_SIGNALS:
        raise ValueError(
            "signals exceed the bounded integrated-loop limit."
        )

    for signal in items:
        if not isinstance(
            signal,
            RealtimeSignal,
        ):
            raise TypeError(
                "signals must contain RealtimeSignal values."
            )

        if signal.authority != INTEGRATED_LOOP_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeSignal authority must remain NONE."
            )

    return items


def _cues(
    values: Iterable[AttentionCue],
) -> tuple[AttentionCue, ...]:
    if isinstance(
        values,
        (
            str,
            bytes,
        ),
    ):
        raise TypeError(
            "cues must be an iterable of AttentionCue values."
        )

    try:
        items = tuple(
            values
        )
    except TypeError as error:
        raise TypeError(
            "cues must be iterable."
        ) from error

    for cue in items:
        if not isinstance(
            cue,
            AttentionCue,
        ):
            raise TypeError(
                "cues must contain AttentionCue values."
            )

        if cue.authority != INTEGRATED_LOOP_AUTHORITY_NONE:
            raise ValueError(
                "AttentionCue authority must remain NONE."
            )

    return items


@dataclass(
    frozen=True,
    slots=True,
)
class IntegratedLoopObservation:
    status: IntegratedLoopStatus
    reason: str
    next_state: TacticalLoopState
    attention_decision: AttentionDecision | None = None
    iteration: TacticalLoopIteration | None = None
    authority: str = field(
        default=INTEGRATED_LOOP_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.status,
            IntegratedLoopStatus,
        ):
            raise TypeError(
                "status must be IntegratedLoopStatus."
            )

        object.__setattr__(
            self,
            "reason",
            _bounded_text(
                self.reason
            ),
        )

        if not self.reason:
            raise ValueError(
                "reason cannot be blank."
            )

        if not isinstance(
            self.next_state,
            TacticalLoopState,
        ):
            raise TypeError(
                "next_state must be TacticalLoopState."
            )

        if (
            self.next_state.authority
            != INTEGRATED_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "next_state authority must remain NONE."
            )

        if (
            self.status
            == IntegratedLoopStatus.OBSERVED
        ):
            if not isinstance(
                self.attention_decision,
                AttentionDecision,
            ):
                raise TypeError(
                    "OBSERVED requires AttentionDecision."
                )

            if not isinstance(
                self.iteration,
                TacticalLoopIteration,
            ):
                raise TypeError(
                    "OBSERVED requires TacticalLoopIteration."
                )

            if (
                self.attention_decision.authority
                != INTEGRATED_LOOP_AUTHORITY_NONE
                or self.iteration.authority
                != INTEGRATED_LOOP_AUTHORITY_NONE
            ):
                raise ValueError(
                    "integrated loop observation must remain AUTHORITY:NONE."
                )

            if (
                self.iteration.next_state
                != self.next_state
            ):
                raise ValueError(
                    "next_state must match iteration.next_state."
                )

        else:
            if (
                self.attention_decision
                is not None
                or self.iteration
                is not None
            ):
                raise ValueError(
                    "SKIPPED cannot carry attention decision or iteration."
                )


def evaluate_integrated_loop_iteration(
    *,
    shadow_result: ShadowCognitionResult,
    action_evaluation: ShadowActionEvaluation,
    loop_state: TacticalLoopState,
    signals: Iterable[RealtimeSignal] = (),
    active_goal: str = "",
    remaining_objective: str = "",
    mission_status: str = "",
    seen_event_ids: Iterable[str] = (),
    acknowledged_event_ids: Iterable[str] = (),
    cues: Iterable[AttentionCue] = (),
    current_time: datetime | None = None,
) -> IntegratedLoopObservation:
    """
    Evaluate exactly one zero-authority RAPHAEL-1K cognitive iteration.

    KUMA remains the owner of the real control loop. The returned disposition is
    advisory cognition only and must not be treated as permission, confirmation,
    execution authority, retry authority, or verified completion.
    """

    if not isinstance(
        shadow_result,
        ShadowCognitionResult,
    ):
        raise TypeError(
            "shadow_result must be ShadowCognitionResult."
        )

    if (
        shadow_result.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
        or shadow_result.snapshot.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
        or shadow_result.situation.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
    ):
        raise ValueError(
            "shadow cognition authority must remain NONE."
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
        != INTEGRATED_LOOP_AUTHORITY_NONE
    ):
        raise ValueError(
            "action_evaluation authority must remain NONE."
        )

    if not isinstance(
        loop_state,
        TacticalLoopState,
    ):
        raise TypeError(
            "loop_state must be TacticalLoopState."
        )

    if (
        loop_state.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
    ):
        raise ValueError(
            "loop_state authority must remain NONE."
        )

    if (
        action_evaluation.status
        != ShadowActionStatus.EVALUATED
        or action_evaluation.candidate
        is None
        or action_evaluation.decision
        is None
    ):
        return IntegratedLoopObservation(
            status=IntegratedLoopStatus.SKIPPED,
            reason=(
                "Live shadow action evaluation does not contain a complete "
                "candidate/decision pair for a frozen tactical-loop frame."
            ),
            next_state=loop_state,
        )

    supplied_signals = _signals(
        signals
    )

    seen = _event_ids(
        seen_event_ids,
        field_name="seen_event_ids",
    )

    acknowledged = _event_ids(
        acknowledged_event_ids,
        field_name="acknowledged_event_ids",
    )

    supplied_cues = _cues(
        cues
    )

    if current_time is None:
        now = datetime.now(
            timezone.utc
        )
    else:
        if not isinstance(
            current_time,
            datetime,
        ):
            raise TypeError(
                "current_time must be datetime or None."
            )

        if (
            current_time.tzinfo is None
            or current_time.utcoffset()
            is None
        ):
            raise ValueError(
                "current_time must be timezone-aware."
            )

        now = current_time.astimezone(
            timezone.utc
        )

    context = AttentionContext(
        current_time=now,
        active_goal=_bounded_text(
            active_goal
        ),
        remaining_objective=_bounded_text(
            remaining_objective
        ),
        mission_status=_bounded_text(
            mission_status
        ),
        seen_event_ids=seen,
        acknowledged_event_ids=acknowledged,
        cues=supplied_cues,
    )

    attention_decision = (
        ProactiveAttentionEngine().decide(
            supplied_signals,
            context,
        )
    )

    if (
        attention_decision.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
    ):
        raise ValueError(
            "attention_decision authority must remain NONE."
        )

    tactical_option = (
        action_evaluation.candidate.option
    )

    frame = TacticalLoopFrame(
        world_state=(
            shadow_result.snapshot
        ),
        situation=(
            shadow_result.situation
        ),
        candidate_options=(
            tactical_option,
        ),
        tactical_decision=(
            action_evaluation.decision
        ),
        attention_decision=(
            attention_decision
        ),
        completion=(
            VerifiedLoopCompletion()
        ),
    )

    iteration = (
        ContinuousTacticalLoop().evaluate_iteration(
            frame,
            loop_state,
        )
    )

    if (
        iteration.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
        or iteration.next_state.authority
        != INTEGRATED_LOOP_AUTHORITY_NONE
    ):
        raise ValueError(
            "tactical-loop iteration authority must remain NONE."
        )

    if (
        iteration.frame.completion.verified_complete
    ):
        raise RuntimeError(
            "Integration-1F must not manufacture verified completion."
        )

    return IntegratedLoopObservation(
        status=IntegratedLoopStatus.OBSERVED,
        reason=iteration.reason,
        next_state=iteration.next_state,
        attention_decision=attention_decision,
        iteration=iteration,
    )
