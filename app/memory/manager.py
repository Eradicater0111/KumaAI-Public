from app.memory.memory import (
    save_memory,
    get_memory,
    get_all_memories,
    delete_memory,
)
from app.memory.retrieval import (
    format_memory_context_for_model,
    retrieve_memories,
)

from app.agent.tool_result import ToolResult

def remember(
    category: str,
    key: str,
    value: str,
) -> ToolResult:

    try:

        save_memory(
            category,
            key,
            value,
        )

        return ToolResult.ok(
            f"Remembered: "
            f"{key} = {value}"
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not remember "
            f"'{key}': {error}"
        )
    """
    Store a long-term memory for the user.

    Parameters:
        category: Broad memory category such as
                  preferences, personal, work, projects, or system.

        key: Short name identifying the memory,
             such as fav_editor, favorite_language,
             or project_name.

        value: The actual information to remember,
               such as VS Code, Python, or KumaAI.

    Example:
        remember(
            category="preferences",
            key="fav_editor",
            value="Cursor"
        )
    """

    save_memory(
        category,
        key,
        value,
    )

    return (
        f"Remembered: "
        f"{key} = {value}"
    )

    return (
        f"Remembered: "
        f"{key} = {value}"
    )


def recall(
    category: str,
    key: str,
) -> ToolResult:

    try:

        value = get_memory(
            category,
            key,
        )

        if value is None:

            return ToolResult.fail(
                f"No memory found for "
                f"'{key}'."
            )

        return ToolResult.ok(
            value
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not recall "
            f"'{key}': {error}"
        )


def forget(
    category: str,
    key: str,
) -> ToolResult:

    deleted = delete_memory(
        category,
        key,
    )

    if not deleted:

        return ToolResult.fail(
            f"No memory found for "
            f"'{key}'."
        )

    return ToolResult.ok(
        f"Forgot the memory "
        f"'{key}'."
    )

def get_memory_context(
    user_message: str,
    limit: int = 5,
    threshold: float = 0.25,
    *,
    project_scope: str | None = None,
    subject: str | None = "user",
    now=None,
):

    if not user_message:
        return ""

    matches = retrieve_memories(
        user_message,
        limit=limit,
        threshold=threshold,
        project_scope=project_scope,
        subject=subject,
        now=now,
    )

    return format_memory_context_for_model(
        matches
    )
