"""
KUMA-AVATAR-1B — one-way semantic avatar renderer projection.

This module projects the frozen KUMA-AVATAR-1A AvatarSnapshot into the
existing KumaBodyState vocabulary.

The projection is intentionally lossy. The current body renderer exposes one
discrete visual state, while AvatarSnapshot carries independent lifecycle,
expression, gaze, motion-energy, and speech fields.

Precedence:
1. Non-IDLE lifecycle mode wins over cosmetic expression.
2. IDLE may be refined by a positive-intensity expression.
3. Gaze and motion energy are preserved in AvatarSnapshot for richer future
   renderers but do not alter today's discrete KumaBodyState.
4. The renderer projection remains AUTHORITY:NONE.

Critical boundaries:
- RENDER PROJECTION != COGNITION
- BODY STATE != FACT
- EXPRESSION != PERMISSION
- RENDERER OUTPUT != EXECUTION
- PRESENTATION SINK != CONTROL LOOP
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ui.avatar_runtime import (
    AVATAR_AUTHORITY_NONE,
    AvatarExpression,
    AvatarMode,
    AvatarSnapshot,
)
from app.ui.body_state import (
    KumaBodyState,
)


AVATAR_RENDER_AUTHORITY_NONE = AVATAR_AUTHORITY_NONE


_MODE_TO_BODY_STATE = {
    AvatarMode.IDLE: KumaBodyState.IDLE,
    AvatarMode.LISTENING: KumaBodyState.LISTENING,
    AvatarMode.THINKING: KumaBodyState.THINKING,
    AvatarMode.SPEAKING: KumaBodyState.SPEAKING,
    AvatarMode.ATTENTION: KumaBodyState.ALERT,
    AvatarMode.SUCCESS: KumaBodyState.HAPPY,
    AvatarMode.ERROR: KumaBodyState.ALERT,
    AvatarMode.SLEEP: KumaBodyState.SLEEP,
}


_IDLE_EXPRESSION_TO_BODY_STATE = {
    AvatarExpression.HAPPY: KumaBodyState.HAPPY,
    AvatarExpression.FOCUSED: KumaBodyState.FOCUSED,
    AvatarExpression.ALERT: KumaBodyState.ALERT,
}


@dataclass(
    frozen=True,
    slots=True,
)
class AvatarRenderProjection:
    """
    Immutable zero-authority projection into the current body-state renderer.

    This object contains presentation output only. It carries no tool,
    permission, confirmation, action, verification, model, memory, or
    cognitive-loop state.
    """

    body_state: KumaBodyState
    source_mode: AvatarMode
    expression_applied: bool
    authority: str = field(
        default=AVATAR_RENDER_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.body_state,
            KumaBodyState,
        ):
            raise TypeError(
                "body_state must be KumaBodyState."
            )

        if not isinstance(
            self.source_mode,
            AvatarMode,
        ):
            raise TypeError(
                "source_mode must be AvatarMode."
            )

        if type(
            self.expression_applied
        ) is not bool:
            raise TypeError(
                "expression_applied must be bool."
            )


def project_avatar_snapshot(
    snapshot: AvatarSnapshot,
) -> AvatarRenderProjection:
    """
    Project one immutable AvatarSnapshot into today's body-state vocabulary.

    Non-IDLE lifecycle meaning is never replaced by a cosmetic expression.
    IDLE may use HAPPY / FOCUSED / ALERT when expression intensity is positive.
    NEUTRAL and GENTLE remain IDLE in the current discrete renderer.
    """

    if not isinstance(
        snapshot,
        AvatarSnapshot,
    ):
        raise TypeError(
            "snapshot must be AvatarSnapshot."
        )

    body_state = _MODE_TO_BODY_STATE[
        snapshot.mode
    ]

    expression_applied = False

    if (
        snapshot.mode
        == AvatarMode.IDLE
        and snapshot.expression_intensity
        > 0.0
    ):
        refined = (
            _IDLE_EXPRESSION_TO_BODY_STATE.get(
                snapshot.expression
            )
        )

        if refined is not None:
            body_state = refined
            expression_applied = True

    return AvatarRenderProjection(
        body_state=body_state,
        source_mode=snapshot.mode,
        expression_applied=expression_applied,
    )
