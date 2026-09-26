from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import subprocess
import sys

import pytest

from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation
from app.desktop.provenance import ScreenDesktopProvenance
from app.desktop.screen_binding import DesktopScreenBinding
from app.ui_observation.desktop_binding import DesktopUIBinding
from app.ui_observation.screen_binding import (
    StructuredUIScreenBindingResult,
    bind_structured_ui_to_screen,
)


APP = ApplicationIdentity(123, "test.app", "Example")


def desktop(captured, number, *, status="available", diagnostics=(), app=APP):
    return DesktopContextObservation(
        observation_id=f"{number:032x}",
        captured_at_monotonic=captured,
        status=status,
        active_application=app,
        enumeration_succeeded=True,
        diagnostics=diagnostics,
    )


def ui_binding(**changes):
    values = dict(
        ui_observation_id="1" * 32,
        desktop_before_id="2" * 32,
        desktop_after_id="3" * 32,
        application_pid=123,
        application_bundle_id="test.app",
        desktop_before_captured_at=100.0,
        ui_captured_at=101.0,
        desktop_after_captured_at=103.0,
        bound_at_monotonic=103.2,
        expires_at_monotonic=105.0,
        desktop_before_status="available",
        desktop_after_status="available",
        ui_status="available",
        desktop_before_diagnostics=(),
        desktop_after_diagnostics=(),
        ui_diagnostics=(),
    )
    values.update(changes)
    return DesktopUIBinding(**values)


def screen_provenance(
    *,
    screen_id="4" * 32,
    before_id="2" * 32,
    after_id="3" * 32,
    pid=123,
    bundle="test.app",
    before_time=100.0,
    screen_time=102.0,
    after_time=103.0,
    bound_at=103.1,
    expires_at=106.0,
    before_status="available",
    after_status="available",
    before_diagnostics=(),
    after_diagnostics=(),
):
    app = ApplicationIdentity(pid, bundle, "Screen Source")
    before = DesktopContextObservation(
        observation_id=before_id,
        captured_at_monotonic=before_time,
        status=before_status,
        active_application=app,
        enumeration_succeeded=True,
        diagnostics=before_diagnostics,
    )
    after = DesktopContextObservation(
        observation_id=after_id,
        captured_at_monotonic=after_time,
        status=after_status,
        active_application=app,
        enumeration_succeeded=True,
        diagnostics=after_diagnostics,
    )
    binding = DesktopScreenBinding(
        screen_observation_id=screen_id,
        desktop_before_id=before_id,
        desktop_after_id=after_id,
        application_pid=pid,
        application_bundle_id=bundle,
        desktop_before_captured_at=before_time,
        screen_captured_at=screen_time,
        desktop_after_captured_at=after_time,
        bound_at_monotonic=bound_at,
        expires_at_monotonic=expires_at,
        desktop_before_status=before_status,
        desktop_after_status=after_status,
        desktop_before_diagnostics=before_diagnostics,
        desktop_after_diagnostics=after_diagnostics,
    )
    return ScreenDesktopProvenance(
        binding=binding,
        desktop_before=before,
        desktop_after=after,
    )


def join(*, ui=None, screen=None, now=103.5):
    return bind_structured_ui_to_screen(
        ui or ui_binding(),
        screen or screen_provenance(),
        clock=lambda: now,
    )


def test_valid_join_preserves_exact_ui_binding_screen_provenance_and_earliest_expiry():
    left = ui_binding()
    right = screen_provenance()
    result = join(ui=left, screen=right)

    assert result.linked
    binding = result.binding
    assert binding.ui_binding is left
    assert binding.screen_provenance is right
    assert binding.ui_observation_id == "1" * 32
    assert binding.screen_observation_id == "4" * 32
    assert binding.desktop_before_id == "2" * 32
    assert binding.desktop_after_id == "3" * 32
    assert binding.application_pid == 123
    assert binding.application_bundle_id == "test.app"
    assert binding.linked_at_monotonic == 103.5
    assert binding.expires_at_monotonic == 105.0
    assert result.diagnostics == ()


def test_joined_binding_is_immutable():
    binding = join().binding
    with pytest.raises(FrozenInstanceError):
        binding.linked_at_monotonic = 104


def test_partial_source_integrity_is_preserved_without_promotion():
    left = ui_binding(
        desktop_before_status="partial",
        desktop_before_diagnostics=("focus_unavailable",),
        ui_status="partial",
        ui_diagnostics=("nodes_truncated",),
    )
    right = screen_provenance(
        before_status="partial",
        before_diagnostics=("focus_unavailable",),
    )
    result = join(ui=left, screen=right)

    assert result.linked
    assert result.diagnostics == (
        "desktop_context_partial",
        "structured_ui_partial",
    )
    assert result.binding.ui_binding.ui_status == "partial"


