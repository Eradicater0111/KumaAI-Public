"""Platform-independent, immutable evidence contracts for Phase 7.4A1."""

from dataclasses import asdict, dataclass, field
import math
from uuid import uuid4


MAX_WINDOWS = 64
MAX_TEXT = 1024
COORDINATE_SPACE = "quartz_global_screen_space_top_left_main_display"
STATUSES = frozenset({"available", "partial", "unavailable"})
DIAGNOSTICS = frozenset({
    "unsupported_platform", "native_api_unavailable", "collection_failed",
    "active_application_unavailable", "active_application_changed",
    "window_enumeration_unavailable", "screen_capture_access_unavailable",
    "screen_capture_access_unknown", "window_metadata_missing",
    "malformed_window_record", "duplicate_window_identity", "windows_truncated",
    "focus_unavailable", "collection_timeout", "worker_failed",
    "worker_output_invalid", "collection_busy",
    "window_changed_during_collection", "window_revalidation_unavailable",
})


def positive_int(value):
    return type(value) is int and value > 0


def optional_text(value):
    return value is None or (type(value) is str and len(value) <= MAX_TEXT)


@dataclass(frozen=True)
class ApplicationIdentity:
    pid: int
    bundle_id: str | None = field(default=None, repr=False)
    name: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if not positive_int(self.pid):
            raise ValueError("Invalid application PID.")
        if not optional_text(self.bundle_id) or not optional_text(self.name):
            raise ValueError("Invalid application metadata.")


@dataclass(frozen=True)
class WindowBounds:
    x: float
    y: float
    width: float
    height: float
    coordinate_space: str

    def __post_init__(self):
        for value in (self.x, self.y, self.width, self.height):
            if (type(value) not in (int, float)
                    or not math.isfinite(value)):
                raise ValueError("Bounds must be finite numbers.")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Bounds dimensions must be positive.")
        if self.coordinate_space != COORDINATE_SPACE:
            raise ValueError("An explicit supported coordinate space is required.")


@dataclass(frozen=True)
class WindowObservation:
    owner_pid: int
    native_window_id: int | None = None
    title: str | None = field(default=None, repr=False)
    bounds: WindowBounds | None = None
    focused: bool | None = None

    def __post_init__(self):
        if not positive_int(self.owner_pid):
            raise ValueError("Invalid window owner PID.")
        if self.native_window_id is not None and not positive_int(self.native_window_id):
            raise ValueError("Invalid native window identity.")
        if not optional_text(self.title):
            raise ValueError("Invalid window title.")
        if self.bounds is not None and type(self.bounds) is not WindowBounds:
            raise ValueError("Invalid window bounds.")
        if self.focused is not None and type(self.focused) is not bool:
            raise ValueError("Window focus must be known boolean or unknown.")


@dataclass(frozen=True)
class DesktopContextObservation:
    captured_at_monotonic: float
    status: str
    active_application: ApplicationIdentity | None = None
    windows: tuple[WindowObservation, ...] = ()
    enumeration_succeeded: bool = False
    diagnostics: tuple[str, ...] = ()
    observation_id: str = field(default_factory=lambda: uuid4().hex)
    window_scope: str = "active_application_onscreen_windows"

    def __post_init__(self):
        if (type(self.captured_at_monotonic) not in (int, float)
                or not math.isfinite(self.captured_at_monotonic)
                or self.captured_at_monotonic < 0):
            raise ValueError("Invalid observation timestamp.")
        if type(self.status) is not str or self.status not in STATUSES:
            raise ValueError("Invalid collection status.")
        if (type(self.observation_id) is not str or len(self.observation_id) != 32
                or any(c not in "0123456789abcdef" for c in self.observation_id)):
            raise ValueError("Invalid observation identity.")
        if self.window_scope != "active_application_onscreen_windows":
            raise ValueError("Invalid window scope.")
        if type(self.enumeration_succeeded) is not bool:
            raise ValueError("Invalid enumeration status.")
        if (type(self.diagnostics) is not tuple
                or any(type(d) is not str or d not in DIAGNOSTICS for d in self.diagnostics)
                or len(set(self.diagnostics)) != len(self.diagnostics)):
            raise ValueError("Invalid structured diagnostics.")
        if type(self.windows) is not tuple or len(self.windows) > MAX_WINDOWS:
            raise ValueError("Invalid bounded window collection.")
        if self.active_application is not None and type(self.active_application) is not ApplicationIdentity:
            raise ValueError("Invalid application identity.")
        seen = set()
        for window in self.windows:
            if (type(window) is not WindowObservation or self.active_application is None
                    or window.owner_pid != self.active_application.pid):
                raise ValueError("Windows require matching native process ownership.")
            if window.native_window_id is not None:
                if window.native_window_id in seen:
                    raise ValueError("Duplicate native window identity.")
                seen.add(window.native_window_id)
        if self.windows and not self.enumeration_succeeded:
            raise ValueError("Failed enumeration cannot contain windows.")
        if self.status == "unavailable":
            if self.active_application is not None or self.windows or self.enumeration_succeeded:
                raise ValueError("Unavailable observations cannot claim coherent context.")
        elif self.active_application is None:
            raise ValueError("Available evidence requires an active application.")
        if self.status == "available" and (self.diagnostics or not self.enumeration_succeeded):
            raise ValueError("Available requires complete collection integrity.")
        if self.status == "available" and any(
            w.native_window_id is None or w.title is None or w.bounds is None
            or w.focused is None for w in self.windows
        ):
            raise ValueError("Missing window evidence cannot be fully available.")
        if self.status != "available" and not self.diagnostics:
            raise ValueError("Incomplete observations require diagnostics.")

    def to_dict(self, *, include_titles=False):
        payload = asdict(self)
        if not include_titles:
            for window in payload["windows"]:
                window["title"] = None
        return payload

    @classmethod
    def from_dict(cls, payload):
        # Reject extra fields through constructor signatures; never coerce types.
        if type(payload) is not dict:
            raise ValueError("Observation payload must be an object.")
        data = dict(payload)
        if (type(data.get("windows")) is not list or len(data["windows"]) > MAX_WINDOWS
                or type(data.get("diagnostics")) is not list):
            raise ValueError("Invalid observation collections.")
        app = data.get("active_application")
        data["active_application"] = ApplicationIdentity(**app) if app is not None else None
        windows = []
        for raw in data["windows"]:
            window = dict(raw)
            bounds = window.get("bounds")
            window["bounds"] = WindowBounds(**bounds) if bounds is not None else None
            windows.append(WindowObservation(**window))
        data["windows"] = tuple(windows)
        data["diagnostics"] = tuple(data["diagnostics"])
        return cls(**data)


def unavailable(code, captured_at):
    return DesktopContextObservation(
        captured_at_monotonic=captured_at, status="unavailable", diagnostics=(code,),
    )
