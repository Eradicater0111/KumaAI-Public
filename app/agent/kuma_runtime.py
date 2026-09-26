from app.agent.kuma_agent import KumaAgent

from app.agent.body_lifecycle import (
    release_owned_mouse_button_for_shutdown,
)

from app.tools.computer_tools import (
    screenshot_screen,
    analyze_screen,
    move_mouse,
    move_mouse_vision,
    click_at,
    click_vision,
    type_text,
    press_key,
    scroll,
    hold_mouse,
    hold_mouse_vision,
    release_mouse,
)

from app.tools.system_tools import (
    open_app,
    list_files,
    open_file,
    execute_command,
)

from app.tools.system_monitor import (
    inspect_system,
)

from app.tools.internet_tools import (
    web_search,
    fetch_webpage,
)

from app.tools.location_tools import (
    get_current_location,
)

from app.memory.manager import (
    remember,
    recall,
    forget,
)
from app.memory.completed_turn_observation_owner import (
    KumaMemoryV2CompletedTurnOwner,
)

from app.realtime.runtime import (
    get_realtime_runtime,
)

from app.integration_v2_live_turn_owner import (
    KumaIntegrationV2LiveTurnOwner,
)

from app.integration_v2_production_policy import (
    PRODUCTION_REALTIME_TRIGGER_POLICY,
)

from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner,
)


# =========================================================
# HUMAN-IN-THE-LOOP CONFIRMATION
# =========================================================

def confirm_dangerous_action(
    tool_name,
    arguments,
):
    """
    Ask the local user for explicit approval before a
    dangerous KUMA action is executed.

    Default is DENY. Only an explicit 'y' or 'yes'
    approves the action.
    """

    print()
    print("====================================")
    print("       KUMA ACTION CONFIRMATION")
    print("====================================")
    print()
    print("KUMA → ⚠️ This action is classified as dangerous.")
    print(f"KUMA → Tool      : {tool_name}")
    print(f"KUMA → Arguments : {arguments}")
    print()
    print("KUMA → This action will not run unless you approve it.")
    print()

    try:

        answer = input(
            "KUMA → Allow this action? [y/N]: "
        ).strip().lower()

    except (KeyboardInterrupt, EOFError):

        print()
        print("KUMA → Confirmation cancelled. Action denied.")
        return False

    if answer in {"y", "yes"}:

        print("KUMA → Confirmation received: APPROVED.")
        return True

    print("KUMA → Confirmation received: DENIED.")
    return False


# =========================================================
# CREATE KUMA
# =========================================================

# =========================================================
# KUMA REALTIME-1F — PASSIVE LOCATION OBSERVATION
# =========================================================

def get_current_location_with_realtime(
    detail: str = "approximate",
):
    """
    Preserve the existing USER_AUTHORIZED location tool while
    passively forwarding successful approximate evidence into the
    zero-authority realtime nervous system.
    """

    result = get_current_location(
        detail=detail,
    )

    try:
        get_realtime_runtime().observe_location_tool_result(
            result
        )
    except Exception as error:
        print(
            "KUMA REALTIME → location observation isolated: "
            + type(error).__name__
        )

    return result



def create_kuma():

    kuma = KumaAgent(
        confirmation_callback=confirm_dangerous_action,
    )

    # KUMA REALTIME-1F — LIVE PROCESS OWNER
    kuma.realtime_runtime = get_realtime_runtime()

    # ================================================
    # SYSTEM TOOLS
    # ================================================

    kuma.register_tool(
        "open_app",
        open_app,
    )

    kuma.register_tool(
        "list_files",
        list_files,
    )

    kuma.register_tool(
        "open_file",
        open_file,
    )

    kuma.register_tool(
        "inspect_system",
        inspect_system,
    )

    kuma.register_tool(
    "execute_command",
    execute_command,
    )

    
    # ================================================
    # KUMA LOCATION-1 — LIVE ROAMING LOCATION
    # ================================================

    kuma.register_tool(
        "get_current_location",
        get_current_location_with_realtime,
    )

    # ================================================
    # INTERNET KNOWLEDGE TOOLS
    # ================================================
    #
    # Read-only evidence retrieval. Internet content never
    # grants action authority.
    # ================================================

    kuma.register_tool(
        "web_search",
        web_search,
    )

    kuma.register_tool(
        "fetch_webpage",
        fetch_webpage,
    )

    # ================================================
    # COMPUTER CONTROL TOOLS
    # ================================================

    kuma.register_tool(
        "screenshot_screen",
        screenshot_screen,
    )

    kuma.register_tool(
        "analyze_screen",
        analyze_screen,
    )

    kuma.register_tool(
        "move_mouse",
        move_mouse,
    )

    kuma.register_tool(
        "move_mouse_vision",
        move_mouse_vision,
    )

    kuma.register_tool(
        "click",
        click_at,
)

    kuma.register_tool(
        "type_text",
        type_text,
    )

    kuma.register_tool(
        "press_key",
        press_key,
    )

    kuma.register_tool(
        "scroll",
        scroll,
    )

