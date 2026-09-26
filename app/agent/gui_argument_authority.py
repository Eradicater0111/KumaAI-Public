from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from app.agent.gui_action_grounding import (
    MISSION_GUI_ACTION_TOOLS,
)


GUI_ARGUMENT_CONFIRMATION_TOOL = (
    "mission_gui_argument_authority"
)


@dataclass(frozen=True)
class GuiArgumentAuthorityDecision:
    allowed: bool
    reason: str = ""
    grounded_in_goal: bool = False
    confirmed: bool = False
    semantic_target_verified: bool = False


def _goal_text(
    value: object,
) -> str:
    if type(value) is not str:
        return ""

    return value.strip()


def _normalized_spaces(
    value: object,
) -> str:
    if type(value) is not str:
        return ""

    return " ".join(
        value.strip().split()
    )


def _app_argument(
    arguments: dict,
) -> str:
    value = arguments.get(
        "app_name",
        arguments.get(
            "name",
            "",
        ),
    )

    if type(value) is not str:
        return ""

    return value.strip()


def _app_identity_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    app_name = _app_argument(
        arguments
    )

    if not app_name:
        return False

    request = goal.lower()
    canonical = app_name.lower()

    if not re.search(
        r"\b(open|launch|start)\b",
        request,
    ):
        return False

    aliases = {
        "google chrome": (
            "google chrome",
            "chrome",
        ),
        "visual studio code": (
            "visual studio code",
            "vs code",
            "vscode",
            "code",
        ),
        "terminal": (
            "terminal",
            "mac terminal",
        ),
        "safari": (
            "safari",
        ),
        "finder": (
            "finder",
        ),
        "spotify": (
            "spotify",
        ),
        "discord": (
            "discord",
        ),
        "slack": (
            "slack",
        ),
        "messages": (
            "messages",
            "imessage",
        ),
        "mail": (
            "mail",
            "apple mail",
        ),
    }

    candidates = aliases.get(
        canonical,
        (
            canonical,
        ),
    )

    return any(
        re.search(
            rf"(?<!\w)"
            rf"{re.escape(candidate)}"
            rf"(?!\w)",
            request,
        )
        is not None
        for candidate in candidates
    )


def _explicit_text_payloads(
    goal: str,
) -> tuple[str, ...]:
    """
    Extract only syntactically explicit typing payloads.

    This intentionally does NOT treat arbitrary words appearing
    somewhere in the goal as authorization to type those words.
    """

    candidates: list[str] = []

    # Explicit quoted payloads attached to an actual
    # typing/entry verb.
    quote_patterns = (
        r'\b(?:type|enter|input)\s+"([^"]+)"',
        r"\b(?:type|enter|input)\s+'([^']+)'",
        r'\b(?:type|enter|input)\s+“([^”]+)”',
    )

    for pattern in quote_patterns:
        for match in re.finditer(
            pattern,
            goal,
            re.IGNORECASE,
        ):
            value = _normalized_spaces(
                match.group(1)
            )

            if value:
                candidates.append(
                    value
                )

    # "type hello into the box"
    # "enter hello into the field"
    # "input hello inside the form"
    into_pattern = re.compile(
        r"\b(?:type|enter|input)\s+"
        r"(.+?)\s+"
        r"(?:into|inside)\b",
        re.IGNORECASE,
    )

    for match in into_pattern.finditer(
        goal
    ):
        value = _normalized_spaces(
            match.group(1)
        )

        if value:
            candidates.append(
                value
            )

    # "type this: hello"
    # "type the following: hello"
    colon_pattern = re.compile(
        r"\btype\s+"
        r"(?:this|the\s+following)\s*:\s*"
        r"(.+)$",
        re.IGNORECASE,
    )

    match = colon_pattern.search(
        goal
    )

    if match is not None:
        value = _normalized_spaces(
            match.group(1)
        )

        if value:
            candidates.append(
                value
            )

    return tuple(
        dict.fromkeys(
            candidates
        )
    )


def _type_text_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    text = arguments.get(
        "text"
    )

    if type(text) is not str:
        return False

    payload = _normalized_spaces(
        text
    )

    if not payload:
        return False

    return payload in _explicit_text_payloads(
        goal
    )


