from dataclasses import FrozenInstanceError
from pathlib import Path
import ast
import time

import pytest

from app.agent.gui_perception_context import (
    STRUCTURED_UI_SCREEN_CONTEXTS,
    StructuredUIScreenPerceptionContextStore,
    publish_structured_ui_screen_context,
)
from app.agent.gui_perception_refresh import (
    REFRESH_STATUS_AVAILABLE,
    REFRESH_STATUS_UNKNOWN,
    StructuredUIScreenFreshCorroboration,
    StructuredUIScreenFreshCorroborationResult,
    refresh_structured_ui_screen_context,
)
from app.agent.test_gui_perception_context import (
    APP,
    desktop,
    sources,
    structured_ui,
)
from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation
from app.desktop.provenance import SCREEN_DESKTOP_PROVENANCE
from app.ui_observation.contracts import unavailable as ui_unavailable
from app.vision.observation import SCREEN_OBSERVATIONS, ScreenObservationError


class FakeImage:
    def __init__(self, size=(200, 100)):
        self.size = size


def sequence_clock(*values):
    iterator = iter(values)
    return lambda: next(iterator)


def original_context():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.available
    return base, result.context


def fresh_inputs(base, *, app=APP, image_size=(200, 100), ui=None):
    before = desktop(base + 0.055, 10, app=app)
    after = desktop(base + 0.070, 11, app=app)
    if ui is None:
        ui = structured_ui(base + 0.065, number=12, app=app)
    desktops = iter((before, after))
    return dict(
        desktop_collector=lambda **_kwargs: next(desktops),
        screen_capture=lambda: FakeImage(image_size),
        structured_ui_collector=lambda _app, **_kwargs: ui,
        native_screen_size=lambda: (200, 100),
        clock=sequence_clock(
            base + 0.060,
            base + 0.075,
            base + 0.080,
            base + 0.082,
            base + 0.084,
            base + 0.086,
            base + 0.088,
            base + 0.090,
        ),
    )


def setup_function():
    SCREEN_OBSERVATIONS.clear()
    SCREEN_DESKTOP_PROVENANCE.clear()
    STRUCTURED_UI_SCREEN_CONTEXTS.clear()


def teardown_function():
    SCREEN_OBSERVATIONS.clear()
    SCREEN_DESKTOP_PROVENANCE.clear()
    STRUCTURED_UI_SCREEN_CONTEXTS.clear()


def test_refresh_builds_exact_independent_context_pair():
    base, original = original_context()
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base),
    )

    assert result.status == REFRESH_STATUS_AVAILABLE
    assert result.available
    pair = result.corroboration
    assert pair.original_context is original
    assert pair.original_observation is original.structured_ui_observation
    assert pair.original_binding is original.structured_screen_binding
    assert pair.fresh_observation is pair.fresh_context.structured_ui_observation
    assert pair.fresh_binding is pair.fresh_context.structured_screen_binding
    assert pair.original_screen_observation_id == original.screen_observation_id
    assert pair.fresh_screen_observation_id != original.screen_observation_id
    assert pair.fresh_context.screen_observation.analysis == (
        "INTERNAL_FRESH_STRUCTURED_CORROBORATION_ONLY"
    )
    assert pair.is_fresh(base + 0.091)


def test_refresh_preserves_exact_model_visible_geometry():
    base, original = original_context()
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base),
    )
    fresh = result.corroboration.fresh_context.screen_observation
    old = original.screen_observation
    assert (
        fresh.capture_width,
        fresh.capture_height,
        fresh.vision_width,
        fresh.vision_height,
        fresh.native_width,
        fresh.native_height,
        fresh.vision_scale,
    ) == (
        old.capture_width,
        old.capture_height,
        old.vision_width,
        old.vision_height,
        old.native_width,
        old.native_height,
        old.vision_scale,
    )


