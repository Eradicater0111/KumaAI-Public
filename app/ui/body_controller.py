from __future__ import annotations

from PySide6.QtCore import (
    QObject,
    Slot,
)

from app.ui.body_state import (
    KumaBodyState,
)

from app.ui.avatar_renderer_adapter import (
    project_avatar_snapshot,
)
from app.ui.avatar_runtime import (
    AvatarSnapshot,
)
from app.ui.avatar_visual_mechanics import (
    project_avatar_visual_parameters,
)


from app.emotion import (
    KumaExpressionDirective,
    KumaExpressionMode,
)

class KumaBodyController(QObject):
    """
    Presentation-only bridge from KUMA runtime status
    into KUMA Mini's visual state.

    This is not:
    - a planner
    - an agent
    - a model-facing tool
    - execution authority

    The existing KUMA brain remains the only brain.
    """

    def __init__(
        self,
        body,
    ):
        super().__init__()

        self.body = body

    # =====================================================
    # EMOTIONAL PRESENTATION
    # =====================================================

    def present_expression(
        self,
        directive,
    ):
        """
        Present a conversational expression through KUMA's
        existing body-state vocabulary.

        This is presentation only.

        Semantic one-shot gestures are intentionally preserved
        on the directive for the dedicated gesture channel added
        in COMPANION-4C2.
        """

        if not isinstance(
            directive,
            KumaExpressionDirective,
        ):
            return

        mode = directive.mode

        if mode in {
            KumaExpressionMode.HAPPY,
            KumaExpressionMode.PLAYFUL,
            KumaExpressionMode.ENERGETIC,
        }:
            state = KumaBodyState.HAPPY

        elif mode == KumaExpressionMode.CURIOUS:
            state = KumaBodyState.THINKING

        elif mode == KumaExpressionMode.FOCUSED:
            state = KumaBodyState.FOCUSED

        elif mode == KumaExpressionMode.ALERT:
            state = KumaBodyState.ALERT

        elif mode in {
            KumaExpressionMode.GENTLE,
            KumaExpressionMode.WARM,
            KumaExpressionMode.NEUTRAL,
        }:
            state = KumaBodyState.IDLE

        else:
            state = KumaBodyState.IDLE

        self.body.set_state(
            state
        )


    # =====================================================
    # KUMA-AVATAR-1B SEMANTIC PRESENTATION
    # =====================================================

    def present_avatar_snapshot(
        self,
        snapshot,
    ):
        """
        Project one frozen AvatarSnapshot into the existing body renderer.

        This is a one-way presentation sink. Invalid/non-avatar input is
        ignored instead of clobbering the current body state.
        """

        if not isinstance(
            snapshot,
            AvatarSnapshot,
        ):
            return

        projection = (
            project_avatar_snapshot(
                snapshot
            )
        )

        self.body.set_state(
            projection.body_state
        )

        visual_parameters = (
            project_avatar_visual_parameters(
                snapshot
            )
        )

        visual_sink = getattr(
            self.body,
            "set_avatar_visual_parameters",
            None,
        )

        if callable(
            visual_sink
        ):
            visual_sink(
                visual_parameters
            )


    @Slot(str)
    def handle_runtime_status(
        self,
        status,
    ):
        if type(status) is not str:
            self.body.set_state(
                KumaBodyState.IDLE
            )
            return

        value = (
            status.strip()
            .lower()
        )

        if any(
            marker in value
            for marker in (
                "thinking",
                "reasoning",
                "planning",
                "processing",
            )
        ):
            state = KumaBodyState.THINKING

        elif any(
            marker in value
            for marker in (
                "observing",
                "looking",
                "analyzing screen",
                "perception",
                "vision",
            )
        ):
            state = KumaBodyState.OBSERVING

        elif any(
            marker in value
            for marker in (
                "focus",
                "focused",
            )
        ):
            state = KumaBodyState.FOCUSED

        elif any(
            marker in value
            for marker in (
                "working",
                "executing",
                "running",
                "mission",
                "tool",
            )
        ):
            state = KumaBodyState.WORKING

        elif any(
            marker in value
            for marker in (
                "complete",
                "completed",
                "success",
                "finished",
                "done",
            )
        ):
            state = KumaBodyState.HAPPY

        elif any(
            marker in value
            for marker in (
                "warning",
                "error",
                "blocked",
                "failed",
                "attention",
            )
        ):
            state = KumaBodyState.ALERT

        elif any(
            marker in value
            for marker in (
                "listening",
                "hearing",
            )
        ):
            state = KumaBodyState.LISTENING

        elif any(
            marker in value
            for marker in (
                "sleep",
                "sleeping",
                "resting",
            )
        ):
            state = KumaBodyState.SLEEP

        else:
            state = KumaBodyState.IDLE

        self.body.set_state(
            state
        )
