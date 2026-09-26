from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable

from app.agent.gui_action_grounding import (
    MISSION_GUI_ACTION_TOOLS,
)


GUI_AUTHORITY_EXPLICIT = "explicit_goal"
GUI_AUTHORITY_CONFIRMED = "confirmed_expansion"

VALID_GUI_AUTHORITIES = frozenset(
    {
        GUI_AUTHORITY_EXPLICIT,
        GUI_AUTHORITY_CONFIRMED,
    }
)

GUI_AUTHORITY_CONFIRMATION_TOOL = (
    "mission_gui_authority_expansion"
)


@dataclass(
    frozen=True
)
class GuiPlanAuthorityDecision:

    allowed: bool
    reason: str = ""
    explicit_steps: tuple[str, ...] = ()
    confirmed_steps: tuple[str, ...] = ()


def _normalized_goal(
    goal: object,
) -> str:
    return " ".join(
        str(
            goal
            or ""
        )
        .strip()
        .lower()
        .split()
    )


def explicitly_authorizes_gui_action_class(
    goal: object,
    planned_tool: object,
) -> bool:
    """
    Conservatively determine whether the ORIGINAL user goal
    explicitly authorizes a GUI action class.

    This grants action-class authority only.

    It does NOT authorize:
    - coordinates
    - typed content
    - application identity
    - keyboard key identity
    - target identity
    - tool execution
    - permission bypass
    """

    request = _normalized_goal(
        goal
    )

    if not request:
        return False

    if type(planned_tool) is not str:
        return False

    planned_tool = (
        planned_tool.strip()
    )

    if planned_tool not in MISSION_GUI_ACTION_TOOLS:
        return False

    if planned_tool in {
        "move_mouse",
        "move_mouse_vision",
    }:
        return any(
            phrase in request
            for phrase in (
                "move the mouse",
                "move mouse",
                "move the cursor",
                "move cursor",
                "position the mouse",
                "position the cursor",
            )
        )

    if planned_tool in {
        "click",
        "click_vision",
    }:
        return bool(
            re.search(
                r"\b(click|double[- ]?click|tap)\b",
                request,
            )
            or re.search(
                r"\bpress\s+(?:the\s+)?"
                r"(?:button|link|control)\b",
                request,
            )
        )

    if planned_tool in {
        "hold_mouse",
        "hold_mouse_vision",
    }:
        return bool(
            re.search(
                r"\b(?:hold(?:\s+down)?|press\s+and\s+hold)"
                r"\s+(?:the\s+)?"
                r"(?:(?:left|right|middle)\s+)?"
                r"(?:mouse\s+)?button\b",
                request,
            )
        )

    if planned_tool == "release_mouse":
        return bool(
            re.search(
                r"\b(?:release|let\s+go\s+of)"
                r"\s+(?:the\s+)?"
                r"(?:(?:left|right|middle)\s+)?"
                r"(?:mouse\s+)?button\b",
                request,
            )
        )

    if planned_tool == "scroll":
        return bool(
            re.search(
                r"\bscroll\b",
                request,
            )
        )

    if planned_tool == "press_key":
        key_names = (
            "enter",
            "return",
            "escape",
            "esc",
            "tab",
            "space",
            "backspace",
            "delete",
            "up",
            "down",
            "left",
            "right",
        )

        key_pattern = "|".join(
            re.escape(
                key
            )
            for key in key_names
        )

        return bool(
            re.search(
                rf"\b(?:press|hit)\s+"
                rf"(?:the\s+)?"
                rf"(?:{key_pattern})"
                rf"(?:\s+key)?\b",
                request,
            )
            or re.search(
                r"\bpress\s+(?:a\s+)?key\b",
                request,
            )
        )

    if planned_tool == "type_text":

        # Deliberately reject vague language such as:
        # "write me an email".
        #
        # High-level goals may still use type_text after one
        # explicit plan-authority confirmation.

        explicit_patterns = (
            r"\btype\b.+\b(?:into|inside)\b",
            r"\btype\s+(?:this|the following)\b",
            r"\benter\b.+\b(?:into|inside)\b",
            r"\binput\b.+\b(?:into|inside)\b",
            r"\bfill\s+(?:in|out)\b",
        )

        return any(
            re.search(
                pattern,
                request,
            )
            is not None
            for pattern in explicit_patterns
        )

    if planned_tool == "open_app":

        known_app_markers = (
            "chrome",
            "google chrome",
            "safari",
            "finder",
            "terminal",
            "vscode",
            "vs code",
            "visual studio code",
            "spotify",
            "discord",
            "slack",
            "messages",
            "imessage",
            "mail",
            "apple mail",
        )

        action_marker = bool(
            re.search(
                r"\b(open|launch|start)\b",
                request,
            )
        )

        if not action_marker:
            return False

        if any(
            app in request
            for app in known_app_markers
        ):
            return True

        return bool(
            re.search(
                r"\b(?:app|application|program)\b",
                request,
            )
        )

    return False


