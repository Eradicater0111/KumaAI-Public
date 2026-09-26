from __future__ import annotations

from inspect import signature
from unittest.mock import patch

import pytest

import app.agent.body_button_state as body_state_module

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_HELD,
    BODY_BUTTON_UNKNOWN,
    BodyButtonStateStore,
)
from app.tools.computer_tools import (
    hold_mouse,
    release_mouse,
)


class FakeClock:

    def __init__(
        self,
        *,
        allowed_calls=None,
    ):
        self.calls = 0
        self.allowed_calls = allowed_calls

    def __call__(
        self,
    ):
        self.calls += 1

        if (
            self.allowed_calls is not None
            and self.calls
            > self.allowed_calls
        ):
            raise RuntimeError(
                "clock unavailable"
            )

        return (
            100.0
            + self.calls
        )


@pytest.fixture
def state_store(
    monkeypatch,
):

    store = BodyButtonStateStore(
        clock=FakeClock(),
    )

    monkeypatch.setattr(
        body_state_module,
        "BODY_BUTTON_STATE",
        store,
    )

    return store


def install_store(
    monkeypatch,
    *,
    allowed_clock_calls,
):

    store = BodyButtonStateStore(
        clock=FakeClock(
            allowed_calls=(
                allowed_clock_calls
            ),
        )
    )

    monkeypatch.setattr(
        body_state_module,
        "BODY_BUTTON_STATE",
        store,
    )

    return store


def test_public_callable_contracts_are_exact():

    hold = signature(
        hold_mouse
    )

    release = signature(
        release_mouse
    )

    assert tuple(
        hold.parameters
    ) == (
        "button",
    )

    assert (
        hold.parameters[
            "button"
        ].default
        == "left"
    )

    assert tuple(
        release.parameters
    ) == ()


def test_hold_success_records_live_held_state(
    state_store,
):

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseDown"
    ) as mouse_down:

        result = hold_mouse(
            "left"
        )

    assert result.success

    mouse_down.assert_called_once_with(
        button="left",
    )

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_HELD
    )

    assert state.button == "left"


def test_second_hold_is_blocked_before_physical_effect(
    state_store,
):

    state_store._record_press_success(
        "left"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseDown"
    ) as mouse_down:

        result = hold_mouse(
            "right"
        )

    assert not result.success

    assert (
        "button state"
        in result.error
    )

    mouse_down.assert_not_called()

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_HELD
    )

    assert state.button == "left"


def test_hold_is_blocked_from_unknown_state(
    state_store,
):

    state_store._record_uncertain(
        "middle"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseDown"
    ) as mouse_down:

        result = hold_mouse(
            "left"
        )

    assert not result.success
    mouse_down.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_UNKNOWN
    )


@pytest.mark.parametrize(
    "button",
    (
        "",
        " left",
        "left ",
        "LEFT",
        "sideways",
        True,
        1,
        None,
    ),
)
def test_hold_button_identity_is_exact(
    state_store,
    button,
):

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseDown"
    ) as mouse_down:

        result = hold_mouse(
            button
        )

    assert not result.success
    mouse_down.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_mouse_down_exception_compensates_to_clear(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown",
            side_effect=RuntimeError(
                "down failed"
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseUp"
        ) as mouse_up,
    ):

        result = hold_mouse(
            "left"
        )

    assert not result.success

    mouse_up.assert_called_once_with(
        button="left",
    )

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_mouse_down_and_compensation_failure_enters_unknown(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown",
            side_effect=RuntimeError(
                "down failed"
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseUp",
            side_effect=RuntimeError(
                "up failed"
            ),
        ),
    ):

        result = hold_mouse(
            "right"
        )

    assert not result.success

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "right"


def test_mouse_down_keyboard_interrupt_compensates_then_reraises(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown",
            side_effect=KeyboardInterrupt(),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseUp"
        ) as mouse_up,
    ):

        with pytest.raises(
            KeyboardInterrupt
        ):
            hold_mouse(
                "left"
            )

    mouse_up.assert_called_once_with(
        button="left",
    )

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_mouse_down_keyboard_interrupt_and_cleanup_failure_enters_unknown(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown",
            side_effect=KeyboardInterrupt(),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseUp",
            side_effect=RuntimeError(
                "cleanup failed"
            ),
        ),
    ):

        with pytest.raises(
            KeyboardInterrupt
        ):
            hold_mouse(
                "middle"
            )

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "middle"


def test_press_state_record_failure_compensates_to_clear(
    monkeypatch,
):

    # Initialization gets the only healthy clock read.
    # HELD-state recording then fails after mouseDown succeeds.
    store = install_store(
        monkeypatch,
        allowed_clock_calls=1,
    )

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown"
        ) as mouse_down,
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseUp"
        ) as mouse_up,
    ):

        result = hold_mouse(
            "left"
        )

    assert not result.success

    mouse_down.assert_called_once_with(
        button="left",
    )

    mouse_up.assert_called_once_with(
        button="left",
    )

    assert (
        store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_press_state_record_and_compensation_failure_enters_unknown(
    monkeypatch,
):

    store = install_store(
        monkeypatch,
        allowed_clock_calls=1,
    )

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown"
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseUp",
            side_effect=RuntimeError(
                "cleanup failed"
            ),
        ),
    ):

        result = hold_mouse(
            "left"
        )

    assert not result.success

    state = store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"


def test_release_from_clear_is_blocked_without_mouse_up(
    state_store,
):

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp"
    ) as mouse_up:

        result = release_mouse()

    assert not result.success
    mouse_up.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_release_uses_exact_held_button_and_clears(
    state_store,
):

    state_store._record_press_success(
        "right"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp"
    ) as mouse_up:

        result = release_mouse()

    assert result.success

    mouse_up.assert_called_once_with(
        button="right",
    )

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_release_can_recover_exact_unknown_button(
    state_store,
):

    state_store._record_uncertain(
        "middle"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp"
    ) as mouse_up:

        result = release_mouse()

    assert result.success

    mouse_up.assert_called_once_with(
        button="middle",
    )

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_release_mouse_up_exception_enters_unknown(
    state_store,
):

    state_store._record_press_success(
        "left"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp",
        side_effect=RuntimeError(
            "up failed"
        ),
    ):

        result = release_mouse()

    assert not result.success

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"


def test_release_keyboard_interrupt_marks_unknown_and_reraises(
    state_store,
):

    state_store._record_press_success(
        "right"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp",
        side_effect=KeyboardInterrupt(),
    ):

        with pytest.raises(
            KeyboardInterrupt
        ):
            release_mouse()

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "right"


def test_release_state_record_failure_enters_unknown(
    monkeypatch,
):

    # init=1, press=2, release CLEAR recording=3 -> fail.
    store = install_store(
        monkeypatch,
        allowed_clock_calls=2,
    )

    store._record_press_success(
        "left"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.mouseUp"
    ) as mouse_up:

        result = release_mouse()

    assert not result.success

    mouse_up.assert_called_once_with(
        button="left",
    )

    state = store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"


def test_release_never_accepts_model_supplied_button():

    sig = signature(
        release_mouse
    )

    assert (
        "button"
        not in sig.parameters
    )

    with pytest.raises(
        TypeError
    ):
        release_mouse(
            button="left"
        )
