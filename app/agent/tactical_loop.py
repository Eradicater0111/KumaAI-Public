"""
KUMA RAPHAEL-1K bounded continuous tactical loop.

RAPHAEL-1K composes already-produced, immutable RAPHAEL cognitive outputs into
one bounded loop iteration. It is deliberately NOT a background loop.

The caller owns evidence collection and invokes one iteration at a time:

    WorldStateSnapshot
            +
    TacticalSituation
            +
    candidate TacticalOption values
            +
    TacticalDecision
            +
    AttentionDecision
            +
    caller-owned TacticalLoopState
            ↓
    ContinuousTacticalLoop.evaluate_iteration(...)
            ↓
    TacticalLoopIteration
    AUTHORITY:NONE
            ↓
    STOP

RAPHAEL-1K does not call WorldModelBuilder, TacticalAnalyzer,
TacticalOptionGenerator, TacticalDecisionEngine, ProactiveAttentionEngine, or
RaphaelExecutionBridge. Those phases remain independently testable and their
owners decide when to produce fresh evidence.

Critical invariants:

- CONTINUOUS != UNBOUNDED
- LOOP != BACKGROUND THREAD
- ITERATION != EXECUTION
- ACTION_CANDIDATE != AUTHORIZATION
- ATTENTION != COMMAND
- STALL != PERMISSION TO TRY SOMETHING
- REASONING PROGRESS != REAL-WORLD PROGRESS
- WAIT_FOR_EVIDENCE != POLL FOR EVIDENCE
- COMPLETE requires caller-supplied verified completion evidence
- MAXIMUM CONFIDENCE + MAXIMUM ATTENTION = AUTHORITY:NONE

Anti-livelock is deterministic and state-explicit:

- first observation of a cognitive state: repeat count 0;
- first identical repeat: repeat count 1, normal disposition preserved;
- second identical repeat: WAIT_FOR_EVIDENCE;
- third identical repeat: BLOCKED;
- a changed cognitive state resets the repeat count;
- a hard iteration budget prevents endless caller-driven reasoning.

No permission, confirmation, handoff preparation, tool invocation, provider
refresh, notification, persistence, model call, or runtime mutation occurs
here.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
    fields,
    is_dataclass,
)
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
from typing import Any

from app.agent.cognitive_contracts import (
    COGNITIVE_AUTHORITY_NONE,
    TacticalDecision,
    TacticalDisposition,
    TacticalOption,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.proactive_attention import (
    AttentionDecision,
    AttentionDisposition,
)


TACTICAL_LOOP_AUTHORITY_NONE = (
    COGNITIVE_AUTHORITY_NONE
)

WAIT_REPEAT_THRESHOLD = 2
BLOCK_REPEAT_THRESHOLD = 3
MAX_LOOP_ITERATIONS = 32
_MAX_TEXT_CHARS = 1200
_MAX_CANDIDATES = 64


class LoopDisposition(str, Enum):
    CONTINUE_REASONING = "continue_reasoning"
    WAIT_FOR_EVIDENCE = "wait_for_evidence"
    SURFACE_ADVICE = "surface_advice"
    ACTION_CANDIDATE = "action_candidate"
    COMPLETE = "complete"
    BLOCKED = "blocked"


def _text(
    value,
    *,
    field_name: str,
    allow_empty: bool = False,
) -> str:
    if type(value) is not str:
        raise TypeError(
            f"{field_name} must be a string."
        )

    normalized = " ".join(
        value.split()
    )

    if (
        not allow_empty
        and not normalized
    ):
        raise ValueError(
            f"{field_name} cannot be empty."
        )

    if len(normalized) > _MAX_TEXT_CHARS:
        raise ValueError(
            f"{field_name} exceeds the bounded text limit."
        )

    return normalized


def _sha256_hex(
    value: str,
) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(
            character
            in "0123456789abcdef"
            for character
            in value
        )
    )


def _bounded_nonnegative_int(
    value,
    *,
    field_name: str,
    maximum: int,
) -> int:
    if (
        type(value) is not int
        or value < 0
        or value > maximum
    ):
        raise ValueError(
            f"{field_name} must be an integer between 0 and {maximum}."
        )

    return value


def _canonicalize(
    value: Any,
):
    """
    Convert frozen RAPHAEL contracts into deterministic JSON-safe data.

    Unsupported object types fail closed rather than falling back to repr(),
    which could hide process-specific or mutable state.
    """

    if value is None:
        return None

    if type(value) in (
        str,
        bool,
        int,
    ):
        return value

    if type(value) is float:
        if not math.isfinite(
            value
        ):
            raise ValueError(
                "non-finite float cannot be digested."
            )

        return value

    if isinstance(
        value,
        datetime,
    ):
        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        ).isoformat()

    if isinstance(
        value,
        Enum,
    ):
        return {
            "__enum__": (
                f"{value.__class__.__module__}."
                f"{value.__class__.__qualname__}"
            ),
            "value": _canonicalize(
                value.value
            ),
        }

    if is_dataclass(
        value
    ):
        return {
            "__dataclass__": (
                f"{value.__class__.__module__}."
                f"{value.__class__.__qualname__}"
            ),
            "fields": {
                item.name: _canonicalize(
                    getattr(
                        value,
                        item.name,
                    )
                )
                for item
                in fields(
                    value
                )
            },
        }

    if isinstance(
        value,
        (
            tuple,
            list,
        ),
    ):
        return [
            _canonicalize(
                item
            )
            for item
            in value
        ]

    if isinstance(
        value,
        dict,
    ):
        if any(
            type(key) is not str
            for key
            in value
        ):
            raise TypeError(
                "digest dictionaries must have string keys."
            )

        return {
            key: _canonicalize(
                value[
                    key
                ]
            )
            for key
            in sorted(
                value
            )
        }

    raise TypeError(
        "unsupported value in deterministic tactical-loop digest: "
        f"{type(value).__name__}"
    )


def _digest(
    value: Any,
) -> str:
    encoded = json.dumps(
        _canonicalize(
            value
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    return hashlib.sha256(
        encoded
    ).hexdigest()


@dataclass(
    frozen=True,
    slots=True,
)
class VerifiedLoopCompletion:
    """
    Caller-supplied verified completion evidence.

    This contract does not perform verification itself. A positive COMPLETE
    classification requires an explicit SHA-256 evidence binding supplied by
    the verification owner.
    """

    verified_complete: bool = False
    evidence_digest: str = ""
    reason: str = ""
    authority: str = field(
        default=TACTICAL_LOOP_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if type(
            self.verified_complete
        ) is not bool:
            raise TypeError(
                "verified_complete must be bool."
            )

        object.__setattr__(
            self,
            "evidence_digest",
            _text(
                self.evidence_digest,
                field_name="evidence_digest",
                allow_empty=True,
            ),
        )

        object.__setattr__(
            self,
            "reason",
            _text(
                self.reason,
                field_name="reason",
                allow_empty=True,
            ),
        )

        if self.verified_complete:
            if not _sha256_hex(
                self.evidence_digest
            ):
                raise ValueError(
                    "verified completion requires a lowercase SHA-256 "
                    "evidence digest."
                )

            if not self.reason:
                raise ValueError(
                    "verified completion requires a reason."
                )

        elif self.evidence_digest:
            raise ValueError(
                "non-complete evidence cannot carry a completion digest."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class TacticalLoopState:
    """
    Caller-owned immutable anti-livelock state.

    RAPHAEL-1K does not persist or mutate this state. The returned
    TacticalLoopIteration contains the next immutable state for a later caller
    invocation.
    """

    iterations_seen: int = 0
    previous_cognitive_digest: str = ""
    repeated_state_count: int = 0
    authority: str = field(
        default=TACTICAL_LOOP_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "iterations_seen",
            _bounded_nonnegative_int(
                self.iterations_seen,
                field_name="iterations_seen",
                maximum=MAX_LOOP_ITERATIONS,
            ),
        )

        object.__setattr__(
            self,
            "repeated_state_count",
            _bounded_nonnegative_int(
                self.repeated_state_count,
                field_name="repeated_state_count",
                maximum=BLOCK_REPEAT_THRESHOLD,
            ),
        )

        object.__setattr__(
            self,
            "previous_cognitive_digest",
            _text(
                self.previous_cognitive_digest,
                field_name="previous_cognitive_digest",
                allow_empty=True,
            ),
        )

        if (
            self.previous_cognitive_digest
            and not _sha256_hex(
                self.previous_cognitive_digest
            )
        ):
            raise ValueError(
                "previous_cognitive_digest must be a lowercase SHA-256 digest."
            )

        if self.iterations_seen == 0:
            if self.previous_cognitive_digest:
                raise ValueError(
                    "initial TacticalLoopState cannot carry a previous digest."
                )

            if self.repeated_state_count != 0:
                raise ValueError(
                    "initial TacticalLoopState repeat count must be zero."
                )

        else:
            if not self.previous_cognitive_digest:
                raise ValueError(
                    "non-initial TacticalLoopState requires previous digest."
                )

            if (
                self.repeated_state_count
                > self.iterations_seen - 1
            ):
                raise ValueError(
                    "repeated_state_count cannot exceed prior iteration history."
                )


@dataclass(
    frozen=True,
    slots=True,
)
class TacticalLoopFrame:
    """
    One immutable set of already-produced RAPHAEL cognitive outputs.

    candidate_options are the plain TacticalOption contracts represented by the
    option-generation/decision path. RAPHAEL-1K does not run simulation or
    regenerate them.
    """

    world_state: WorldStateSnapshot
    situation: TacticalSituation
    candidate_options: tuple[
        TacticalOption,
        ...,
    ]
    tactical_decision: TacticalDecision
    attention_decision: AttentionDecision
    completion: VerifiedLoopCompletion = field(
        default_factory=VerifiedLoopCompletion
    )
    authority: str = field(
        default=TACTICAL_LOOP_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.world_state,
            WorldStateSnapshot,
        ):
            raise TypeError(
                "world_state must be WorldStateSnapshot."
            )

        if (
            self.world_state.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "WorldStateSnapshot authority must remain NONE."
            )

        if not isinstance(
            self.situation,
            TacticalSituation,
        ):
            raise TypeError(
                "situation must be TacticalSituation."
            )

        if (
            self.situation.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalSituation authority must remain NONE."
            )

        if (
            self.situation.world_state
            != self.world_state
        ):
            raise ValueError(
                "TacticalSituation must remain bound to the supplied "
                "WorldStateSnapshot."
            )

        if (
            self.world_state.task_goal is not None
            and self.situation.goal
            != self.world_state.task_goal
        ):
            raise ValueError(
                "TacticalSituation goal must match WorldStateSnapshot task_goal."
            )

        if isinstance(
            self.candidate_options,
            (
                str,
                bytes,
            ),
        ):
            raise TypeError(
                "candidate_options must be an iterable of TacticalOption values."
            )

        try:
            candidates = tuple(
                self.candidate_options
            )
        except TypeError as error:
            raise TypeError(
                "candidate_options must be iterable."
            ) from error

        if len(
            candidates
        ) > _MAX_CANDIDATES:
            raise ValueError(
                "candidate_options exceed the bounded candidate limit."
            )

        ids = []

        for option in candidates:
            if not isinstance(
                option,
                TacticalOption,
            ):
                raise TypeError(
                    "candidate_options must contain TacticalOption values."
                )

            if (
                option.authority
                != TACTICAL_LOOP_AUTHORITY_NONE
            ):
                raise ValueError(
                    "candidate TacticalOption authority must remain NONE."
                )

            ids.append(
                option.option_id
            )

        if len(
            ids
        ) != len(
            set(
                ids
            )
        ):
            raise ValueError(
                "candidate_options cannot contain duplicate option IDs."
            )

        candidates = tuple(
            sorted(
                candidates,
                key=lambda option: (
                    option.option_id
                ),
            )
        )

        object.__setattr__(
            self,
            "candidate_options",
            candidates,
        )

        if not isinstance(
            self.tactical_decision,
            TacticalDecision,
        ):
            raise TypeError(
                "tactical_decision must be TacticalDecision."
            )

        if (
            self.tactical_decision.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalDecision authority must remain NONE."
            )

        chosen = (
            self.tactical_decision.chosen_option
        )

        if (
            chosen is not None
            and chosen.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "chosen TacticalOption authority must remain NONE."
            )

        by_id = {
            option.option_id: option
            for option
            in candidates
        }

        if chosen is not None:
            candidate = by_id.get(
                chosen.option_id
            )

            if candidate != chosen:
                raise ValueError(
                    "TacticalDecision chosen option must be present exactly "
                    "in candidate_options."
                )

        for rejected in (
            self.tactical_decision.rejected_options
        ):
            if (
                rejected.authority
                != TACTICAL_LOOP_AUTHORITY_NONE
            ):
                raise ValueError(
                    "rejected TacticalOption authority must remain NONE."
                )

            candidate = by_id.get(
                rejected.option_id
            )

            if candidate != rejected:
                raise ValueError(
                    "TacticalDecision rejected options must be present exactly "
                    "in candidate_options."
                )

        if (
            self.tactical_decision.disposition
            == TacticalDisposition.ACTION_CANDIDATE
            and chosen is None
        ):
            raise ValueError(
                "ACTION_CANDIDATE requires a chosen TacticalOption."
            )

        if (
            self.tactical_decision.disposition
            == TacticalDisposition.BLOCKED
            and chosen is not None
        ):
            raise ValueError(
                "BLOCKED TacticalDecision cannot carry a chosen option."
            )

        if not isinstance(
            self.attention_decision,
            AttentionDecision,
        ):
            raise TypeError(
                "attention_decision must be AttentionDecision."
            )

        if (
            self.attention_decision.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "AttentionDecision authority must remain NONE."
            )

        if (
            self.attention_decision.selected_event
            is not None
            and self.attention_decision.selected_event.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "selected ProactiveEvent authority must remain NONE."
            )

        for assessment in (
            self.attention_decision.ranked_assessments
        ):
            if (
                assessment.authority
                != TACTICAL_LOOP_AUTHORITY_NONE
            ):
                raise ValueError(
                    "AttentionAssessment authority must remain NONE."
                )

        if not isinstance(
            self.completion,
            VerifiedLoopCompletion,
        ):
            raise TypeError(
                "completion must be VerifiedLoopCompletion."
            )

        if (
            self.completion.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "VerifiedLoopCompletion authority must remain NONE."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class TacticalLoopIteration:
    """
    Immutable result of exactly one bounded cognitive iteration.

    ACTION_CANDIDATE is still only a cognitive classification. This result has
    no permission, approval, confirmation, handoff, tool argument, execution,
    notification, or persistence surface.
    """

    iteration_number: int
    disposition: LoopDisposition
    reason: str
    frame: TacticalLoopFrame
    cognitive_digest: str
    iteration_digest: str
    repeated_state_count: int
    stalled: bool
    next_state: TacticalLoopState
    authority: str = field(
        default=TACTICAL_LOOP_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if (
            type(
                self.iteration_number
            ) is not int
            or self.iteration_number < 1
        ):
            raise ValueError(
                "iteration_number must be a positive integer."
            )

        if not isinstance(
            self.disposition,
            LoopDisposition,
        ):
            raise TypeError(
                "disposition must be LoopDisposition."
            )

        object.__setattr__(
            self,
            "reason",
            _text(
                self.reason,
                field_name="reason",
            ),
        )

        if not isinstance(
            self.frame,
            TacticalLoopFrame,
        ):
            raise TypeError(
                "frame must be TacticalLoopFrame."
            )

        if (
            self.frame.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalLoopFrame authority must remain NONE."
            )

        for field_name in (
            "cognitive_digest",
            "iteration_digest",
        ):
            value = getattr(
                self,
                field_name,
            )

            if not _sha256_hex(
                value
            ):
                raise ValueError(
                    f"{field_name} must be a lowercase SHA-256 digest."
                )

        object.__setattr__(
            self,
            "repeated_state_count",
            _bounded_nonnegative_int(
                self.repeated_state_count,
                field_name="repeated_state_count",
                maximum=BLOCK_REPEAT_THRESHOLD,
            ),
        )

        if type(
            self.stalled
        ) is not bool:
            raise TypeError(
                "stalled must be bool."
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
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "next TacticalLoopState authority must remain NONE."
            )

        expected_stalled = (
            self.repeated_state_count
            >= WAIT_REPEAT_THRESHOLD
        )

        if (
            self.stalled
            != expected_stalled
        ):
            raise ValueError(
                "stalled must reflect the repeat threshold."
            )


def cognitive_state_digest(
    frame: TacticalLoopFrame,
) -> str:
    """
    Digest the bounded cognitive state used for anti-livelock comparison.

    Completion evidence is intentionally excluded. It is external verified
    progress evidence and has its own binding in the iteration digest.
    """

    if not isinstance(
        frame,
        TacticalLoopFrame,
    ):
        raise TypeError(
            "frame must be TacticalLoopFrame."
        )

    return _digest(
        {
            "world_state": frame.world_state,
            "situation": frame.situation,
            "candidate_options": (
                frame.candidate_options
            ),
            "tactical_decision": (
                frame.tactical_decision
            ),
            "attention_decision": (
                frame.attention_decision
            ),
        }
    )


def _base_disposition(
    frame: TacticalLoopFrame,
) -> tuple[
    LoopDisposition,
    str,
]:
    tactical = (
        frame.tactical_decision
    )

    attention = (
        frame.attention_decision
    )

    if (
        tactical.disposition
        == TacticalDisposition.ACTION_CANDIDATE
    ):
        return (
            LoopDisposition.ACTION_CANDIDATE,
            (
                "The frozen tactical decision contains one grounded action "
                "candidate. RAPHAEL-1K forwards only the cognitive "
                "classification; authorization and execution remain downstream."
            ),
        )

    if (
        tactical.disposition
        == TacticalDisposition.BLOCKED
    ):
        return (
            LoopDisposition.BLOCKED,
            (
                "The frozen tactical decision is BLOCKED. The loop cannot "
                "invent evidence, capabilities, permission, or an alternative "
                "action."
            ),
        )

    attention_surface = (
        attention.disposition
        in (
            AttentionDisposition.SURFACE,
            AttentionDisposition.ESCALATE_ATTENTION,
        )
    )

    if (
        tactical.disposition
        == TacticalDisposition.ADVISE
    ):
        if (
            tactical.chosen_option is None
            and not attention_surface
        ):
            return (
                LoopDisposition.CONTINUE_REASONING,
                (
                    "The tactical layer advises without a chosen option and "
                    "proactive attention does not require surfacing. One later "
                    "caller-driven reasoning iteration may use fresh evidence."
                ),
            )

        return (
            LoopDisposition.SURFACE_ADVICE,
            (
                "The frozen tactical/attention outputs merit cognitive advice "
                "surfacing. RAPHAEL-1K itself performs no user notification."
            ),
        )

    if (
        tactical.disposition
        == TacticalDisposition.DEFER
    ):
        if attention_surface:
            return (
                LoopDisposition.SURFACE_ADVICE,
                (
                    "Tactical action is deferred, but an existing proactive "
                    "attention decision merits cognitive surfacing. No side "
                    "effect occurs in RAPHAEL-1K."
                ),
            )

        return (
            LoopDisposition.WAIT_FOR_EVIDENCE,
            (
                "The tactical decision is deferred and no proactive attention "
                "signal requires surfacing. Fresh external evidence is needed "
                "before another useful reasoning step."
            ),
        )

    return (
        LoopDisposition.CONTINUE_REASONING,
        (
            "No terminal or externally actionable cognitive classification "
            "was produced. A later caller may supply fresh evidence for another "
            "bounded iteration."
        ),
    )


class ContinuousTacticalLoop:
    """
    Stateless one-iteration tactical loop evaluator.

    Despite the name, this class contains no internal unbounded loop. The
    caller explicitly carries TacticalLoopState between invocations.
    """

    __slots__ = ()

    def evaluate_iteration(
        self,
        frame: TacticalLoopFrame,
        state: TacticalLoopState,
    ) -> TacticalLoopIteration:
        if not isinstance(
            frame,
            TacticalLoopFrame,
        ):
            raise TypeError(
                "frame must be TacticalLoopFrame."
            )

        if (
            frame.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalLoopFrame authority must remain NONE."
            )

        if not isinstance(
            state,
            TacticalLoopState,
        ):
            raise TypeError(
                "state must be TacticalLoopState."
            )

        if (
            state.authority
            != TACTICAL_LOOP_AUTHORITY_NONE
        ):
            raise ValueError(
                "TacticalLoopState authority must remain NONE."
            )

        cognitive_digest = (
            cognitive_state_digest(
                frame
            )
        )

        repeated = (
            state.iterations_seen > 0
            and state.previous_cognitive_digest
            == cognitive_digest
        )

        if repeated:
            repeat_count = min(
                BLOCK_REPEAT_THRESHOLD,
                state.repeated_state_count
                + 1,
            )
        else:
            repeat_count = 0

        budget_exhausted = (
            state.iterations_seen
            >= MAX_LOOP_ITERATIONS
        )

        if budget_exhausted:
            next_state = state
        else:
            next_state = (
                TacticalLoopState(
                    iterations_seen=(
                        state.iterations_seen
                        + 1
                    ),
                    previous_cognitive_digest=(
                        cognitive_digest
                    ),
                    repeated_state_count=(
                        repeat_count
                    ),
                )
            )

        if (
            frame.completion.verified_complete
        ):
            disposition = (
                LoopDisposition.COMPLETE
            )

            reason = (
                "Caller-supplied verified completion evidence marks the "
                "objective complete. RAPHAEL-1K stops reasoning without "
                "claiming that it performed the verification."
            )

        elif (
            frame.tactical_decision.disposition
            == TacticalDisposition.BLOCKED
        ):
            disposition = (
                LoopDisposition.BLOCKED
            )

            reason = (
                "The tactical decision is BLOCKED. Attention priority cannot "
                "override the tactical block or create action authority."
            )

        elif budget_exhausted:
            disposition = (
                LoopDisposition.BLOCKED
            )

            reason = (
                "The bounded tactical-loop iteration budget is exhausted. "
                "Further self-reasoning is blocked until an external owner "
                "starts a new bounded state with fresh evidence."
            )

        elif (
            repeat_count
            >= BLOCK_REPEAT_THRESHOLD
        ):
            disposition = (
                LoopDisposition.BLOCKED
            )

            reason = (
                "The same bounded cognitive state repeated through the "
                "anti-livelock budget. RAPHAEL-1K blocks instead of trying "
                "another action or manufacturing progress."
            )

        elif (
            repeat_count
            >= WAIT_REPEAT_THRESHOLD
        ):
            disposition = (
                LoopDisposition.WAIT_FOR_EVIDENCE
            )

            reason = (
                "The same bounded cognitive state repeated without new "
                "evidence. RAPHAEL-1K waits for externally supplied evidence "
                "rather than continuing self-reasoning."
            )

        else:
            (
                disposition,
                reason,
            ) = _base_disposition(
                frame
            )

        stalled = (
            repeat_count
            >= WAIT_REPEAT_THRESHOLD
        )

        iteration_number = (
            state.iterations_seen
            + 1
        )

        iteration_digest = _digest(
            {
                "iteration_number": (
                    iteration_number
                ),
                "cognitive_digest": (
                    cognitive_digest
                ),
                "previous_state": (
                    state
                ),
                "next_state": (
                    next_state
                ),
                "completion": (
                    frame.completion
                ),
                "disposition": (
                    disposition
                ),
                "reason": reason,
                "repeat_count": (
                    repeat_count
                ),
            }
        )

        return TacticalLoopIteration(
            iteration_number=(
                iteration_number
            ),
            disposition=disposition,
            reason=reason,
            frame=frame,
            cognitive_digest=(
                cognitive_digest
            ),
            iteration_digest=(
                iteration_digest
            ),
            repeated_state_count=(
                repeat_count
            ),
            stalled=stalled,
            next_state=next_state,
        )
