"""
KUMA Screen Vision Analyzer

Phase 2.2:
- Receive a captured PIL image.
- Resize large screenshots for efficient vision processing.
- Send the image directly to Gemini Vision.
- No Gemini Files API.
- No Gemini tools/function calling.
- Return concise structured visual analysis.
- Coordinates are ALWAYS reported in prepared vision-image space.
"""

from __future__ import annotations

import io
import os
import time
from dataclasses import dataclass

from google import genai
from google.genai import types
from PIL import Image

from app.vision.coordinates import CoordinateMapper

@dataclass(frozen=True)
class VisionAnalysis:
    """
    Trusted output from one prepared vision request.

    Geometry is produced by KUMA's image pipeline, not Gemini.
    """

    analysis: str
    capture_width: int
    capture_height: int
    vision_width: int
    vision_height: int
    vision_scale: float

    def __str__(self) -> str:
        return self.analysis


# =========================================================
# CONFIGURATION
# =========================================================

VISION_MODEL = "gemini-3.6-flash"

MAX_VISION_DIMENSION = 1800


# =========================================================
# VISION PROMPT
# =========================================================

VISION_PROMPT = """
You are KUMA's visual perception system.

Analyze the current computer screen.

Your job is OBSERVATION ONLY.

Identify:

1. Active application.
2. Major visible windows and panels.
3. Important visible UI elements.
4. Buttons, fields, tabs, menus, dialogs, and controls.
5. Visible errors or warnings.
6. Whether the screen is waiting for user input.
7. Approximate coordinates of visible interactive elements.

IMPORTANT COORDINATE RULES:

The image you are analyzing is exactly:

{vision_width} × {vision_height} pixels.

Coordinate system:

- Origin (0, 0) = top-left.
- X increases to the right.
- Y increases downward.
- Maximum valid X = {vision_width_minus_one}.
- Maximum valid Y = {vision_height_minus_one}.

ALL coordinates MUST use this vision-image coordinate system.

DO NOT:

- use native macOS coordinates
- use Retina/display coordinates
- convert coordinates
- invent coordinates
- report coordinates for invisible elements
- guess when an element cannot be located reliably

Coordinates should be approximate CENTER points of visible
clickable targets.

If a coordinate cannot be reliably determined, write:

coordinate: unreliable

RETURN EXACTLY THIS STRUCTURE:

ACTIVE_APPLICATION:
<application name>

SCREEN_STATE:
<brief description>

VISIBLE_TARGETS:
- name: <target name>
  coordinate: (<x>, <y>)
  confidence: high|medium|low

- name: <target name>
  coordinate: (<x>, <y>)
  confidence: high|medium|low

WARNINGS:
- <warning or "none">

WAITING_FOR_INPUT:
yes|no

Be factual and concise.

Only describe what is actually visible.
"""


# =========================================================
# ERRORS
# =========================================================

class VisionAnalysisError(RuntimeError):
    """Raised when screen analysis fails."""


# =========================================================
# IMAGE PREPARATION
# =========================================================

def _prepare_image(
    image: Image.Image,
    max_dimension: int = MAX_VISION_DIMENSION,
) -> tuple[bytes, tuple[int, int], float]:
    """
    Prepare a screenshot for Gemini Vision.

    Large screenshots are resized while preserving aspect ratio.

    Returns:
        PNG bytes,
        prepared image dimensions,
        scale factor relative to original image.
    """

    image = image.convert("RGB")

    original_size = image.size
    largest_dimension = max(original_size)

    if largest_dimension <= max_dimension:

        scale = 1.0
        prepared = image

    else:

        scale = max_dimension / largest_dimension

        prepared = image.resize(
            (
                round(image.width * scale),
                round(image.height * scale),
            ),
            Image.Resampling.LANCZOS,
        )

    buffer = io.BytesIO()

    prepared.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    return (
        buffer.getvalue(),
        prepared.size,
        scale,
    )


# =========================================================
# RETRY HANDLING
# =========================================================

def _is_retryable_error(
    error: Exception,
) -> bool:
    """
    Determine whether a Gemini error is likely temporary.
    """

    message = str(error).lower()

    retryable_markers = (
        "503",
        "unavailable",
        "high demand",
        "temporarily unavailable",
        "deadline exceeded",
        "429",
        "resource exhausted",
    )

    return any(
        marker in message
        for marker in retryable_markers
    )


# =========================================================
# IMAGE ANALYSIS
# =========================================================

