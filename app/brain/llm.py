import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.personality.personality import KUMA_PERSONALITY
from app.agent.executor import ActionExecutor

from app.tools.system_tools import (
    open_app,
    list_files,
    open_file,
)

from app.memory.manager import (
    remember,
    recall,
    forget,
    get_memory_context,
)

from app.knowledge import (
    KnowledgeDomain,
    KnowledgeResolver,
)

from app.tools.system_monitor import inspect_system

from app.tools.computer_tools import (
    screenshot_screen,
    analyze_screen,
    move_mouse,
    click,
    type_text,
    press_key,
    scroll,
)

# =========================================================
# KUMA ACTION REGISTRY
# =========================================================

TOOL_REGISTRY = {

    "open_app": open_app,
    "list_files": list_files,
    "open_file": open_file,

    "remember": remember,
    "recall": recall,
    "forget": forget,

    "inspect_system": inspect_system,

    "screenshot_screen": screenshot_screen,
    "analyze_screen": analyze_screen,

    "move_mouse": move_mouse,
    "click": click,
    "type_text": type_text,
    "press_key": press_key,
    "scroll": scroll,

}


action_executor = ActionExecutor(
    TOOL_REGISTRY
)


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# GEMINI CLIENT
# =========================================================

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


# =========================================================
# KUMA TOOLS
# =========================================================

open_app_tool = types.FunctionDeclaration.from_callable(
    callable=open_app,
    client=client,
)

list_files_tool = types.FunctionDeclaration.from_callable(
    callable=list_files,
    client=client,
)

open_file_tool = types.FunctionDeclaration.from_callable(
    callable=open_file,
    client=client,
)

remember_tool = types.FunctionDeclaration.from_callable(
    callable=remember,
    client=client,
)

recall_tool = types.FunctionDeclaration.from_callable(
    callable=recall,
    client=client,
)

forget_tool = types.FunctionDeclaration.from_callable(
    callable=forget,
    client=client,
)

inspect_system_tool = types.FunctionDeclaration.from_callable(
    callable=inspect_system,
    client=client,
)

screenshot_screen_tool = types.FunctionDeclaration.from_callable(
    callable=screenshot_screen,
    client=client,
)

analyze_screen_tool = types.FunctionDeclaration.from_callable(
    callable=analyze_screen,
    client=client,
)

move_mouse_tool = types.FunctionDeclaration.from_callable(
    callable=move_mouse,
    client=client,
)

click_tool = types.FunctionDeclaration.from_callable(
    callable=click,
    client=client,
)

type_text_tool = types.FunctionDeclaration.from_callable(
    callable=type_text,
    client=client,
)

press_key_tool = types.FunctionDeclaration.from_callable(
    callable=press_key,
    client=client,
)

scroll_tool = types.FunctionDeclaration.from_callable(
    callable=scroll,
    client=client,
)

TOOLS = types.Tool(
    function_declarations=[
        open_app_tool,
        list_files_tool,
        open_file_tool,

        remember_tool,
        recall_tool,
        forget_tool,

        inspect_system_tool,

        screenshot_screen_tool,
        analyze_screen_tool,

        move_mouse_tool,
        click_tool,
        type_text_tool,
        press_key_tool,
        scroll_tool,
    ]
)


# =========================================================
# TOOL EXECUTION
# =========================================================

def execute_tool(
    name,
    args,
    approved=False,
):
    """
    Execute a registered KUMA tool through the safety-aware
    ActionExecutor.

    Important:
    - Dangerous tools NEVER execute automatically.
    - The first call is intentionally made with approved=False.
    - Confirmation is handled by KumaAgent/runtime.
    - This function only reports the executor result.
    """

    action = action_executor.execute(
        tool_name=name,
        arguments=args,
        approved=approved,
    )

    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------

    if action.success:
        return action.result

    # -----------------------------------------------------
    # CONFIRMATION REQUIRED
    # -----------------------------------------------------

    if action.requires_confirmation:

        return {
            "status": "confirmation_required",
            "tool": name,
            "arguments": args,
            "message": (
                f"KUMA requires confirmation before "
                f"executing '{name}'."
            ),
            "error": action.error,
        }

    # -----------------------------------------------------
    # NORMAL TOOL FAILURE
    # -----------------------------------------------------

    return {
        "status": "error",
        "tool": name,
        "message": f"KUMA tool '{name}' failed.",
        "error": action.error,
    }


# =========================================================
# KUMA MEMORY-1J — LEGACY BRAIN RELEVANCE GATE
# =========================================================
#
# The legacy Gemini lane must obey the same zero-authority memory
# relevance plan as the canonical KumaAgent lane.
# =========================================================

