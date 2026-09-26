from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import subprocess
import sys

import pytest

from app.agent.gui_target_point_binding import (
    POINT_BINDING_STATUS_MATCHED,
    POINT_BINDING_STATUS_MISMATCH,
    POINT_BINDING_STATUS_UNKNOWN,
    StructuredUITargetPointBinding,
    StructuredUITargetPointBindingResult,
    bind_structured_ui_target_point,
)
from app.agent.test_gui_target_evidence import NEW_SCREEN, NEW_UI, item, observation
from app.agent.test_gui_target_orchestration import make_intent, orchestrate
from app.vision.coordinates import CoordinateMapper
from app.vision.observation import SCREEN_OBSERVATIONS


OTHER_SCREEN = "9" * 32


def make_active_screen(
    monkeypatch,
    *,
    observation_id=NEW_SCREEN,
    captured=107.0,
    vision_width=400,
    vision_height=300,
    native_width=800,
    native_height=600,
):
    SCREEN_OBSERVATIONS.clear()
    monkeypatch.setattr(
        "app.vision.observation.secrets.token_hex",
        lambda _count: observation_id,
    )
    return SCREEN_OBSERVATIONS.create(
        captured_at_monotonic=captured,
        capture_width=1600,
        capture_height=1200,
        vision_width=vision_width,
        vision_height=vision_height,
        native_width=native_width,
        native_height=native_height,
        vision_scale=0.25,
        analysis="VISIBLE_TARGETS: Save",
    )


@pytest.fixture(autouse=True)
def clear_screen_store():
    SCREEN_OBSERVATIONS.clear()
    yield
    SCREEN_OBSERVATIONS.clear()


def bind(monkeypatch, *, result=None, x=250, y=175, now=109.5):
    screen = make_active_screen(monkeypatch)
    result = result or orchestrate()
    bound = bind_structured_ui_target_point(
        result,
        x,
        y,
        clock=lambda: now,
    )
    return screen, result, bound


def test_happy_path_binds_exact_b8c_graph_active_screen_and_mapper_point(monkeypatch):
    screen, result, bound = bind(monkeypatch)

    assert bound.status == POINT_BINDING_STATUS_MATCHED
    assert bound.matched
    binding = bound.binding
    assert binding.orchestration_result is result
    assert binding.screen_observation is screen
    assert binding.evidence is result.evidence
    assert binding.screen_observation_id == NEW_SCREEN
    assert binding.ui_observation_id == NEW_UI
    assert binding.vision_point == (250, 175)

    mapper = CoordinateMapper(
        vision_width=screen.vision_width,
        vision_height=screen.vision_height,
        screen_width=screen.native_width,
        screen_height=screen.native_height,
    )
    assert binding.native_point == mapper.vision_to_screen(250, 175)
    assert binding.native_point == (500, 350)
    assert binding.ax_geometry == (420.0, 330.0, 160.0, 55.0)
    assert binding.checked_at_monotonic == 109.5
    assert binding.expires_at_monotonic == 115.0


