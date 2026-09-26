from __future__ import annotations

import inspect
import time
from unittest.mock import patch

import pytest

import app.agent.body_button_state as body_state_module

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_HELD,
    BODY_BUTTON_UNKNOWN,
    BodyButtonStateStore,
)

from app.agent.tool_result import ToolResult

from app.tools.computer_tools import (
    hold_mouse_vision,
)

from app.vision.coordinates import (
    CoordinateMapper,
)

from app.vision.gui_target_verifier import (
    GUI_HOLD_TARGET_ATTESTATIONS,
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
)

from app.vision.observation import (
    ScreenObservationError,
    ScreenObservationStore,
)


@pytest.fixture(
    autouse=True
)
def clear_hold_receipt():

    GUI_HOLD_TARGET_ATTESTATIONS.clear()

    yield

    GUI_HOLD_TARGET_ATTESTATIONS.clear()


@pytest.fixture
def body_store(
    monkeypatch,
):

    store = BodyButtonStateStore(
        clock=time.monotonic,
    )

    monkeypatch.setattr(
        body_state_module,
        "BODY_BUTTON_STATE",
        store,
    )

    return store


def make_screen_store():

    return ScreenObservationStore(
        max_age_seconds=30.0,
    )


def create_observation(
    store,
):

    return store.create(
        captured_at_monotonic=(
            time.monotonic()
        ),
        capture_width=2940,
        capture_height=1912,
        vision_width=1800,
        vision_height=1171,
        native_width=1470,
        native_height=956,
        vision_scale=(
            1800 / 2940
        ),
        analysis=(
            "VISIBLE_TARGETS:\n"
            "- name: target\n"
            "  coordinate: (900, 585)"
        ),
    )


def verification_for(
    observation,
    *,
    x=900,
    y=585,
):

    return GuiTargetVerificationResult(
        status=TARGET_STATUS_SATISFIED,
        summary="Target matched.",
        evidence="Trusted semantic evidence.",
        observation_id=(
            observation.observation_id
        ),
        x=x,
        y=y,
        goal_sha256="goal-digest",
        image_sha256="image-digest",
        target_region_sha256=(
            "target-region-digest"
        ),
    )


def issue_hold_receipt(
    observation,
    *,
    x=900,
    y=585,
    button="left",
):

    return (
        GUI_HOLD_TARGET_ATTESTATIONS.issue(
            result=verification_for(
                observation,
                x=x,
                y=y,
            ),
            button=button,
        )
    )


def test_callable_contract_is_exact():

    signature = inspect.signature(
        hold_mouse_vision
    )

    assert tuple(
        signature.parameters
    ) == (
        "x",
        "y",
        "observation_id",
        "button",
    )

    assert (
        signature.parameters[
            "button"
        ].default
        == "left"
    )

    assert (
        "duration"
        not in signature.parameters
    )


@pytest.mark.parametrize(
    "button",
    (
        "",
        " left",
        "left ",
        "LEFT",
        "Right",
        "sideways",
        True,
        1,
        None,
    ),
)
def test_button_identity_is_exact_and_non_normalizing(
    body_store,
    button,
):

    result = hold_mouse_vision(
        x=10,
        y=10,
        observation_id="obs",
        button=button,
    )

    assert not result.success

    assert (
        body_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


@pytest.mark.parametrize(
    "observation_id",
    (
        "",
        " obs",
        "obs ",
        True,
        1,
        None,
    ),
)
def test_observation_identity_is_exact(
    body_store,
    observation_id,
):

    result = hold_mouse_vision(
        x=10,
        y=10,
        observation_id=observation_id,
    )

    assert not result.success

    assert (
        body_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_success_moves_to_trusted_point_then_holds(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation,
        button="left",
    )

    mapper = CoordinateMapper(
        vision_width=(
            observation.vision_width
        ),
        vision_height=(
            observation.vision_height
        ),
        screen_width=(
            observation.native_width
        ),
        screen_height=(
            observation.native_height
        ),
    )

    expected_x, expected_y = (
        mapper.vision_to_screen(
            900,
            585,
        )
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ) as move_to,
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown"
        ) as mouse_down,
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
            button="left",
        )

    assert result.success, result.error

    move_to.assert_called_once_with(
        expected_x,
        expected_y,
        duration=0.15,
    )

    mouse_down.assert_called_once_with(
        button="left",
    )

    state = body_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_HELD
    )

    assert state.button == "left"

    with pytest.raises(
        ScreenObservationError
    ):
        screen_store.peek(
            observation.observation_id
        )


def test_held_state_blocks_before_observation_or_receipt_consumption(
    monkeypatch,
    body_store,
):

    body_store._record_press_success(
        "right"
    )

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation,
        button="left",
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

    with patch.object(
        screen_store,
        "peek",
        wraps=screen_store.peek,
    ) as peek:

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
            button="left",
        )

    assert not result.success
    peek.assert_not_called()

    # Early body refusal must not consume trusted target evidence.
    claimed = (
        GUI_HOLD_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
            button="left",
        )
    )

    assert claimed.button == "left"


