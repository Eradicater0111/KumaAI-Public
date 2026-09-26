"""Explicit read-only orchestration over trusted, timeout-aware dependencies.

No native capture adapter, global store, model, or execution integration is
installed. Callbacks own cancellation of their blocking work; late returns
never produce a published link.
"""

from dataclasses import dataclass
import threading
import time
from typing import Protocol

from app.desktop.contracts import DesktopContextObservation
from app.desktop.collector import validate_window_limit
from app.desktop.screen_binding import (
    DesktopScreenBinding, DesktopScreenBindingResult, REJECTION_CODES,
    bind_desktop_to_screen,
)
from app.desktop.store import DesktopContextStore, _finite_number
from app.vision.observation import ScreenObservation


WORKFLOW_CODES = frozenset({
    'workflow_busy', 'workflow_timeout', 'clock_unavailable',
    'before_collection_failed', 'capture_failed', 'after_collection_failed',
    'invalid_stage_result', 'invalid_stage_timestamp', 'publication_failed',
    'capture_permission_unavailable',
}) | REJECTION_CODES


class DesktopCollector(Protocol):
    def __call__(self, *, timeout_seconds: float, max_windows: int) -> DesktopContextObservation: ...


class CaptureObservation(Protocol):
    def __call__(self, *, timeout_seconds: float) -> ScreenObservation: ...


@dataclass(frozen=True)
class DesktopWorkflowResult:
    binding: DesktopScreenBinding | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if self.binding is not None:
            DesktopScreenBindingResult(self.binding, self.diagnostics)
        elif (type(self.diagnostics) is not tuple or len(self.diagnostics) != 1
              or type(self.diagnostics[0]) is not str or self.diagnostics[0] not in WORKFLOW_CODES):
            raise ValueError('Failed workflows require one structured diagnostic.')

    @property
    def linked(self):
        return self.binding is not None


class _WorkflowFailure(Exception):
    def __init__(self, code):
        self.code = code