@pytest.mark.parametrize(
    "screen",
    [
        screen_provenance(before_id="5" * 32),
        screen_provenance(after_id="5" * 32),
    ],
)
def test_exact_desktop_source_ids_must_match(screen):
    assert join(screen=screen).diagnostics == ("desktop_source_mismatch",)


@pytest.mark.parametrize(
    "screen",
    [
        screen_provenance(pid=456),
        screen_provenance(bundle="other.app"),
    ],
)
def test_exact_pid_and_bundle_must_match(screen):
    assert join(screen=screen).diagnostics == ("application_identity_mismatch",)


@pytest.mark.parametrize(
    "screen",
    [
        screen_provenance(before_time=99.5),
        screen_provenance(after_time=102.5),
        screen_provenance(
            before_status="partial",
            before_diagnostics=("focus_unavailable",),
        ),
        screen_provenance(
            after_status="partial",
            after_diagnostics=("focus_unavailable",),
        ),
    ],
)
def test_exact_desktop_metadata_must_match(screen):
    assert join(screen=screen).diagnostics == ("desktop_metadata_mismatch",)


def test_cross_evidence_id_collision_is_rejected():
    screen = screen_provenance(screen_id="1" * 32)
    assert join(screen=screen).diagnostics == ("evidence_id_collision",)


@pytest.mark.parametrize("value", [object(), None])
def test_invalid_ui_binding_is_rejected(value):
    result = bind_structured_ui_to_screen(
        value,
        screen_provenance(),
        clock=lambda: 103.5,
    )
    assert result.diagnostics == ("invalid_ui_binding",)


@pytest.mark.parametrize("value", [object(), None])
def test_invalid_screen_provenance_is_rejected(value):
    result = bind_structured_ui_to_screen(
        ui_binding(),
        value,
        clock=lambda: 103.5,
    )
    assert result.diagnostics == ("invalid_screen_provenance",)


def test_bare_screen_binding_is_not_accepted_without_provenance_sources():
    result = bind_structured_ui_to_screen(
        ui_binding(),
        screen_provenance().binding,
        clock=lambda: 103.5,
    )
    assert result.diagnostics == ("invalid_screen_provenance",)


def test_join_rejects_clock_before_either_source_binding_exists():
    left = ui_binding(bound_at_monotonic=103.4)
    right = screen_provenance(bound_at=103.2)
    result = join(ui=left, screen=right, now=103.3)
    assert result.diagnostics == ("source_binding_from_future",)


@pytest.mark.parametrize(
    "left,right,now",
    [
        (ui_binding(expires_at_monotonic=104.0), screen_provenance(), 104.0),
        (ui_binding(), screen_provenance(expires_at=104.0), 104.0),
        (ui_binding(expires_at_monotonic=104.0), screen_provenance(), 104.5),
    ],
)
def test_join_fails_when_either_source_binding_has_expired(left, right, now):
    result = join(ui=left, screen=right, now=now)
    assert result.diagnostics == ("source_binding_expired",)


def test_join_never_extends_lifetime_beyond_earliest_source_expiry():
    left = ui_binding(expires_at_monotonic=104.25)
    right = screen_provenance(expires_at=105.5)
    result = join(ui=left, screen=right, now=103.5)
    assert result.linked
    assert result.binding.expires_at_monotonic == 104.25
    assert result.binding.is_fresh(104.249)
    assert not result.binding.is_fresh(104.25)


def test_joined_contract_rejects_extended_or_shortened_expiry():
    binding = join().binding
    with pytest.raises(ValueError, match="earliest source expiry"):
        replace(binding, expires_at_monotonic=binding.expires_at_monotonic + 0.1)
    with pytest.raises(ValueError, match="earliest source expiry"):
        replace(binding, expires_at_monotonic=binding.expires_at_monotonic - 0.1)


def test_joined_contract_rejects_mismatched_nested_screen_provenance():
    binding = join().binding
    wrong = screen_provenance(before_id="5" * 32)
    with pytest.raises(ValueError, match="desktop observation IDs"):
        replace(binding, screen_provenance=wrong)


def test_joined_contract_rejects_cross_evidence_id_collision():
    binding = join().binding
    collision = screen_provenance(screen_id=binding.ui_observation_id)
    with pytest.raises(ValueError, match="distinct"):
        replace(binding, screen_provenance=collision)


