from unittest.mock import patch

from app.tools.computer_tools import (
    press_key,
)


def test_press_key_success_marks_effect_started():
    with (
        patch(
            "app.tools.computer_tools._enforce_pyautogui_safety"
        ),
        patch(
            "app.tools.computer_tools.pyautogui.press"
        ) as physical,
    ):
        result = press_key(
            "enter"
        )

    assert result.success
    assert result.effect_started is True

    physical.assert_called_once_with(
        "enter"
    )


def test_press_key_failure_after_physical_boundary_preserves_marker():
    with (
        patch(
            "app.tools.computer_tools._enforce_pyautogui_safety"
        ),
        patch(
            "app.tools.computer_tools.pyautogui.press",
            side_effect=RuntimeError(
                "physical failure"
            ),
        ),
    ):
        result = press_key(
            "enter"
        )

    assert not result.success
    assert result.effect_started is True


def test_press_key_validation_failure_has_not_started_effect():
    result = press_key(
        "definitely-not-a-key"
    )

    assert not result.success
    assert result.effect_started is False
