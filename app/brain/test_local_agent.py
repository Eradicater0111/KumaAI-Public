"""Manual model demo. Run explicitly with python -m app.brain.test_local_agent."""


def main():
    from app.brain.local_agent import LocalKumaAgent
    from app.memory.manager import forget, recall, remember
    from app.tools.system_monitor import inspect_system
    from app.tools.system_tools import list_files, open_app, open_file


    def get_kuma_status() -> str:
        """Return the current status of KUMA."""

        return (
            "KUMA is online. "
            "Local brain is operational. "
            "All core systems are ready."
        )


    kuma = LocalKumaAgent()

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


if __name__ == "__main__":
    main()
