"""
KUMA RAPHAEL-1J proactive cognition / event attention.

RAPHAEL-1J consumes explicit caller-supplied RealtimeSignal values that KUMA's
existing realtime change detector has already produced. It does not create a
second event bus, poll providers, drain runtime queues, refresh weather, read
location, inspect mutable task/mission objects, notify the user, or execute
anything.

RealtimeSignal -> privacy-minimized ProactiveEvent -> bounded attention
assessment -> deterministic AttentionDecision.

Critical invariants:
- REALTIME SIGNAL != COMMAND
- ATTENTION != PERMISSION
- URGENCY != AUTHORITY
- SURFACE != USER NOTIFICATION SIDE EFFECT
- ESCALATE_ATTENTION != EXECUTION AUTHORITY
- PROACTIVE THOUGHT != PROACTIVE EXECUTION
- MAXIMUM ATTENTION PRIORITY + MAXIMUM CONFIDENCE = AUTHORITY:NONE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Iterable

from app.agent.cognitive_contracts import COGNITIVE_AUTHORITY_NONE
from app.realtime import RealtimeFact, RealtimeRelevanceLevel, RealtimeSignal


PROACTIVE_ATTENTION_AUTHORITY_NONE = COGNITIVE_AUTHORITY_NONE

_MAX_TEXT_CHARS = 1200
_MAX_ITEMS = 128
_MAX_SIGNALS = 64

FRESHNESS_WINDOW_HOURS = 6.0

NOVELTY_WEIGHT = 0.20
GOAL_RELEVANCE_WEIGHT = 0.20
TIME_SENSITIVITY_WEIGHT = 0.20
CONSEQUENCE_WEIGHT = 0.20
CONFIDENCE_WEIGHT = 0.10
FRESHNESS_WEIGHT = 0.10

CONTEXT_FLOOR = 0.50
CONTEXT_SHARE = 0.50

SURFACE_THRESHOLD = 0.55
ESCALATE_THRESHOLD = 0.78
ESCALATE_FACTOR_FLOOR = 0.75


class AttentionDisposition(str, Enum):
    IGNORE = "ignore"
    DEFER = "defer"
    SURFACE = "surface"
    ESCALATE_ATTENTION = "escalate_attention"


def _text(value, *, field_name: str, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise TypeError(f"{field_name} must be a string.")

    normalized = " ".join(value.split())

    if not allow_empty and not normalized:
        raise ValueError(f"{field_name} cannot be empty.")

    if len(normalized) > _MAX_TEXT_CHARS:
        raise ValueError(f"{field_name} exceeds the bounded text limit.")

    return normalized


def _text_tuple(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings.")

    try:
        raw = tuple(values)
    except TypeError as error:
        raise TypeError(f"{field_name} must be iterable.") from error

    if len(raw) > _MAX_ITEMS:
        raise ValueError(f"{field_name} exceeds the bounded item limit.")

    result = []
    seen = set()

    for item in raw:
        normalized = _text(item, field_name=field_name)

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(normalized)

    return tuple(result)


def _factor(value, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")

    result = float(value)

    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0.")

    return result


def _sha256_hex(value: str) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _normalize_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime.")

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _digest_payload(payload) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _fact_digest(fact: RealtimeFact | None) -> str:
    if fact is None:
        return ""

    return _text(
        str(getattr(fact, "raw_evidence_digest", "") or ""),
        field_name="raw_evidence_digest",
        allow_empty=True,
    )


def _validate_signal(signal: RealtimeSignal) -> None:
    if not isinstance(signal, RealtimeSignal):
        raise TypeError("signal must be RealtimeSignal.")

    if signal.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
        raise ValueError("RealtimeSignal authority must remain NONE.")

    if not isinstance(signal.level, RealtimeRelevanceLevel):
        raise TypeError("RealtimeSignal.level must be RealtimeRelevanceLevel.")

    _text(signal.kind, field_name="signal.kind")
    _text(signal.reason, field_name="signal.reason")
    _factor(signal.score, field_name="signal.score")

    if not isinstance(signal.fact, RealtimeFact):
        raise TypeError("RealtimeSignal.fact must be RealtimeFact.")

    if signal.fact.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
        raise ValueError("RealtimeFact authority must remain NONE.")

    _factor(signal.fact.confidence, field_name="fact.confidence")
    _normalize_datetime(signal.fact.observed_at, field_name="fact.observed_at")

    if signal.previous_fact is not None and not isinstance(
        signal.previous_fact,
        RealtimeFact,
    ):
        raise TypeError(
            "RealtimeSignal.previous_fact must be RealtimeFact or None."
        )

    if (
        signal.previous_fact is not None
        and signal.previous_fact.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE
    ):
        raise ValueError("Previous RealtimeFact authority must remain NONE.")


def _signal_payload(signal: RealtimeSignal) -> dict:
    fact = signal.fact

    return {
        "kind": signal.kind,
        "level": signal.level.value,
        "score": float(signal.score),
        "reason": signal.reason,
        "observed_at": _normalize_datetime(
            fact.observed_at,
            field_name="fact.observed_at",
        ).isoformat(),
        "confidence": float(fact.confidence),
        "source_evidence_digest": _fact_digest(fact),
        "previous_evidence_digest": _fact_digest(signal.previous_fact),
    }


def realtime_signal_event_id(signal: RealtimeSignal) -> str:
    """Return a stable event identity without copying raw fact values."""

    _validate_signal(signal)
    return _digest_payload(_signal_payload(signal))


@dataclass(frozen=True, slots=True)
class ProactiveEvent:
    """Privacy-minimized zero-authority projection of one RealtimeSignal."""

    event_id: str
    kind: str
    reason: str
    realtime_level: RealtimeRelevanceLevel
    realtime_score: float
    observed_at: datetime
    confidence: float
    source_evidence_digest: str
    previous_evidence_digest: str = ""
    authority: str = field(
        default=PROACTIVE_ATTENTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not _sha256_hex(self.event_id):
            raise ValueError(
                "event_id must be a lowercase SHA-256 digest."
            )

        object.__setattr__(self, "kind", _text(self.kind, field_name="kind"))
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, field_name="reason"),
        )

        if not isinstance(self.realtime_level, RealtimeRelevanceLevel):
            raise TypeError(
                "realtime_level must be RealtimeRelevanceLevel."
            )

        object.__setattr__(
            self,
            "realtime_score",
            _factor(self.realtime_score, field_name="realtime_score"),
        )
        object.__setattr__(
            self,
            "observed_at",
            _normalize_datetime(self.observed_at, field_name="observed_at"),
        )
        object.__setattr__(
            self,
            "confidence",
            _factor(self.confidence, field_name="confidence"),
        )
        object.__setattr__(
            self,
            "source_evidence_digest",
            _text(
                self.source_evidence_digest,
                field_name="source_evidence_digest",
                allow_empty=True,
            ),
        )
        object.__setattr__(
            self,
            "previous_evidence_digest",
            _text(
                self.previous_evidence_digest,
                field_name="previous_evidence_digest",
                allow_empty=True,
            ),
        )


def project_realtime_signal(signal: RealtimeSignal) -> ProactiveEvent:
    """Project an existing realtime signal without preserving raw value/location."""

    _validate_signal(signal)
    fact = signal.fact

    return ProactiveEvent(
        event_id=realtime_signal_event_id(signal),
        kind=signal.kind,
        reason=signal.reason,
        realtime_level=signal.level,
        realtime_score=float(signal.score),
        observed_at=fact.observed_at,
        confidence=float(fact.confidence),
        source_evidence_digest=_fact_digest(fact),
        previous_evidence_digest=_fact_digest(signal.previous_fact),
    )


@dataclass(frozen=True, slots=True)
class AttentionCue:
    """Explicit structured relevance metadata for one ProactiveEvent."""

    event_id: str
    goal_relevance: float = 0.0
    time_sensitivity: float = 0.0
    consequence_of_ignoring: float = 0.0
    reason: str = "No explicit structured relevance cue supplied."
    authority: str = field(
        default=PROACTIVE_ATTENTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not _sha256_hex(self.event_id):
            raise ValueError(
                "AttentionCue.event_id must be a lowercase SHA-256 digest."
            )

        for field_name in (
            "goal_relevance",
            "time_sensitivity",
            "consequence_of_ignoring",
        ):
            object.__setattr__(
                self,
                field_name,
                _factor(getattr(self, field_name), field_name=field_name),
            )

        object.__setattr__(
            self,
            "reason",
            _text(self.reason, field_name="reason"),
        )


@dataclass(frozen=True, slots=True)
class AttentionContext:
    """
    Immutable caller projection.

    Goal/objective/status strings are audit context only. They are never parsed
    for keywords. The caller owns seen/acknowledged lifecycle state.
    """

    current_time: datetime
    active_goal: str = ""
    remaining_objective: str = ""
    mission_status: str = ""
    seen_event_ids: tuple[str, ...] = ()
    acknowledged_event_ids: tuple[str, ...] = ()
    cues: tuple[AttentionCue, ...] = ()
    authority: str = field(
        default=PROACTIVE_ATTENTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "current_time",
            _normalize_datetime(self.current_time, field_name="current_time"),
        )

        for field_name in (
            "active_goal",
            "remaining_objective",
            "mission_status",
        ):
            object.__setattr__(
                self,
                field_name,
                _text(
                    getattr(self, field_name),
                    field_name=field_name,
                    allow_empty=True,
                ),
            )

        for field_name in (
            "seen_event_ids",
            "acknowledged_event_ids",
        ):
            normalized = _text_tuple(
                getattr(self, field_name),
                field_name=field_name,
            )

            for event_id in normalized:
                if not _sha256_hex(event_id):
                    raise ValueError(
                        f"{field_name} values must be lowercase SHA-256 digests."
                    )

            object.__setattr__(self, field_name, normalized)

        if isinstance(self.cues, (str, bytes)):
            raise TypeError(
                "cues must be an iterable of AttentionCue values."
            )

        try:
            cue_tuple = tuple(self.cues)
        except TypeError as error:
            raise TypeError("cues must be iterable.") from error

        if len(cue_tuple) > _MAX_ITEMS:
            raise ValueError("cues exceed the bounded item limit.")

        cue_ids = []

        for cue in cue_tuple:
            if not isinstance(cue, AttentionCue):
                raise TypeError(
                    "cues must contain AttentionCue values."
                )

            if cue.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
                raise ValueError("AttentionCue authority must remain NONE.")

            cue_ids.append(cue.event_id)

        if len(cue_ids) != len(set(cue_ids)):
            raise ValueError(
                "AttentionContext cannot contain duplicate cue event IDs."
            )

        object.__setattr__(self, "cues", cue_tuple)

    def cue_map(self) -> dict[str, AttentionCue]:
        return {cue.event_id: cue for cue in self.cues}


@dataclass(frozen=True, slots=True)
class AttentionAssessment:
    """
    Auditable score for one ProactiveEvent.

    attention_score is always <= realtime_score, so contextual metadata cannot
    manufacture a stronger realtime relevance claim.
    """

    event: ProactiveEvent
    disposition: AttentionDisposition
    novelty: float
    goal_relevance: float
    time_sensitivity: float
    consequence_of_ignoring: float
    confidence: float
    freshness: float
    context_quality: float
    multiplier: float
    attention_score: float
    reason: str
    authority: str = field(
        default=PROACTIVE_ATTENTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.event, ProactiveEvent):
            raise TypeError("event must be ProactiveEvent.")

        if self.event.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
            raise ValueError("ProactiveEvent authority must remain NONE.")

        if not isinstance(self.disposition, AttentionDisposition):
            raise TypeError(
                "disposition must be AttentionDisposition."
            )

        for field_name in (
            "novelty",
            "goal_relevance",
            "time_sensitivity",
            "consequence_of_ignoring",
            "confidence",
            "freshness",
            "context_quality",
            "multiplier",
            "attention_score",
        ):
            object.__setattr__(
                self,
                field_name,
                _factor(getattr(self, field_name), field_name=field_name),
            )

        if self.attention_score > self.event.realtime_score + 1e-12:
            raise ValueError(
                "attention_score cannot exceed the underlying realtime score."
            )

        object.__setattr__(
            self,
            "reason",
            _text(self.reason, field_name="reason"),
        )


@dataclass(frozen=True, slots=True)
class AttentionDecision:
    """One deterministic zero-authority proactive attention decision."""

    disposition: AttentionDisposition
    reason: str
    selected_event: ProactiveEvent | None
    ranked_assessments: tuple[AttentionAssessment, ...]
    authority: str = field(
        default=PROACTIVE_ATTENTION_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, AttentionDisposition):
            raise TypeError(
                "disposition must be AttentionDisposition."
            )

        object.__setattr__(
            self,
            "reason",
            _text(self.reason, field_name="reason"),
        )

        if isinstance(self.ranked_assessments, (str, bytes)):
            raise TypeError(
                "ranked_assessments must be an iterable of "
                "AttentionAssessment values."
            )

        try:
            ranked = tuple(self.ranked_assessments)
        except TypeError as error:
            raise TypeError(
                "ranked_assessments must be iterable."
            ) from error

        for assessment in ranked:
            if not isinstance(assessment, AttentionAssessment):
                raise TypeError(
                    "ranked_assessments must contain AttentionAssessment values."
                )

            if assessment.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
                raise ValueError(
                    "AttentionAssessment authority must remain NONE."
                )

        object.__setattr__(self, "ranked_assessments", ranked)

        surfacing = self.disposition in (
            AttentionDisposition.SURFACE,
            AttentionDisposition.ESCALATE_ATTENTION,
        )

        if surfacing:
            if not isinstance(self.selected_event, ProactiveEvent):
                raise ValueError(
                    "SURFACE/ESCALATE_ATTENTION requires selected_event."
                )

            ids = {
                assessment.event.event_id
                for assessment in ranked
            }

            if self.selected_event.event_id not in ids:
                raise ValueError(
                    "selected_event must be present in ranked_assessments."
                )

            if (
                self.selected_event.authority
                != PROACTIVE_ATTENTION_AUTHORITY_NONE
            ):
                raise ValueError(
                    "selected_event authority must remain NONE."
                )

        elif self.selected_event is not None:
            raise ValueError(
                "IGNORE/DEFER cannot carry selected_event."
            )


def freshness_factor(observed_at: datetime, *, now: datetime) -> float:
    """Bounded freshness with future timestamps clamped to age zero."""

    observed = _normalize_datetime(observed_at, field_name="observed_at")
    current = _normalize_datetime(now, field_name="now")

    age_seconds = max(
        0.0,
        (current - observed).total_seconds(),
    )
    age_hours = age_seconds / 3600.0

    return 1.0 / (
        1.0
        + age_hours / FRESHNESS_WINDOW_HOURS
    )


def _default_cue(event_id: str) -> AttentionCue:
    return AttentionCue(event_id=event_id)


def _assessment_reason(disposition: AttentionDisposition) -> str:
    if disposition == AttentionDisposition.ESCALATE_ATTENTION:
        return (
            "Existing realtime relevance remains highly salient after bounded "
            "context discounting with explicit time-sensitivity and consequence. "
            "This escalates attention only and grants no authority."
        )

    if disposition == AttentionDisposition.SURFACE:
        return (
            "Existing realtime relevance remains salient enough for downstream "
            "cognitive surfacing. No user-facing or execution side effect occurs."
        )

    if disposition == AttentionDisposition.DEFER:
        return (
            "The realtime signal is eligible but not salient enough to surface "
            "now. It is deferred without side effects."
        )

    return (
        "The realtime signal does not qualify for proactive attention under "
        "the bounded zero-authority policy."
    )


class ProactiveAttentionEngine:
    """Stateless deterministic zero-authority attention ranking."""

    def assess(
        self,
        event: ProactiveEvent,
        context: AttentionContext,
    ) -> AttentionAssessment:
        if not isinstance(event, ProactiveEvent):
            raise TypeError("event must be ProactiveEvent.")

        if event.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
            raise ValueError("ProactiveEvent authority must remain NONE.")

        if not isinstance(context, AttentionContext):
            raise TypeError("context must be AttentionContext.")

        if context.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
            raise ValueError("AttentionContext authority must remain NONE.")

        cue = context.cue_map().get(
            event.event_id,
            _default_cue(event.event_id),
        )

        acknowledged = (
            event.event_id
            in set(context.acknowledged_event_ids)
        )
        seen = event.event_id in set(context.seen_event_ids)

        novelty = (
            0.0
            if acknowledged
            else (0.50 if seen else 1.0)
        )

        freshness = freshness_factor(
            event.observed_at,
            now=context.current_time,
        )

        context_quality = (
            NOVELTY_WEIGHT * novelty
            + GOAL_RELEVANCE_WEIGHT * cue.goal_relevance
            + TIME_SENSITIVITY_WEIGHT * cue.time_sensitivity
            + CONSEQUENCE_WEIGHT * cue.consequence_of_ignoring
            + CONFIDENCE_WEIGHT * event.confidence
            + FRESHNESS_WEIGHT * freshness
        )

        multiplier = (
            CONTEXT_FLOOR
            + CONTEXT_SHARE * context_quality
        )

        attention_score = (
            event.realtime_score
            * multiplier
        )

        if (
            acknowledged
            or event.realtime_level == RealtimeRelevanceLevel.IGNORE
            or event.realtime_score <= 0.0
        ):
            disposition = AttentionDisposition.IGNORE
            attention_score = 0.0

        elif (
            attention_score >= ESCALATE_THRESHOLD
            and cue.time_sensitivity >= ESCALATE_FACTOR_FLOOR
            and cue.consequence_of_ignoring >= ESCALATE_FACTOR_FLOOR
        ):
            disposition = AttentionDisposition.ESCALATE_ATTENTION

        elif attention_score >= SURFACE_THRESHOLD:
            disposition = AttentionDisposition.SURFACE

        else:
            # The existing realtime subsystem has already classified this
            # event as positively relevant. If it is not acknowledged,
            # upstream-ignored, zero-score, surfaceable, or escalation-worthy,
            # preserve it as deferred attention rather than erasing that
            # upstream relevance into IGNORE.
            disposition = AttentionDisposition.DEFER

        return AttentionAssessment(
            event=event,
            disposition=disposition,
            novelty=novelty,
            goal_relevance=cue.goal_relevance,
            time_sensitivity=cue.time_sensitivity,
            consequence_of_ignoring=cue.consequence_of_ignoring,
            confidence=event.confidence,
            freshness=freshness,
            context_quality=context_quality,
            multiplier=multiplier,
            attention_score=attention_score,
            reason=_assessment_reason(disposition),
        )

    def decide(
        self,
        signals: Iterable[RealtimeSignal],
        context: AttentionContext,
    ) -> AttentionDecision:
        if not isinstance(context, AttentionContext):
            raise TypeError("context must be AttentionContext.")

        if context.authority != PROACTIVE_ATTENTION_AUTHORITY_NONE:
            raise ValueError("AttentionContext authority must remain NONE.")

        if isinstance(signals, (str, bytes)):
            raise TypeError(
                "signals must be an iterable of RealtimeSignal values."
            )

        try:
            signal_tuple = tuple(signals)
        except TypeError as error:
            raise TypeError("signals must be iterable.") from error

        if len(signal_tuple) > _MAX_SIGNALS:
            raise ValueError(
                "signals exceed the bounded proactive-attention limit."
            )

        events = tuple(
            project_realtime_signal(signal)
            for signal in signal_tuple
        )

        event_ids = tuple(
            event.event_id
            for event in events
        )

        if len(event_ids) != len(set(event_ids)):
            raise ValueError(
                "signals contain duplicate proactive event identities."
            )

        current_ids = set(event_ids)

        unknown_cues = tuple(
            cue.event_id
            for cue in context.cues
            if cue.event_id not in current_ids
        )

        if unknown_cues:
            raise ValueError(
                "AttentionContext contains cue IDs absent from the current "
                "signal batch."
            )

        assessments = tuple(
            self.assess(event, context)
            for event in events
        )

        order = {
            AttentionDisposition.ESCALATE_ATTENTION: 3,
            AttentionDisposition.SURFACE: 2,
            AttentionDisposition.DEFER: 1,
            AttentionDisposition.IGNORE: 0,
        }

        ranked = tuple(
            sorted(
                assessments,
                key=lambda assessment: (
                    -order[assessment.disposition],
                    -assessment.attention_score,
                    assessment.event.event_id,
                ),
            )
        )

        if not ranked:
            return AttentionDecision(
                disposition=AttentionDisposition.IGNORE,
                reason=(
                    "No realtime signals were supplied for proactive attention."
                ),
                selected_event=None,
                ranked_assessments=(),
            )

        top = ranked[0]

        if top.disposition == AttentionDisposition.ESCALATE_ATTENTION:
            return AttentionDecision(
                disposition=AttentionDisposition.ESCALATE_ATTENTION,
                reason=(
                    "One existing realtime signal merits escalated cognitive "
                    "attention. This is not permission and causes no action."
                ),
                selected_event=top.event,
                ranked_assessments=ranked,
            )

        if top.disposition == AttentionDisposition.SURFACE:
            return AttentionDecision(
                disposition=AttentionDisposition.SURFACE,
                reason=(
                    "One existing realtime signal merits downstream cognitive "
                    "surfacing. No user-facing side effect occurs in 1J."
                ),
                selected_event=top.event,
                ranked_assessments=ranked,
            )

        if top.disposition == AttentionDisposition.DEFER:
            return AttentionDecision(
                disposition=AttentionDisposition.DEFER,
                reason=(
                    "Eligible realtime signals exist, but none currently "
                    "qualifies for cognitive surfacing."
                ),
                selected_event=None,
                ranked_assessments=ranked,
            )

        return AttentionDecision(
            disposition=AttentionDisposition.IGNORE,
            reason=(
                "No supplied realtime signal currently qualifies for proactive "
                "attention."
            ),
            selected_event=None,
            ranked_assessments=ranked,
        )
