"""
KUMA Vision Tools

Safe screen-observation tools.

These tools OBSERVE only.
They do not click, type, move the mouse,
or modify the computer.
"""

from app.agent.tool_result import ToolResult

from app.vision.screen import (
    capture_screen,
    ScreenCaptureError,
)

from app.vision.analyzer import (
    analyze_image,
    VisionAnalysisError,
)


def analyze_screen() -> ToolResult:
    """
    Capture and analyze the current screen.

    Observation only.
    No computer state is modified.
    """

    try:

        image = capture_screen()

        analysis = analyze_image(
            image
        )

        return ToolResult.ok(
            str(
                analysis
            )
        )

    except ScreenCaptureError as error:

        return ToolResult.fail(
            f"Could not capture screen: {error}"
        )

    except VisionAnalysisError as error:

        return ToolResult.fail(
            f"Could not analyze screen: {error}"
        )

    except Exception as error:

        return ToolResult.fail(
            f"Screen analysis failed: {error}"
        )