# ================================================
    # MEMORY TOOLS
    # ================================================

    kuma.register_tool(
        "remember",
        remember,
    )

    kuma.register_tool(
        "recall",
        recall,
    )

    kuma.register_tool(
        "forget",
        forget,
    )

    kuma.register_tool(
    "click_vision",
    click_vision,
)


    kuma.register_tool(
        "hold_mouse",
        hold_mouse,
    )

    kuma.register_tool(
        "hold_mouse_vision",
        hold_mouse_vision,
    )

    kuma.register_tool(
        "release_mouse",
        release_mouse,
    )

    return kuma


# =========================================================
# CLI RUNTIME
# =========================================================


# =========================================================
# KUMA MEMORY-V2E — PRODUCTION MEMORY-OPERATION CLASSIFICATION
# =========================================================
#
# This is a read-only caller-owned classification boundary.
# It does not execute remember/recall/forget.
#
# ANY EXPLICIT MEMORY OPERATION -> SKIP IMPLICIT EXTRACTION
# CLASSIFICATION != EXECUTION
# CLASSIFICATION FAILURE -> SKIP IMPLICIT EXTRACTION
# MEMORY OBSERVATION != RUNTIME TRACE
# MEMORY OBSERVATION != PERSISTENCE
# AUTHORITY: NONE
# =========================================================


def _explicit_memory_operation_requested(
    kuma,
    user_message,
):
    """
    Return whether the current turn explicitly requests any memory operation.

    remember/recall/forget overlap is intentionally treated as a union.
    Classification failure fails closed for implicit extraction while leaving
    the already-explicit user turn free to run normally.
    """

    try:
        return any(
            bool(
                kuma.explicitly_requests_tool_action(
                    user_message,
                    tool_name,
                    {},
                )
            )
            for tool_name in (
                "remember",
                "recall",
                "forget",
            )
        )

    except Exception:
        return True


def main():

    kuma = create_kuma()

    memory_owner = (
        KumaMemoryV2CompletedTurnOwner()
    )

    runtime_owner = (
        KumaRuntimeV2LiveOwner()
    )

    integration_owner = (
        KumaIntegrationV2LiveTurnOwner(
            runtime_owner=runtime_owner,
            realtime_runtime=kuma.realtime_runtime,
            trigger_policy=(
                PRODUCTION_REALTIME_TRIGGER_POLICY
            ),
        )
    )

    kuma._runtime_observer = (
        runtime_owner.observe_pipeline_event
    )

    print()
    print("====================================")
    print("        KUMA PERSONAL ASSISTANT")
    print("====================================")
    print()
    print("KUMA → Online.")
    print("KUMA → Local brain ready.")
    print("KUMA → Tools loaded.")
    print("KUMA → Dangerous actions require confirmation.")
    print("KUMA → Type 'exit' to shut down.")
    print()

    try:

        while True:

            try:

                user_message = input(
                    "You → "
                ).strip()

            except (
                KeyboardInterrupt,
                EOFError,
            ):

                print(
                    "\nKUMA → Shutting down."
                )
                break

            if not user_message:
                continue

            if user_message.lower() in {
                "exit",
                "quit",
                "shutdown",
            }:

                print(
                    "KUMA → Shutting down."
                )
                break

            try:

                explicit_memory_operation_requested = (
                    _explicit_memory_operation_requested(
                        kuma,
                        user_message,
                    )
                )

                response = memory_owner.run(
                    lambda: integration_owner.run(
                        lambda prepared_realtime_turn: kuma.run(
                            user_message,
                            prepared_realtime_turn=(
                                prepared_realtime_turn
                            ),
                        )
                    ),
                    user_message=user_message,
                    explicit_memory_operation_requested=(
                        explicit_memory_operation_requested
                    ),
                )

                print()
                print(
                    f"KUMA → {response}"
                )
                print()

            except Exception as error:

                print()
                print(
                    f"KUMA ERROR → {error}"
                )
                print()

    finally:

        try:
            cleanup = (
                release_owned_mouse_button_for_shutdown()
            )

            if not cleanup.success:

                print()
                print(
                    "KUMA SAFETY → Mouse-button shutdown "
                    "cleanup failed."
                )
                print(
                    f"KUMA SAFETY → {cleanup.error}"
                )
                print(
                    "KUMA SAFETY → Release the mouse button "
                    "manually if necessary."
                )

            elif (
                cleanup.result
                and "already CLEAR"
                not in str(
                    cleanup.result
                )
            ):

                print(
                    f"KUMA → {cleanup.result}"
                )

        finally:
            runtime_owner.close()


if __name__ == "__main__":
    main()