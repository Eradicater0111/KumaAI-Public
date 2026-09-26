from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import subprocess
import sys

import pytest

from app.agent.gui_target_evidence import (
    EVIDENCE_STATUS_AVAILABLE,
    EVIDENCE_STATUS_UNKNOWN,
    StructuredUITargetEvidence,
    StructuredUITargetEvidenceResult,
    assemble_structured_ui_target_evidence,
)
from app.agent.gui_target_intent import StructuredUITargetIntent
from app.desktop.contracts import ApplicationIdentity, DesktopContextObservation
from app.desktop.provenance import ScreenDesktopProvenance
from app.desktop.screen_binding import DesktopScreenBinding
from app.ui_observation.contracts import StructuredUIObservation, UIElementObservation
from app.ui_observation.desktop_binding import DesktopUIBinding
from app.ui_observation.screen_binding import StructuredUIScreenBinding
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
    TARGET_STATUS_RESOLVED,
    resolve_structured_ui_target,
)
from app.ui_observation.target_revalidation import (
    CONTINUITY_STATUS_MATCHED,
    revalidate_structured_ui_target,
)


OLD_UI = "1" * 32
OLD_BEFORE = "2" * 32
OLD_AFTER = "3" * 32
OLD_SCREEN = "4" * 32
NEW_UI = "5" * 32
NEW_BEFORE = "6" * 32
NEW_AFTER = "7" * 32
NEW_SCREEN = "8" * 32


def item(
    path=(),
    *,
    owner_pid=123,
    role="AXButton",
    subrole=None,
    title="Save",
    description=None,
    enabled=True,
    focused=False,
    selected=False,
    position_x=10.0,
    position_y=20.0,
    width=100.0,
    height=40.0,
):
    return UIElementObservation(
        path=path,
        owner_pid=owner_pid,
        role=role,
        subrole=subrole,
        title=title,
        description=description,
        enabled=enabled,
        focused=focused,
        selected=selected,
        position_x=position_x,
        position_y=position_y,
        width=width,
        height=height,
    )


def observation(
    *children,
    pid=123,
    bundle="test.app",
    name="Example",
    observation_id=OLD_UI,
    captured=101.0,
    status="available",
    diagnostics=(),
):
    app = ApplicationIdentity(pid, bundle, name)
    root = UIElementObservation(
        path=(),
        owner_pid=pid,
        role="AXApplication",
        title=name,
        enabled=True,
        position_x=0.0,
        position_y=0.0,
        width=800.0,
        height=600.0,
    )
    fixed = tuple(
        replace(child, path=(index,), owner_pid=pid)
        for index, child in enumerate(children)
    )
    return StructuredUIObservation(
        captured_at_monotonic=captured,
        status=status,
        active_application=app,
        elements=(root, *fixed),
        traversal_succeeded=True,
        diagnostics=diagnostics,
        observation_id=observation_id,
    )


def binding(
    *,
    pid=123,
    bundle="test.app",
    name="Example",
    ui_id=OLD_UI,
    before_id=OLD_BEFORE,
    after_id=OLD_AFTER,
    screen_id=OLD_SCREEN,
    before_time=100.0,
    ui_time=101.0,
    screen_time=102.0,
    after_time=103.0,
    screen_bound=103.1,
    ui_bound=103.2,
    linked=103.5,
    expiry=110.0,
    ui_status="available",
    ui_diagnostics=(),
):
    app = ApplicationIdentity(pid, bundle, name)
    before = DesktopContextObservation(
        observation_id=before_id,
        captured_at_monotonic=before_time,
        status="available",
        active_application=app,
        enumeration_succeeded=True,
    )
    after = DesktopContextObservation(
        observation_id=after_id,
        captured_at_monotonic=after_time,
        status="available",
        active_application=app,
        enumeration_succeeded=True,
    )
    ui = DesktopUIBinding(
        ui_observation_id=ui_id,
        desktop_before_id=before_id,
        desktop_after_id=after_id,
        application_pid=pid,
        application_bundle_id=bundle,
        desktop_before_captured_at=before_time,
        ui_captured_at=ui_time,
        desktop_after_captured_at=after_time,
        bound_at_monotonic=ui_bound,
        expires_at_monotonic=expiry,
        desktop_before_status="available",
        desktop_after_status="available",
        ui_status=ui_status,
        desktop_before_diagnostics=(),
        desktop_after_diagnostics=(),
        ui_diagnostics=ui_diagnostics,
    )
    screen = DesktopScreenBinding(
        screen_observation_id=screen_id,
        desktop_before_id=before_id,
        desktop_after_id=after_id,
        application_pid=pid,
        application_bundle_id=bundle,
        desktop_before_captured_at=before_time,
        screen_captured_at=screen_time,
        desktop_after_captured_at=after_time,
        bound_at_monotonic=screen_bound,
        expires_at_monotonic=expiry,
        desktop_before_status="available",
        desktop_after_status="available",
    )
    provenance = ScreenDesktopProvenance(
        binding=screen,
        desktop_before=before,
        desktop_after=after,
    )
    return StructuredUIScreenBinding(
        ui_binding=ui,
        screen_provenance=provenance,
        linked_at_monotonic=linked,
        expires_at_monotonic=expiry,
    )


