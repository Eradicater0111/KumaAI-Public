"""Bounded read-only workflow for one desktop-bound focus observation.

8D1E composes already-existing evidence layers:

    desktop before
        ->
    isolated native focus observation
        ->
    desktop after
        ->
    DesktopFocusBinding
        ->
    exact-ID focus publication

A successful workflow publishes the exact FocusedUIObservation and an exact
FocusDesktopProvenance object graph containing the same focus, binding, and
desktop-before/desktop-after source objects.

The returned binding is historical evidence only. Later trusted consumers must
recover active provenance by the exact focus observation ID rather than trusting
a caller-supplied or reconstructed binding.

A new attempt invalidates prior focus publication and provenance before
collecting anything. Any unsuccessful attempt leaves neither active.

The workflow grants no text authority, keyboard authority, permission,
semantic-target authority, or physical execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import threading
import time

from app.desktop.collector import (
    validate_window_limit,
)
from app.desktop.contracts import (
    ApplicationIdentity,
    DesktopContextObservation,
)
from app.ui_observation.focus_binding import (
    DesktopFocusBinding,
    DesktopFocusBindingResult,
    REJECTION_CODES as FOCUS_BINDING_REJECTION_CODES,
    bind_desktop_to_focus,
)
from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FocusedUIObservation,
)
from app.ui_observation.focus_store import (
    FOCUSED_UI_OBSERVATIONS,
    FocusedUIObservationStore,
)
from app.ui_observation.focus_provenance import (
    FOCUS_DESKTOP_PROVENANCE,
    FocusDesktopProvenance,
    FocusDesktopProvenanceStore,
)


LOCAL_WORKFLOW_CODES = frozenset({
    "workflow_busy",
    "workflow_timeout",
    "clock_unavailable",
    "store_reset_failed",
    "desktop_before_collection_failed",
    "focus_collection_failed",
    "desktop_after_collection_failed",
    "invalid_stage_result",
    "invalid_stage_timestamp",
    "focused_ui_unavailable",
    "application_identity_incomplete",
    "publication_failed",
    "evidence_expired",
})


WORKFLOW_CODES = frozenset(
    set(
        LOCAL_WORKFLOW_CODES
    )
    | set(
        FOCUS_BINDING_REJECTION_CODES
    )
)


_WORKFLOW_LOCK = threading.Lock()


def _finite_number(
    value,
):
    if type(value) not in (
        int,
        float,
    ):
        return False

    try:
        return math.isfinite(
            value
        )
    except OverflowError:
        return False


def _complete_application(
    value,
):
    return (
        type(value) is ApplicationIdentity
        and type(value.pid) is int
        and value.pid > 0
        and type(value.bundle_id) is str
        and bool(
            value.bundle_id.strip()
        )
    )


@dataclass(frozen=True)
class FocusObservationWorkflowResult:
    """Read-only result for one exact bounded focus collection."""

    binding: DesktopFocusBinding | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if (
            type(self.diagnostics) is not tuple
            or any(
                type(code) is not str
                for code in self.diagnostics
            )
            or len(set(self.diagnostics))
            != len(self.diagnostics)
        ):
            raise ValueError(
                "Focus workflow diagnostics must be immutable and unique."
            )

        if self.binding is not None:
            DesktopFocusBindingResult(
                binding=self.binding,
                diagnostics=self.diagnostics,
            )
            return

        if (
            len(self.diagnostics) != 1
            or self.diagnostics[0]
            not in WORKFLOW_CODES
        ):
            raise ValueError(
                "Failed focus workflow requires one structured diagnostic."
            )

    @property
    def available(
        self,
    ):
        return (
            self.binding is not None
        )

    @property
    def focus_observation_id(
        self,
    ):
        if self.binding is None:
            return ""

        return (
            self.binding.focus_observation_id
        )


class _WorkflowFailure(
    Exception
):
    def __init__(
        self,
        code,
    ):
        self.code = code


def collect_bound_focused_ui(
    *,
    timeout_seconds=3.0,
    max_windows=32,
    max_age_seconds=5.0,
    max_capture_gap_seconds=3.0,
    desktop_collector=None,
    focus_collector=None,
    store=FOCUSED_UI_OBSERVATIONS,
    provenance_store=FOCUS_DESKTOP_PROVENANCE,
    clock=time.monotonic,
):
    """Collect and publish one exact desktop-bound focused AX observation.

    Production callers normally use defaults.

    Tests may inject read-only collectors, an exact FocusedUIObservationStore,
    and a deterministic monotonic clock.

    There is deliberately no latest-focus lookup here. The returned binding
    carries the exact focus observation ID, and consumers must use that exact
    ID against active focus evidence.

    This function performs no AX write and no physical input.
    """

    validate_window_limit(
        max_windows
    )

    if (
        type(timeout_seconds)
        not in (
            int,
            float,
        )
        or not math.isfinite(
            timeout_seconds
        )
        or not (
            0.05
            <= timeout_seconds
            <= 10.0
        )
    ):
        raise ValueError(
            "timeout_seconds must be finite and between 0.05 and 10."
        )

    if not callable(
        clock
    ):
        raise TypeError(
            "clock must be callable."
        )

    if type(store) is not FocusedUIObservationStore:
        raise TypeError(
            "store must be a FocusedUIObservationStore."
        )

    if type(
        provenance_store
    ) is not FocusDesktopProvenanceStore:
        raise TypeError(
            "provenance_store must be a "
            "FocusDesktopProvenanceStore."
        )

    bind_desktop_to_focus(
        None,
        None,
        None,
        clock=lambda: 0.0,
        max_age_seconds=max_age_seconds,
        max_capture_gap_seconds=max_capture_gap_seconds,
    )

    if desktop_collector is None:
        from app.desktop.runtime import (
            collect_desktop_context,
        )

        desktop_collector = (
            collect_desktop_context
        )

    if focus_collector is None:
        from app.ui_observation.focus_runtime import (
            collect_focused_ui,
        )

        focus_collector = (
            collect_focused_ui
        )

    if not callable(
        desktop_collector
    ):
        raise TypeError(
            "desktop_collector must be callable."
        )

    if not callable(
        focus_collector
    ):
        raise TypeError(
            "focus_collector must be callable."
        )

    if not _WORKFLOW_LOCK.acquire(
        blocking=False
    ):
        return FocusObservationWorkflowResult(
            diagnostics=(
                "workflow_busy",
            )
        )

    published = False
    last_now = None

    def now():
        nonlocal last_now

        try:
            value = clock()
        except Exception:
            raise _WorkflowFailure(
                "clock_unavailable"
            ) from None

        if (
            not _finite_number(
                value
            )
            or value < 0
            or (
                last_now is not None
                and value < last_now
            )
        ):
            raise _WorkflowFailure(
                "clock_unavailable"
            )

        last_now = float(
            value
        )

        return float(
            value
        )

    def remaining(
        deadline,
    ):
        value = (
            deadline
            - now()
        )

        if value < 0.05:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        return value

    def invoke_desktop(
        failure_code,
        deadline,
    ):
        started = now()

        budget = (
            deadline
            - started
        )

        if budget < 0.05:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        try:
            value = desktop_collector(
                timeout_seconds=budget,
                max_windows=max_windows,
            )
        except TimeoutError:
            raise _WorkflowFailure(
                "workflow_timeout"
            ) from None
        except Exception:
            raise _WorkflowFailure(
                failure_code
            ) from None

        finished = now()

        if finished >= deadline:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        if type(value) is not DesktopContextObservation:
            raise _WorkflowFailure(
                "invalid_stage_result"
            )

        captured = (
            value.captured_at_monotonic
        )

        if (
            not _finite_number(
                captured
            )
            or captured < started
            or captured > finished
        ):
            raise _WorkflowFailure(
                "invalid_stage_timestamp"
            )

        if len(
            value.windows
        ) > max_windows:
            raise _WorkflowFailure(
                "invalid_stage_result"
            )

        if value.status == "unavailable":
            raise _WorkflowFailure(
                "desktop_context_unavailable"
            )

        return value

    def invoke_focus(
        application,
        deadline,
    ):
        started = now()

        budget = (
            deadline
            - started
        )

        if budget < 0.05:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        try:
            value = focus_collector(
                application,
                timeout_seconds=budget,
            )
        except TimeoutError:
            raise _WorkflowFailure(
                "workflow_timeout"
            ) from None
        except Exception:
            raise _WorkflowFailure(
                "focus_collection_failed"
            ) from None

        finished = now()

        if finished >= deadline:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        if type(value) is not FocusedUIObservation:
            raise _WorkflowFailure(
                "invalid_stage_result"
            )

        captured = (
            value.captured_at_monotonic
        )

        if (
            not _finite_number(
                captured
            )
            or captured < started
            or captured > finished
        ):
            raise _WorkflowFailure(
                "invalid_stage_timestamp"
            )

        if (
            value.status
            != FOCUS_STATUS_AVAILABLE
        ):
            raise _WorkflowFailure(
                "focused_ui_unavailable"
            )

        return value

    try:
        try:
            len(store)
        except ValueError:
            raise _WorkflowFailure(
                "clock_unavailable"
            ) from None
        except Exception:
            raise _WorkflowFailure(
                "store_reset_failed"
            ) from None

        try:
            len(
                provenance_store
            )
        except Exception:
            raise _WorkflowFailure(
                "clock_unavailable"
            ) from None

        try:
            provenance_store.clear()
            store.clear()
        except Exception:
            raise _WorkflowFailure(
                "store_reset_failed"
            ) from None

        started = now()

        deadline = (
            started
            + float(
                timeout_seconds
            )
        )

        before = invoke_desktop(
            "desktop_before_collection_failed",
            deadline,
        )

        application = (
            before.active_application
        )

        if not _complete_application(
            application
        ):
            raise _WorkflowFailure(
                "application_identity_incomplete"
            )

        focus = invoke_focus(
            application,
            deadline,
        )

        after = invoke_desktop(
            "desktop_after_collection_failed",
            deadline,
        )

        binding_result = (
            bind_desktop_to_focus(
                focus,
                before,
                after,
                clock=now,
                max_age_seconds=(
                    max_age_seconds
                ),
                max_capture_gap_seconds=(
                    max_capture_gap_seconds
                ),
            )
        )

        if not binding_result.linked:
            raise _WorkflowFailure(
                binding_result.diagnostics[0]
            )

        binding = (
            binding_result.binding
        )

        current = now()

        if current >= deadline:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        if not binding.is_fresh(
            current
        ):
            raise _WorkflowFailure(
                "evidence_expired"
            )

        try:
            accepted = (
                store.publish(
                    focus
                )
            )
        except Exception:
            raise _WorkflowFailure(
                "publication_failed"
            ) from None

        if not accepted:
            raise _WorkflowFailure(
                "publication_failed"
            )

        try:
            provenance = (
                FocusDesktopProvenance(
                    binding=binding,
                    focus_observation=focus,
                    desktop_before=before,
                    desktop_after=after,
                )
            )
        except Exception:
            raise _WorkflowFailure(
                "publication_failed"
            ) from None

        try:
            provenance_accepted = (
                provenance_store.publish(
                    provenance
                )
            )
        except Exception:
            raise _WorkflowFailure(
                "publication_failed"
            ) from None

        if not provenance_accepted:
            raise _WorkflowFailure(
                "publication_failed"
            )

        current = now()

        if current >= deadline:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        if not binding.is_fresh(
            current
        ):
            raise _WorkflowFailure(
                "evidence_expired"
            )

        try:
            active = store.get(
                focus.observation_id
            )
        except Exception:
            raise _WorkflowFailure(
                "publication_failed"
            ) from None

        if active is not focus:
            raise _WorkflowFailure(
                "publication_failed"
            )

        try:
            active_provenance = (
                provenance_store.get(
                    focus.observation_id
                )
            )
        except Exception:
            raise _WorkflowFailure(
                "publication_failed"
            ) from None

        if (
            active_provenance
            is not provenance
            or active_provenance.focus_observation
            is not focus
            or active_provenance.binding
            is not binding
        ):
            raise _WorkflowFailure(
                "publication_failed"
            )

        current = now()

        if current >= deadline:
            raise _WorkflowFailure(
                "workflow_timeout"
            )

        if not binding.is_fresh(
            current
        ):
            raise _WorkflowFailure(
                "evidence_expired"
            )

        result = (
            FocusObservationWorkflowResult(
                binding=binding,
                diagnostics=(
                    binding_result.diagnostics
                ),
            )
        )

        published = True

        return result

    except _WorkflowFailure as error:
        return FocusObservationWorkflowResult(
            diagnostics=(
                error.code,
            )
        )

    except Exception:
        return FocusObservationWorkflowResult(
            diagnostics=(
                "publication_failed",
            )
        )

    finally:
        if not published:
            try:
                provenance_store.clear()
            except Exception:
                pass

            try:
                store.clear()
            except Exception:
                pass

        _WORKFLOW_LOCK.release()
