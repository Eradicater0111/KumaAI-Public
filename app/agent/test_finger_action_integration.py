from __future__ import annotations

from pathlib import Path

import pytest

import app.agent.body_button_state as body_state_module

from app.agent.body_action_verifier import (
    FINGER_BODY_STATE_TOOLS,
    verify_body_action_postcondition,
)

from app.agent.body_button_state import (
    BodyButtonStateStore,
)

from app.agent.capability_registry import (
    create_default_capability_registry,
)

from app.agent.gui_action_grounding import (
    MISSION_GUI_ACTION_TOOLS,
    MISSION_SEMANTIC_TARGET_TOOLS,
)

from app.agent.gui_argument_authority import (
    authorize_runtime_gui_arguments,
)

from app.agent.permissions import (
    PermissionLevel,
    TOOL_PERMISSIONS,
)

from app.agent.tool_registry import (
    KUMA_TOOLS,
)

from app.agent.virtual_body import (
    BODY_ACTION_CONTRACTS,
    BODY_ACTION_HOLD,
    BODY_ACTION_RELEASE,
    BODY_ACTION_TOOL_NAMES,
    BODY_COORDINATE_NONE,
    BODY_COORDINATE_TRUSTED_VISION,
    BODY_TARGET_CURRENT_POINTER,
    BODY_TARGET_OWNED_BUTTON_STATE,
    BODY_TARGET_TRUSTED_SEMANTIC,
)

from app.vision.gui_objective_verifier import (
    GUI_OUTCOME_TOOLS,
)


FINGER = {
    "hold_mouse",
    "hold_mouse_vision",
    "release_mouse",
}


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


def test_public_finger_surface_is_atomic():

    assert (
        FINGER
        <= set(
            BODY_ACTION_TOOL_NAMES
        )
    )

    assert (
        FINGER
        <= set(
            KUMA_TOOLS
        )
    )

    registry = (
        create_default_capability_registry()
    )

    assert (
        FINGER
        <= set(
            registry.tools_for(
                "mouse_control"
            )
        )
    )


def test_finger_permissions_are_explicit():

    for tool_name in FINGER:

        assert (
            TOOL_PERMISSIONS[
                tool_name
            ]
            == PermissionLevel.USER_AUTHORIZED
        )


def test_body_contracts_distinguish_target_ownership():

    raw_hold = (
        BODY_ACTION_CONTRACTS[
            "hold_mouse"
        ]
    )

    trusted_hold = (
        BODY_ACTION_CONTRACTS[
            "hold_mouse_vision"
        ]
    )

    release = (
        BODY_ACTION_CONTRACTS[
            "release_mouse"
        ]
    )

    assert (
        raw_hold.action
        == BODY_ACTION_HOLD
    )

    assert (
        raw_hold.coordinate_space
        == BODY_COORDINATE_NONE
    )

    assert (
        raw_hold.target_binding
        == BODY_TARGET_CURRENT_POINTER
    )

    assert (
        trusted_hold.action
        == BODY_ACTION_HOLD
    )

    assert (
        trusted_hold.coordinate_space
        == BODY_COORDINATE_TRUSTED_VISION
    )

    assert (
        trusted_hold.target_binding
        == BODY_TARGET_TRUSTED_SEMANTIC
    )

    assert (
        release.action
        == BODY_ACTION_RELEASE
    )

    assert (
        release.coordinate_space
        == BODY_COORDINATE_NONE
    )

    assert (
        release.target_binding
        == BODY_TARGET_OWNED_BUTTON_STATE
    )


def test_only_trusted_hold_enters_semantic_target_set():

    assert (
        "hold_mouse_vision"
        in MISSION_SEMANTIC_TARGET_TOOLS
    )

    assert (
        "hold_mouse"
        not in MISSION_SEMANTIC_TARGET_TOOLS
    )

    assert (
        "release_mouse"
        not in MISSION_SEMANTIC_TARGET_TOOLS
    )

    assert (
        FINGER
        <= MISSION_GUI_ACTION_TOOLS
    )


def test_finger_actions_are_not_visual_outcome_tools():

    assert not (
        FINGER
        & set(
            GUI_OUTCOME_TOOLS
        )
    )


