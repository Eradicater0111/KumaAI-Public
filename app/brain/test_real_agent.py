"""Manual model demo. Run explicitly with python -m app.brain.test_real_agent."""


def main():
    from app.brain.local_agent import LocalKumaAgent

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


    kuma = LocalKumaAgent()


    # =====================================================
    # SYSTEM TOOLS
    # =====================================================

    kuma.register_tool(
        "open_app",
        open_app
    )

    kuma.register_tool(
        "list_files",
        list_files
    )

    kuma.register_tool(
        "open_file",
        open_file
    )

    kuma.register_tool(
        "inspect_system",
        inspect_system
    )


    # =====================================================
    # MEMORY TOOLS
    # =====================================================

    kuma.register_tool(
        "remember",
        remember
    )

    kuma.register_tool(
        "recall",
        recall
    )

    kuma.register_tool(
        "forget",
        forget
    )


    # =====================================================
    # TEST
    # =====================================================

    result = kuma.run(
        "Inspect my system and tell me what you think about its current state."
    )

    print("\n")
    print("====================================")
    print("FINAL KUMA RESPONSE")
    print("====================================")
    print(result)


if __name__ == "__main__":
    main()
