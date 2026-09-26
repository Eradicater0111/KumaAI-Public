from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


# =========================================================
# VIRTUAL BODY EFFECTORS
# =========================================================

BODY_EFFECTOR_POINTER = "pointer"
BODY_EFFECTOR_KEYBOARD = "keyboard"
BODY_EFFECTOR_VIEWPORT = "viewport"

VALID_BODY_EFFECTORS = frozenset(
    {
        BODY_EFFECTOR_POINTER,
        BODY_EFFECTOR_KEYBOARD,
        BODY_EFFECTOR_VIEWPORT,
    }
)


# =========================================================
# BODY ACTION CLASSES
# =========================================================

BODY_ACTION_MOVE = "move"
BODY_ACTION_CLICK = "click"
BODY_ACTION_HOLD = "hold"
BODY_ACTION_RELEASE = "release"
BODY_ACTION_TYPE_TEXT = "type_text"
BODY_ACTION_PRESS_KEY = "press_key"
BODY_ACTION_SCROLL = "scroll"

VALID_BODY_ACTIONS = frozenset(
    {
        BODY_ACTION_MOVE,
        BODY_ACTION_CLICK,
        BODY_ACTION_HOLD,
        BODY_ACTION_RELEASE,
        BODY_ACTION_TYPE_TEXT,
        BODY_ACTION_PRESS_KEY,
        BODY_ACTION_SCROLL,
    }
)


# =========================================================
# COORDINATE / TARGET BINDING
# =========================================================

BODY_COORDINATE_NONE = "none"
BODY_COORDINATE_NATIVE_SCREEN = "native_screen"
BODY_COORDINATE_TRUSTED_VISION = "trusted_vision"

VALID_BODY_COORDINATE_SPACES = frozenset(
    {
        BODY_COORDINATE_NONE,
        BODY_COORDINATE_NATIVE_SCREEN,
        BODY_COORDINATE_TRUSTED_VISION,
    }
)

# Raw native coordinates are physically bounded but do not
# prove semantic target identity.
BODY_TARGET_RAW_NATIVE = "raw_native_coordinate"

# B8 establishes the exact semantic target and derives the
# executable point independently of the model proposal.
BODY_TARGET_TRUSTED_SEMANTIC = "trusted_semantic_target"

# A raw hold acts on the pointer's current physical location.
# This identifies a body-relative target, not a semantic UI target.
BODY_TARGET_CURRENT_POINTER = "current_pointer"

# Release acts exclusively on KUMA's live process-local finger
# state. Planner/model arguments never provide button identity.
BODY_TARGET_OWNED_BUTTON_STATE = "owned_button_state"

# The physical tool currently acts against ambient foreground
# desktop state without a trusted step-local element binding.
#
# Phase 8 will progressively replace this state for keyboard
# and viewport actions with explicit trusted body targeting.
BODY_TARGET_UNBOUND_CONTEXT = "unbound_frontmost_context"

VALID_BODY_TARGET_BINDINGS = frozenset(
    {
        BODY_TARGET_RAW_NATIVE,
        BODY_TARGET_TRUSTED_SEMANTIC,
        BODY_TARGET_CURRENT_POINTER,
        BODY_TARGET_OWNED_BUTTON_STATE,
        BODY_TARGET_UNBOUND_CONTEXT,
    }
)


# =========================================================
# ACTION CONTRACT
# =========================================================

@dataclass(
    frozen=True
)
class BodyActionContract:
    """
    Declarative description of one existing physical KUMA action.

    This contract grants no authority, performs no input, and does
    not replace MissionService permissions or verification.
    """

    tool_name: str
    effector: str
    action: str
    coordinate_space: str
    target_binding: str

    def __post_init__(
        self,
    ) -> None:

        if (
            type(self.tool_name) is not str
            or not self.tool_name
            or self.tool_name != self.tool_name.strip()
        ):
            raise ValueError(
                "Body action requires an exact tool name."
            )

        if self.effector not in VALID_BODY_EFFECTORS:
            raise ValueError(
                "Body action has an unknown effector."
            )

        if self.action not in VALID_BODY_ACTIONS:
            raise ValueError(
                "Body action has an unknown action class."
            )

        if (
            self.coordinate_space
            not in VALID_BODY_COORDINATE_SPACES
        ):
            raise ValueError(
                "Body action has an unknown coordinate space."
            )

        if (
            self.target_binding
            not in VALID_BODY_TARGET_BINDINGS
        ):
            raise ValueError(
                "Body action has an unknown target binding."
            )