def _press_key_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    key = arguments.get(
        "key"
    )

    if type(key) is not str:
        return False

    key = key.strip().lower()

    if not key:
        return False

    aliases = {
        "enter": (
            "enter",
            "return",
        ),
        "return": (
            "return",
            "enter",
        ),
        "esc": (
            "esc",
            "escape",
        ),
        "escape": (
            "escape",
            "esc",
        ),
        "space": (
            "space",
            "spacebar",
        ),
    }

    candidates = aliases.get(
        key,
        (
            key,
        ),
    )

    request = goal.lower()

    for candidate in candidates:
        escaped = re.escape(
            candidate
        )

        if re.search(
            rf"\b(?:press|hit)\s+"
            rf"(?:the\s+)?"
            rf"{escaped}"
            rf"(?:\s+key)?\b",
            request,
        ):
            return True

    return False


def _scroll_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    amount = arguments.get(
        "amount"
    )

    if type(amount) is not int:
        return False

    if amount == 0:
        return True

    request = goal.lower()

    expected_direction = (
        "up"
        if amount > 0
        else "down"
    )

    magnitude = abs(
        amount
    )

    patterns = (
        rf"\bscroll\s+{expected_direction}"
        rf"(?:\s+by)?\s+{magnitude}\b",
        rf"\bscroll\s+{magnitude}\s+"
        rf"{expected_direction}\b",
    )

    return any(
        re.search(
            pattern,
            request,
        )
        is not None
        for pattern in patterns
    )


def _explicit_coordinates(
    goal: str,
) -> tuple[tuple[int, int], ...]:
    coordinates: list[
        tuple[int, int]
    ] = []

    patterns = (
        r"\bx\s*=\s*(-?\d+)"
        r"\s*[,; ]+\s*"
        r"y\s*=\s*(-?\d+)\b",

        r"\(\s*(-?\d+)"
        r"\s*,\s*(-?\d+)\s*\)",

        r"\bat\s+(-?\d+)"
        r"\s*,\s*(-?\d+)\b",
    )

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            goal,
            re.IGNORECASE,
        ):
            try:
                coordinates.append(
                    (
                        int(
                            match.group(1)
                        ),
                        int(
                            match.group(2)
                        ),
                    )
                )
            except Exception:
                continue

    return tuple(
        dict.fromkeys(
            coordinates
        )
    )


def _hold_button_modifier_grounded(
    goal: str,
    arguments: dict,
    *,
    trusted_target: bool,
) -> bool:
    """
    Ground only the hold action's exact button modifier.

    For trusted semantic holds, observation/x/y remain runtime
    target-proof values and are not treated as human coordinates.
    """

    if type(arguments) is not dict:
        return False

    allowed_keys = (
        {
            "x",
            "y",
            "observation_id",
            "button",
        }
        if trusted_target
        else {
            "button",
        }
    )

    if set(arguments) - allowed_keys:
        return False

    if trusted_target:
        if (
            type(arguments.get("x")) is not int
            or type(arguments.get("y")) is not int
            or type(
                arguments.get(
                    "observation_id"
                )
            ) is not str
            or not arguments.get(
                "observation_id"
            )
        ):
            return False

    button = arguments.get(
        "button",
        "left",
    )

    if (
        type(button) is not str
        or button not in {
            "left",
            "right",
            "middle",
        }
    ):
        return False

    request = goal.lower()

    action_pattern = (
        r"\b(?:hold(?:\s+down)?|press\s+and\s+hold)"
        r"\s+(?:the\s+)?"
    )

    if button == "right":
        target_pattern = (
            r"right\s+(?:mouse\s+)?button\b"
        )

    elif button == "middle":
        target_pattern = (
            r"middle\s+(?:mouse\s+)?button\b"
        )

    else:
        target_pattern = (
            r"(?:(?:left\s+)?(?:mouse\s+)?button)\b"
        )

        if re.search(
            r"\b(?:right|middle)\s+"
            r"(?:mouse\s+)?button\b",
            request,
        ):
            return False

    return bool(
        re.search(
            action_pattern
            + target_pattern,
            request,
        )
    )


def _release_mouse_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    """
    Release accepts no planner/model button identity.

    Exact release identity comes only from live
    BODY_BUTTON_STATE at the physical boundary.
    """

    if (
        type(arguments) is not dict
        or arguments
    ):
        return False

    return bool(
        re.search(
            r"\b(?:release|let\s+go\s+of)"
            r"\s+(?:the\s+)?"
            r"(?:(?:left|right|middle)\s+)?"
            r"(?:mouse\s+)?button\b",
            goal.lower(),
        )
    )