def old_binding(**changes):
    return binding(**changes)


def fresh_binding(**changes):
    values = dict(
        ui_id=NEW_UI,
        before_id=NEW_BEFORE,
        after_id=NEW_AFTER,
        screen_id=NEW_SCREEN,
        before_time=105.0,
        ui_time=106.0,
        screen_time=107.0,
        after_time=108.0,
        screen_bound=108.1,
        ui_bound=108.2,
        linked=108.5,
        expiry=115.0,
    )
    values.update(changes)
    return binding(**values)


def make_intent(**changes):
    values = dict(
        role="AXButton",
        text="Save",
        require_enabled=True,
        require_positive_area=True,
    )
    values.update(changes)
    return StructuredUITargetIntent(**values)


def matched_result(*, intent=None, selector=None, fresh=None, now=109.0, ui_diagnostic=None):
    intent = intent or make_intent()
    selector = selector or intent.to_selector()

    old_obs = observation(item())
    old_bind = old_binding()
    original_result = resolve_structured_ui_target(
        old_obs,
        old_bind,
        selector,
        clock=lambda: 104.0,
    )
    assert original_result.status == TARGET_STATUS_RESOLVED

    if ui_diagnostic is None:
        fresh_obs = fresh or observation(
            item(position_x=420.0, position_y=330.0, width=160.0, height=55.0),
            observation_id=NEW_UI,
            captured=106.0,
        )
        fresh_bind = fresh_binding()
    else:
        fresh_obs = fresh or observation(
            item(position_x=420.0, position_y=330.0, width=160.0, height=55.0),
            observation_id=NEW_UI,
            captured=106.0,
            status="partial",
            diagnostics=(ui_diagnostic,),
        )
        fresh_bind = fresh_binding(
            ui_status="partial",
            ui_diagnostics=(ui_diagnostic,),
        )

    result = revalidate_structured_ui_target(
        original_result.resolution,
        fresh_obs,
        fresh_bind,
        clock=lambda: now,
    )
    assert result.status == CONTINUITY_STATUS_MATCHED
    return intent, selector, result


def assemble(*, intent=None, selector=None, result=None, now=109.25):
    if result is None:
        made_intent, made_selector, made_result = matched_result(
            intent=intent,
            selector=selector,
        )
        intent = made_intent
        selector = made_selector
        result = made_result
    return assemble_structured_ui_target_evidence(
        intent,
        selector,
        result,
        clock=lambda: now,
    )


def test_matched_b7_result_becomes_available_exact_evidence():
    result = assemble()
    assert result.status == EVIDENCE_STATUS_AVAILABLE
    assert result.available
    evidence = result.evidence
    assert evidence.original_ui_observation_id == OLD_UI
    assert evidence.ui_observation_id == NEW_UI
    assert evidence.screen_observation_id == NEW_SCREEN
    assert evidence.application_pid == 123
    assert evidence.application_bundle_id == "test.app"


