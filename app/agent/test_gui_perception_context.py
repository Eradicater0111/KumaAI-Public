from dataclasses import FrozenInstanceError, replace
import time

import pytest

from app.agent.gui_perception_context import (
    CONTEXT_STATUS_AVAILABLE,
    CONTEXT_STATUS_UNKNOWN,
    STRUCTURED_UI_SCREEN_CONTEXTS,
    StructuredUIScreenPerceptionContext,
    StructuredUIScreenPerceptionContextError,
    StructuredUIScreenPerceptionContextStore,
    publish_structured_ui_screen_context,
)
from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation
from app.desktop.provenance import (
    SCREEN_DESKTOP_PROVENANCE,
    ScreenDesktopProvenance,
)
from app.desktop.screen_binding import bind_desktop_to_screen
from app.ui_observation.contracts import (
    StructuredUIObservation,
    UIElementObservation,
    unavailable as ui_unavailable,
)
from app.vision.observation import SCREEN_OBSERVATIONS


APP = ApplicationIdentity(4242, "test.app", "Example")


def desktop(captured, number, *, app=APP):
    return DesktopContextObservation(
        observation_id=f"{number:032x}",
        captured_at_monotonic=captured,
        status="available",
        active_application=app,
        enumeration_succeeded=True,
        diagnostics=(),
    )


def structured_ui(captured, number=3, *, app=APP):
    return StructuredUIObservation(
        observation_id=f"{number:032x}",
        captured_at_monotonic=captured,
        status="available",
        active_application=app,
        elements=(
            UIElementObservation(
                path=(),
                owner_pid=app.pid,
                role="AXApplication",
                title="Example",
                position_x=0.0,
                position_y=0.0,
                width=200.0,
                height=100.0,
            ),
        ),
        traversal_succeeded=True,
        diagnostics=(),
    )


def sources():
    base = time.monotonic() - 0.10
    before = desktop(base, 1)
    screen = SCREEN_OBSERVATIONS.create(
        captured_at_monotonic=base + 0.01,
        capture_width=200,
        capture_height=100,
        vision_width=200,
        vision_height=100,
        native_width=200,
        native_height=100,
        vision_scale=1.0,
        analysis="VISIBLE_TARGETS:\n- Save at (50, 20)",
    )
    ui = structured_ui(base + 0.02)
    after = desktop(base + 0.03, 2)
    screen_binding = bind_desktop_to_screen(
        screen,
        before,
        after,
        clock=lambda: base + 0.04,
        max_age_seconds=SCREEN_OBSERVATIONS.max_age_seconds,
        max_capture_gap_seconds=5.0,
    )
    assert screen_binding.linked
    provenance = ScreenDesktopProvenance(
        binding=screen_binding.binding,
        desktop_before=before,
        desktop_after=after,
    )
    assert SCREEN_DESKTOP_PROVENANCE.publish(provenance)
    return base, screen, ui, provenance


def setup_function():
    SCREEN_OBSERVATIONS.clear()
    SCREEN_DESKTOP_PROVENANCE.clear()
    STRUCTURED_UI_SCREEN_CONTEXTS.clear()


def teardown_function():
    SCREEN_OBSERVATIONS.clear()
    SCREEN_DESKTOP_PROVENANCE.clear()
    STRUCTURED_UI_SCREEN_CONTEXTS.clear()


def test_publish_builds_exact_same_bracket_context():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )

    assert result.status == CONTEXT_STATUS_AVAILABLE
    assert result.available
    context = result.context
    assert context.screen_observation is screen
    assert context.structured_ui_observation is ui
    assert context.screen_provenance is provenance
    assert context.structured_screen_binding.ui_binding is context.ui_binding
    assert context.structured_screen_binding.screen_provenance is provenance
    assert context.screen_observation_id == screen.observation_id
    assert context.ui_observation_id == ui.observation_id
    assert context.application_pid == APP.pid
    assert context.application_bundle_id == APP.bundle_id
    assert context.expires_at_monotonic == context.structured_screen_binding.expires_at_monotonic


def test_published_context_is_exactly_retrievable_by_screen_id():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.available
    assert STRUCTURED_UI_SCREEN_CONTEXTS.peek(screen.observation_id) is result.context
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek("f" * 32)


def test_claim_is_single_use():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    claimed = STRUCTURED_UI_SCREEN_CONTEXTS.claim(screen.observation_id)
    assert claimed is result.context
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.claim(screen.observation_id)


def test_wrong_claim_consumes_context_before_validation():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.available
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.claim("f" * 32)
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek(screen.observation_id)


def test_equal_value_reconstructed_screen_object_is_not_trusted():
    base, screen, ui, provenance = sources()
    reconstructed = replace(screen)
    assert reconstructed == screen
    assert reconstructed is not screen

    result = publish_structured_ui_screen_context(
        reconstructed,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.status == CONTEXT_STATUS_UNKNOWN
    assert result.diagnostics == ("context_publication_failed",)


def test_unavailable_structured_ui_never_publishes_context():
    base, screen, _, provenance = sources()
    unavailable = ui_unavailable(
        "accessibility_permission_denied",
        base + 0.02,
    )
    result = publish_structured_ui_screen_context(
        screen,
        unavailable,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.status == CONTEXT_STATUS_UNKNOWN
    assert result.diagnostics == ("structured_ui_unavailable",)
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek(screen.observation_id)


def test_application_identity_change_fails_closed():
    base, screen, _, provenance = sources()
    other = ApplicationIdentity(APP.pid + 1, "other.app", "Other")
    mismatched = structured_ui(base + 0.02, app=other)
    result = publish_structured_ui_screen_context(
        screen,
        mismatched,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.status == CONTEXT_STATUS_UNKNOWN
    assert result.diagnostics == ("ui_binding_unavailable",)


def test_context_invalidates_when_screen_source_is_cleared():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.available
    SCREEN_OBSERVATIONS.clear()
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek(screen.observation_id)


def test_context_invalidates_when_provenance_source_is_cleared():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    assert result.available
    SCREEN_DESKTOP_PROVENANCE.clear()
    with pytest.raises(StructuredUIScreenPerceptionContextError):
        STRUCTURED_UI_SCREEN_CONTEXTS.peek(screen.observation_id)


def test_context_contract_is_immutable():
    base, screen, ui, provenance = sources()
    result = publish_structured_ui_screen_context(
        screen,
        ui,
        provenance,
        clock=lambda: base + 0.05,
    )
    with pytest.raises(FrozenInstanceError):
        result.context.expires_at_monotonic = 0


def test_context_has_no_authority_or_execution_surface():
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
    fields = set(StructuredUIScreenPerceptionContext.__dataclass_fields__)
    assert not (fields & forbidden)