def _move_mouse_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    x = arguments.get(
        "x"
    )
    y = arguments.get(
        "y"
    )

    if (
        type(x) is not int
        or type(y) is not int
    ):
        return False

    request = goal.lower()

    if not any(
        phrase in request
        for phrase in (
            "move the mouse",
            "move mouse",
            "move the cursor",
            "move cursor",
            "position the mouse",
            "position the cursor",
        )
    ):
        return False

    return (
        (
            x,
            y,
        )
        in _explicit_coordinates(
            goal
        )
    )


def _raw_click_grounded(
    goal: str,
    arguments: dict,
) -> bool:
    x = arguments.get(
        "x"
    )
    y = arguments.get(
        "y"
    )

    if (
        type(x) is not int
        or type(y) is not int
    ):
        return False

    if (
        (
            x,
            y,
        )
        not in _explicit_coordinates(
            goal
        )
    ):
        return False

    request = goal.lower()

    button = arguments.get(
        "button",
        "left",
    )

    clicks = arguments.get(
        "clicks",
        1,
    )

    if type(button) is not str:
        return False

    button = button.strip().lower()

    if button == "right":
        if "right click" not in request:
            return False

    elif button == "middle":
        if "middle click" not in request:
            return False

    elif button != "left":
        return False

    if type(clicks) is not int:
        return False

    if clicks == 2:
        if not re.search(
            r"\bdouble[- ]?click\b",
            request,
        ):
            return False

    elif clicks != 1:
        return False

    return bool(
        re.search(
            r"\bclick\b",
            request,
        )
    )


def arguments_grounded_in_human_goal(
    *,
    goal: object,
    tool_name: object,
    arguments: object,
) -> bool:
    """
    Determine whether authority-sensitive normalized arguments
    are directly grounded in the ORIGINAL human mission goal.

    Physical bounds remain the responsibility of 7.3A.

    click_vision deliberately returns False here because a trusted
    ScreenObservation proves provenance/geometry, not that a point
    semantically corresponds to the human-requested UI target.
    """

    goal = _goal_text(
        goal
    )

    if not goal:
        return False

    if type(tool_name) is not str:
        return False

    tool_name = tool_name.strip()

    if tool_name not in MISSION_GUI_ACTION_TOOLS:
        return True

    if type(arguments) is not dict:
        return False

    if tool_name == "open_app":
        return _app_identity_grounded(
            goal,
            arguments,
        )

    if tool_name == "type_text":
        return _type_text_grounded(
            goal,
            arguments,
        )

    if tool_name == "press_key":
        return _press_key_grounded(
            goal,
            arguments,
        )

    if tool_name == "scroll":
        return _scroll_grounded(
            goal,
            arguments,
        )

    if tool_name == "hold_mouse":
        return _hold_button_modifier_grounded(
            goal,
            arguments,
            trusted_target=False,
        )

    if tool_name == "hold_mouse_vision":
        # Semantic target proof provides WHERE. Model-proposed
        # target coordinates are never direct human grounding.
        return False

    if tool_name == "release_mouse":
        return _release_mouse_grounded(
            goal,
            arguments,
        )

    if tool_name == "move_mouse_vision":
        # Trusted semantic movement receives its executable
        # target from MissionService's fresh target-proof chain.
        # Model observation/x/y values are therefore proposals,
        # not directly human-grounded coordinates.
        return False

    if tool_name == "move_mouse":
        return _move_mouse_grounded(
            goal,
            arguments,
        )

    if tool_name == "click":
        return _raw_click_grounded(
            goal,
            arguments,
        )

    if tool_name == "click_vision":
        # 7.1 proves trusted observation binding, freshness,
        # geometry, and single use.
        #
        # It does NOT prove semantic target identity.
        return False

    return False