def validate_runtime_gui_authority(
    planned_tool: object,
    gui_authority: object,
) -> tuple[bool, str]:
    """
    Ensure persisted GUI action-class authority exists before
    a physical GUI mission step may execute.

    This does not grant tool permission.
    """

    if type(planned_tool) is not str:
        return (
            False,
            "Mission planned_tool must be a string.",
        )

    planned_tool = (
        planned_tool.strip()
    )

    if planned_tool not in MISSION_GUI_ACTION_TOOLS:

        if gui_authority in {
            None,
            "",
        }:
            return True, ""

        return (
            False,
            "Non-GUI mission step cannot carry GUI authority.",
        )

    if type(gui_authority) is not str:
        return (
            False,
            "GUI authority must be a string.",
        )

    gui_authority = (
        gui_authority.strip()
    )

    if gui_authority not in VALID_GUI_AUTHORITIES:
        return (
            False,
            "GUI mission step has no valid human-derived "
            "action-class authority.",
        )

    return True, ""


def authorize_plan_gui_actions(
    *,
    goal: str,
    plan: Any,
    confirmation_fn: (
        Callable[[str, dict], bool]
        | None
    ),
) -> GuiPlanAuthorityDecision:
    """
    Bind human-derived action-class authority to a fresh plan.

    The planner cannot assign this authority itself.

    Explicitly grounded action classes are accepted directly.
    Planner-introduced GUI action classes require one explicit,
    fail-closed confirmation covering the expansion set.

    Confirmation here authorizes only the plan's GUI action
    classes. It does NOT approve eventual tool execution.
    """

    if not isinstance(
        goal,
        str,
    ) or not goal.strip():
        return GuiPlanAuthorityDecision(
            allowed=False,
            reason=(
                "Mission goal is required for GUI authority "
                "validation."
            ),
        )

    steps = list(
        getattr(
            plan,
            "steps",
            [],
        )
        or []
    )

    explicit_steps: list[str] = []
    expansion_steps = []

    for step in steps:

        planned_tool = str(
            getattr(
                step,
                "planned_tool",
                "",
            )
            or ""
        ).strip()

        # Authority metadata is trusted-runtime state.
        # Never inherit anything a planner-shaped object may
        # already contain.
        step.gui_authority = ""
        step.gui_authority_goal = ""

        if planned_tool not in MISSION_GUI_ACTION_TOOLS:
            continue

        if explicitly_authorizes_gui_action_class(
            goal,
            planned_tool,
        ):
            step.gui_authority = (
                GUI_AUTHORITY_EXPLICIT
            )
            step.gui_authority_goal = goal

            explicit_steps.append(
                str(
                    getattr(
                        step,
                        "id",
                        "",
                    )
                    or ""
                )
            )

            continue

        expansion_steps.append(
            step
        )

    if not expansion_steps:
        return GuiPlanAuthorityDecision(
            allowed=True,
            explicit_steps=tuple(
                explicit_steps
            ),
        )

    if confirmation_fn is None:
        return GuiPlanAuthorityDecision(
            allowed=False,
            reason=(
                "Mission plan introduces GUI action classes "
                "that are not explicit in the user goal, and "
                "no confirmation boundary is available."
            ),
            explicit_steps=tuple(
                explicit_steps
            ),
        )

    expansion_summary = [
        {
            "step_id": str(
                getattr(
                    step,
                    "id",
                    "",
                )
                or ""
            ),
            "objective": str(
                getattr(
                    step,
                    "objective",
                    "",
                )
                or ""
            ),
            "planned_tool": str(
                getattr(
                    step,
                    "planned_tool",
                    "",
                )
                or ""
            ),
        }
        for step in expansion_steps
    ]

    confirmation_arguments = {
        "goal": goal,
        "authority_scope": (
            "gui_action_classes_only"
        ),
        "proposed_steps": expansion_summary,
        "notice": (
            "Approval allows these GUI action classes to "
            "remain in the mission plan. It does not approve "
            "tool execution, coordinates, typed content, "
            "targets, keys, or bypass runtime permissions."
        ),
    }

    try:
        approved = bool(
            confirmation_fn(
                GUI_AUTHORITY_CONFIRMATION_TOOL,
                confirmation_arguments,
            )
        )

    except Exception:
        approved = False

    if not approved:
        return GuiPlanAuthorityDecision(
            allowed=False,
            reason=(
                "Mission plan GUI authority expansion was "
                "not approved."
            ),
            explicit_steps=tuple(
                explicit_steps
            ),
        )

    confirmed_steps: list[str] = []

    for step in expansion_steps:
        step.gui_authority = (
            GUI_AUTHORITY_CONFIRMED
        )
        step.gui_authority_goal = goal

        confirmed_steps.append(
            str(
                getattr(
                    step,
                    "id",
                    "",
                )
                or ""
            )
        )

    return GuiPlanAuthorityDecision(
        allowed=True,
        explicit_steps=tuple(
            explicit_steps
        ),
        confirmed_steps=tuple(
            confirmed_steps
        ),
    )
