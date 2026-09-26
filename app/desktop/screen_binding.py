"""Metadata-only desktop context bracketing for trusted screen evidence.

A bracket or binding is historical evidence only. It is not pixel evidence,
a screen-store claim, permission, semantic target authority, or execution
authority.
"""

from dataclasses import dataclass, field
import math
import time

from app.desktop.contracts import DesktopContextObservation, DIAGNOSTICS, MAX_TEXT


MAX_BINDING_AGE_SECONDS = 60.0
MAX_CAPTURE_GAP_SECONDS = 5.0
REJECTION_CODES = frozenset({
    'clock_unavailable', 'invalid_capture_metadata', 'invalid_screen_metadata',
    'invalid_desktop_metadata', 'invalid_capture_bracket',
    'desktop_context_unavailable', 'application_identity_incomplete',
    'application_changed', 'desktop_samples_not_distinct',
    'capture_order_invalid', 'capture_gap_exceeded', 'capture_timestamp_mismatch',
    'evidence_from_future', 'evidence_expired',
})


def _timestamp(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _identifier(value):
    return (type(value) is str and len(value) == 32
            and all(c in '0123456789abcdef' for c in value))


def _bundle(value):
    return type(value) is str and 0 < len(value) <= MAX_TEXT and bool(value.strip())


def _policy(max_age_seconds, max_capture_gap_seconds):
    return (
        _timestamp(max_age_seconds)
        and 0.05 <= max_age_seconds <= MAX_BINDING_AGE_SECONDS
        and _timestamp(max_capture_gap_seconds)
        and 0 < max_capture_gap_seconds <= min(MAX_CAPTURE_GAP_SECONDS, max_age_seconds)
    )


def _partial_diagnostics(before_status, after_status):
    return ('desktop_context_partial',) if 'partial' in (before_status, after_status) else ()


@dataclass(frozen=True)
class DesktopCaptureBracket:
    """Native desktop evidence that bracketed one physical screen capture.

    It intentionally carries no screen observation ID or semantic analysis.
    A later ScreenObservation can be linked only if it records the exact same
    capture timestamp and the bracket is still fresh.
    """

    desktop_before_id: str
    desktop_after_id: str
    application_pid: int
    application_bundle_id: str = field(repr=False)
    desktop_before_captured_at: float
    screen_captured_at: float
    desktop_after_captured_at: float
    bracketed_at_monotonic: float
    expires_at_monotonic: float
    desktop_before_status: str
    desktop_after_status: str
    desktop_before_diagnostics: tuple[str, ...] = ()
    desktop_after_diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if not all(_identifier(v) for v in (
                self.desktop_before_id, self.desktop_after_id)):
            raise ValueError('Bracket desktop IDs must be canonical observation IDs.')
        if self.desktop_before_id == self.desktop_after_id:
            raise ValueError('Two distinct desktop observations are required.')
        if type(self.application_pid) is not int or self.application_pid <= 0:
            raise ValueError('Invalid application PID.')
        if not _bundle(self.application_bundle_id):
            raise ValueError('Complete application identity is required.')
        times = (
            self.desktop_before_captured_at,
            self.screen_captured_at,
            self.desktop_after_captured_at,
            self.bracketed_at_monotonic,
            self.expires_at_monotonic,
        )
        if not all(_timestamp(v) for v in times):
            raise ValueError('Bracket times must be finite and nonnegative.')
        before, screen, after, bracketed, expiry = times
        if not (before <= screen <= after <= bracketed < expiry and before < after):
            raise ValueError('Bracket capture order or expiry is invalid.')
        if (after - before > MAX_CAPTURE_GAP_SECONDS
                or expiry - before > MAX_BINDING_AGE_SECONDS):
            raise ValueError('Bracket interval exceeds its hard bounds.')
        _validate_source_integrity(
            self.desktop_before_status,
            self.desktop_before_diagnostics,
            self.desktop_after_status,
            self.desktop_after_diagnostics,
        )

    def is_fresh(self, now):
        return (_timestamp(now)
                and self.bracketed_at_monotonic <= now < self.expires_at_monotonic)


@dataclass(frozen=True)
class DesktopCaptureBracketResult:
    bracket: DesktopCaptureBracket | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        _validate_result(self.bracket, DesktopCaptureBracket, self.diagnostics)

    @property
    def bracketed(self):
        return self.bracket is not None


@dataclass(frozen=True)
class DesktopScreenBinding:
    screen_observation_id: str
    desktop_before_id: str
    desktop_after_id: str
    application_pid: int
    application_bundle_id: str = field(repr=False)
    desktop_before_captured_at: float
    screen_captured_at: float
    desktop_after_captured_at: float
    bound_at_monotonic: float
    expires_at_monotonic: float
    desktop_before_status: str
    desktop_after_status: str
    desktop_before_diagnostics: tuple[str, ...] = ()
    desktop_after_diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if not all(_identifier(v) for v in (
                self.screen_observation_id, self.desktop_before_id, self.desktop_after_id)):
            raise ValueError('Binding IDs must be canonical observation IDs.')
        if self.desktop_before_id == self.desktop_after_id:
            raise ValueError('Two distinct desktop observations are required.')
        if type(self.application_pid) is not int or self.application_pid <= 0:
            raise ValueError('Invalid application PID.')
        if not _bundle(self.application_bundle_id):
            raise ValueError('Complete application identity is required.')
        times = (
            self.desktop_before_captured_at,
            self.screen_captured_at,
            self.desktop_after_captured_at,
            self.bound_at_monotonic,
            self.expires_at_monotonic,
        )
        if not all(_timestamp(v) for v in times):
            raise ValueError('Binding times must be finite and nonnegative.')
        before, screen, after, bound, expiry = times
        if not (before <= screen <= after <= bound < expiry and before < after):
            raise ValueError('Binding capture order or expiry is invalid.')
        if (after - before > MAX_CAPTURE_GAP_SECONDS
                or expiry - before > MAX_BINDING_AGE_SECONDS):
            raise ValueError('Binding interval exceeds its hard bounds.')
        _validate_source_integrity(
            self.desktop_before_status,
            self.desktop_before_diagnostics,
            self.desktop_after_status,
            self.desktop_after_diagnostics,
        )

    def is_fresh(self, now):
        """Check the recorded time limit only, never current app/pixel state."""
        return (_timestamp(now)
                and self.bound_at_monotonic <= now < self.expires_at_monotonic)


@dataclass(frozen=True)
class DesktopScreenBindingResult:
    binding: DesktopScreenBinding | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        _validate_result(self.binding, DesktopScreenBinding, self.diagnostics)

    @property
    def linked(self):
        return self.binding is not None


def _validate_source_integrity(before_status, before_codes, after_status, after_codes):
    for status, codes in ((before_status, before_codes), (after_status, after_codes)):
        if type(status) is not str or status not in ('available', 'partial'):
            raise ValueError('Unavailable desktop context cannot be linked.')
        if (type(codes) is not tuple
                or any(type(code) is not str or code not in DIAGNOSTICS for code in codes)
                or len(set(codes)) != len(codes)
                or bool(codes) != (status == 'partial')):
            raise ValueError('Source diagnostics must preserve observation integrity.')


def _validate_result(value, expected_type, diagnostics):
    if (type(diagnostics) is not tuple
            or any(type(code) is not str for code in diagnostics)):
        raise ValueError('Diagnostics must be immutable.')
    if value is None:
        if (len(diagnostics) != 1 or diagnostics[0] not in REJECTION_CODES):
            raise ValueError('An unsuccessful result requires one rejection code.')
        return
    if type(value) is not expected_type:
        raise ValueError('Invalid result evidence type.')
    expected = _partial_diagnostics(
        value.desktop_before_status,
        value.desktop_after_status,
    )
    if diagnostics != expected:
        raise ValueError('Diagnostics must preserve partial source integrity.')


def bracket_desktop_capture(captured_at_monotonic, before, after, *, clock=time.monotonic,
                            max_age_seconds=5.0, max_capture_gap_seconds=1.0):
    """Bracket one already-completed physical screen capture with desktop metadata.

    The caller supplies the physical capture timestamp. No screenshot, model,
    ScreenObservation, store, native API, or execution tool is touched here.
    """
    if not _policy(max_age_seconds, max_capture_gap_seconds):
        raise ValueError('Invalid binding age or capture-gap limit.')
    if not callable(clock):
        raise TypeError('clock must be callable.')

    def reject(code):
        return DesktopCaptureBracketResult(diagnostics=(code,))

    try:
        now = clock()
    except Exception:
        return reject('clock_unavailable')
    if not _timestamp(now):
        return reject('clock_unavailable')
    if not _timestamp(captured_at_monotonic):
        return reject('invalid_capture_metadata')
    if type(before) is not DesktopContextObservation or type(after) is not DesktopContextObservation:
        return reject('invalid_desktop_metadata')
    if before.status == 'unavailable' or after.status == 'unavailable':
        return reject('desktop_context_unavailable')
    left, right = before.active_application, after.active_application
    if left is None or right is None or not _bundle(left.bundle_id) or not _bundle(right.bundle_id):
        return reject('application_identity_incomplete')
    if left.pid != right.pid or left.bundle_id != right.bundle_id:
        return reject('application_changed')
    if before.observation_id == after.observation_id:
        return reject('desktop_samples_not_distinct')
    start, captured, end = (
        before.captured_at_monotonic,
        captured_at_monotonic,
        after.captured_at_monotonic,
    )
    if max(start, captured, end) > now:
        return reject('evidence_from_future')
    if not start <= captured <= end or start >= end:
        return reject('capture_order_invalid')
    if end - start > max_capture_gap_seconds:
        return reject('capture_gap_exceeded')
    expiry = start + max_age_seconds
    if now >= expiry:
        return reject('evidence_expired')

    bracket = DesktopCaptureBracket(
        desktop_before_id=before.observation_id,
        desktop_after_id=after.observation_id,
        application_pid=left.pid,
        application_bundle_id=left.bundle_id,
        desktop_before_captured_at=start,
        screen_captured_at=captured,
        desktop_after_captured_at=end,
        bracketed_at_monotonic=now,
        expires_at_monotonic=expiry,
        desktop_before_status=before.status,
        desktop_after_status=after.status,
        desktop_before_diagnostics=before.diagnostics,
        desktop_after_diagnostics=after.diagnostics,
    )
    return DesktopCaptureBracketResult(
        bracket=bracket,
        diagnostics=_partial_diagnostics(before.status, after.status),
    )


def finalize_screen_binding(screen, bracket, *, clock=time.monotonic):
    """Bind a later ScreenObservation to the exact physical capture bracket.

    Semantic analysis is intentionally ignored. The screen observation must
    carry the exact capture timestamp recorded by the bracket and finalization
    must happen while the bracket remains fresh.
    """
    if not callable(clock):
        raise TypeError('clock must be callable.')

    def reject(code):
        return DesktopScreenBindingResult(diagnostics=(code,))

    try:
        now = clock()
    except Exception:
        return reject('clock_unavailable')
    if not _timestamp(now):
        return reject('clock_unavailable')

    from app.vision.observation import ScreenObservation
    if (type(screen) is not ScreenObservation
            or not _identifier(screen.observation_id)
            or not _timestamp(screen.captured_at_monotonic)):
        return reject('invalid_screen_metadata')
    if type(bracket) is not DesktopCaptureBracket:
        return reject('invalid_capture_bracket')
    if now < bracket.bracketed_at_monotonic:
        return reject('evidence_from_future')
    if now >= bracket.expires_at_monotonic:
        return reject('evidence_expired')
    if screen.captured_at_monotonic != bracket.screen_captured_at:
        return reject('capture_timestamp_mismatch')

    binding = DesktopScreenBinding(
        screen_observation_id=screen.observation_id,
        desktop_before_id=bracket.desktop_before_id,
        desktop_after_id=bracket.desktop_after_id,
        application_pid=bracket.application_pid,
        application_bundle_id=bracket.application_bundle_id,
        desktop_before_captured_at=bracket.desktop_before_captured_at,
        screen_captured_at=bracket.screen_captured_at,
        desktop_after_captured_at=bracket.desktop_after_captured_at,
        bound_at_monotonic=now,
        expires_at_monotonic=bracket.expires_at_monotonic,
        desktop_before_status=bracket.desktop_before_status,
        desktop_after_status=bracket.desktop_after_status,
        desktop_before_diagnostics=bracket.desktop_before_diagnostics,
        desktop_after_diagnostics=bracket.desktop_after_diagnostics,
    )
    return DesktopScreenBindingResult(
        binding=binding,
        diagnostics=_partial_diagnostics(
            bracket.desktop_before_status,
            bracket.desktop_after_status,
        ),
    )


def bind_desktop_to_screen(screen, before, after, *, clock=time.monotonic,
                           max_age_seconds=5.0, max_capture_gap_seconds=1.0):
    """Backward-compatible one-stage composition of bracket + finalization.

    The caller remains responsible for provenance and actual sampling order.
    This function performs no collection and touches no screen store.
    """
    if not _policy(max_age_seconds, max_capture_gap_seconds):
        raise ValueError('Invalid binding age or capture-gap limit.')
    if not callable(clock):
        raise TypeError('clock must be callable.')

    from app.vision.observation import ScreenObservation
    if (type(screen) is not ScreenObservation
            or not _identifier(screen.observation_id)
            or not _timestamp(screen.captured_at_monotonic)):
        # Preserve the legacy contract: policy is validated first, but malformed
        # screen metadata is rejected without consulting desktop evidence.
        return DesktopScreenBindingResult(diagnostics=('invalid_screen_metadata',))

    bracket_result = bracket_desktop_capture(
        screen.captured_at_monotonic,
        before,
        after,
        clock=clock,
        max_age_seconds=max_age_seconds,
        max_capture_gap_seconds=max_capture_gap_seconds,
    )
    if not bracket_result.bracketed:
        return DesktopScreenBindingResult(diagnostics=bracket_result.diagnostics)

    # The compatibility path finalizes at the exact time at which bracketing was
    # validated, preserving the previous single clock-read behavior.
    return finalize_screen_binding(
        screen,
        bracket_result.bracket,
        clock=lambda: bracket_result.bracket.bracketed_at_monotonic,
    )
