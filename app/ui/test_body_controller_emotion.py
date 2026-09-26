from app.emotion import (
    KumaExpressionDirective,
    KumaExpressionMode,
)

from app.ui.body_controller import (
    KumaBodyController,
)

from app.ui.body_state import (
    KumaBodyState,
)


class FakeBody:
    def __init__(self):
        self.state = None

    def set_state(
        self,
        state,
    ):
        self.state = state


def present(
    mode,
):
    body = FakeBody()

    controller = KumaBodyController(
        body
    )

    controller.present_expression(
        KumaExpressionDirective(
            mode=mode
        )
    )

    return body.state


def test_energetic_maps_to_happy():
    assert present(
        KumaExpressionMode.ENERGETIC
    ) == KumaBodyState.HAPPY


def test_playful_maps_to_happy():
    assert present(
        KumaExpressionMode.PLAYFUL
    ) == KumaBodyState.HAPPY


def test_curiosity_maps_to_thinking():
    assert present(
        KumaExpressionMode.CURIOUS
    ) == KumaBodyState.THINKING


def test_focus_maps_to_focused():
    assert present(
        KumaExpressionMode.FOCUSED
    ) == KumaBodyState.FOCUSED


def test_alert_maps_to_alert():
    assert present(
        KumaExpressionMode.ALERT
    ) == KumaBodyState.ALERT


def test_gentle_maps_to_idle():
    assert present(
        KumaExpressionMode.GENTLE
    ) == KumaBodyState.IDLE
