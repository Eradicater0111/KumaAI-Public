"""Manual model demo. Run explicitly with python -m app.agent.test_ollama_speed."""


def main():
    import time

    from ollama import chat

    from app.tools.system_tools import (
        open_app,
        list_files,
        open_file,
    )

    from app.tools.system_monitor import (
        inspect_system,
    )

    from app.memory.manager import (
        remember,
        recall,
        forget,
    )

    from app.tools.system_tools import (
        open_app,
        list_files,
        open_file,
    )

    from app.tools.system_monitor import (
        inspect_system,
    )

    from app.memory.manager import (
        remember,
        recall,
        forget,
    )



    MODEL = "qwen3:8b"

    # =====================================================
    # TEST 3 — KUMA PROMPT + REAL TOOLS
    # =====================================================

    from app.tools.system_tools import (
        open_app,
        list_files,
        open_file,
    )

    from app.tools.system_monitor import (
        inspect_system,
    )

    from app.memory.manager import (
        remember,
        recall,
        forget,
    )


    print("\n====================================")
    print("TEST 3 — KUMA PROMPT + TOOLS")
    print("====================================")


    tools = [
        open_app,
        list_files,
        open_file,
        inspect_system,
        remember,
        recall,
        forget,
    ]


    start = time.perf_counter()

    response = chat(

        model=MODEL,

        messages=[
            {
                "role": "system",

                "content": """
    You are KUMA, a personal AI companion who lives alongside the user through your floating desktop body and connected devices.

    Use tools when necessary.

    Do not use tools unnecessarily.

    Never claim an action succeeded unless
    the corresponding tool actually succeeded.

    Analyze information before giving
    recommendations.

    You may give your own opinion when useful.
    """,
            },

            {
                "role": "user",

                "content": (
                    "Inspect my system and tell me "
                    "what you think about its current state."
                ),
            },
        ],

        tools=tools,

        think=False,

        options={
            "num_ctx": 2048,
            "temperature": 0.2,
        },
    )

    elapsed = time.perf_counter() - start


    print(
        f"Time: {elapsed:.2f}s"
    )

    print(
        "\nTool calls:"
    )

    print(
        response.message.tool_calls
    )

    print(
        "\nResponse:"
    )

    print(
        response.message.content
    )


    # =====================================================
    # TEST 1 — NORMAL CHAT
    # =====================================================

    print("\n====================================")
    print("TEST 1 — NORMAL QWEN")
    print("====================================")

    start = time.perf_counter()

    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: KUMA ONLINE",
            }
        ],
        think=False,
    )

    elapsed = time.perf_counter() - start

    print("Response:", response.message.content)
    print(f"Time: {elapsed:.2f}s")


    # =====================================================
    # TEST 2 — KUMA SYSTEM PROMPT
    # =====================================================

    print("\n====================================")
    print("TEST 2 — KUMA PROMPT")
    print("====================================")

    start = time.perf_counter()

    response = chat(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": """
    You are KUMA, a personal AI companion who lives alongside the user through your floating desktop body and connected devices.

    Your job is to understand the user's command,
    reason about what needs to happen, and use tools
    when they are actually necessary.

    You are allowed to:

    - inspect the computer
    - inspect files
    - open applications
    - remember information
    - recall information
    - forget information
    - analyze system information
    - form opinions
    - make recommendations

    Do not use tools unnecessarily.

    Never claim an action happened unless the tool
    actually succeeded.

    Analyze information before giving recommendations.

    You may give your own opinion when useful,
    but clearly distinguish observations from opinions.

    Never invent tool results.

    Never execute destructive actions without
    explicit user confirmation.
    """,
            },
            {
                "role": "user",
                "content": "What is 27 multiplied by 43?",
            },
        ],
        think=False,
    )

    elapsed = time.perf_counter() - start

    print("Response:", response.message.content)
    print(f"Time: {elapsed:.2f}s")


if __name__ == "__main__":
    main()
