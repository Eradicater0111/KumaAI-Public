import os
import subprocess
from pathlib import Path

from app.agent.tool_result import ToolResult


def open_app(app_name: str) -> str:
    """
    Open or launch a macOS APPLICATION.

    Use this capability when the user wants to launch, open,
    start, or run an application such as Chrome, Safari,
    Spotify, Finder, Terminal, or VS Code.

    IMPORTANT:
    This capability opens APPLICATIONS.

    Do NOT use open_file for application-launch requests.
    Do NOT treat an .app bundle as a normal file when the user
    asks to launch the application.
    """

    if not app_name or not app_name.strip():
        return ToolResult.fail(
            "No application name was provided."
        )

    requested_name = app_name.strip()

    # ---------------------------------------------------------
    # Common macOS application aliases
    # ---------------------------------------------------------

    app_aliases = {
        "chrome": "Google Chrome",
        "google chrome": "Google Chrome",

        "code": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "vscode": "Visual Studio Code",
        "visual studio code": "Visual Studio Code",

        "safari": "Safari",
        "firefox": "Firefox",
        "brave": "Brave Browser",
        "brave browser": "Brave Browser",

        "spotify": "Spotify",
        "discord": "Discord",
        "slack": "Slack",

        "terminal": "Terminal",
        "iterm": "iTerm",
        "iterm2": "iTerm",

        "finder": "Finder",
        "notes": "Notes",
        "calendar": "Calendar",
        "mail": "Mail",
        "messages": "Messages",

        "system settings": "System Settings",
        "settings": "System Settings",

        "activity monitor": "Activity Monitor",
    }

    normalized_name = " ".join(
        requested_name.lower().split()
    )

    resolved_name = app_aliases.get(
        normalized_name,
        requested_name,
    )

    try:
        result = subprocess.run(
            ["open", "-a", resolved_name],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # -----------------------------------------------------
        # macOS failed to find/open the application
        # -----------------------------------------------------

        if result.returncode != 0:

            error_message = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"macOS could not find or open '{resolved_name}'."
            )

            return ToolResult.fail(
                f"Could not open '{requested_name}'. "
                f"macOS reported: {error_message}"
            )

        # -----------------------------------------------------
        # Success
        # -----------------------------------------------------

        if requested_name.lower() != resolved_name.lower():
            return ToolResult.ok(
                f"Opened {requested_name} "
                f"({resolved_name}) successfully."
            )

        return ToolResult.ok(
            f"Opened {requested_name} successfully."
        )

    except subprocess.TimeoutExpired:
        return ToolResult.fail(
            f"Could not confirm opening '{requested_name}': "
            "the macOS open command timed out."
        )

    except Exception as error:
        return ToolResult.fail(
            f"Could not open '{requested_name}': {error}"
        )
    
def list_files(folder: str = "~") -> str:
    """
    List files in a folder.

    If no folder is specified, list the current user's
    home directory.

    User-relative paths such as ~, Downloads, Documents,
    Desktop, Pictures, Movies, and Music are resolved using
    Path.home().

    Never assume or invent the macOS username.
    """

    try:
        # ---------------------------------------------
        # Normalize common natural-language paths
        # ---------------------------------------------

        folder = folder.strip()

        normalized = folder.lower().strip("/")

        if normalized in {
            "downloads",
            "download",
        }:
            path = Path.home() / "Downloads"

        elif normalized in {
            "documents",
            "document",
        }:
            path = Path.home() / "Documents"

        elif normalized in {
            "desktop",
        }:
            path = Path.home() / "Desktop"

        elif normalized in {
            "pictures",
            "photos",
            "images",
        }:
            path = Path.home() / "Pictures"

        elif normalized in {
            "movies",
            "videos",
        }:
            path = Path.home() / "Movies"

        elif normalized in {
            "music",
        }:
            path = Path.home() / "Music"

        else:
            # Expand ~ and resolve normal paths
            path = Path(folder).expanduser()

        # ---------------------------------------------
        # Validate path
        # ---------------------------------------------

        if not path.exists():
            return (
                f"The folder '{folder}' does not exist."
            )

        if not path.is_dir():
            return (
                f"'{folder}' is not a folder."
            )

        # ---------------------------------------------
        # Read directory
        # ---------------------------------------------

        files = sorted(
            path.iterdir(),
            key=lambda item: item.name.lower(),
        )

        if not files:
            return (
                f"The folder '{path.name}' is empty."
            )

        result = []

        for file in files[:50]:

            if file.is_dir():
                result.append(
                    f"[Folder] {file.name}"
                )

            else:
                result.append(
                    file.name
                )

        return (
            f"Contents of {path}:\n"
            + "\n".join(result)
        )

    except PermissionError:
        return (
            f"Permission denied while reading "
            f"'{folder}'."
        )

    except Exception as error:
        return (
            f"Could not read the folder "
            f"'{folder}': {error}"
        )
    