def test_envelope_preserves_exact_intent_selector_and_b7_graph_objects():
    intent, selector, revalidation = matched_result()
    result = assemble(intent=intent, selector=selector, result=revalidation)
    evidence = result.evidence
    assert evidence.intent is intent
    assert evidence.selector is selector
    assert evidence.revalidation_result is revalidation
    assert evidence.revalidation is revalidation.revalidation
    assert evidence.revalidation.selector is selector


def test_equal_value_but_distinct_selector_is_rejected_by_identity():
    intent, selector, result = matched_result()
    substituted = StructuredUITargetSelector(
        role=selector.role,
        subrole=selector.subrole,
        text=selector.text,
        require_enabled=selector.require_enabled,
        require_positive_area=selector.require_positive_area,
    )
    assert substituted == selector
    assert substituted is not selector
    assembled = assemble_structured_ui_target_evidence(
        intent,
        substituted,
        result,
        clock=lambda: 109.25,
    )
    assert assembled.status == EVIDENCE_STATUS_UNKNOWN
    assert assembled.diagnostics == ("selector_identity_mismatch",)


def test_intent_selector_value_mismatch_is_rejected_before_identity():
    intent, selector, result = matched_result()
    changed = make_intent(text="Delete")
    assembled = assemble_structured_ui_target_evidence(
        changed,
        selector,
        result,
        clock=lambda: 109.25,
    )
    assert assembled.diagnostics == ("intent_selector_mismatch",)


@pytest.mark.parametrize(
    "bad,slot,code",
    [
        (object(), "intent", "invalid_intent"),
        (object(), "selector", "invalid_selector"),
        (object(), "result", "invalid_revalidation"),
    ],
)
def test_wrong_contract_types_fail_closed(bad, slot, code):
    intent, selector, result = matched_result()
    values = dict(intent=intent, selector=selector, revalidation_result=result)
    if slot == "result":
        values["revalidation_result"] = bad
    else:
        values[slot] = bad
    assembled = assemble_structured_ui_target_evidence(
        values["intent"],
        values["selector"],
        values["revalidation_result"],
        clock=lambda: 109.25,
    )
    assert assembled.status == EVIDENCE_STATUS_UNKNOWN
    assert assembled.diagnostics == (code,)


def test_nonmatched_b7_result_cannot_be_promoted_to_evidence():
    intent, selector, matched = matched_result()
    ambiguous_obs = observation(
        item(),
        item(),
        observation_id=NEW_UI,
        captured=106.0,
    )
    original = matched.revalidation.original
    not_matched = revalidate_structured_ui_target(
        original,
        ambiguous_obs,
        fresh_binding(),
        clock=lambda: 109.0,
    )
    assembled = assemble_structured_ui_target_evidence(
        intent,
        selector,
        not_matched,
        clock=lambda: 109.25,
    )
    assert assembled.status == EVIDENCE_STATUS_UNKNOWN
    assert assembled.diagnostics == ("revalidation_not_matched",)


def test_clock_failure_and_nonfinite_clock_fail_closed_without_leakage():
    intent, selector, result = matched_result()
    assembled = assemble_structured_ui_target_evidence(
        intent,
        selector,
        result,
        clock=lambda: (_ for _ in ()).throw(RuntimeError("private details")),
    )
    assert assembled.diagnostics == ("clock_unavailable",)
    assert "private" not in repr(assembled)

    assembled = assemble_structured_ui_target_evidence(
        intent,
        selector,
        result,
        clock=lambda: float("nan"),
    )
    assert assembled.diagnostics == ("clock_unavailable",)


def test_noncallable_clock_is_rejected():
    intent, selector, result = matched_result()
    with pytest.raises(TypeError):
        assemble_structured_ui_target_evidence(
            intent,
            selector,
            result,
            clock=None,
        )


def test_evidence_from_future_and_expiry_boundaries_fail_closed():
    intent, selector, result = matched_result()
    future = assemble_structured_ui_target_evidence(
        intent,
        selector,
        result,
        clock=lambda: 108.999,
    )
    assert future.diagnostics == ("evidence_from_future",)

    expired = assemble_structured_ui_target_evidence(
        intent,
        selector,
        result,
        clock=lambda: 115.0,
    )
    assert expired.diagnostics == ("evidence_expired",)