def test_unknown_state_blocks_before_observation(
    monkeypatch,
    body_store,
):

    body_store._record_uncertain(
        "middle"
    )

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

    with patch.object(
        screen_store,
        "peek",
        wraps=screen_store.peek,
    ) as peek:

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
        )

    assert not result.success
    peek.assert_not_called()


def test_button_mismatch_consumes_hold_receipt_but_not_observation(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation,
        button="left",
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.size",
        return_value=(
            1470,
            956,
        ),
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
            button="right",
        )

    assert not result.success

    assert (
        screen_store.peek(
            observation.observation_id
        )
        is observation
    )

    with pytest.raises(
        ValueError,
        match="No semantic hold",
    ):
        GUI_HOLD_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
            button="left",
        )


def test_geometry_change_invalidates_receipt_and_observation(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

    with patch(
        "app.tools.computer_tools."
        "pyautogui.size",
        return_value=(
            1400,
            900,
        ),
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
        )

    assert not result.success

    with pytest.raises(
        ScreenObservationError
    ):
        screen_store.peek(
            observation.observation_id
        )

    with pytest.raises(
        ValueError,
        match="No semantic hold",
    ):
        GUI_HOLD_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
            button="left",
        )


def test_desktop_failure_prevents_physical_effect(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                False,
                "desktop changed",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ) as move_to,
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown"
        ) as mouse_down,
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
        )

    assert not result.success
    move_to.assert_not_called()
    mouse_down.assert_not_called()

    assert (
        body_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_pixel_change_prevents_physical_effect(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                False,
                "pixels changed",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ) as move_to,
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown"
        ) as mouse_down,
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
        )

    assert not result.success
    move_to.assert_not_called()
    mouse_down.assert_not_called()


def test_final_geometry_change_consumes_observation_without_effect(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

    with (
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            side_effect=(
                (1470, 956),
                (1400, 900),
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ) as move_to,
        patch(
            "app.tools.computer_tools."
            "pyautogui.mouseDown"
        ) as mouse_down,
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
        )

    assert not result.success
    move_to.assert_not_called()
    mouse_down.assert_not_called()

    with pytest.raises(
        ScreenObservationError
    ):
        screen_store.peek(
            observation.observation_id
        )


def test_move_failure_never_attempts_mouse_down(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "move_mouse",
            return_value=(
                ToolResult.fail(
                    "move failed"
                )
            ),
        ) as move,
        patch(
            "app.tools.computer_tools."
            "hold_mouse"
        ) as hold,
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
        )

    assert not result.success
    move.assert_called_once()
    hold.assert_not_called()

    assert (
        body_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_mouse_down_failure_compensates_to_clear(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation,
        button="right",
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ),
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

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
            button="right",
        )

    assert not result.success

    mouse_up.assert_called_once_with(
        button="right",
    )

    assert (
        body_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_mouse_down_and_compensation_failure_enters_unknown(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation,
        button="middle",
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ),
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
                "cleanup failed"
            ),
        ),
    ):

        result = hold_mouse_vision(
            x=900,
            y=585,
            observation_id=(
                observation.observation_id
            ),
            button="middle",
        )

    assert not result.success

    state = body_store.snapshot()

    assert (
        state.status
        == BODY_BUTTON_UNKNOWN
    )

    assert state.button == "middle"


def test_keyboard_interrupt_compensates_then_reraises(
    monkeypatch,
    body_store,
):

    screen_store = (
        make_screen_store()
    )

    observation = create_observation(
        screen_store
    )

    issue_hold_receipt(
        observation
    )

    monkeypatch.setattr(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        screen_store,
    )

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
            "_revalidate_physical_vision_hold_desktop_context",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=(
                True,
                "",
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.moveTo"
        ),
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
            hold_mouse_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

    mouse_up.assert_called_once_with(
        button="left",
    )

    assert (
        body_store.snapshot().status
        == BODY_BUTTON_CLEAR
    )


def test_trusted_hold_uses_raw_effectors_under_outer_lock():

    source = inspect.getsource(
        hold_mouse_vision
    )

    assert (
        "serialized_transition()"
        in source
    )

    assert (
        "move_mouse("
        in source
    )

    assert (
        "hold_mouse("
        in source
    )

    # Trusted wrapper itself must not create a second direct
    # physical implementation.
    assert (
        "pyautogui.moveTo("
        not in source
    )

    assert (
        "pyautogui.mouseDown("
        not in source
    )

    assert (
        "pyautogui.mouseUp("
        not in source
    )


def test_hold_receipt_claim_precedes_physical_delegates():

    source = inspect.getsource(
        hold_mouse_vision
    )

    claim = source.index(
        "GUI_HOLD_TARGET_ATTESTATIONS.claim"
    )

    move = source.index(
        "move_mouse("
    )

    hold = source.index(
        "hold_mouse("
    )

    assert claim < move < hold