def test_refresh_replaces_global_screen_and_provenance_with_fresh_exact_sources():
    base, original = original_context()
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base),
    )
    fresh = result.corroboration.fresh_context

    with pytest.raises(ScreenObservationError):
        SCREEN_OBSERVATIONS.peek(original.screen_observation_id)
    assert SCREEN_OBSERVATIONS.peek(fresh.screen_observation_id) is fresh.screen_observation
    assert SCREEN_DESKTOP_PROVENANCE.get(fresh.screen_observation_id) is fresh.screen_provenance


def test_global_b8k1_context_is_consumed_not_republished():
    base, original = original_context()
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base),
    )
    assert result.available
    with pytest.raises(Exception):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek(original.screen_observation_id)
    with pytest.raises(Exception):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek(result.corroboration.fresh_screen_observation_id)


def test_second_refresh_attempt_fails_and_clears_first_fresh_sources():
    base, original = original_context()
    first = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base),
    )
    assert first.available
    fresh_id = first.corroboration.fresh_screen_observation_id

    second = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base + 0.30),
    )
    assert second.status == REFRESH_STATUS_UNKNOWN
    assert second.diagnostics == ("original_context_unavailable",)
    with pytest.raises(ScreenObservationError):
        SCREEN_OBSERVATIONS.peek(fresh_id)


def test_wrong_claim_consumes_original_and_clears_sources():
    _, original = original_context()
    result = refresh_structured_ui_screen_context(
        "f" * 32,
    )
    assert result.diagnostics == ("original_context_unavailable",)
    with pytest.raises(ScreenObservationError):
        SCREEN_OBSERVATIONS.peek(original.screen_observation_id)


def test_invalid_screen_id_fails_without_collection():
    result = refresh_structured_ui_screen_context("")
    assert result.status == REFRESH_STATUS_UNKNOWN
    assert result.diagnostics == ("invalid_screen_observation_id",)


def test_invalid_context_store_fails_closed():
    result = refresh_structured_ui_screen_context(
        "a" * 32,
        context_store=object(),
    )
    assert result.diagnostics == ("invalid_context_store",)


def test_application_change_before_capture_fails_closed():
    base, original = original_context()
    other = ApplicationIdentity(APP.pid + 1, "other.app", "Other")
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base, app=other),
    )
    assert result.diagnostics == ("application_identity_changed",)
    with pytest.raises(ScreenObservationError):
        SCREEN_OBSERVATIONS.peek(original.screen_observation_id)


def test_capture_geometry_change_fails_closed():
    base, original = original_context()
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base, image_size=(201, 100)),
    )
    assert result.diagnostics == ("screen_geometry_changed",)


def test_native_geometry_change_fails_closed():
    base, original = original_context()
    kwargs = fresh_inputs(base)
    kwargs["native_screen_size"] = lambda: (201, 100)
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **kwargs,
    )
    assert result.diagnostics == ("screen_geometry_changed",)


def test_unavailable_fresh_ui_fails_closed():
    base, original = original_context()
    unavailable = ui_unavailable(
        "accessibility_permission_denied",
        base + 0.065,
    )
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base, ui=unavailable),
    )
    assert result.diagnostics == ("structured_ui_unavailable",)


def test_application_change_in_fresh_ui_fails_closed():
    base, original = original_context()
    other = ApplicationIdentity(APP.pid + 1, "other.app", "Other")
    mismatched_ui = structured_ui(base + 0.065, number=12, app=other)
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base, ui=mismatched_ui),
    )
    assert result.diagnostics == ("application_identity_changed",)


def test_application_change_after_capture_fails_closed():
    base, original = original_context()
    other = ApplicationIdentity(APP.pid + 1, "other.app", "Other")
    before = desktop(base + 0.055, 10)
    after = desktop(base + 0.070, 11, app=other)
    desktops = iter((before, after))
    kwargs = fresh_inputs(base)
    kwargs["desktop_collector"] = lambda **_kwargs: next(desktops)
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **kwargs,
    )
    assert result.diagnostics == ("application_identity_changed",)


