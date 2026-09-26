from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
    RuntimeGuiStepAuthorityProvenance,
)


KEY_INTENT_EVIDENCE_MAX_AGE_SECONDS = 5.0

KEY_EVIDENCE_STATUS_ISSUED = "issued"
KEY_EVIDENCE_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExactKeyIntentEvidence:
    authority_provenance: RuntimeGuiStepAuthorityProvenance
    source_step_id: str
    source_planned_tool: str
    source_gui_authority: str
    source_human_goal: str
    raw_key: str
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(
        self,
        now: float,
    ) -> bool:
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class ExactKeyIntentEvidenceResult:
    status: str
    evidence: ExactKeyIntentEvidence | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status == KEY_EVIDENCE_STATUS_ISSUED
            and self.evidence is not None
        )


def _human_explicitly_authorized_key(
    human_goal: str,
    key: str,
) -> bool:
    aliases = {
        "enter": ("enter", "return"),
        "return": ("return", "enter"),
        "esc": ("esc", "escape"),
        "escape": ("escape", "esc"),
        "space": ("space", "spacebar"),
    }

    candidates = aliases.get(
        key,
        (key,),
    )

    request = human_goal.lower()

    for candidate in candidates:
        escaped = re.escape(
            candidate
        )

        if re.search(
            rf"\b(?:press|hit)\s+"
            rf"(?:the\s+)?"
            rf"{escaped}"
            rf"(?:\s+key)?\b",
            request,
        ):
            return True

    return False


def derive_exact_key_intent_evidence(
    authority_provenance,
    proposed_key,
    *,
    clock=time.monotonic,
):
    def unknown(code):
        return ExactKeyIntentEvidenceResult(
            status=KEY_EVIDENCE_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    if (
        type(authority_provenance)
        is not RuntimeGuiStepAuthorityProvenance
    ):
        return unknown(
            "invalid_authority_provenance"
        )

    try:
        active = (
            RUNTIME_GUI_STEP_AUTHORITY.get_current(
                authority_provenance.plan,
                authority_provenance.step,
            )
        )
    except Exception:
        active = None

    if active is not authority_provenance:
        return unknown(
            "authority_not_current"
        )

    if (
        authority_provenance.planned_tool
        != "press_key"
    ):
        return unknown(
            "wrong_planned_tool"
        )

    if type(proposed_key) is not str:
        return unknown(
            "invalid_key"
        )

    key = proposed_key.strip().lower()

    if not key:
        return unknown(
            "invalid_key"
        )

    human_goal = (
        authority_provenance.human_goal
    )

    if (
        type(human_goal) is not str
        or not _human_explicitly_authorized_key(
            human_goal,
            key,
        )
    ):
        return unknown(
            "key_not_explicitly_authorized"
        )

    try:
        now = clock()
    except Exception:
        return unknown(
            "clock_unavailable"
        )

    if type(now) not in (int, float):
        return unknown(
            "clock_unavailable"
        )

    evidence = ExactKeyIntentEvidence(
        authority_provenance=(
            authority_provenance
        ),
        source_step_id=(
            authority_provenance.step_id
        ),
        source_planned_tool=(
            authority_provenance.planned_tool
        ),
        source_gui_authority=(
            authority_provenance.gui_authority
        ),
        source_human_goal=human_goal,
        raw_key=key,
        issued_at_monotonic=now,
        expires_at_monotonic=(
            now
            + KEY_INTENT_EVIDENCE_MAX_AGE_SECONDS
        ),
    )

    return ExactKeyIntentEvidenceResult(
        status=KEY_EVIDENCE_STATUS_ISSUED,
        evidence=evidence,
    )
