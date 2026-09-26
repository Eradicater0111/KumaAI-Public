"""Immutable, bounded contracts for native structured UI evidence."""

from dataclasses import asdict, dataclass, field
import math
from uuid import uuid4

from app.desktop.contracts import ApplicationIdentity, MAX_TEXT as DESKTOP_MAX_TEXT, positive_int


MAX_UI_NODES = 256
MAX_UI_DEPTH = 8
MAX_UI_CHILDREN = 64
MAX_UI_TEXT = min(512, DESKTOP_MAX_TEXT)
STATUSES = frozenset({"available", "partial", "unavailable"})
DIAGNOSTICS = frozenset({
    "unsupported_platform",
    "native_api_unavailable",
    "collection_failed",
    "expected_application_incomplete",
    "accessibility_permission_denied",
    "active_application_unavailable",
    "active_application_changed",
    "application_element_unavailable",
    "application_element_mismatch",
    "traversal_failed",
    "node_read_failed",
    "foreign_element",
    "role_unavailable",
    "geometry_unavailable",
    "children_unavailable",
    "children_truncated",
    "depth_truncated",
    "nodes_truncated",
    "cycle_or_duplicate_element",
    "collection_timeout",
    "worker_failed",
    "worker_output_invalid",
    "collection_busy",
})


def optional_ui_text(value):
    return value is None or (type(value) is str and len(value) <= MAX_UI_TEXT)


def valid_path(path):
    return (
        type(path) is tuple
        and len(path) <= MAX_UI_DEPTH
        and all(type(index) is int and 0 <= index < MAX_UI_CHILDREN for index in path)
    )


@dataclass(frozen=True)
class UIElementObservation:
    """One snapshot-local AX element. Paths are evidence, not stable identity."""

    path: tuple[int, ...]
    owner_pid: int
    role: str | None = None
    subrole: str | None = None
    title: str | None = field(default=None, repr=False)
    description: str | None = field(default=None, repr=False)
    enabled: bool | None = None
    focused: bool | None = None
    selected: bool | None = None
    position_x: float | None = None
    position_y: float | None = None
    width: float | None = None
    height: float | None = None

    def __post_init__(self):
        if not valid_path(self.path):
            raise ValueError("Invalid bounded UI element path.")
        if not positive_int(self.owner_pid):
            raise ValueError("Invalid UI element owner PID.")
        for value in (self.role, self.subrole, self.title, self.description):
            if not optional_ui_text(value):
                raise ValueError("Invalid bounded UI element text.")
        for value in (self.enabled, self.focused, self.selected):
            if value is not None and type(value) is not bool:
                raise ValueError("UI element state must be boolean or unknown.")

        point = (self.position_x, self.position_y)
        if (point[0] is None) != (point[1] is None):
            raise ValueError("UI element AX position must be complete or unknown.")
        for value in point:
            if (
                value is not None
                and (type(value) not in (int, float) or not math.isfinite(value))
            ):
                raise ValueError("UI element AX position must be finite numeric evidence.")

        size = (self.width, self.height)
        if (size[0] is None) != (size[1] is None):
            raise ValueError("UI element AX size must be complete or unknown.")
        for value in size:
            if (
                value is not None
                and (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or value < 0
                )
            ):
                raise ValueError("UI element AX size must be finite and nonnegative.")


@dataclass(frozen=True)
class StructuredUIObservation:
    captured_at_monotonic: float
    status: str
    active_application: ApplicationIdentity | None = None
    elements: tuple[UIElementObservation, ...] = ()
    traversal_succeeded: bool = False
    diagnostics: tuple[str, ...] = ()
    observation_id: str = field(default_factory=lambda: uuid4().hex)
    scope: str = "frontmost_application_accessibility_tree"

    def __post_init__(self):
        if (
            type(self.captured_at_monotonic) not in (int, float)
            or not math.isfinite(self.captured_at_monotonic)
            or self.captured_at_monotonic < 0
        ):
            raise ValueError("Invalid UI observation timestamp.")
        if type(self.status) is not str or self.status not in STATUSES:
            raise ValueError("Invalid UI observation status.")
        if (
            type(self.observation_id) is not str
            or len(self.observation_id) != 32
            or any(c not in "0123456789abcdef" for c in self.observation_id)
        ):
            raise ValueError("Invalid UI observation identity.")
        if self.scope != "frontmost_application_accessibility_tree":
            raise ValueError("Invalid UI observation scope.")
        if type(self.traversal_succeeded) is not bool:
            raise ValueError("Invalid traversal status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str or code not in DIAGNOSTICS for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Invalid structured UI diagnostics.")
        if type(self.elements) is not tuple or len(self.elements) > MAX_UI_NODES:
            raise ValueError("Invalid bounded UI element collection.")
        if self.active_application is not None and type(self.active_application) is not ApplicationIdentity:
            raise ValueError("Invalid active application identity.")

        seen = set()
        for index, element in enumerate(self.elements):
            if type(element) is not UIElementObservation:
                raise ValueError("Invalid UI element observation.")
            if self.active_application is None or element.owner_pid != self.active_application.pid:
                raise ValueError("UI elements require matching process ownership.")
            if element.path in seen:
                raise ValueError("Duplicate UI element path.")
            seen.add(element.path)
            if element.path:
                parent = element.path[:-1]
                if parent not in seen:
                    raise ValueError("UI elements require a previously observed parent path.")
            elif index != 0:
                raise ValueError("Root UI element must be first.")

        if self.elements and self.elements[0].path != ():
            raise ValueError("UI evidence requires a root element.")
        if self.elements and not self.traversal_succeeded:
            raise ValueError("Failed traversal cannot claim UI elements.")

        if self.status == "unavailable":
            if self.active_application is not None or self.elements or self.traversal_succeeded:
                raise ValueError("Unavailable UI evidence cannot claim coherent context.")
        else:
            if self.active_application is None or not self.traversal_succeeded or not self.elements:
                raise ValueError("Available UI evidence requires a traversed application tree.")

        if self.status == "available" and self.diagnostics:
            raise ValueError("Available UI evidence cannot contain diagnostics.")
        if self.status != "available" and not self.diagnostics:
            raise ValueError("Incomplete UI evidence requires diagnostics.")

    def to_dict(self, *, include_text=False):
        payload = asdict(self)
        if not include_text:
            for element in payload["elements"]:
                element["title"] = None
                element["description"] = None
        return payload

    @classmethod
    def from_dict(cls, payload):
        if type(payload) is not dict:
            raise ValueError("UI observation payload must be an object.")
        data = dict(payload)
        if (
            type(data.get("elements")) is not list
            or len(data["elements"]) > MAX_UI_NODES
            or type(data.get("diagnostics")) is not list
        ):
            raise ValueError("Invalid UI observation collections.")
        app = data.get("active_application")
        data["active_application"] = ApplicationIdentity(**app) if app is not None else None
        elements = []
        for raw in data["elements"]:
            if type(raw) is not dict:
                raise ValueError("Invalid UI element payload.")
            element = dict(raw)
            path = element.get("path")
            if type(path) is not list:
                raise ValueError("Invalid UI element path payload.")
            element["path"] = tuple(path)
            elements.append(UIElementObservation(**element))
        data["elements"] = tuple(elements)
        data["diagnostics"] = tuple(data["diagnostics"])
        return cls(**data)


def unavailable(code, captured_at):
    return StructuredUIObservation(
        captured_at_monotonic=captured_at,
        status="unavailable",
        diagnostics=(code,),
    )