def analyze_image(
    image: Image.Image,
    max_attempts: int = 3,
) -> VisionAnalysis:
    """
    Analyze a captured screen image with Gemini Vision.

    Args:
        image:
            PIL screenshot returned by capture_screen().

        max_attempts:
            Maximum number of Gemini attempts for temporary
            service errors.

    Returns:
        VisionAnalysis containing Gemini's observation plus
        KUMA-generated capture/prepared-image geometry.

    Raises:
        VisionAnalysisError:
            If analysis fails.
    """

    # -----------------------------------------------------
    # Validate image
    # -----------------------------------------------------

    if not isinstance(image, Image.Image):

        raise VisionAnalysisError(
            f"Expected PIL.Image.Image, "
            f"got {type(image).__name__}."
        )

    # -----------------------------------------------------
    # API KEY
    # -----------------------------------------------------

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:

        raise VisionAnalysisError(
            "GEMINI_API_KEY is not configured."
        )

    # -----------------------------------------------------
    # Prepare request
    # -----------------------------------------------------

    try:

        client = genai.Client(
            api_key=api_key,
        )

        # -------------------------------------------------
        # Prepare image
        # -------------------------------------------------

        (
            image_bytes,
            prepared_size,
            vision_scale,
        ) = _prepare_image(image)

        screen_width, screen_height = image.size

        vision_width, vision_height = prepared_size

        # -------------------------------------------------
        # Coordinate mapper
        # -------------------------------------------------

        coordinate_mapper = CoordinateMapper(
            vision_width=vision_width,
            vision_height=vision_height,
            screen_width=screen_width,
            screen_height=screen_height,
        )

        print(
            "KUMA VISION → Image prepared:"
            f" {screen_width}x{screen_height}"
            f" → {vision_width}x{vision_height}"
            f" (scale={vision_scale:.3f})"
        )

        print(
            "KUMA VISION → Coordinate mapper:"
            f" vision={vision_width}x{vision_height}"
            f" screen={screen_width}x{screen_height}"
            f" scale=("
            f"{coordinate_mapper.scale_x:.4f},"
            f"{coordinate_mapper.scale_y:.4f}"
            f")"
        )

        # -------------------------------------------------
        # Build dimension-aware prompt
        # -------------------------------------------------

        vision_prompt = VISION_PROMPT.format(
            vision_width=vision_width,
            vision_height=vision_height,
            vision_width_minus_one=vision_width - 1,
            vision_height_minus_one=vision_height - 1,
        )

        # -------------------------------------------------
        # Build image part
        # -------------------------------------------------

        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/png",
        )

    except Exception as error:

        raise VisionAnalysisError(
            f"Could not prepare vision request: {error}"
        ) from error

    # =====================================================
    # GEMINI REQUEST LOOP
    # =====================================================

    last_error: Exception | None = None

    for attempt in range(
        1,
        max_attempts + 1,
    ):

        try:

            print(
                f"KUMA VISION → Gemini attempt "
                f"{attempt}/{max_attempts}..."
            )

            start = time.perf_counter()

            # -------------------------------------------------
            # IMPORTANT:
            #
            # This is an observation-only request.
            #
            # No:
            # - tools
            # - function declarations
            # - automatic function calling
            # - Gemini Files API
            #
            # Gemini only receives:
            #   1. screenshot
            #   2. vision prompt
            # -------------------------------------------------

            response = client.models.generate_content(
                model=VISION_MODEL,
                contents=[
                    image_part,
                    vision_prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.1,
                ),
            )

            elapsed = (
                time.perf_counter()
                - start
            )

            print(
                "KUMA VISION → Gemini completed "
                f"in {elapsed:.2f}s."
            )

            # -------------------------------------------------
            # Validate response
            # -------------------------------------------------

            text = response.text

            if not text or not text.strip():

                raise VisionAnalysisError(
                    "Vision model returned no analysis."
                )

            return VisionAnalysis(
                analysis=text.strip(),
                capture_width=screen_width,
                capture_height=screen_height,
                vision_width=vision_width,
                vision_height=vision_height,
                vision_scale=vision_scale,
            )

        # -----------------------------------------------------
        # Known KUMA vision failure
        # -----------------------------------------------------

        except VisionAnalysisError:

            raise

        # -----------------------------------------------------
        # Gemini / network failure
        # -----------------------------------------------------

        except Exception as error:

            last_error = error

            print(
                "KUMA VISION → Attempt "
                f"{attempt} failed: {error}"
            )

            # -------------------------------------------------
            # Stop if:
            #
            # - final attempt
            # - error is not retryable
            # -------------------------------------------------

            if (
                attempt >= max_attempts
                or not _is_retryable_error(error)
            ):

                break

            # -------------------------------------------------
            # Exponential backoff
            #
            # attempt 1 -> 2 seconds
            # attempt 2 -> 4 seconds
            # -------------------------------------------------

            delay = 2 ** attempt

            print(
                "KUMA VISION → Temporary Gemini "
                f"error. Retrying in {delay}s..."
            )

            time.sleep(delay)

    # =====================================================
    # FAILURE
    # =====================================================

    raise VisionAnalysisError(
        "Vision analysis failed after "
        f"{max_attempts} attempt(s): "
        f"{last_error}"
    ) from last_error