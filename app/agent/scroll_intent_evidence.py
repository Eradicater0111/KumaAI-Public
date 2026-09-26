from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
    RuntimeGuiStepAuthorityProvenance,
)


SCROLL_INTENT_MAX_AGE_SECONDS = 5.0

SCROLL_INTENT_STATUS_ISSUED = "issued"
SCROLL_INTENT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExactScrollIntentEvidence:
    authority_provenance: RuntimeGuiStepAuthorityProvenance
    source_step_id: str
    source_planned_tool: str
    source_human_goal: str
    amount: int
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(
        self,
        now,
    ) -> bool:
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class ExactScrollIntentEvidenceResult:
    status: str
    evidence: ExactScrollIntentEvidence | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status == SCROLL_INTENT_STATUS_ISSUED
            and self.evidence is not None
        )


def _human_authorized_exact_scroll(
    human_goal,
    amount,
):
    if type(human_goal) is not str:
        return False

    request = human_goal.lower()

    if amount == 0:
        return bool(
            re.search(
                r"\bscroll\b",
                request,
            )
        )

    direction = (
        "up"
        if amount > 0
        else "down"
    )

    magnitude = abs(
        amount
    )

    patterns = (
        rf"\bscroll\s+{direction}"
        rf"(?:\s+by)?\s+{magnitude}\b",
        rf"\bscroll\s+{magnitude}\s+"
        rf"{direction}\b",
    )

    return any(
        re.search(
            pattern,
            request,
        )
        is not None
        for pattern in patterns
    )


def derive_exact_scroll_intent_evidence(
    authority_provenance,
    proposed_amount,
    *,
    clock=time.monotonic,
):
    def unknown(code):
        return ExactScrollIntentEvidenceResult(
            status=SCROLL_INTENT_STATUS_UNKNOWN,
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
        current = (
            RUNTIME_GUI_STEP_AUTHORITY.get_current(
                authority_provenance.plan,
                authority_provenance.step,
            )
        )
    except Exception:
        current = None

    if current is not authority_provenance:
        return unknown(
            "authority_not_current"
        )

    if (
        authority_provenance.planned_tool
        != "scroll"
    ):
        return unknown(
            "wrong_planned_tool"
        )

    if type(proposed_amount) is not int:
        return unknown(
            "invalid_scroll_amount"
        )

    human_goal = (
        authority_provenance.human_goal
    )

    if not _human_authorized_exact_scroll(
        human_goal,
        proposed_amount,
    ):
        return unknown(
            "scroll_not_explicitly_authorized"
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

    evidence = ExactScrollIntentEvidence(
        authority_provenance=(
            authority_provenance
        ),
        source_step_id=(
            authority_provenance.step_id
        ),
        source_planned_tool="scroll",
        source_human_goal=human_goal,
        amount=proposed_amount,
        issued_at_monotonic=now,
        expires_at_monotonic=(
            now
            + SCROLL_INTENT_MAX_AGE_SECONDS
        ),
    )

    return ExactScrollIntentEvidenceResult(
        status=SCROLL_INTENT_STATUS_ISSUED,
        evidence=evidence,
    )