class DesktopObservationWorkflow:
    """One current linked observation and at most two retained desktop samples.

    A new attempt invalidates previous publication. While collection is active,
    reads return None and another run returns busy. No failure falls back to a
    prior result. A returned immutable result is historical, not action authority.
    """

    def __init__(self, *, desktop_collector: DesktopCollector,
                 capture_observation: CaptureObservation, clock=time.monotonic,
                 timeout_seconds=3.0, max_windows=32,
                 max_age_seconds=5.0, max_capture_gap_seconds=1.0):
        if not all(callable(v) for v in (desktop_collector, capture_observation, clock)):
            raise TypeError('Dependencies and clock must be callable.')
        if not _finite_number(timeout_seconds) or not 0.05 <= timeout_seconds <= 10:
            raise ValueError('timeout_seconds must be finite and between 0.05 and 10.')
        validate_window_limit(max_windows)
        # Validate A3 policy without invoking dependencies or any native API.
        bind_desktop_to_screen(None, None, None, clock=lambda: 0,
                               max_age_seconds=max_age_seconds,
                               max_capture_gap_seconds=max_capture_gap_seconds)
        self._collector = desktop_collector
        self._capture = capture_observation
        self._clock = clock
        self._timeout = float(timeout_seconds)
        self._max_windows = max_windows
        self._max_age = max_age_seconds
        self._max_gap = max_capture_gap_seconds
        self._lock = threading.Lock()
        self._last_now = None
        self._result = None
        self._store = DesktopContextStore(capacity=2, ttl_seconds=max_age_seconds,
                                          clock=self._now)

    def _now(self):
        try:
            now = self._clock()
        except Exception:
            raise _WorkflowFailure('clock_unavailable') from None
        if (not _finite_number(now) or now < 0
                or (self._last_now is not None and now < self._last_now)):
            raise _WorkflowFailure('clock_unavailable')
        self._last_now = now
        return now

    def _invalidate(self):
        self._result = None
        self._store.clear()

    def _invoke(self, callback, kind, failure_code, deadline, **kwargs):
        started = self._now()
        remaining = deadline - started
        # A1's collector accepts a minimum timeout of 0.05 seconds.
        if remaining < 0.05:
            raise _WorkflowFailure('workflow_timeout')
        try:
            value = callback(timeout_seconds=remaining, **kwargs)
        except TimeoutError:
            raise _WorkflowFailure('workflow_timeout') from None
        except Exception:
            raise _WorkflowFailure(failure_code) from None
        finished = self._now()
        if finished >= deadline:
            raise _WorkflowFailure('workflow_timeout')
        if type(value) is not kind:
            raise _WorkflowFailure('invalid_stage_result')
        captured = value.captured_at_monotonic
        if not _finite_number(captured) or not started <= captured <= finished:
            raise _WorkflowFailure('invalid_stage_timestamp')
        if kind is DesktopContextObservation:
            if len(value.windows) > self._max_windows:
                raise _WorkflowFailure('invalid_stage_result')
            if value.status == 'unavailable':
                raise _WorkflowFailure('desktop_context_unavailable')
            if {'screen_capture_access_unavailable', 'screen_capture_access_unknown'} & set(value.diagnostics):
                raise _WorkflowFailure('capture_permission_unavailable')
        return value

    def run(self) -> DesktopWorkflowResult:
        if not self._lock.acquire(blocking=False):
            return DesktopWorkflowResult(diagnostics=('workflow_busy',))
        published = False
        try:
            self._invalidate()
            deadline = self._now() + self._timeout
            before = self._invoke(self._collector, DesktopContextObservation,
                                  'before_collection_failed', deadline,
                                  max_windows=self._max_windows)
            # A missing identity must be rejected before triggering capture.
            app = before.active_application
            if app is None or not app.bundle_id or not app.bundle_id.strip():
                raise _WorkflowFailure('application_identity_incomplete')
            screen = self._invoke(self._capture, ScreenObservation, 'capture_failed', deadline)
            after = self._invoke(self._collector, DesktopContextObservation,
                                 'after_collection_failed', deadline,
                                 max_windows=self._max_windows)
            result = bind_desktop_to_screen(screen, before, after, clock=self._now,
                                            max_age_seconds=self._max_age,
                                            max_capture_gap_seconds=self._max_gap)
            if not result.linked:
                raise _WorkflowFailure(result.diagnostics[0])
            if self._now() >= deadline:
                raise _WorkflowFailure('workflow_timeout')
            if not self._store.put(before) or not self._store.put(after):
                raise _WorkflowFailure('publication_failed')
            current = self._now()
            if current >= deadline:
                raise _WorkflowFailure('workflow_timeout')
            if (not result.binding.is_fresh(current)
                    or self._store.get(before.observation_id) is None
                    or self._store.get(after.observation_id) is None):
                raise _WorkflowFailure('evidence_expired')
            current = self._now()
            if current >= deadline:
                raise _WorkflowFailure('workflow_timeout')
            if not result.binding.is_fresh(current):
                raise _WorkflowFailure('evidence_expired')
            self._result = DesktopWorkflowResult(result.binding, result.diagnostics)
            published = True
            return self._result
        except _WorkflowFailure as error:
            return DesktopWorkflowResult(diagnostics=(error.code,))
        except Exception:
            return DesktopWorkflowResult(diagnostics=('publication_failed',))
        finally:
            if not published:
                self._invalidate()
            self._lock.release()

    def _current(self):
        if self._result is None:
            return None
        try:
            binding = self._result.binding
            if (not binding.is_fresh(self._now())
                    or self._store.get(binding.desktop_before_id) is None
                    or self._store.get(binding.desktop_after_id) is None
                    or not binding.is_fresh(self._now())):
                self._invalidate()
        except Exception:
            self._invalidate()
        return self._result

    def latest(self) -> DesktopWorkflowResult | None:
        if not self._lock.acquire(blocking=False):
            return None
        try:
            return self._current()
        finally:
            self._lock.release()

    def get_context(self, observation_id: str) -> DesktopContextObservation | None:
        if type(observation_id) is not str:
            raise TypeError('observation_id must be a string.')
        if not self._lock.acquire(blocking=False):
            return None
        try:
            if self._current() is None:
                return None
            try:
                context = self._store.get(observation_id)
                return context if self._current() is not None else None
            except Exception:
                self._invalidate()
                return None
        finally:
            self._lock.release()
