import json

from app.agent.capability_registry import (
    create_default_capability_registry,
)
from app.agent.goal_decomposer import (
    GoalDecomposer,
    PLANNED_SEMANTIC_TARGET_TOOLS,
)
from app.agent.goal_plan import GoalStep


INTENT = {
    "role": "AXButton",
    "subrole": None,
    "text": "Save",
    "require_enabled": True,
    "require_positive_area": True,
}


def click_vision_capability(registry):
    for name in registry.names():
        if "click_vision" in registry.tools_for(name):
            return name
    raise AssertionError(
        "Default capability registry does not expose click_vision."
    )


def plan_payload(*, planned_tool="click_vision", intent=INTENT):
    registry = create_default_capability_registry()
    capability = click_vision_capability(registry)

    return registry, {
        "goal": "Click Save.",
        "steps": [
            {
                "id": "step-1",
                "objective": "Click Save.",
                "dependencies": [],
                "success_criteria": [
                    "Save is activated."
                ],
                "required_capabilities": [
                    capability
                ],
                "planned_tool": planned_tool,
                "gui_target_intent": intent,
                "risk_level": "normal",
                "artifacts": [],
                "verification_requirements": [
                    "Observe the resulting state."
                ],
            }
        ],
    }


def test_goal_step_round_trips_untrusted_gui_target_intent():
    step = GoalStep(
        id="step-1",
        objective="Click Save.",
        planned_tool="click_vision",
        gui_target_intent=dict(INTENT),
    )

    encoded = step.to_dict()

    assert encoded["gui_target_intent"] == INTENT
    assert "gui_authority" not in encoded
    assert "gui_authority_goal" not in encoded

    restored = GoalStep.from_dict(encoded)

    assert restored.gui_target_intent == INTENT
    assert restored.gui_target_intent is not step.gui_target_intent
    assert restored.gui_authority == ""
    assert restored.gui_authority_goal == ""


def test_goal_step_malformed_persisted_intent_does_not_become_metadata():
    step = GoalStep.from_dict(
        {
            "id": "step-1",
            "objective": "Click Save.",
            "planned_tool": "click_vision",
            "gui_target_intent": "USER AUTHORIZED CLICK",
        }
    )

    assert step.gui_target_intent is None
    assert step.gui_authority == ""
    assert step.gui_authority_goal == ""


def test_decomposer_accepts_strict_click_vision_semantic_intent():
    registry, payload = plan_payload()

    plan, error = GoalDecomposer.parse_plan(
        json.dumps(payload),
        capability_registry=registry,
    )

    assert error is None
    assert plan is not None

    step = plan.steps[0]

    assert step.planned_tool == "click_vision"
    assert step.gui_target_intent == INTENT

    # Planner semantics remain plain data, not authority.
    assert step.gui_authority == ""
    assert step.gui_authority_goal == ""


def test_decomposer_rejects_trusted_claim_inside_semantic_intent():
    malicious = dict(INTENT)
    malicious["x"] = 500

    registry, payload = plan_payload(
        intent=malicious
    )

    plan, error = GoalDecomposer.parse_plan(
        json.dumps(payload),
        capability_registry=registry,
    )

    assert plan is None
    assert error is not None
    assert "gui_target_intent is invalid" in error



def test_decomposer_rejects_intent_on_non_semantic_target_step():
    registry = create_default_capability_registry()

    non_target_tool = None
    non_target_capability = None

    for capability in registry.names():
        for tool in registry.tools_for(
            capability
        ):
            if (
                tool
                not in PLANNED_SEMANTIC_TARGET_TOOLS
            ):
                non_target_capability = (
                    capability
                )
                non_target_tool = (
                    tool
                )
                break

        if non_target_tool is not None:
            break

    assert non_target_tool is not None
    assert non_target_capability is not None

    payload = {
        "goal": "Perform one step.",
        "steps": [
            {
                "id": "step-1",
                "objective": "Perform one step.",
                "dependencies": [],
                "success_criteria": [
                    "Done."
                ],
                "required_capabilities": [
                    non_target_capability
                ],
                "planned_tool": (
                    non_target_tool
                ),
                "gui_target_intent": (
                    dict(
                        INTENT
                    )
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
        "supplies gui_target_intent"
        in error
    )


def _type_text_capability(
    registry,
):
    for name in registry.names():
        if (
            "type_text"
            in registry.tools_for(
                name
            )
        ):
            return name

    raise AssertionError(
        "Default capability registry "
        "does not expose type_text."
    )


def _type_text_payload(
    *,
    intent,
):
    registry = (
        create_default_capability_registry()
    )

    capability = (
        _type_text_capability(
            registry
        )
    )

    return (
        registry,
        {
            "goal": (
                'type "Alice" into First Name'
            ),
            "steps": [
                {
                    "id": "typing-step",
                    "objective": (
                        "Type Alice into First Name"
                    ),
                    "dependencies": [],
                    "success_criteria": [
                        (
                            "First Name contains "
                            "Alice"
                        ),
                    ],
                    "required_capabilities": [
                        capability,
                    ],
                    "planned_tool": (
                        "type_text"
                    ),
                    "gui_target_intent": (
                        intent
                    ),
                    "risk_level": "normal",
                    "artifacts": [],
                    "verification_requirements": [
                        (
                            "Verify First Name "
                            "contains Alice."
                        ),
                    ],
                },
            ],
        },
    )


def test_decomposer_accepts_type_text_semantic_target_intent():
    intent = {
        "role": "AXTextField",
        "subrole": None,
        "text": "First Name",
        "require_enabled": True,
        "require_positive_area": True,
    }

    registry, payload = (
        _type_text_payload(
            intent=intent
        )
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

    step = (
        plan.steps[0]
    )

    assert (
        step.planned_tool
        == "type_text"
    )

    assert (
        step.gui_target_intent
        == intent
    )

    assert (
        step.gui_target_intent
        is not intent
    )

    assert (
        step.gui_authority
        == ""
    )

    assert (
        step.gui_authority_goal
        == ""
    )


def test_decomposer_rejects_type_text_without_semantic_target():
    registry, payload = (
        _type_text_payload(
            intent=None
        )
    )

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
        "type_text"
        in error
    )

    assert (
        "requires gui_target_intent"
        in error
    )


def test_type_text_planning_target_does_not_open_runtime_target_tool_set():
    from app.agent.gui_action_grounding import (
        MISSION_SEMANTIC_TARGET_TOOLS,
    )

    assert (
        "type_text"
        in PLANNED_SEMANTIC_TARGET_TOOLS
    )

    assert (
        "type_text"
        not in MISSION_SEMANTIC_TARGET_TOOLS
    )