def test_evidence_is_immutable_and_uses_exact_b7_lifetime():
    evidence = assemble().evidence
    with pytest.raises(FrozenInstanceError):
        evidence.expires_at_monotonic = 999
    assert evidence.expires_at_monotonic == 115.0
    assert evidence.is_fresh(109.25)
    assert evidence.is_fresh(114.999)
    assert not evidence.is_fresh(115.0)


def test_constructor_rejects_lifetime_extension_or_shortening():
    intent, selector, result = matched_result()
    good = assemble(intent=intent, selector=selector, result=result).evidence
    for expiry in (114.9, 115.1):
        with pytest.raises(ValueError, match="lifetime"):
            replace(good, expires_at_monotonic=expiry)


def test_constructor_rejects_assembly_before_revalidation():
    intent, selector, result = matched_result()
    with pytest.raises(ValueError, match="timing"):
        StructuredUITargetEvidence(
            intent=intent,
            selector=selector,
            revalidation_result=result,
            assembled_at_monotonic=108.9,
            expires_at_monotonic=115.0,
        )


def test_nonblocking_source_partiality_is_preserved_not_promoted():
    intent, selector, result = matched_result(ui_diagnostic="geometry_unavailable")
    assembled = assemble(intent=intent, selector=selector, result=result)
    assert assembled.available
    assert assembled.diagnostics == ("structured_ui_partial",)
    assert assembled.evidence.source_diagnostics == ("structured_ui_partial",)


def test_path_is_snapshot_local_and_fresh_geometry_is_preserved_as_ax_evidence_only():
    intent = make_intent()
    selector = intent.to_selector()

    old_obs = observation(item(position_x=10.0, position_y=20.0, width=100.0, height=40.0))
    old_result = resolve_structured_ui_target(
        old_obs,
        old_binding(),
        selector,
        clock=lambda: 104.0,
    )
    fresh_obs = observation(
        item(title="Other"),
        item(position_x=420.0, position_y=330.0, width=160.0, height=55.0),
        observation_id=NEW_UI,
        captured=106.0,
    )
    revalidation = revalidate_structured_ui_target(
        old_result.resolution,
        fresh_obs,
        fresh_binding(),
        clock=lambda: 109.0,
    )
    assembled = assemble_structured_ui_target_evidence(
        intent,
        selector,
        revalidation,
        clock=lambda: 109.25,
    )
    evidence = assembled.evidence
    assert evidence.snapshot_path == (1,)
    assert evidence.ax_geometry == (420.0, 330.0, 160.0, 55.0)
    assert not hasattr(evidence, "x")
    assert not hasattr(evidence, "y")


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
        "x",
        "y",
    ],
)
def test_evidence_has_no_authority_or_click_surface(name):
    evidence = assemble().evidence
    assert not hasattr(evidence, name)


def test_evidence_has_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(StructuredUITargetEvidence, "from_dict")
    assert not hasattr(StructuredUITargetEvidence, "to_dict")
    assert not hasattr(StructuredUITargetEvidenceResult, "from_dict")


def test_result_contract_rejects_forged_available_and_unknown_combinations():
    evidence = assemble().evidence
    with pytest.raises(ValueError):
        StructuredUITargetEvidenceResult(
            status=EVIDENCE_STATUS_AVAILABLE,
            evidence=None,
        )
    with pytest.raises(ValueError):
        StructuredUITargetEvidenceResult(
            status=EVIDENCE_STATUS_UNKNOWN,
            evidence=evidence,
            diagnostics=("evidence_expired",),
        )
    with pytest.raises(ValueError):
        StructuredUITargetEvidenceResult(
            status=EVIDENCE_STATUS_UNKNOWN,
            diagnostics=("made_up",),
        )


def test_module_has_no_external_effects_or_action_surface():
    module = Path(__file__).with_name("gui_target_evidence.py")
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
        'AppKit', 'Quartz', 'ApplicationServices', 'ollama', 'pyautogui',
        'app.tools', 'app.vision.gui_target_verifier', 'app.agent.mission_service',
        'app.ui_observation.runtime', 'app.ui_observation.macos')):
        raise AssertionError('forbidden import')
sys.addaudithook(audit)
import app.agent.gui_target_evidence as module
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
