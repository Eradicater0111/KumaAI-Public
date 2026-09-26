from __future__ import annotations

from typing import Any

from app.agent.virtual_body import (
    BODY_ACTION_CONTRACTS,
    BODY_ACTION_TOOL_NAMES,
    BODY_TARGET_TRUSTED_SEMANTIC,
)


# Mission GUI actions include the physical virtual-body surface
# plus application launch, which is outcome-bearing GUI state
# but is not itself a body effector.
MISSION_GUI_ACTION_TOOLS = (
    frozenset(
        {
            "open_app",
        }
    )
    | BODY_ACTION_TOOL_NAMES
)


MISSION_SEMANTIC_TARGET_TOOLS = frozenset(
    tool_name
    for tool_name, contract
    in BODY_ACTION_CONTRACTS.items()
    if contract.target_binding
    == BODY_TARGET_TRUSTED_SEMANTIC
)


def tool_names_for_capabilities(
    capability_registry: Any,
    capabilities: list[str] | tuple[str, ...] | None,
) -> frozenset[str]:
    """
    Resolve the exact runtime tool names exposed by a set of
    semantic capabilities.

    This function grants no permission.
    """

    names: set[str] = set()

    for capability in capabilities or []:
        if type(capability) is not str:
            continue

        capability = capability.strip()

        if not capability:
            continue

        try:
            tools = (
                capability_registry.tools_for(
                    capability
                )
                or []
            )
        except Exception:
            continue

        for tool_name in tools:
            if type(tool_name) is not str:
                continue

            tool_name = (
                tool_name.strip()
            )

            if tool_name:
                names.add(
                    tool_name
                )

    return frozenset(
        names
    )


def gui_tool_names_for_capabilities(
    capability_registry: Any,
    capabilities: list[str] | tuple[str, ...] | None,
) -> frozenset[str]:
    """
    Return only physical/outcome-bearing GUI tools exposed by
    the supplied capabilities.
    """

    return frozenset(
        tool_name
        for tool_name in tool_names_for_capabilities(
            capability_registry,
            capabilities,
        )
        if tool_name in MISSION_GUI_ACTION_TOOLS
    )


def validate_planned_tool_binding(
    capability_registry: Any,
    capabilities: list[str] | tuple[str, ...] | None,
    planned_tool: object,
) -> tuple[bool, str]:
    """
    Validate the planner's durable tool binding.

    Any mission step whose capabilities expose a physical GUI
    action must bind exactly one such tool before execution.

    This validates planning structure only.
    It does not grant execution permission.
    """

    if type(planned_tool) is not str:
        return (
            False,
            "Mission planned_tool must be a string.",
        )

    planned_tool = (
        planned_tool.strip()
    )

    allowed_tools = (
        tool_names_for_capabilities(
            capability_registry,
            capabilities,
        )
    )

    gui_tools = (
        gui_tool_names_for_capabilities(
            capability_registry,
            capabilities,
        )
    )

    if gui_tools:
        if not planned_tool:
            return (
                False,
                "Mission step exposes GUI actions but has no "
                "planner-bound GUI tool.",
            )

        if planned_tool not in gui_tools:
            return (
                False,
                f"Planned GUI tool '{planned_tool}' is not "
                "exposed by the mission step's required "
                "capabilities.",
            )

        return True, ""

    if planned_tool:
        if planned_tool not in allowed_tools:
            return (
                False,
                f"Planned tool '{planned_tool}' is not exposed "
                "by the mission step's required capabilities.",
            )

    return True, ""


def validate_runtime_gui_tool_binding(
    capability_registry: Any,
    capabilities: list[str] | tuple[str, ...] | None,
    planned_tool: object,
    selected_tool: object,
) -> tuple[bool, str]:
    """
    Enforce planner → runtime GUI tool identity.

    A runtime model may choose arguments for the bound GUI tool,
    but may not substitute another GUI action class.
    """

    valid, error = (
        validate_planned_tool_binding(
            capability_registry,
            capabilities,
            planned_tool,
        )
    )

    if not valid:
        return valid, error

    if type(selected_tool) is not str:
        return (
            False,
            "Runtime-selected tool must be a string.",
        )

    selected_tool = (
        selected_tool.strip()
    )

    planned_tool = (
        planned_tool.strip()
    )

    gui_tools = (
        gui_tool_names_for_capabilities(
            capability_registry,
            capabilities,
        )
    )

    if gui_tools:
        if selected_tool != planned_tool:
            return (
                False,
                f"Runtime GUI tool '{selected_tool}' does not "
                f"match planner-bound tool "
                f"'{planned_tool}'.",
            )

    if (
        selected_tool in MISSION_GUI_ACTION_TOOLS
        and selected_tool not in gui_tools
    ):
        return (
            False,
            f"Runtime GUI tool '{selected_tool}' is not "
            "grounded by the mission step's capabilities.",
        )

    return True, ""
