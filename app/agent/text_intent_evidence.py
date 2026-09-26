"""Exact human-rooted text-intent evidence for KUMA 8D3.

The existing GUI argument-grounding path intentionally normalizes whitespace.
That is suitable as a conservative grounding predicate, but it cannot prove
the exact character sequence that a keyboard effect would later emit.

8D3A derives a separate exact payload from the original human goal carried by
an exact, active RuntimeGuiStepAuthorityProvenance.

A naked GoalStep is never accepted as authority.

An equal-value or reconstructed provenance object is never accepted as
authority.

The exact provenance must still be the object returned by the active
process-local runtime authority store for the exact current GoalPlan /
GoalStep pair.

This module:
- preserves exact captured payload characters,
- performs no whitespace normalization,
- requires exact active runtime provenance,
- is short-lived,
- performs no focus collection,
- grants no keyboard permission,
- performs no physical input.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)
import math
import re
import time

from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
    RuntimeGuiStepAuthorityProvenance,
)


EXACT_TEXT_INTENT_MAX_AGE_SECONDS = 5.0

TEXT_INTENT_STATUS_MATCHED = "matched"
TEXT_INTENT_STATUS_UNKNOWN = "unknown"

VALID_TEXT_INTENT_STATUSES = frozenset({
    TEXT_INTENT_STATUS_MATCHED,
    TEXT_INTENT_STATUS_UNKNOWN,
})

TEXT_INTENT_UNKNOWN_CODES = frozenset({
    "invalid_authority_provenance",
    "inactive_authority_provenance",
    "invalid_proposed_text",
    "wrong_planned_tool",
    "human_goal_unavailable",
    "exact_text_not_authorized",
    "clock_unavailable",
})


def _timestamp(
    value,
):
    return (
        type(value)
        in (
            int,
            float,
        )
        and math.isfinite(
            value
        )
        and value >= 0
    )


def _exact_explicit_text_payloads(
    goal,
):
    """Extract exact typing payload characters from one human goal.

    Syntax intentionally mirrors the existing conservative grounding grammar,
    but captured payload characters are never collapsed, stripped, case-folded,
    or otherwise rewritten.
    """

    if type(goal) is not str:
        return ()

    candidates = []

    quote_patterns = (
        r'\b(?:type|enter|input)\s+"([^"]+)"',
        r"\b(?:type|enter|input)\s+'([^']+)'",
        r'\b(?:type|enter|input)\s+“([^”]+)”',
    )

    for pattern in quote_patterns:
        for match in re.finditer(
            pattern,
            goal,
            re.IGNORECASE,
        ):
            value = match.group(
                1
            )

            if value:
                candidates.append(
                    value
                )

    into_pattern = re.compile(
        r"\b(?:type|enter|input)\s+"
        r"(.+?)\s+"
        r"(?:into|inside)\b",
        re.IGNORECASE,
    )

    for match in into_pattern.finditer(
        goal
    ):
        value = match.group(
            1
        )

        if value:
            candidates.append(
                value
            )

    colon_pattern = re.compile(
        r"\btype\s+"
        r"(?:this|the\s+following)\s*:\s*"
        r"(.+)$",
        re.IGNORECASE,
    )

    match = colon_pattern.search(
        goal
    )

    if match is not None:
        value = match.group(
            1
        )

        if value:
            candidates.append(
                value
            )

    return tuple(
        dict.fromkeys(
            candidates
        )
    )


def exact_explicit_text_payloads(
    goal,
):
    """Public read-only exact extraction helper."""

    return _exact_explicit_text_payloads(
        goal
    )


def _active_exact_authority_provenance(
    provenance,
):
    if (
        type(provenance)
        is not RuntimeGuiStepAuthorityProvenance
    ):
        return False

    try:
        active = (
            RUNTIME_GUI_STEP_AUTHORITY
            .get_current(
                provenance.plan,
                provenance.step,
            )
        )
    except Exception:
        return False

    return (
        active
        is provenance
    )


@dataclass(frozen=True)
class ExactTextIntentEvidence:
    """Short-lived exact human text-intent evidence.

    This proves only that ``raw_text`` occurs as one exact explicit typing
    payload inside the human goal of the exact active runtime authority
    provenance.

    It is not focus proof.
    It is not a focused-text receipt.
    It is not keyboard authority.
    """

    authority_provenance: (
        RuntimeGuiStepAuthorityProvenance
    ) = field(
        repr=False
    )

    source_step_id: str

    source_planned_tool: str

    source_gui_authority: str = field(
        repr=False
    )

    source_human_goal: str = field(
        repr=False
    )

    raw_text: str = field(
        repr=False
    )

    issued_at_monotonic: float

    expires_at_monotonic: float

    def __post_init__(
        self,
    ):
        provenance = (
            self.authority_provenance
        )

        if (
            type(provenance)
            is not RuntimeGuiStepAuthorityProvenance
        ):
            raise ValueError(
                "Exact runtime GUI step authority "
                "provenance is required."
            )

        if not _active_exact_authority_provenance(
            provenance
        ):
            raise ValueError(
                "Exact active runtime GUI step authority "
                "provenance is required."
            )

        if (
            type(self.source_step_id)
            is not str
            or not self.source_step_id
            or self.source_step_id
            != provenance.step_id
        ):
            raise ValueError(
                "Exact source step ID is invalid."
            )

        if (
            type(self.source_planned_tool)
            is not str
            or self.source_planned_tool
            != "type_text"
            or self.source_planned_tool
            != provenance.planned_tool
        ):
            raise ValueError(
                "Exact text intent requires "
                "active type_text provenance."
            )

        if (
            type(self.source_gui_authority)
            is not str
            or not self.source_gui_authority
            or self.source_gui_authority
            != provenance.gui_authority
        ):
            raise ValueError(
                "Runtime GUI authority snapshot "
                "does not match provenance."
            )

        if (
            type(self.source_human_goal)
            is not str
            or not self.source_human_goal
            or self.source_human_goal
            != provenance.human_goal
            or self.source_human_goal
            != provenance.gui_authority_goal
        ):
            raise ValueError(
                "Original human goal snapshot "
                "does not match provenance."
            )

        if (
            type(self.raw_text)
            is not str
            or not self.raw_text
        ):
            raise ValueError(
                "Exact raw text payload is required."
            )

        if not (
            _timestamp(
                self.issued_at_monotonic
            )
            and _timestamp(
                self.expires_at_monotonic
            )
        ):
            raise ValueError(
                "Exact text-intent times are invalid."
            )

        if (
            self.issued_at_monotonic
            < provenance.issued_at_monotonic
        ):
            raise ValueError(
                "Exact text intent cannot predate "
                "its authority provenance."
            )

        if (
            self.expires_at_monotonic
            != (
                self.issued_at_monotonic
                + EXACT_TEXT_INTENT_MAX_AGE_SECONDS
            )
        ):
            raise ValueError(
                "Exact text-intent lifetime is invalid."
            )

        if (
            self.raw_text
            not in _exact_explicit_text_payloads(
                self.source_human_goal
            )
        ):
            raise ValueError(
                "Raw text is not exactly authorized "
                "by the human goal."
            )

    @property
    def source_step(
        self,
    ):
        return (
            self.authority_provenance
            .step
        )

    @property
    def source_plan(
        self,
    ):
        return (
            self.authority_provenance
            .plan
        )

    def is_current(
        self,
        now,
    ):
        if not (
            _timestamp(
                now
            )
            and self.issued_at_monotonic
            <= now
            < self.expires_at_monotonic
        ):
            return False

        provenance = (
            self.authority_provenance
        )

        if not _active_exact_authority_provenance(
            provenance
        ):
            return False

        if (
            provenance.step_id
            != self.source_step_id
            or provenance.planned_tool
            != self.source_planned_tool
            or provenance.gui_authority
            != self.source_gui_authority
            or provenance.human_goal
            != self.source_human_goal
            or provenance.gui_authority_goal
            != self.source_human_goal
        ):
            return False

        return (
            self.raw_text
            in _exact_explicit_text_payloads(
                self.source_human_goal
            )
        )


@dataclass(frozen=True)
class ExactTextIntentEvidenceResult:
    """Non-executing result of exact human text-intent derivation."""

    status: str

    evidence: (
        ExactTextIntentEvidence
        | None
    ) = field(
        default=None,
        repr=False,
    )

    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if (
            type(self.status)
            is not str
            or self.status
            not in VALID_TEXT_INTENT_STATUSES
        ):
            raise ValueError(
                "Invalid exact text-intent result status."
            )

        if (
            type(self.diagnostics)
            is not tuple
            or any(
                type(code)
                is not str
                for code
                in self.diagnostics
            )
            or len(
                set(
                    self.diagnostics
                )
            )
            != len(
                self.diagnostics
            )
        ):
            raise ValueError(
                "Exact text-intent diagnostics "
                "must be immutable and unique."
            )

        if (
            self.status
            == TEXT_INTENT_STATUS_MATCHED
        ):
            if (
                type(self.evidence)
                is not ExactTextIntentEvidence
                or self.diagnostics
            ):
                raise ValueError(
                    "Matched text-intent result requires "
                    "one exact evidence object."
                )

            return

        if self.evidence is not None:
            raise ValueError(
                "Unknown text-intent result cannot "
                "carry evidence."
            )

        if (
            len(
                self.diagnostics
            )
            != 1
            or self.diagnostics[
                0
            ]
            not in TEXT_INTENT_UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown text-intent result requires "
                "one structured diagnostic."
            )

    @property
    def matched(
        self,
    ):
        return (
            self.status
            == TEXT_INTENT_STATUS_MATCHED
            and self.evidence
            is not None
        )


def _unknown(
    code,
):
    return ExactTextIntentEvidenceResult(
        status=(
            TEXT_INTENT_STATUS_UNKNOWN
        ),
        diagnostics=(
            code,
        ),
    )


def derive_exact_text_intent_evidence(
    authority_provenance,
    proposed_text,
    *,
    clock=time.monotonic,
):
    """Derive exact human-rooted text evidence without physical effects."""

    if (
        type(authority_provenance)
        is not RuntimeGuiStepAuthorityProvenance
    ):
        return _unknown(
            "invalid_authority_provenance"
        )

    if not _active_exact_authority_provenance(
        authority_provenance
    ):
        return _unknown(
            "inactive_authority_provenance"
        )

    if (
        type(proposed_text)
        is not str
        or not proposed_text
    ):
        return _unknown(
            "invalid_proposed_text"
        )

    if (
        authority_provenance.planned_tool
        != "type_text"
    ):
        return _unknown(
            "wrong_planned_tool"
        )

    human_goal = (
        authority_provenance
        .human_goal
    )

    if (
        type(human_goal)
        is not str
        or not human_goal
    ):
        return _unknown(
            "human_goal_unavailable"
        )

    if (
        proposed_text
        not in _exact_explicit_text_payloads(
            human_goal
        )
    ):
        return _unknown(
            "exact_text_not_authorized"
        )

    if not callable(
        clock
    ):
        return _unknown(
            "clock_unavailable"
        )

    try:
        issued = (
            clock()
        )
    except Exception:
        return _unknown(
            "clock_unavailable"
        )

    if not _timestamp(
        issued
    ):
        return _unknown(
            "clock_unavailable"
        )

    if (
        issued
        < authority_provenance
        .issued_at_monotonic
    ):
        return _unknown(
            "clock_unavailable"
        )

    try:
        evidence = (
            ExactTextIntentEvidence(
                authority_provenance=(
                    authority_provenance
                ),
                source_step_id=(
                    authority_provenance
                    .step_id
                ),
                source_planned_tool=(
                    authority_provenance
                    .planned_tool
                ),
                source_gui_authority=(
                    authority_provenance
                    .gui_authority
                ),
                source_human_goal=(
                    human_goal
                ),
                raw_text=(
                    proposed_text
                ),
                issued_at_monotonic=(
                    issued
                ),
                expires_at_monotonic=(
                    issued
                    + EXACT_TEXT_INTENT_MAX_AGE_SECONDS
                ),
            )
        )
    except Exception:
        return _unknown(
            "inactive_authority_provenance"
        )

    return ExactTextIntentEvidenceResult(
        status=(
            TEXT_INTENT_STATUS_MATCHED
        ),
        evidence=evidence,
        diagnostics=(),
    )
