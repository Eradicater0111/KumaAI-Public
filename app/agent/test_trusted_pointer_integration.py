import json
from unittest.mock import Mock

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.goal_decomposer import (
    GoalDecomposer,
)
from app.agent.gui_action_grounding import (
    MISSION_GUI_ACTION_TOOLS,
    MISSION_SEMANTIC_TARGET_TOOLS,
)
from app.agent.gui_argument_authority import (
    arguments_grounded_in_human_goal,
    authorize_runtime_gui_arguments,
)
from app.agent.gui_intent_authority import (
    explicitly_authorizes_gui_action_class,
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
    BODY_ACTION_TOOL_NAMES,
    BODY_COORDINATE_NATIVE_SCREEN,
    BODY_COORDINATE_TRUSTED_VISION,
    BODY_TARGET_RAW_NATIVE,
    BODY_TARGET_TRUSTED_SEMANTIC,
)


TARGET_INTENT = {
    "role": "AXButton",
    "subrole": None,
    "text": "Settings",
    "require_enabled": True,
    "require_positive_area": True,
}


def capability_for(
    registry,
    tool_name,
):
    for capability in registry.names():
        if tool_name in registry.tools_for(
            capability
        ):
            return capability

    raise AssertionError(
        f"No capability exposes {tool_name}."
    )


def move_plan_payload():
    registry = (
        create_default_capability_registry()
    )

    capability = capability_for(
        registry,
        "move_mouse_vision",
    )

    payload = {
        "goal": (
            "Move the cursor to Settings."
        ),
        "steps": [
            {
                "id": "move-settings",
                "objective": (
                    "Move the cursor to Settings."
                ),
                "dependencies": [],
                "success_criteria": [
                    "Pointer reaches Settings."
                ],
                "required_capabilities": [
                    capability
                ],
                "planned_tool": (
                    "move_mouse_vision"
                ),
                "gui_target_intent": dict(
                    TARGET_INTENT
                ),
                "risk_level": "normal",
                "artifacts": [],
                "verification_requirements": [],
            }
        ],
    }

    return registry, payload


def test_trusted_move_is_canonical_body_action():

    assert (
        "move_mouse_vision"
        in BODY_ACTION_TOOL_NAMES
    )

    contract = BODY_ACTION_CONTRACTS[
        "move_mouse_vision"
    ]

    assert (
        contract.coordinate_space
        == BODY_COORDINATE_TRUSTED_VISION
    )

    assert (
        contract.target_binding
        == BODY_TARGET_TRUSTED_SEMANTIC
    )

    raw = BODY_ACTION_CONTRACTS[
        "move_mouse"
    ]

    assert (
        raw.coordinate_space
        == BODY_COORDINATE_NATIVE_SCREEN
    )

    assert (
        raw.target_binding
        == BODY_TARGET_RAW_NATIVE
    )


def test_trusted_move_is_registered_and_permissioned():

    assert (
        "move_mouse_vision"
        in KUMA_TOOLS
    )

    assert (
        TOOL_PERMISSIONS[
            "move_mouse_vision"
        ]
        == PermissionLevel.USER_AUTHORIZED
    )

    assert (
        "move_mouse_vision"
        in MISSION_GUI_ACTION_TOOLS
    )

    assert (
        "move_mouse_vision"
        in MISSION_SEMANTIC_TARGET_TOOLS
    )

    assert (
        "move_mouse"
        not in MISSION_SEMANTIC_TARGET_TOOLS
    )


def test_default_capability_exposes_trusted_move():

    registry = (
        create_default_capability_registry()
    )

    capability = capability_for(
        registry,
        "move_mouse_vision",
    )

    assert (
        "move_mouse"
        in registry.tools_for(
            capability
        )
    )

    assert (
        "move_mouse_vision"
        in registry.tools_for(
            capability
        )
    )


def test_decomposer_accepts_semantic_target_for_trusted_move():

    registry, payload = (
        move_plan_payload()
    )

    plan, error = (
        GoalDecomposer.parse_plan(
            json.dumps(
                payload
            ),
            capability_registry=registry,
        )
    )

    assert error is None
    assert plan is not None

    step = plan.steps[0]

    assert (
        step.planned_tool
        == "move_mouse_vision"
    )

    assert (
        step.gui_target_intent
        == TARGET_INTENT
    )


def test_decomposer_rejects_target_intent_on_raw_move():

    registry = (
        create_default_capability_registry()
    )

    capability = capability_for(
        registry,
        "move_mouse",
    )

    payload = {
        "goal": (
            "Move the cursor to x=100, y=200."
        ),
        "steps": [
            {
                "id": "raw-move",
                "objective": (
                    "Move the cursor to x=100, y=200."
                ),
                "dependencies": [],
                "success_criteria": [
                    "Pointer reaches the coordinate."
                ],
                "required_capabilities": [
                    capability
                ],
                "planned_tool": "move_mouse",
                "gui_target_intent": dict(
                    TARGET_INTENT
                ),
                "risk_level": "normal",
                "artifacts": [],
                "verification_requirements": [],
            }
        ],
    }

    plan, error = (
        GoalDecomposer.parse_plan(
            json.dumps(
                payload
            ),
            capability_registry=registry,
        )
    )

    assert plan is None
    assert error is not None

    assert (
        "trusted semantic target tool"
        in error
    )


def test_human_move_language_authorizes_both_move_classes():

    goal = (
        "Move the cursor to Settings."
    )

    assert (
        explicitly_authorizes_gui_action_class(
            goal,
            "move_mouse",
        )
    )

    assert (
        explicitly_authorizes_gui_action_class(
            goal,
            "move_mouse_vision",
        )
    )


def test_model_coordinates_never_directly_ground_trusted_move():

    assert not arguments_grounded_in_human_goal(
        goal=(
            "Move the cursor to x=100, y=200."
        ),
        tool_name="move_mouse_vision",
        arguments={
            "observation_id": "obs-model",
            "x": 100,
            "y": 200,
        },
    )


def test_semantic_target_allows_canonical_move_without_confirmation():

    confirmation = Mock(
        return_value=False
    )

    decision = (
        authorize_runtime_gui_arguments(
            goal=(
                "Move the cursor to Settings."
            ),
            tool_name="move_mouse_vision",
            arguments={
                "observation_id": (
                    "obs-fresh"
                ),
                "x": 250,
                "y": 179,
            },
            confirmation_fn=confirmation,
            semantic_target_verified=True,
        )
    )

    assert decision.allowed

    assert (
        decision.semantic_target_verified
    )

    confirmation.assert_not_called()


def test_nondefault_move_duration_requires_exact_confirmation():

    confirmation = Mock(
        return_value=False
    )

    decision = (
        authorize_runtime_gui_arguments(
            goal=(
                "Move the cursor to Settings."
            ),
            tool_name="move_mouse_vision",
            arguments={
                "observation_id": (
                    "obs-fresh"
                ),
                "x": 250,
                "y": 179,
                "duration": 0.5,
            },
            confirmation_fn=confirmation,
            semantic_target_verified=True,
        )
    )

    assert not decision.allowed

    confirmation.assert_called_once()