def _memory_context_for_request(
    request: str,
) -> str:
    """
    Return secure long-term-memory context only when KnowledgeResolver
    explicitly plans the internal memory provider.

    This is read-only context selection. It grants no tool permission,
    execution authority, approval, or remember/forget authorization.
    """

    normalized_request = str(
        request
        or ""
    ).strip()

    if not normalized_request:
        return ""

    plan = KnowledgeResolver().plan(
        normalized_request
    )

    if (
        plan.authority != "NONE"
        or plan.intent.authority != "NONE"
    ):
        return ""

    if (
        plan.intent.domain
        != KnowledgeDomain.MEMORY
    ):
        return ""

    if (
        "memory"
        not in plan.provider_order
    ):
        return ""

    try:
        return (
            get_memory_context(
                normalized_request
            )
            or ""
        )

    except Exception as error:
        print(
            "KUMA MEMORY CONTEXT ERROR → "
            f"{error}"
        )

        return ""

# =========================================================
# KUMA STREAMING BRAIN
# =========================================================

def ask_kuma_stream(
    user_message: str,
    history=None,
):

    conversation = KUMA_PERSONALITY + "\n\n"


    # =====================================================
    # LONG-TERM MEMORY
    # =====================================================

    memory_context = _memory_context_for_request(
        user_message
    )

    if memory_context:

        conversation += (
            memory_context
            + "\n\n"
        )


    # =====================================================
    # SHORT-TERM CONVERSATION
    # =====================================================

    if history:

        conversation += (
            "Previous conversation:\n"
        )

        for role, message in history:

            conversation += (
                f"{role}: {message}\n"
            )

        conversation += "\n"


    # =====================================================
    # CURRENT MESSAGE
    # =====================================================

    conversation += (
        f"User: {user_message}"
    )


    # =====================================================
    # GEMINI CONTENTS
    # =====================================================

    contents = [

        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text=conversation
                )
            ],
        )

    ]


    # =====================================================
    # KUMA AGENT LOOP
    # =====================================================

    while True:

        print(
            "\nKUMA → Thinking..."
        )


        response_stream = (
            client.models.generate_content_stream(

                model="gemini-3.5-flash-lite",

                contents=contents,

                config=types.GenerateContentConfig(
                    tools=[TOOLS]
                ),
            )
        )


        tool_calls = []
        model_content = None


        # =================================================
        # READ GEMINI STREAM
        # =================================================

        for chunk in response_stream:

            if not chunk.candidates:
                continue

            candidate = chunk.candidates[0]

            if not candidate.content:
                continue


            # ---------------------------------------------
            # KEEP MODEL RESPONSE
            # ---------------------------------------------

            model_content = candidate.content


            # ---------------------------------------------
            # CHECK FOR TOOLS
            # ---------------------------------------------

            for part in candidate.content.parts:

                if part.function_call:

                    tool_calls.append(
                        part.function_call
                    )


            # ---------------------------------------------
            # NORMAL TEXT
            # ---------------------------------------------

            if chunk.text:

                yield chunk.text


        # =================================================
        # NO TOOL CALL
        # =================================================

        if not tool_calls:

            print(
                "KUMA → Finished"
            )

            return


        # =================================================
        # SAVE MODEL RESPONSE
        # =================================================

        if model_content:

            contents.append(
                model_content
            )


        # =================================================
        # EXECUTE TOOLS
        # =================================================

        function_response_parts = []


        for tool_call in tool_calls:

            tool_name = tool_call.name

            tool_args = dict(
                tool_call.args
            )


            print(
                f"KUMA TOOL → "
                f"{tool_name}"
                f"({tool_args})"
            )


            try:

                result = execute_tool(
                    tool_name,
                    tool_args
                )

            except Exception as e:

                result = (
                    f"Tool error: {e}"
                )


            print(
                f"KUMA TOOL RESULT → "
                f"{result}"
            )


            # -----------------------------------------
            # TOOL RESULT
            # -----------------------------------------

            function_response_parts.append(

                types.Part.from_function_response(

                    name=tool_name,

                    response={
                        "result": result
                    },

                )

            )


        # =================================================
        # SEND RESULTS BACK TO GEMINI
        # =================================================

        contents.append(

            types.Content(

                role="user",

                parts=function_response_parts,

            )

        )


        # =================================================
        # LOOP
        # =================================================

        # Gemini now sees the tool results and can decide:
        #
        # 1. Answer the user
        # 2. Call another tool
        # 3. Inspect more information
        # 4. Continue reasoning
        #
        # The while loop handles that automatically.