def test_trusted_default_left_hold_needs_no_extra_c2_confirmation():

    decision = authorize_runtime_gui_arguments(
        goal=(
            "Hold the mouse button on the Save button."
        ),
        tool_name="hold_mouse_vision",
        arguments={
            "x": 250,
            "y": 179,
            "observation_id": "obs-1",
            "button": "left",
        },
        confirmation_fn=None,
        semantic_target_verified=True,
    )

    assert decision.allowed
    assert decision.semantic_target_verified


def test_trusted_explicit_right_hold_is_goal_grounded():

    decision = authorize_runtime_gui_arguments(
        goal=(
            "Hold the right mouse button on the target."
        ),
        tool_name="hold_mouse_vision",
        arguments={
            "x": 250,
            "y": 179,
            "observation_id": "obs-1",
            "button": "right",
        },
        confirmation_fn=None,
        semantic_target_verified=True,
    )

    assert decision.allowed
    assert decision.grounded_in_goal
    assert decision.semantic_target_verified


def test_trusted_unrequested_right_hold_fails_closed():

    decision = authorize_runtime_gui_arguments(
        goal=(
            "Hold the mouse button on the target."
        ),
        tool_name="hold_mouse_vision",
        arguments={
            "x": 250,
            "y": 179,
            "observation_id": "obs-1",
            "button": "right",
        },
        confirmation_fn=None,
        semantic_target_verified=True,
    )

    assert not decision.allowed


def test_raw_default_left_hold_can_be_goal_grounded():

    decision = authorize_runtime_gui_arguments(
        goal="Hold the mouse button.",
        tool_name="hold_mouse",
        arguments={},
        confirmation_fn=None,
    )

    assert decision.allowed
    assert decision.grounded_in_goal


def test_release_has_zero_argument_authority():

    decision = authorize_runtime_gui_arguments(
        goal="Release the mouse button.",
        tool_name="release_mouse",
        arguments={},
        confirmation_fn=None,
    )

    assert decision.allowed
    assert decision.grounded_in_goal

    rejected = authorize_runtime_gui_arguments(
        goal="Release the mouse button.",
        tool_name="release_mouse",
        arguments={
            "button": "left",
        },
        confirmation_fn=None,
    )

    assert not rejected.allowed


def test_hold_body_postcondition_requires_exact_button(
    state_store,
):

    state_store._record_press_success(
        "right"
    )

    verified, summary = (
        verify_body_action_postcondition(
            tool_name="hold_mouse",
            arguments={
                "button": "right",
            },
        )
    )

    assert verified
    assert "HELD" in summary

    wrong, _ = (
        verify_body_action_postcondition(
            tool_name="hold_mouse",
            arguments={
                "button": "left",
            },
        )
    )

    assert not wrong


def test_release_body_postcondition_requires_clear(
    state_store,
):

    verified, summary = (
        verify_body_action_postcondition(
            tool_name="release_mouse",
            arguments={},
        )
    )

    assert verified
    assert "CLEAR" in summary

    state_store._record_press_success(
        "left"
    )

    verified, _ = (
        verify_body_action_postcondition(
            tool_name="release_mouse",
            arguments={},
        )
    )

    assert not verified


def test_release_verifier_rejects_button_argument():

    verified, _ = (
        verify_body_action_postcondition(
            tool_name="release_mouse",
            arguments={
                "button": "left",
            },
        )
    )

    assert not verified


def test_finger_verifier_surface_is_exact():

    assert (
        FINGER_BODY_STATE_TOOLS
        == frozenset(
            FINGER
        )
    )


def test_planner_prompt_names_trusted_hold_target():

    source = (
        Path(__file__)
        .with_name(
            "goal_decomposer.py"
        )
        .read_text()
    )

    assert (
        '"hold_mouse_vision" MUST include'
        in source
    )


def test_mission_service_has_full_hold_chain():

    source = (
        Path(__file__)
        .with_name(
            "mission_service.py"
        )
        .read_text()
    )

    assert (
        "GUI_HOLD_TARGET_ATTESTATIONS.issue"
        in source
    )

    assert (
        "_revalidate_vision_hold_desktop_context"
        in source
    )

    assert (
        "verify_body_action_postcondition"
        in source
    )

    assert (
        'recovery_action="escalate"'
        in source
    )


def test_legacy_brain_does_not_gain_finger_actions():

    root = (
        Path(__file__)
        .parents[2]
    )

    source = (
        root
        / "app"
        / "brain"
        / "llm.py"
    ).read_text()

    for tool_name in FINGER:

        assert (
            f'"{tool_name}"'
            not in source
        )
