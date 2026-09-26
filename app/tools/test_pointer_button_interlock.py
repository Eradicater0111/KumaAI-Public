from __future__ import annotations

import inspect
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
    click_at,
    click_vision,
    move_mouse,
    move_mouse_vision,
)


@pytest.fixture
def state_store(
    monkeypatch,
):

    store = BodyButtonStateStore(
        clock=lambda: 100.0,
    )

    monkeypatch.setattr(
        body_state_module,
        "BODY_BUTTON_STATE",
        store,
    )

    return store


def test_raw_move_is_blocked_while_held(
    state_store,
):

    state_store._record_press_success(
        "left"
    )

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size"
        ) as size,
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ) as move,
    ):

        result = move_mouse(
            100,
            100,
        )

    assert not result.success
    size.assert_not_called()
    move.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_HELD
    )


def test_raw_move_is_blocked_while_unknown(
    state_store,
):

    state_store._record_uncertain(
        "right"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.moveTo"
    ) as move:

        result = move_mouse(
            100,
            100,
        )

    assert not result.success
    move.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_UNKNOWN
    )


def test_raw_click_is_blocked_while_held(
    state_store,
):

    state_store._record_press_success(
        "middle"
    )

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size"
        ) as size,
        patch(
            "app.tools.computer_tools."
            "pyautogui.click"
        ) as click,
    ):

        result = click_at(
            100,
            100,
        )

    assert not result.success
    size.assert_not_called()
    click.assert_not_called()


def test_raw_click_is_blocked_while_unknown(
    state_store,
):

    state_store._record_uncertain(
        "left"
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.click"
    ) as click:

        result = click_at(
            100,
            100,
        )

    assert not result.success
    click.assert_not_called()


def test_trusted_click_blocks_before_observation_consumption(
    state_store,
):

    state_store._record_press_success(
        "left"
    )

    with (
        patch(
            "app.vision.observation."
            "SCREEN_OBSERVATIONS.peek"
        ) as peek,
        patch(
            "app.tools.computer_tools."
            "click_at"
        ) as raw_click,
    ):

        result = click_vision(
            x=10,
            y=10,
            observation_id="obs-test",
        )

    assert not result.success

    peek.assert_not_called()
    raw_click.assert_not_called()


def test_trusted_move_blocks_before_observation_consumption(
    state_store,
):

    state_store._record_uncertain(
        "middle"
    )

    with (
        patch(
            "app.vision.observation."
            "SCREEN_OBSERVATIONS.peek"
        ) as peek,
        patch(
            "app.tools.computer_tools."
            "move_mouse"
        ) as raw_move,
    ):

        result = move_mouse_vision(
            x=10,
            y=10,
            observation_id="obs-test",
        )

    assert not result.success

    peek.assert_not_called()
    raw_move.assert_not_called()


def test_click_exception_enters_unknown(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1470,
                956,
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.click",
            side_effect=RuntimeError(
                "compound click failed"
            ),
        ),
    ):

        result = click_at(
            100,
            100,
            button="right",
        )

    assert not result.success

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "right"


def test_click_keyboard_interrupt_enters_unknown_and_reraises(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1470,
                956,
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.click",
            side_effect=KeyboardInterrupt(),
        ),
    ):

        with pytest.raises(
            KeyboardInterrupt
        ):
            click_at(
                100,
                100,
                button="left",
            )

    state = state_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "left"


def test_safety_failure_before_click_preserves_clear(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1470,
                956,
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "_enforce_pyautogui_safety",
            side_effect=RuntimeError(
                "safety setup failed"
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.click"
        ) as click,
    ):

        result = click_at(
            100,
            100,
        )

    assert not result.success
    click.assert_not_called()

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_successful_click_preserves_clear(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1470,
                956,
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.click"
        ),
    ):

        result = click_at(
            100,
            100,
        )

    assert result.success

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_successful_move_preserves_clear(
    state_store,
):

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1470,
                956,
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ),
    ):

        result = move_mouse(
            100,
            100,
        )

    assert result.success

    assert (
        state_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_raw_pointer_effects_hold_serialized_transition():

    move_source = inspect.getsource(
        move_mouse
    )

    click_source = inspect.getsource(
        click_at
    )

    assert (
        "serialized_transition()"
        in move_source
    )

    assert (
        "serialized_transition()"
        in click_source
    )


def test_trusted_pointer_wrappers_have_early_body_guard():

    click_source = inspect.getsource(
        click_vision
    )

    move_source = inspect.getsource(
        move_mouse_vision
    )

    assert (
        "_pointer_button_block_reason"
        in click_source
    )

    assert (
        "_pointer_button_block_reason"
        in move_source
    )

    assert (
        click_source.index(
            "_pointer_button_block_reason"
        )
        <
        click_source.index(
            "SCREEN_OBSERVATIONS.peek"
        )
    )

    assert (
        move_source.index(
            "_pointer_button_block_reason"
        )
        <
        move_source.index(
            "SCREEN_OBSERVATIONS.peek"
        )
    )
