from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.agent.gui_action_grounding import (
    MISSION_GUI_ACTION_TOOLS,
)

from app.agent.virtual_body import (
    BODY_ACTION_CONTRACTS,
    BODY_ACTION_TOOL_NAMES,
    BODY_COORDINATE_NATIVE_SCREEN,
    BODY_COORDINATE_TRUSTED_VISION,
    BODY_EFFECTOR_KEYBOARD,
    BODY_EFFECTOR_POINTER,
    BODY_EFFECTOR_VIEWPORT,
    BODY_TARGET_RAW_NATIVE,
    BODY_TARGET_TRUSTED_SEMANTIC,
    BODY_TARGET_UNBOUND_CONTEXT,
    VirtualBodyState,
    body_action_contract_for,
    is_body_action_tool,
)


def test_body_action_surface_is_exact():

    assert BODY_ACTION_TOOL_NAMES == frozenset(
        {
            "move_mouse",
            "move_mouse_vision",
            "click",
            "click_vision",
            "hold_mouse",
            "hold_mouse_vision",
            "release_mouse",
            "type_text",
            "press_key",
            "scroll",
        }
    )

    # open_app remains a mission GUI action, but is not a
    # physical body effector.
    assert MISSION_GUI_ACTION_TOOLS == (
        BODY_ACTION_TOOL_NAMES
        | {
            "open_app",
        }
    )


def test_pointer_actions_distinguish_raw_and_trusted_targeting():

    move = BODY_ACTION_CONTRACTS[
        "move_mouse"
    ]

    trusted_move = BODY_ACTION_CONTRACTS[
        "move_mouse_vision"
    ]

    click = BODY_ACTION_CONTRACTS[
        "click"
    ]

    vision = BODY_ACTION_CONTRACTS[
        "click_vision"
    ]

    assert move.effector == BODY_EFFECTOR_POINTER
    assert trusted_move.effector == BODY_EFFECTOR_POINTER
    assert click.effector == BODY_EFFECTOR_POINTER
    assert vision.effector == BODY_EFFECTOR_POINTER

    assert (
        move.coordinate_space
        == BODY_COORDINATE_NATIVE_SCREEN
    )

    assert (
        click.target_binding
        == BODY_TARGET_RAW_NATIVE
    )

    assert (
        trusted_move.coordinate_space
        == BODY_COORDINATE_TRUSTED_VISION
    )

    assert (
        trusted_move.target_binding
        == BODY_TARGET_TRUSTED_SEMANTIC
    )

    assert (
        vision.coordinate_space
        == BODY_COORDINATE_TRUSTED_VISION
    )

    assert (
        vision.target_binding
        == BODY_TARGET_TRUSTED_SEMANTIC
    )


def test_keyboard_and_viewport_are_explicitly_unbound_today():

    assert (
        BODY_ACTION_CONTRACTS[
            "type_text"
        ].effector
        == BODY_EFFECTOR_KEYBOARD
    )

    assert (
        BODY_ACTION_CONTRACTS[
            "press_key"
        ].effector
        == BODY_EFFECTOR_KEYBOARD
    )

    assert (
        BODY_ACTION_CONTRACTS[
            "scroll"
        ].effector
        == BODY_EFFECTOR_VIEWPORT
    )

    for tool_name in (
        "type_text",
        "press_key",
        "scroll",
    ):
        assert (
            BODY_ACTION_CONTRACTS[
                tool_name
            ].target_binding
            == BODY_TARGET_UNBOUND_CONTEXT
        )


def test_body_action_lookup_is_fail_closed():

    assert is_body_action_tool(
        "click_vision"
    )

    assert not is_body_action_tool(
        "open_app"
    )

    assert not is_body_action_tool(
        ""
    )

    assert not is_body_action_tool(
        None
    )

    assert (
        body_action_contract_for(
            "unknown_tool"
        )
        is None
    )

    assert (
        body_action_contract_for(
            " click_vision"
        )
        is None
    )

    assert (
        body_action_contract_for(
            "click_vision "
        )
        is None
    )

    assert (
        body_action_contract_for(
            " click_vision "
        )
        is None
    )

    assert not is_body_action_tool(
        " move_mouse_vision "
    )



def test_virtual_body_state_preserves_only_known_state():

    state = VirtualBodyState(
        frontmost_application_pid=123,
        frontmost_application_bundle_id=(
            "com.example.App"
        ),
        screen_observation_id="obs-1",
        pointer_native_point=(
            100,
            200,
        ),
    )

    assert state.application_known
    assert state.screen_known
    assert state.pointer_known

    assert (
        state.frontmost_application_bundle_id
        == "com.example.App"
    )

    assert state.pointer_native_point == (
        100,
        200,
    )


def test_virtual_body_state_can_represent_unknown_state():

    state = VirtualBodyState()

    assert not state.application_known
    assert not state.screen_known
    assert not state.pointer_known


def test_application_identity_is_atomic():

    with pytest.raises(
        ValueError
    ):
        VirtualBodyState(
            frontmost_application_pid=123,
        )

    with pytest.raises(
        ValueError
    ):
        VirtualBodyState(
            frontmost_application_bundle_id=(
                "com.example.App"
            ),
        )


@pytest.mark.parametrize(
    "point",
    [
        [1, 2],
        (True, 2),
        (1, False),
        (-1, 2),
        (1, -2),
        (1,),
    ],
)
def test_invalid_pointer_state_is_rejected(
    point,
):

    with pytest.raises(
        ValueError
    ):
        VirtualBodyState(
            pointer_native_point=point
        )


def test_virtual_body_state_is_immutable():

    state = VirtualBodyState()

    with pytest.raises(
        FrozenInstanceError
    ):
        state.platform = "other"


def test_virtual_body_does_not_claim_focus_identity():

    state = VirtualBodyState()

    assert not hasattr(
        state,
        "focused_window_id",
    )

    assert not hasattr(
        state,
        "focused_element_id",
    )


def test_virtual_body_module_has_no_execution_or_authority_imports():

    source = (
        Path(__file__)
        .with_name(
            "virtual_body.py"
        )
        .read_text()
    )

    forbidden = (
        "import pyautogui",
        "from app.tools",
        "from app.agent.mission_service",
        "from app.agent.permissions",
        "GUI_TARGET_ATTESTATIONS",
    )

    for marker in forbidden:
        assert marker not in source
