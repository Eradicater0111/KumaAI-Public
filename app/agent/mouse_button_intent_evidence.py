from __future__ import annotations

from dataclasses import dataclass, field
import re
import time

from app.agent.body_button_state import (
    BODY_MOUSE_BUTTONS,
)
from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
    RuntimeGuiStepAuthorityProvenance,
)


MOUSE_BUTTON_INTENT_MAX_AGE_SECONDS = 5.0

MOUSE_INTENT_STATUS_ISSUED = "issued"
MOUSE_INTENT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExactMouseHoldIntentEvidence:
    authority_provenance: RuntimeGuiStepAuthorityProvenance
    button: str
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(self, now):
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class ExactMouseReleaseIntentEvidence:
    authority_provenance: RuntimeGuiStepAuthorityProvenance
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(self, now):
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class MouseIntentEvidenceResult:
    status: str
    evidence: object | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status
            == MOUSE_INTENT_STATUS_ISSUED
            and self.evidence is not None
        )


def _active_exact_authority(
    authority,
    planned_tool,
):
    if (
        type(authority)
        is not RuntimeGuiStepAuthorityProvenance
    ):
        return False

    try:
        current = (
            RUNTIME_GUI_STEP_AUTHORITY.get_current(
                authority.plan,
                authority.step,
            )
        )
    except Exception:
        current = None

    return (
        current is authority
        and authority.planned_tool
        == planned_tool
    )


def _hold_authorized(
    human_goal,
    button,
):
    if type(human_goal) is not str:
        return False

    request = human_goal.lower()

    action = (
        r"\b(?:hold(?:\s+down)?|press\s+and\s+hold)"
        r"\s+(?:the\s+)?"
    )

    if button == "right":
        target = (
            r"right\s+(?:mouse\s+)?button\b"
        )

    elif button == "middle":
        target = (
            r"middle\s+(?:mouse\s+)?button\b"
        )

    else:
        target = (
            r"(?:(?:left\s+)?(?:mouse\s+)?button)\b"
        )

        if re.search(
            r"\b(?:right|middle)\s+"
            r"(?:mouse\s+)?button\b",
            request,
        ):
            return False

    return bool(
        re.search(
            action + target,
            request,
        )
    )


def derive_exact_mouse_hold_intent_evidence(
    authority,
    proposed_button,
    *,
    clock=time.monotonic,
):
    def unknown(code):
        return MouseIntentEvidenceResult(
            status=MOUSE_INTENT_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    if not _active_exact_authority(
        authority,
        "hold_mouse",
    ):
        return unknown(
            "authority_unavailable"
        )

    if (
        type(proposed_button) is not str
        or proposed_button
        not in BODY_MOUSE_BUTTONS
    ):
        return unknown(
            "invalid_button"
        )

    if not _hold_authorized(
        authority.human_goal,
        proposed_button,
    ):
        return unknown(
            "button_not_authorized"
        )

    try:
        now = clock()
    except Exception:
        return unknown(
            "clock_unavailable"
        )

    return MouseIntentEvidenceResult(
        status=MOUSE_INTENT_STATUS_ISSUED,
        evidence=ExactMouseHoldIntentEvidence(
            authority_provenance=authority,
            button=proposed_button,
            issued_at_monotonic=now,
            expires_at_monotonic=(
                now
                + MOUSE_BUTTON_INTENT_MAX_AGE_SECONDS
            ),
        ),
    )


def derive_exact_mouse_release_intent_evidence(
    authority,
    *,
    clock=time.monotonic,
):
    def unknown(code):
        return MouseIntentEvidenceResult(
            status=MOUSE_INTENT_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    if not _active_exact_authority(
        authority,
        "release_mouse",
    ):
        return unknown(
            "authority_unavailable"
        )

    human_goal = authority.human_goal

    if (
        type(human_goal) is not str
        or re.search(
            r"\b(?:release|let\s+go\s+of)"
            r"\s+(?:the\s+)?"
            r"(?:(?:left|right|middle)\s+)?"
            r"(?:mouse\s+)?button\b",
            human_goal.lower(),
        )
        is None
    ):
        return unknown(
            "release_not_authorized"
        )

    try:
        now = clock()
    except Exception:
        return unknown(
            "clock_unavailable"
        )

    return MouseIntentEvidenceResult(
        status=MOUSE_INTENT_STATUS_ISSUED,
        evidence=ExactMouseReleaseIntentEvidence(
            authority_provenance=authority,
            issued_at_monotonic=now,
            expires_at_monotonic=(
                now
                + MOUSE_BUTTON_INTENT_MAX_AGE_SECONDS
            ),
        ),
    )


@dataclass(frozen=True)
class ExactMouseHoldVisionIntentEvidence:
    authority_provenance: RuntimeGuiStepAuthorityProvenance
    button: str
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(self, now):
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


def derive_exact_mouse_hold_vision_intent_evidence(
    authority,
    proposed_button,
    *,
    clock=time.monotonic,
):
    def unknown(code):
        return MouseIntentEvidenceResult(
            status=MOUSE_INTENT_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    if not _active_exact_authority(
        authority,
        "hold_mouse_vision",
    ):
        return unknown(
            "authority_unavailable"
        )

    if (
        type(proposed_button) is not str
        or proposed_button
        not in BODY_MOUSE_BUTTONS
    ):
        return unknown(
            "invalid_button"
        )

    if not _hold_authorized(
        authority.human_goal,
        proposed_button,
    ):
        return unknown(
            "button_not_authorized"
        )

    try:
        now = clock()
    except Exception:
        return unknown(
            "clock_unavailable"
        )

    return MouseIntentEvidenceResult(
        status=MOUSE_INTENT_STATUS_ISSUED,
        evidence=ExactMouseHoldVisionIntentEvidence(
            authority_provenance=authority,
            button=proposed_button,
            issued_at_monotonic=now,
            expires_at_monotonic=(
                now
                + MOUSE_BUTTON_INTENT_MAX_AGE_SECONDS
            ),
        ),
    )