def open_file(file_path: str) -> ToolResult:
    """
    Open a USER FILE using its associated macOS application.

    Use this capability when the user asks to open, read,
    or view a specific file such as a PDF, image, document,
    spreadsheet, or text file.

    IMPORTANT:
    Do NOT use this capability to launch applications.
    For application-launch requests, use open_app instead.
    """

    if not file_path or not file_path.strip():
        return ToolResult.fail(
            "No file path was provided."
        )

    file_path = file_path.strip()

    try:

        path = Path(
            file_path
        ).expanduser()

        # -------------------------------------------------
        # FILE EXISTENCE
        # -------------------------------------------------

        if not path.exists():

            return ToolResult.fail(
                f"I couldn't find {file_path}."
            )

        # -------------------------------------------------
        # DIRECTORY CHECK
        # -------------------------------------------------

        if not path.is_file():

            return ToolResult.fail(
                f"{file_path} is not a file."
            )

        # -------------------------------------------------
        # OPEN FILE
        # -------------------------------------------------

        result = subprocess.run(
            ["open", str(path)],
            capture_output=True,
            text=True,
            timeout=15,
        )

        # -------------------------------------------------
        # MACOS FAILURE
        # -------------------------------------------------

        if result.returncode != 0:

            error_message = (
                result.stderr.strip()
                or result.stdout.strip()
                or "macOS could not open the file."
            )

            return ToolResult.fail(
                f"Could not open '{path.name}'. "
                f"macOS reported: {error_message}"
            )

        # -------------------------------------------------
        # SUCCESS
        # -------------------------------------------------

        return ToolResult.ok(
            f"Opened {path.name} successfully."
        )

    except subprocess.TimeoutExpired:

        return ToolResult.fail(
            f"Could not confirm opening "
            f"'{file_path}': macOS timed out."
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not open '{file_path}': {error}"
        )

    # =========================================================
# EXECUTE COMMAND
# =========================================================

def execute_command(command: str) -> ToolResult:
    """
    Execute the exact shell command requested by the user.

    Use this tool whenever the user explicitly asks KUMA
    to run, execute, or invoke a terminal/shell command.

    Do not explain how to run the command manually.
    Do not simulate execution.
    Do not invent output.

    Args:
        command: The exact shell command to execute.
    """
    if not command or not command.strip():
        return ToolResult.fail(
            "No command was provided."
        )

    command = command.strip()

    try:

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # -------------------------------------------------
        # COMMAND FAILURE
        # -------------------------------------------------

        if result.returncode != 0:

            error_message = (
                stderr
                or stdout
                or f"Command exited with code {result.returncode}."
            )

            return ToolResult.fail(
                f"Command failed with exit code "
                f"{result.returncode}: {error_message}"
            )

        # -------------------------------------------------
        # COMMAND SUCCESS
        # -------------------------------------------------

        output = stdout or "(no output)"

        # Prevent enormous terminal responses
        if len(output) > 4000:
            output = output[:4000] + "\n...[output truncated]"

        return ToolResult.ok(
            f"Command executed successfully.\n"
            f"Output:\n{output}"
        )

    except subprocess.TimeoutExpired:

        return ToolResult.fail(
            "Command execution timed out after 30 seconds."
        )

    except Exception as error:

        return ToolResult.fail(
            f"Could not execute command: {error}"
        )