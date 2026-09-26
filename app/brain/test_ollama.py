"""Manual model demo. Run explicitly with python -m app.brain.test_ollama."""


def main():
    from ollama import chat


    def get_kuma_status() -> str:
        """Return the current status of KUMA."""
        return "KUMA is online, all core systems are operational."


    tools = [
        get_kuma_status
    ]

    messages = [
        {
            "role": "user",
            "content": "Check KUMA's status and tell me what you find."
        }
    ]

    # =========================================================
    # FIRST MODEL CALL
    # =========================================================

    response = chat(
        model="qwen3:8b",
        messages=messages,
        tools=tools,
        think=False,
    )

    print("\nMODEL RESPONSE:")
    print(response.message.content)

    # =========================================================
    # HANDLE TOOL CALL
    # =========================================================

    if response.message.tool_calls:

        messages.append(response.message)

        for tool_call in response.message.tool_calls:

            tool_name = tool_call.function.name
            arguments = tool_call.function.arguments
        
            print(
                f"\nKUMA TOOL → {tool_name}({arguments})"
            )

            if tool_name == "get_kuma_status":

                result = get_kuma_status()

            else:

                result = "Unknown tool."

            print(
                f"KUMA TOOL RESULT → {result}"
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": result,
                }
            )

        # =====================================================
        # SECOND MODEL CALL
        # =====================================================

        final_response = chat(
            model="qwen3:8b",
            messages=messages,
            tools=tools,
            think=False,
        )

        print("\nFINAL KUMA RESPONSE:")
        print(final_response.message.content)

    else:

        print("\nNo tool was requested.")


if __name__ == "__main__":
    main()
