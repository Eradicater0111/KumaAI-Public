import os
import platform
import shutil
import subprocess

from app.agent.tool_result import ToolResult


def get_system_info() -> str:

    system = platform.system()
    machine = platform.machine()

    return (
        f"Operating System: {system}\n"
        f"Architecture: {machine}\n"
        f"CPU Cores: {os.cpu_count()}\n"
    )


def get_disk_info() -> str:

    total, used, free = shutil.disk_usage("/")

    gb = 1024 ** 3

    return (
        f"Disk Total: {total / gb:.2f} GB\n"
        f"Disk Used: {used / gb:.2f} GB\n"
        f"Disk Free: {free / gb:.2f} GB\n"
    )


def get_running_processes() -> ToolResult:

    try:

        result = subprocess.run(
            [
                "ps",
                "-axo",
                "pid,%cpu,%mem,comm",
                "-r",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:

            return ToolResult.fail(
                "Unable to retrieve running processes."
            )

        lines = result.stdout.strip().splitlines()

        if not lines:

            return ToolResult.fail(
                "No process information available."
            )

        # Keep header + top 10 CPU-consuming processes

        header = lines[0]
        processes = lines[1:11]

        return ToolResult.ok(
            "\n".join(
                [header] + processes
            )
        )

    except subprocess.TimeoutExpired:

        return ToolResult.fail(
            "Retrieving running processes timed out."
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not retrieve running processes: {error}"
        )


def inspect_system() -> ToolResult:
    """
    Inspect the current computer's system state.

    Use this tool when the user asks KUMA to inspect or check
    the current state of their computer, including:

    - operating system
    - CPU information
    - CPU usage/process activity
    - disk capacity and usage
    - running processes
    - general system status

    This is a read-only diagnostic capability.

    Do not use open_app to perform ordinary system inspection.
    Do not use execute_command unless the user explicitly
    requests a shell command.
    """

    try:

        system_info = get_system_info()

        disk_info = get_disk_info()

        process_result = get_running_processes()

        if not process_result.success:

            return ToolResult.fail(
                process_result.error
                or "Unable to retrieve running processes."
            )

        result = (
            "SYSTEM INFORMATION\n"
            "==================\n\n"
            + system_info
            + "\n"
            + disk_info
            + "\nRUNNING PROCESSES\n"
            "=================\n"
            + process_result.result
        )

        return ToolResult.ok(
            result
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not inspect system: {error}"
        )