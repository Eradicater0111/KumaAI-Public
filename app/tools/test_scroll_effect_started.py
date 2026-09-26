from unittest.mock import patch

from app.tools.computer_tools import (
    scroll,
)


def test_scroll_success_marks_effect_started():
    with (
        patch(
            "app.tools.computer_tools._enforce_pyautogui_safety"
        ),
        patch(
            "app.tools.computer_tools.pyautogui.scroll"
        ) as physical,
    ):
        result = scroll(
            -2
        )

    assert result.success
    assert result.effect_started is True

    physical.assert_called_once_with(
        -2
    )


def test_scroll_failure_after_boundary_preserves_effect_marker():
    with (
        patch(
            "app.tools.computer_tools._enforce_pyautogui_safety"
        ),
        patch(
            "app.tools.computer_tools.pyautogui.scroll",
            side_effect=RuntimeError(
                "wheel failure"
            ),
        ),
    ):
        result = scroll(
            -2
        )

    assert not result.success
    assert result.effect_started is True


def test_scroll_validation_failure_does_not_start_effect():
    result = scroll(
        "down"
    )

    assert not result.success
    assert result.effect_started is False


def test_zero_scroll_has_no_physical_effect():
    with patch(
        "app.tools.computer_tools.pyautogui.scroll"
    ) as physical:
        result = scroll(
            0
        )

    assert result.success
    assert result.effect_started is False
    physical.assert_not_called()