def authorize_runtime_gui_arguments(
    *,
    goal: str,
    tool_name: str,
    arguments: dict,
    confirmation_fn: (
        Callable[[str, dict], bool]
        | None
    ),
    semantic_target_verified: bool = False,
) -> GuiArgumentAuthorityDecision:
    """
    Authorize authority-sensitive normalized GUI arguments.

    Grounded arguments proceed directly.

    Otherwise the exact normalized argument set must pass a
    fail-closed human confirmation boundary.

    This does NOT:
    - bypass permission checks
    - execute the tool
    - prove semantic visual target identity
    - weaken 7.1 trusted observation binding
    - weaken 7.3A physical bounds
    """

    if tool_name not in MISSION_GUI_ACTION_TOOLS:
        return GuiArgumentAuthorityDecision(
            allowed=True,
            grounded_in_goal=True,
        )

    if (
        type(goal) is not str
        or not goal.strip()
    ):
        return GuiArgumentAuthorityDecision(
            allowed=False,
            reason=(
                "GUI argument authority has no trusted "
                "original human mission goal."
            ),
        )

    if type(arguments) is not dict:
        return GuiArgumentAuthorityDecision(
            allowed=False,
            reason=(
                "GUI argument authority requires normalized "
                "tool arguments."
            ),
        )

    # -------------------------------------------------
    # TRUSTED SEMANTIC TARGET ATTESTATION
    # -------------------------------------------------
    #
    # Only MissionService may set semantic_target_verified
    # after the read-only GuiTargetVerifier has returned a
    # satisfied result for the exact observation/x/y.
    #
    # Semantic target verification proves WHERE the intended
    # target is. It does not authorize stronger click
    # modifiers.
    #
    # Therefore only the canonical single-left click may
    # proceed without exact argument confirmation.
    # -------------------------------------------------

    if (
        tool_name == "move_mouse_vision"
        and semantic_target_verified is True
    ):
        duration = arguments.get(
            "duration",
            0.15,
        )

        # Target proof authorizes WHERE.
        #
        # The canonical/default movement duration may proceed
        # under already-authorized MOVE action-class authority.
        # Any stronger/non-default movement timing still requires
        # exact C2 human argument confirmation.
        if (
            type(duration) in {
                int,
                float,
            }
            and not isinstance(
                duration,
                bool,
            )
            and float(duration) == 0.15
        ):
            return GuiArgumentAuthorityDecision(
                allowed=True,
                semantic_target_verified=True,
            )

    if (
        tool_name == "hold_mouse_vision"
        and semantic_target_verified is True
    ):
        button = arguments.get(
            "button",
            "left",
        )

        # Trusted target proof authorizes WHERE.
        #
        # Canonical left-button HOLD may proceed under the
        # already-authorized HOLD action class.
        if (
            type(button) is str
            and button == "left"
        ):
            return GuiArgumentAuthorityDecision(
                allowed=True,
                semantic_target_verified=True,
            )

        # Right/middle are stronger modifiers and therefore
        # require exact grounding in the ORIGINAL human goal.
        if (
            type(button) is str
            and button in {
                "right",
                "middle",
            }
            and _hold_button_modifier_grounded(
                goal,
                arguments,
                trusted_target=True,
            )
        ):
            return GuiArgumentAuthorityDecision(
                allowed=True,
                grounded_in_goal=True,
                semantic_target_verified=True,
            )

    if (
        tool_name == "click_vision"
        and semantic_target_verified is True
    ):
        button = arguments.get(
            "button",
            "left",
        )

        clicks = arguments.get(
            "clicks",
            1,
        )

        if (
            type(button) is str
            and button.strip().lower() == "left"
            and type(clicks) is int
            and clicks == 1
        ):
            return GuiArgumentAuthorityDecision(
                allowed=True,
                semantic_target_verified=True,
            )

    if arguments_grounded_in_human_goal(
        goal=goal,
        tool_name=tool_name,
        arguments=arguments,
    ):
        return GuiArgumentAuthorityDecision(
            allowed=True,
            grounded_in_goal=True,
        )

    if confirmation_fn is None:
        return GuiArgumentAuthorityDecision(
            allowed=False,
            reason=(
                "GUI arguments are not explicitly grounded "
                "in the original human goal and no "
                "confirmation boundary is available."
            ),
        )

    confirmation_arguments = {
        "goal": goal,
        "planned_tool": tool_name,
        "authority_scope": (
            "exact_normalized_gui_arguments"
        ),
        "arguments": dict(
            arguments
        ),
        "notice": (
            "Approval authorizes only this exact normalized "
            "GUI argument set for this execution attempt. "
            "It does not bypass permissions and does not "
            "prove semantic visual-target identity."
        ),
    }

    try:
        approved = bool(
            confirmation_fn(
                GUI_ARGUMENT_CONFIRMATION_TOOL,
                confirmation_arguments,
            )
        )

    except Exception:
        approved = False

    if not approved:
        return GuiArgumentAuthorityDecision(
            allowed=False,
            reason=(
                "GUI runtime arguments were not grounded "
                "in the original human goal and were not "
                "explicitly approved."
            ),
        )

    return GuiArgumentAuthorityDecision(
        allowed=True,
        confirmed=True,
    )
