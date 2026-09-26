"""Planner-facing semantic GUI target intent with no observation authority.

B8A lets an untrusted planner describe *what semantic UI target it means*.
It deliberately cannot carry, reconstruct, or imply trusted observation,
provenance, geometry, resolution, revalidation, permission, attestation, or
action-authority evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ui_observation.contracts import MAX_UI_TEXT
from app.ui_observation.target_resolution import StructuredUITargetSelector


INTENT_FIELDS = frozenset({
    "role",
    "subrole",
    "text",
    "require_enabled",
    "require_positive_area",
})


# Names are documented here for tests/review only. ``from_dict`` rejects every
# unknown key, not merely these examples. This list makes the trust boundary
# conspicuous to future maintainers.
FORBIDDEN_TRUST_CLAIM_FIELDS = frozenset({
    "ui_observation_id",
    "screen_observation_id",
    "desktop_before_id",
    "desktop_after_id",
    "application_pid",
    "application_bundle_id",
    "path",
    "position_x",
    "position_y",
    "width",
    "height",
    "resolved",
    "matched",
    "revalidated",
    "expires_at_monotonic",
    "semantic_target_verified",
    "authorized",
    "permission",
    "attestation",
    "click",
    "x",
    "y",
})


def _normalize_optional_text(value, *, name: str):
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"GUI target intent {name} must be text or null.")
    value = value.strip()
    if not value or len(value) > MAX_UI_TEXT:
        raise ValueError(
            f"GUI target intent {name} must be bounded and nonblank."
        )
    return value


@dataclass(frozen=True)
class StructuredUITargetIntent:
    """Untrusted semantic target requirements supplied by planning.

    This object contains requirements only. It is not evidence. It has no
    observation IDs, application identity, AX path, geometry, timestamps,
    verification state, permission state, attestation, coordinates, or action.
    """

    role: str | None = None
    subrole: str | None = None
    text: str | None = field(default=None, repr=False)
    require_enabled: bool = False
    require_positive_area: bool = False

    def __post_init__(self):
        role = _normalize_optional_text(self.role, name="role")
        subrole = _normalize_optional_text(self.subrole, name="subrole")
        text = _normalize_optional_text(self.text, name="text")

        if role is None and subrole is None and text is None:
            raise ValueError(
                "GUI target intent requires at least one semantic constraint."
            )

        if (
            type(self.require_enabled) is not bool
            or type(self.require_positive_area) is not bool
        ):
            raise ValueError(
                "GUI target intent requirements must be booleans."
            )

        object.__setattr__(self, "role", role)
        object.__setattr__(self, "subrole", subrole)
        object.__setattr__(self, "text", text)

    @classmethod
    def from_dict(cls, data) -> "StructuredUITargetIntent":
        """Parse one strict planner payload without ignoring extra claims."""

        if type(data) is not dict:
            raise ValueError("GUI target intent must be a dictionary.")

        keys = set(data)
        unknown = keys - INTENT_FIELDS
        if unknown:
            raise ValueError(
                "GUI target intent contains unsupported or trusted-claim fields."
            )

        return cls(
            role=data.get("role"),
            subrole=data.get("subrole"),
            text=data.get("text"),
            require_enabled=data.get("require_enabled", False),
            require_positive_area=data.get("require_positive_area", False),
        )

    def to_dict(self) -> dict:
        """Return only planner-owned semantic requirement fields."""

        return {
            "role": self.role,
            "subrole": self.subrole,
            "text": self.text,
            "require_enabled": self.require_enabled,
            "require_positive_area": self.require_positive_area,
        }

    def to_selector(self) -> StructuredUITargetSelector:
        """Translate requirements into B6's pure selector contract only."""

        return StructuredUITargetSelector(
            role=self.role,
            subrole=self.subrole,
            text=self.text,
            require_enabled=self.require_enabled,
            require_positive_area=self.require_positive_area,
        )
