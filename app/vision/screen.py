"""
KUMA Screen Vision

Phase 2.1:
- Capture the current macOS screen.
- Keep screen access isolated from the agent.
- Return a PIL Image.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image


class ScreenCaptureError(RuntimeError):
    """Raised when KUMA cannot capture the screen."""


def capture_screen() -> Image.Image:
    """
    Capture the primary macOS display.

    Returns:
        PIL.Image.Image

    Raises:
        ScreenCaptureError:
            If macOS screenshot capture fails.
    """

    temp_path = None

    try:
        with NamedTemporaryFile(
            suffix=".png",
            delete=False,
        ) as temp:
            temp_path = Path(temp.name)

        process = subprocess.run(
            [
                "screencapture",
                "-x",
                str(temp_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if process.returncode != 0:
            raise ScreenCaptureError(
                process.stderr.strip()
                or "macOS screencapture failed."
            )

        if not temp_path.exists():
            raise ScreenCaptureError(
                "Screenshot file was not created."
            )

        image = Image.open(temp_path)

        # Force image data to load before deleting
        # the temporary file.
        image.load()

        return image.copy()

    except FileNotFoundError as error:
        raise ScreenCaptureError(
            "macOS screencapture command was not found."
        ) from error

    except Exception as error:

        if isinstance(
            error,
            ScreenCaptureError,
        ):
            raise

        raise ScreenCaptureError(
            f"Screen capture failed: {error}"
        ) from error

    finally:

        if temp_path is not None:

            try:
                temp_path.unlink(
                    missing_ok=True
                )
            except Exception:
                pass