def test_result_contract_rejects_forged_success_or_failure_diagnostics():
    binding = join().binding
    with pytest.raises(ValueError):
        StructuredUIScreenBindingResult(
            binding=binding,
            diagnostics=("structured_ui_partial",),
        )
    with pytest.raises(ValueError):
        StructuredUIScreenBindingResult(diagnostics=())


def test_clock_failure_is_sanitized_and_invalid_clock_fails_closed():
    result = bind_structured_ui_to_screen(
        ui_binding(),
        screen_provenance(),
        clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
    )
    assert result.diagnostics == ("clock_unavailable",)
    assert "private" not in repr(result)

    result = bind_structured_ui_to_screen(
        ui_binding(),
        screen_provenance(),
        clock=lambda: float("nan"),
    )
    assert result.diagnostics == ("clock_unavailable",)


def test_noncallable_clock_is_rejected():
    with pytest.raises(TypeError):
        bind_structured_ui_to_screen(
            ui_binding(),
            screen_provenance(),
            clock=None,
        )


def test_binding_freshness_has_exact_boundaries():
    binding = join(now=103.5).binding
    assert not binding.is_fresh(103.499)
    assert binding.is_fresh(103.5)
    assert binding.is_fresh(104.999)
    assert not binding.is_fresh(105.0)
    assert not binding.is_fresh(float("nan"))


def test_screen_and_ui_capture_times_may_differ_inside_same_exact_desktop_bracket():
    left = ui_binding(ui_captured_at=100.5)
    right = screen_provenance(screen_time=102.5)
    result = join(ui=left, screen=right)
    assert result.linked
    assert result.binding.ui_binding.ui_captured_at == 100.5
    assert result.binding.screen_provenance.binding.screen_captured_at == 102.5


def test_screen_provenance_sources_are_preserved_exactly():
    provenance = screen_provenance()
    result = join(screen=provenance)
    assert result.binding.screen_provenance.desktop_before is provenance.desktop_before
    assert result.binding.screen_provenance.desktop_after is provenance.desktop_after


def test_binding_module_has_no_external_effects_or_action_surface():
    script = r"""
import sys

def audit(event, args):
    if event == 'open':
        mode, flags = args[1:3]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & 3):
            raise AssertionError('write')
    if event.startswith(('socket.', 'subprocess.', 'os.system', 'os.spawn',
                         'os.remove', 'os.rename', 'os.mkdir')):
        raise AssertionError(event)
    if event == 'import' and args[0].startswith((
        'AppKit', 'Quartz', 'ApplicationServices', 'ollama', 'pyautogui',
        'app.agent', 'app.memory', 'app.tools', 'app.desktop.runtime',
        'app.ui_observation.runtime', 'app.ui_observation.macos',
        'app.ui_observation.store', 'app.vision.screen')):
        raise AssertionError('forbidden import')
sys.addaudithook(audit)

from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation
from app.desktop.provenance import ScreenDesktopProvenance
from app.desktop.screen_binding import DesktopScreenBinding
from app.ui_observation.desktop_binding import DesktopUIBinding
from app.ui_observation.screen_binding import bind_structured_ui_to_screen

app = ApplicationIdentity(123, 'test.app')
before = DesktopContextObservation(
    observation_id='2'*32, captured_at_monotonic=100,
    status='available', active_application=app, enumeration_succeeded=True)
after = DesktopContextObservation(
    observation_id='3'*32, captured_at_monotonic=103,
    status='available', active_application=app, enumeration_succeeded=True)
ui = DesktopUIBinding(
    ui_observation_id='1'*32, desktop_before_id='2'*32, desktop_after_id='3'*32,
    application_pid=123, application_bundle_id='test.app',
    desktop_before_captured_at=100, ui_captured_at=101,
    desktop_after_captured_at=103, bound_at_monotonic=103.1,
    expires_at_monotonic=105)
screen = DesktopScreenBinding(
    screen_observation_id='4'*32, desktop_before_id='2'*32, desktop_after_id='3'*32,
    application_pid=123, application_bundle_id='test.app',
    desktop_before_captured_at=100, screen_captured_at=102,
    desktop_after_captured_at=103, bound_at_monotonic=103.2,
    expires_at_monotonic=105, desktop_before_status='available',
    desktop_after_status='available')
provenance = ScreenDesktopProvenance(
    binding=screen, desktop_before=before, desktop_after=after)
result = bind_structured_ui_to_screen(ui, provenance, clock=lambda: 103.3)
assert result.linked
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ""

    source = Path(__file__).with_name("screen_binding.py").read_text()
    for forbidden in (
        "AXUIElementPerformAction",
        "AXUIElementSetAttributeValue",
        "click(",
        "pyautogui",
        "ollama",
    ):
        assert forbidden not in source
