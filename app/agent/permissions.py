from enum import Enum


# =========================================================
# PERMISSION LEVELS
# =========================================================

class PermissionLevel(Enum):

    SAFE = "safe"

    USER_AUTHORIZED = "user_authorized"

    DANGEROUS = "dangerous"


# =========================================================
# TOOL PERMISSIONS
# =========================================================

TOOL_PERMISSIONS = {

    # -----------------------------------------------------
    # SAFE
    # -----------------------------------------------------

    "inspect_system": PermissionLevel.SAFE,
    "list_files": PermissionLevel.SAFE,
    "open_file": PermissionLevel.SAFE,
    "recall": PermissionLevel.SAFE,
    "screenshot_screen": PermissionLevel.SAFE,
    "analyze_screen": PermissionLevel.SAFE,
    "web_search": PermissionLevel.SAFE,
    "fetch_webpage": PermissionLevel.SAFE,

    # -----------------------------------------------------
    # USER AUTHORIZED
    #
    # These can execute when the user's request clearly
    # asks KUMA to perform the action.
    # -----------------------------------------------------

    # Sensitive read-only personal context; current request grounding
    # and the user's local opt-in are both required.
    "get_current_location": PermissionLevel.USER_AUTHORIZED,

    "remember": PermissionLevel.USER_AUTHORIZED,
    "forget": PermissionLevel.USER_AUTHORIZED,
    "open_app": PermissionLevel.USER_AUTHORIZED,
    "move_mouse": PermissionLevel.USER_AUTHORIZED,
    "move_mouse_vision": PermissionLevel.USER_AUTHORIZED,
    "click": PermissionLevel.USER_AUTHORIZED,
    "click_vision": PermissionLevel.USER_AUTHORIZED,
    "hold_mouse": PermissionLevel.USER_AUTHORIZED,
    "hold_mouse_vision": PermissionLevel.USER_AUTHORIZED,
    "release_mouse": PermissionLevel.USER_AUTHORIZED,
    "type_text": PermissionLevel.USER_AUTHORIZED,
    "press_key": PermissionLevel.USER_AUTHORIZED,
    "scroll": PermissionLevel.USER_AUTHORIZED,

    # -----------------------------------------------------
    # DANGEROUS
    #
    # These will eventually require explicit UI approval.
    # -----------------------------------------------------

    "delete_file": PermissionLevel.DANGEROUS,
    "execute_command": PermissionLevel.DANGEROUS,

}


# =========================================================
# GET PERMISSION
# =========================================================

def has_explicit_permission(tool_name: str) -> bool:
    """Return whether a tool has canonical permission metadata."""

    if type(tool_name) is not str:
        return False

    tool_name = tool_name.strip()

    return bool(tool_name) and tool_name in TOOL_PERMISSIONS


def require_explicit_permission(tool_name: str) -> PermissionLevel:
    """Return canonical permission metadata or reject registration.

    KUMA's production tool-registration boundary must never admit a tool
    whose permission class was forgotten. Generic executor adapters still
    support synthetic/injected tool names for isolated tests, but canonical
    runtime registration calls this helper and therefore fails closed.
    """

    if not has_explicit_permission(tool_name):
        raise ValueError(
            "Tool requires an explicit permission classification: "
            f"{tool_name!r}"
        )

    return TOOL_PERMISSIONS[tool_name.strip()]


def get_permission_level(tool_name: str):
    """Return the execution permission level for a tool identity.

    Missing or malformed identities fail closed. Unknown non-empty string
    identities retain the legacy USER_AUTHORIZED fallback for injected test
    adapters; production KUMA registration is separately fail-closed through
    require_explicit_permission().
    """

    if type(tool_name) is not str:
        return PermissionLevel.DANGEROUS

    tool_name = tool_name.strip()

    if not tool_name:
        return PermissionLevel.DANGEROUS

    return TOOL_PERMISSIONS.get(
        tool_name,
        PermissionLevel.USER_AUTHORIZED,
    )


def get_recovery_permission_level(
    tool_name: str,
    *,
    tool_known: bool | None = None,
):
    """
    Classify tool risk for AUTOMATIC RECOVERY.

    Recovery is stricter than normal execution when identity is
    ambiguous:

    - missing or malformed tool identity -> DANGEROUS
    - runtime explicitly says the tool is unknown -> DANGEROUS
    - otherwise preserve the existing permission classification

    tool_known=None is intentionally supported for isolated test
    adapters that do not expose a runtime tool registry.
    """

    if type(tool_name) is not str:
        return PermissionLevel.DANGEROUS

    tool_name = tool_name.strip()

    if not tool_name:
        return PermissionLevel.DANGEROUS

    if tool_known is False:
        return PermissionLevel.DANGEROUS

    return get_permission_level(
        tool_name
    )


# =========================================================
# CHECKS
# =========================================================

def requires_confirmation(tool_name: str) -> bool:

    return (
        get_permission_level(tool_name)
        == PermissionLevel.DANGEROUS
    )


def is_dangerous(tool_name: str) -> bool:

    return (
        get_permission_level(tool_name)
        == PermissionLevel.DANGEROUS
    )


def is_safe(tool_name: str) -> bool:

    return (
        get_permission_level(tool_name)
        == PermissionLevel.SAFE
    )


def is_user_authorized(tool_name: str) -> bool:

    return (
        get_permission_level(tool_name)
        == PermissionLevel.USER_AUTHORIZED
    )