def test_candidate_outside_fresh_ax_target_is_explicit_mismatch(monkeypatch):
    make_active_screen(monkeypatch)
    bound = bind_structured_ui_target_point(
        orchestrate(),
        100,
        100,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_MISMATCH
    assert not bound.matched
    assert bound.binding is None
    assert bound.diagnostics == ("candidate_outside_target",)


def test_b8c_evidence_must_still_be_current(monkeypatch):
    make_active_screen(monkeypatch)
    bound = bind_structured_ui_target_point(
        orchestrate(),
        250,
        175,
        clock=lambda: 115.0,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("evidence_not_current",)


def test_unknown_orchestration_cannot_become_point_evidence(monkeypatch):
    make_active_screen(monkeypatch)
    unavailable = orchestrate(
        original=observation(item(title="Other")),
        clock=lambda: 104.0,
    )
    bound = bind_structured_ui_target_point(
        unavailable,
        250,
        175,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("orchestration_unavailable",)


def test_active_screen_id_must_equal_fresh_b8c_screen_provenance(monkeypatch):
    make_active_screen(monkeypatch, observation_id=OTHER_SCREEN)
    bound = bind_structured_ui_target_point(
        orchestrate(),
        250,
        175,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("screen_observation_unavailable",)


def test_active_screen_capture_time_must_equal_fresh_binding(monkeypatch):
    make_active_screen(monkeypatch, captured=107.1)
    bound = bind_structured_ui_target_point(
        orchestrate(),
        250,
        175,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("screen_observation_mismatch",)


def test_incomplete_ax_position_fails_closed(monkeypatch):
    make_active_screen(monkeypatch)
    fresh = observation(
        item(position_x=None, position_y=None, width=160.0, height=55.0),
        observation_id=NEW_UI,
        captured=106.0,
    )
    result = orchestrate(
        intent=make_intent(require_positive_area=False),
        fresh=fresh,
    )
    assert result.available

    bound = bind_structured_ui_target_point(
        result,
        250,
        175,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("geometry_unavailable",)


def test_ax_geometry_outside_primary_native_rectangle_is_unsupported(monkeypatch):
    make_active_screen(monkeypatch)
    fresh = observation(
        item(position_x=-10.0, position_y=330.0, width=160.0, height=55.0),
        observation_id=NEW_UI,
        captured=106.0,
    )
    result = orchestrate(
        intent=make_intent(require_positive_area=False),
        fresh=fresh,
    )
    assert result.available

    bound = bind_structured_ui_target_point(
        result,
        250,
        175,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("coordinate_space_unsupported",)


@pytest.mark.parametrize("x,y", [(-1, 1), (1, -1), (400, 1), (1, 300), (True, 1), (1, False)])
def test_invalid_vision_points_fail_closed(monkeypatch, x, y):
    make_active_screen(monkeypatch)
    bound = bind_structured_ui_target_point(
        orchestrate(),
        x,
        y,
        clock=lambda: 109.5,
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("invalid_vision_point",)


def test_constructor_rejects_equal_value_reconstructed_screen_observation(monkeypatch):
    _screen, _result, bound = bind(monkeypatch)
    good = bound.binding
    clone = replace(good.screen_observation)
    assert clone == good.screen_observation
    assert clone is not good.screen_observation

    with pytest.raises(ValueError, match="exact active screen object"):
        replace(good, screen_observation=clone)


def test_constructor_rejects_native_coordinate_substitution(monkeypatch):
    _screen, _result, bound = bind(monkeypatch)
    good = bound.binding
    with pytest.raises(ValueError, match="trusted coordinate mapping"):
        replace(good, native_x=good.native_x + 1)


def test_binding_and_result_are_immutable(monkeypatch):
    _screen, _result, bound = bind(monkeypatch)
    with pytest.raises(FrozenInstanceError):
        bound.binding.native_x = 1
    with pytest.raises(FrozenInstanceError):
        bound.status = POINT_BINDING_STATUS_UNKNOWN


@pytest.mark.parametrize(
    "name",
    [
        "semantic_target_verified",
        "authorized",
        "permission",
        "approved",
        "attestation",
        "execute",
        "click",
    ],
)
def test_binding_has_no_authority_surface(monkeypatch, name):
    _screen, _result, bound = bind(monkeypatch)
    assert not hasattr(bound.binding, name)
    assert not hasattr(bound, name)


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(StructuredUITargetPointBinding, "from_dict")
    assert not hasattr(StructuredUITargetPointBinding, "to_dict")
    assert not hasattr(StructuredUITargetPointBindingResult, "from_dict")
    assert not hasattr(StructuredUITargetPointBindingResult, "to_dict")


def test_noncallable_clock_is_rejected():
    with pytest.raises(TypeError):
        bind_structured_ui_target_point(
            orchestrate(),
            250,
            175,
            clock=None,
        )


def test_clock_failure_fails_closed_without_exception_text(monkeypatch):
    make_active_screen(monkeypatch)
    bound = bind_structured_ui_target_point(
        orchestrate(),
        250,
        175,
        clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
    )
    assert bound.status == POINT_BINDING_STATUS_UNKNOWN
    assert bound.diagnostics == ("clock_unavailable",)
    assert "private" not in repr(bound)


def test_result_contract_rejects_forged_combinations(monkeypatch):
    _screen, _result, good = bind(monkeypatch)
    with pytest.raises(ValueError):
        StructuredUITargetPointBindingResult(
            status=POINT_BINDING_STATUS_MATCHED,
            binding=None,
        )
    with pytest.raises(ValueError):
        StructuredUITargetPointBindingResult(
            status=POINT_BINDING_STATUS_UNKNOWN,
            binding=good.binding,
            diagnostics=("clock_unavailable",),
        )
    with pytest.raises(ValueError):
        StructuredUITargetPointBindingResult(
            status=POINT_BINDING_STATUS_MISMATCH,
            diagnostics=("made_up",),
        )


def test_module_has_no_native_api_model_permission_or_execution_imports():
    module = Path(__file__).with_name("gui_target_point_binding.py")
    script = r'''
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
        'AppKit', 'Quartz', 'ApplicationServices', 'google.genai', 'ollama',
        'pyautogui', 'app.tools', 'app.agent.mission_service',
        'app.vision.gui_target_verifier', 'app.ui_observation.runtime',
        'app.ui_observation.macos')):
        raise AssertionError('forbidden import')
sys.addaudithook(audit)
import app.agent.gui_target_point_binding as module
for name in ('click', 'execute', 'authorize', 'semantic_target_verified'):
    assert not hasattr(module, name)
'''
    completed = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=module.parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