_BODY_ACTION_CONTRACTS = {
    "move_mouse": BodyActionContract(
        tool_name="move_mouse",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_MOVE,
        coordinate_space=(
            BODY_COORDINATE_NATIVE_SCREEN
        ),
        target_binding=(
            BODY_TARGET_RAW_NATIVE
        ),
    ),
    "move_mouse_vision": BodyActionContract(
        tool_name="move_mouse_vision",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_MOVE,
        coordinate_space=(
            BODY_COORDINATE_TRUSTED_VISION
        ),
        target_binding=(
            BODY_TARGET_TRUSTED_SEMANTIC
        ),
    ),
    "click": BodyActionContract(
        tool_name="click",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_CLICK,
        coordinate_space=(
            BODY_COORDINATE_NATIVE_SCREEN
        ),
        target_binding=(
            BODY_TARGET_RAW_NATIVE
        ),
    ),
    "click_vision": BodyActionContract(
        tool_name="click_vision",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_CLICK,
        coordinate_space=(
            BODY_COORDINATE_TRUSTED_VISION
        ),
        target_binding=(
            BODY_TARGET_TRUSTED_SEMANTIC
        ),
    ),
    "hold_mouse": BodyActionContract(
        tool_name="hold_mouse",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_HOLD,
        coordinate_space=(
            BODY_COORDINATE_NONE
        ),
        target_binding=(
            BODY_TARGET_CURRENT_POINTER
        ),
    ),
    "hold_mouse_vision": BodyActionContract(
        tool_name="hold_mouse_vision",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_HOLD,
        coordinate_space=(
            BODY_COORDINATE_TRUSTED_VISION
        ),
        target_binding=(
            BODY_TARGET_TRUSTED_SEMANTIC
        ),
    ),
    "release_mouse": BodyActionContract(
        tool_name="release_mouse",
        effector=BODY_EFFECTOR_POINTER,
        action=BODY_ACTION_RELEASE,
        coordinate_space=(
            BODY_COORDINATE_NONE
        ),
        target_binding=(
            BODY_TARGET_OWNED_BUTTON_STATE
        ),
    ),
    "type_text": BodyActionContract(
        tool_name="type_text",
        effector=BODY_EFFECTOR_KEYBOARD,
        action=BODY_ACTION_TYPE_TEXT,
        coordinate_space=(
            BODY_COORDINATE_NONE
        ),
        target_binding=(
            BODY_TARGET_UNBOUND_CONTEXT
        ),
    ),
    "press_key": BodyActionContract(
        tool_name="press_key",
        effector=BODY_EFFECTOR_KEYBOARD,
        action=BODY_ACTION_PRESS_KEY,
        coordinate_space=(
            BODY_COORDINATE_NONE
        ),
        target_binding=(
            BODY_TARGET_UNBOUND_CONTEXT
        ),
    ),
    "scroll": BodyActionContract(
        tool_name="scroll",
        effector=BODY_EFFECTOR_VIEWPORT,
        action=BODY_ACTION_SCROLL,
        coordinate_space=(
            BODY_COORDINATE_NONE
        ),
        target_binding=(
            BODY_TARGET_UNBOUND_CONTEXT
        ),
    ),
}

BODY_ACTION_CONTRACTS = (
    MappingProxyType(
        _BODY_ACTION_CONTRACTS
    )
)

BODY_ACTION_TOOL_NAMES = frozenset(
    BODY_ACTION_CONTRACTS
)


def body_action_contract_for(
    tool_name: object,
) -> BodyActionContract | None:
    """
    Return the declarative body contract for an exact tool identity.

    Unknown or malformed tool identities are not body actions.
    """

    if type(tool_name) is not str:
        return None

    if (
        not tool_name
        or tool_name != tool_name.strip()
    ):
        return None

    return BODY_ACTION_CONTRACTS.get(
        tool_name
    )


def is_body_action_tool(
    tool_name: object,
) -> bool:
    return (
        body_action_contract_for(
            tool_name
        )
        is not None
    )


# =========================================================
# VIRTUAL BODY STATE
# =========================================================

@dataclass(
    frozen=True
)
class VirtualBodyState:
    """
    Immutable snapshot-shaped state for KUMA's local virtual body.

    All fields are descriptive only.

    Missing information remains unknown rather than being inferred.
    In particular, this contract intentionally does not claim a
    focused window or focused accessibility element.

    It grants no permission and performs no action.
    """

    platform: str = "macos"

    frontmost_application_pid: int | None = None

    frontmost_application_bundle_id: str | None = None

    screen_observation_id: str | None = None

    pointer_native_point: (
        tuple[int, int]
        | None
    ) = None

    def __post_init__(
        self,
    ) -> None:

        if self.platform != "macos":
            raise ValueError(
                "Virtual body platform must currently be macos."
            )

        pid = (
            self.frontmost_application_pid
        )

        bundle = (
            self.frontmost_application_bundle_id
        )

        # Application identity is atomic. A PID without bundle ID,
        # or a bundle ID without PID, must remain unknown.
        if (pid is None) != (bundle is None):
            raise ValueError(
                "Frontmost application identity requires both "
                "PID and bundle ID."
            )

        if pid is not None:
            if (
                type(pid) is not int
                or pid <= 0
            ):
                raise ValueError(
                    "Frontmost application PID must be "
                    "a positive integer."
                )

            if (
                type(bundle) is not str
                or not bundle.strip()
                or bundle != bundle.strip()
            ):
                raise ValueError(
                    "Frontmost application bundle ID must "
                    "be an exact non-empty string."
                )

        observation_id = (
            self.screen_observation_id
        )

        if observation_id is not None:
            if (
                type(observation_id) is not str
                or not observation_id.strip()
                or observation_id
                != observation_id.strip()
            ):
                raise ValueError(
                    "Screen observation ID must be an exact "
                    "non-empty string when known."
                )

        point = (
            self.pointer_native_point
        )

        if point is not None:
            if (
                type(point) is not tuple
                or len(point) != 2
            ):
                raise ValueError(
                    "Pointer native point must be an exact "
                    "(x, y) tuple."
                )

            x, y = point

            if (
                type(x) is not int
                or type(y) is not int
                or x < 0
                or y < 0
            ):
                raise ValueError(
                    "Pointer native coordinates must be "
                    "non-negative integers."
                )

    @property
    def application_known(
        self,
    ) -> bool:
        return (
            self.frontmost_application_pid
            is not None
        )

    @property
    def screen_known(
        self,
    ) -> bool:
        return (
            self.screen_observation_id
            is not None
        )

    @property
    def pointer_known(
        self,
    ) -> bool:
        return (
            self.pointer_native_point
            is not None
        )