def test_reused_fresh_ui_id_fails_closed():
    base, original = original_context()
    old_ui = original.structured_ui_observation
    reused = type(old_ui)(
        observation_id=old_ui.observation_id,
        captured_at_monotonic=base + 0.065,
        status=old_ui.status,
        active_application=old_ui.active_application,
        elements=old_ui.elements,
        traversal_succeeded=old_ui.traversal_succeeded,
        diagnostics=old_ui.diagnostics,
    )
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base, ui=reused),
    )
    assert result.diagnostics == ("fresh_evidence_reused",)


def test_non_newer_ui_evidence_fails_closed():
    base, original = original_context()
    old_ui = original.structured_ui_observation
    # Keep the fresh bracket valid while making the UI timestamp equal to the
    # original snapshot timestamp. B8K2 must reject it as non-new evidence.
    before_time = old_ui.captured_at_monotonic - 0.001
    after_time = old_ui.captured_at_monotonic + 0.020
    before = DesktopContextObservation(
        observation_id="a" * 32,
        captured_at_monotonic=before_time,
        status="available",
        active_application=APP,
        enumeration_succeeded=True,
        diagnostics=(),
    )
    after = DesktopContextObservation(
        observation_id="b" * 32,
        captured_at_monotonic=after_time,
        status="available",
        active_application=APP,
        enumeration_succeeded=True,
        diagnostics=(),
    )
    same_time_ui = type(old_ui)(
        observation_id="c" * 32,
        captured_at_monotonic=old_ui.captured_at_monotonic,
        status=old_ui.status,
        active_application=old_ui.active_application,
        elements=old_ui.elements,
        traversal_succeeded=old_ui.traversal_succeeded,
        diagnostics=old_ui.diagnostics,
    )
    desktops = iter((before, after))
    # The new physical screen timestamp is inside this deliberately older UI
    # bracket but still after the original physical screen timestamp.
    capture_time = max(
        original.screen_observation.captured_at_monotonic + 0.001,
        before_time,
    )
    clock = sequence_clock(
        capture_time,
        after_time + 0.001,
        after_time + 0.002,
        after_time + 0.003,
        after_time + 0.004,
        after_time + 0.005,
        after_time + 0.006,
        after_time + 0.007,
    )
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        desktop_collector=lambda **_kwargs: next(desktops),
        screen_capture=lambda: FakeImage(),
        structured_ui_collector=lambda _app, **_kwargs: same_time_ui,
        native_screen_size=lambda: (200, 100),
        clock=clock,
    )
    assert result.diagnostics == ("fresh_evidence_not_newer",)


def test_refresh_contract_is_immutable_and_has_no_authority_surface():
    base, original = original_context()
    result = refresh_structured_ui_screen_context(
        original.screen_observation_id,
        **fresh_inputs(base),
    )
    pair = result.corroboration
    with pytest.raises(FrozenInstanceError):
        pair.expires_at_monotonic = 0

    forbidden = {
        "allowed",
        "approved",
        "permission",
        "semantic_target_verified",
        "attestation",
        "button",
        "clicks",
        "execute",
    }
    fields = set(StructuredUIScreenFreshCorroboration.__dataclass_fields__)
    assert not (fields & forbidden)


def test_module_imports_no_model_verifier_permission_or_execution_surface():
    path = Path(__file__).with_name("gui_perception_refresh.py")
    tree = ast.parse(path.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden_prefixes = (
        "google.genai",
        "ollama",
        "app.vision.gui_target_verifier",
        "app.agent.gui_argument_authority",
        "app.agent.permissions",
        "app.agent.gui_target_evidence_producer",
        "app.agent.gui_target_evidence_consumption",
    )
    assert not any(
        module.startswith(forbidden_prefixes)
        for module in imported
    )


def test_result_contract_rejects_malformed_status_evidence_pairs():
    with pytest.raises(ValueError):
        StructuredUIScreenFreshCorroborationResult(status="made_up")
    with pytest.raises(ValueError):
        StructuredUIScreenFreshCorroborationResult(
            status=REFRESH_STATUS_AVAILABLE,
            diagnostics=("clock_unavailable",),
        )
    with pytest.raises(ValueError):
        StructuredUIScreenFreshCorroborationResult(
            status=REFRESH_STATUS_UNKNOWN,
            diagnostics=("made_up",),
        )
