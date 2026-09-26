"""
KUMA Coordinate Mapping

Converts coordinates between the resized vision image
and the actual macOS screen.
"""

from __future__ import annotations

from dataclasses import dataclass


class CoordinateMappingError(RuntimeError):
    """Raised when coordinate mapping fails."""


@dataclass(frozen=True)
class CoordinateMapper:
    vision_width: int
    vision_height: int
    screen_width: int
    screen_height: int

    @property
    def scale_x(self) -> float:
        return self.screen_width / self.vision_width

    @property
    def scale_y(self) -> float:
        return self.screen_height / self.vision_height

    def vision_to_screen(
        self,
        x: float,
        y: float,
    ) -> tuple[int, int]:

        if not (
            0 <= x < self.vision_width
            and 0 <= y < self.vision_height
        ):
            raise CoordinateMappingError(
                f"Vision coordinate ({x}, {y}) "
                f"is outside "
                f"{self.vision_width}x{self.vision_height}."
            )

        screen_x = round(x * self.scale_x)
        screen_y = round(y * self.scale_y)

        screen_x = min(
            max(screen_x, 0),
            self.screen_width - 1,
        )

        screen_y = min(
            max(screen_y, 0),
            self.screen_height - 1,
        )

        return screen_x, screen_y

    def screen_to_vision(
        self,
        x: float,
        y: float,
    ) -> tuple[int, int]:

        if not (
            0 <= x < self.screen_width
            and 0 <= y < self.screen_height
        ):
            raise CoordinateMappingError(
                f"Screen coordinate ({x}, {y}) "
                f"is outside "
                f"{self.screen_width}x{self.screen_height}."
            )

        vision_x = round(x / self.scale_x)
        vision_y = round(y / self.scale_y)

        vision_x = min(
            max(vision_x, 0),
            self.vision_width - 1,
        )

        vision_y = min(
            max(vision_y, 0),
            self.vision_height - 1,
        )

        return vision_x, vision_y