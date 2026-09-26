from ollama import chat


class LocalKumaAgent:

    def __init__(self, model="qwen3:8b"):

        self.model = model
        self.tools = {}

    # =====================================================
    # REGISTER TOOL
    # =====================================================

    def register_tool(self, name, function):

        self.tools[name] = function

    # =====================================================
    # EXECUTE TOOL
    # =====================================================

    def execute_tool(self, name, arguments):

        if name not in self.tools:

            return f"Unknown tool: {name}"

        try:

            result = self.tools[name](**arguments)

            return str(result)

        except Exception as error:

            return f"Tool execution failed: {error}"

    # =====================================================
    # THINK
    # =====================================================

    def run(self, user_message):

        messages = [

            {
                "role": "system",
                "content": """
You are KUMA, a personal AI companion who lives alongside the user through your floating desktop body and connected devices.

You can reason about the user's request and use
available tools when necessary.

Do not use tools unnecessarily.

Never claim that an action was completed unless
the tool actually returned a successful result.

You may inspect information, analyze it, form
an opinion, and recommend actions.

For potentially destructive or irreversible
actions, require explicit user confirmation
before execution.
"""
            },

            {
                "role": "user",
                "content": user_message
            }

        ]

        # =================================================
        # AGENT LOOP
        # =================================================

        while True:

            print("\nKUMA → Thinking...")

            response = chat(
                model=self.model,
                messages=messages,
                tools=list(self.tools.values()),
                think=False,
            )

            # ---------------------------------------------
            # Store model response
            # ---------------------------------------------

            messages.append(response.message)

            # ---------------------------------------------
            # No tool requested
            # ---------------------------------------------

            if not response.message.tool_calls:

                return response.message.content

            # ---------------------------------------------
            # Execute tools
            # ---------------------------------------------

            for tool_call in response.message.tool_calls:

                name = tool_call.function.name

                arguments = (
                    tool_call.function.arguments
                )

                print(
                    f"KUMA TOOL → "
                    f"{name}({arguments})"
                )

                result = self.execute_tool(
                    name,
                    arguments
                )

                print(
                    f"KUMA TOOL RESULT → "
                    f"{result}"
                )

                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": result,
                    }
                )