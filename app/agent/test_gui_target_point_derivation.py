from dataclasses import (
    FrozenInstanceError,
    replace,
)
from pathlib import Path
import subprocess
import sys

import pytest

from app.agent.gui_target_point_derivation import (
    DERIVATION_STATUS_MATCHED,
    DERIVATION_STATUS_UNKNOWN,
    StructuredUITargetPointDerivation,
    StructuredUITargetPointDerivationResult,
    derive_structured_ui_target_point,
)
from app.agent.test_gui_target_evidence import (
    NEW_SCREEN,
    NEW_UI,
    item,
    observation,
)
from app.agent.test_gui_target_orchestration import (
    make_intent,
    orchestrate,
)
from app.agent.test_gui_target_point_binding import (
    OTHER_SCREEN,
    make_active_screen,
)
from app.vision.observation import (
    SCREEN_OBSERVATIONS,
)


@pytest.fixture(autouse=True)
def clear_screen_store():
    SCREEN_OBSERVATIONS.clear()

    yield

    SCREEN_OBSERVATIONS.clear()


def derive(
    monkeypatch,
    *,
    result=None,
    now=109.5,
):
    screen = make_active_screen(
        monkeypatch
    )

    result = (
        result
        or orchestrate()
    )

    derived = (
        derive_structured_ui_target_point(
            result,
            clock=lambda: now,
        )
    )

    return (
        screen,
        result,
        derived,
    )


def test_happy_path_derives_nearest_representable_center_point(
    monkeypatch,
):
    screen, result, derived = derive(
        monkeypatch
    )

    assert (
        derived.status
        == DERIVATION_STATUS_MATCHED
    )

    assert derived.matched

    evidence = (
        derived.derivation
    )

    assert (
        evidence.orchestration_result
        is result
    )

    assert (
        evidence.screen_observation
        is screen
    )

    assert (
        evidence.screen_observation_id
        == NEW_SCREEN
    )

    assert (
        evidence.ui_observation_id
        == NEW_UI
    )

    # Native AX geometry:
    # x: [420, 580), center = 500
    # y: [330, 385), center = 357.5
    #
    # 2x native/vision scale makes the closest exactly
    # representable native point (500, 358).
    assert (
        evidence.vision_point
        == (250, 179)
    )

    assert (
        evidence.native_point
        == (500, 358)
    )

    assert (
        evidence.ax_geometry
        == (
            420.0,
            330.0,
            160.0,
            55.0,
        )
    )

    # The matched derivation must carry B8D's exact
    # final point-binding graph, not its own authority.
    assert (
        evidence.binding.vision_point
        == evidence.vision_point
    )

    assert (
        evidence.binding.native_point
        == evidence.native_point
    )


def test_tie_break_is_deterministic_and_prefers_lower_vision_coordinate(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    fresh = observation(
        item(
            position_x=499.0,
            position_y=330.0,
            width=4.0,
            height=55.0,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )

    result = orchestrate(
        fresh=fresh,
    )

    assert result.available

    derived = (
        derive_structured_ui_target_point(
            result,
            clock=lambda: 109.5,
        )
    )

    assert derived.matched

    # Native x=500 and x=502 are both one unit from
    # center x=501. Lower vision coordinate wins.
    assert (
        derived.derivation.vision_point[0]
        == 250
    )

    assert (
        derived.derivation.native_point[0]
        == 500
    )


def test_ax_rect_without_representable_vision_x_fails_closed(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    fresh = observation(
        item(
            position_x=421.1,
            position_y=330.0,
            width=0.5,
            height=55.0,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )

    result = orchestrate(
        fresh=fresh,
    )

    assert result.available

    derived = (
        derive_structured_ui_target_point(
            result,
            clock=lambda: 109.5,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "no_representable_point",
    )


def test_ax_rect_without_representable_vision_y_fails_closed(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    fresh = observation(
        item(
            position_x=420.0,
            position_y=331.1,
            width=160.0,
            height=0.5,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )

    result = orchestrate(
        fresh=fresh,
    )

    assert result.available

    derived = (
        derive_structured_ui_target_point(
            result,
            clock=lambda: 109.5,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "no_representable_point",
    )


def test_stale_b8c_evidence_cannot_become_derived_point(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    derived = (
        derive_structured_ui_target_point(
            orchestrate(),
            clock=lambda: 115.0,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "evidence_not_current",
    )


def test_unknown_orchestration_cannot_become_derived_point(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    unavailable = orchestrate(
        original=observation(
            item(
                title="Other"
            )
        ),
        clock=lambda: 104.0,
    )

    derived = (
        derive_structured_ui_target_point(
            unavailable,
            clock=lambda: 109.5,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "orchestration_unavailable",
    )


def test_active_screen_must_match_fresh_b8c_screen_id(
    monkeypatch,
):
    make_active_screen(
        monkeypatch,
        observation_id=OTHER_SCREEN,
    )

    derived = (
        derive_structured_ui_target_point(
            orchestrate(),
            clock=lambda: 109.5,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "screen_observation_unavailable",
    )


def test_incomplete_ax_geometry_fails_closed(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    fresh = observation(
        item(
            position_x=None,
            position_y=None,
            width=160.0,
            height=55.0,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )

    result = orchestrate(
        intent=make_intent(
            require_positive_area=False
        ),
        fresh=fresh,
    )

    assert result.available

    derived = (
        derive_structured_ui_target_point(
            result,
            clock=lambda: 109.5,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "geometry_unavailable",
    )


def test_off_primary_ax_geometry_is_unsupported(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    fresh = observation(
        item(
            position_x=-10.0,
            position_y=330.0,
            width=160.0,
            height=55.0,
        ),
        observation_id=NEW_UI,
        captured=106.0,
    )

    result = orchestrate(
        intent=make_intent(
            require_positive_area=False
        ),
        fresh=fresh,
    )

    assert result.available

    derived = (
        derive_structured_ui_target_point(
            result,
            clock=lambda: 109.5,
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "coordinate_space_unsupported",
    )


def test_constructor_rejects_equal_value_reconstructed_screen(
    monkeypatch,
):
    _screen, _result, derived = derive(
        monkeypatch
    )

    good = (
        derived.derivation
    )

    clone = replace(
        good.screen_observation
    )

    assert (
        clone
        == good.screen_observation
    )

    assert (
        clone
        is not good.screen_observation
    )

    with pytest.raises(
        ValueError,
        match="exact B8C/B8D",
    ):
        replace(
            good,
            screen_observation=clone,
        )


def test_derivation_and_result_are_immutable(
    monkeypatch,
):
    _screen, _result, derived = derive(
        monkeypatch
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        derived.derivation.screen_observation = (
            None
        )

    with pytest.raises(
        FrozenInstanceError
    ):
        derived.status = (
            DERIVATION_STATUS_UNKNOWN
        )


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
        "button",
        "clicks",
    ],
)
def test_derivation_has_no_authority_surface(
    monkeypatch,
    name,
):
    _screen, _result, derived = derive(
        monkeypatch
    )

    assert not hasattr(
        derived.derivation,
        name,
    )

    assert not hasattr(
        derived,
        name,
    )


def test_no_dict_reconstruction_or_serialization_surface():
    assert not hasattr(
        StructuredUITargetPointDerivation,
        "from_dict",
    )

    assert not hasattr(
        StructuredUITargetPointDerivation,
        "to_dict",
    )

    assert not hasattr(
        StructuredUITargetPointDerivationResult,
        "from_dict",
    )

    assert not hasattr(
        StructuredUITargetPointDerivationResult,
        "to_dict",
    )


def test_noncallable_clock_is_rejected():
    with pytest.raises(
        TypeError
    ):
        derive_structured_ui_target_point(
            orchestrate(),
            clock=None,
        )


def test_clock_failure_fails_closed_without_exception_text(
    monkeypatch,
):
    make_active_screen(
        monkeypatch
    )

    derived = (
        derive_structured_ui_target_point(
            orchestrate(),
            clock=lambda: (
                (_ for _ in ()).throw(
                    RuntimeError(
                        "private details"
                    )
                )
            ),
        )
    )

    assert not derived.matched

    assert derived.diagnostics == (
        "clock_unavailable",
    )

    assert (
        "private"
        not in repr(derived)
    )


def test_result_contract_rejects_forged_combinations(
    monkeypatch,
):
    _screen, _result, good = derive(
        monkeypatch
    )

    with pytest.raises(
        ValueError
    ):
        StructuredUITargetPointDerivationResult(
            status=DERIVATION_STATUS_MATCHED,
            derivation=None,
        )

    with pytest.raises(
        ValueError
    ):
        StructuredUITargetPointDerivationResult(
            status=DERIVATION_STATUS_UNKNOWN,
            derivation=good.derivation,
            diagnostics=(
                "clock_unavailable",
            ),
        )

    with pytest.raises(
        ValueError
    ):
        StructuredUITargetPointDerivationResult(
            status=DERIVATION_STATUS_UNKNOWN,
            diagnostics=(
                "made_up",
            ),
        )


def test_module_has_no_model_verifier_permission_authority_or_execution_imports():
    module = Path(
        __file__
    ).with_name(
        "gui_target_point_derivation.py"
    )

    script = r"""
import sys

def audit(event, args):
    if event == 'open':
        mode, flags = args[1:3]
        if (
            isinstance(mode, str)
            and any(c in mode for c in 'wax+')
        ) or (
            isinstance(flags, int)
            and flags & 3
        ):
            raise AssertionError('write')

    if event.startswith((
        'socket.',
        'subprocess.',
        'os.system',
        'os.spawn',
        'os.remove',
        'os.rename',
        'os.mkdir',
    )):
        raise AssertionError(event)

    if (
        event == 'import'
        and args[0].startswith((
            'AppKit',
            'Quartz',
            'ApplicationServices',
            'google.genai',
            'ollama',
            'pyautogui',
            'app.tools',
            'app.agent.mission_service',
            'app.vision.gui_target_verifier',
            'app.agent.permissions',
            'app.agent.gui_argument_authority',
        ))
    ):
        raise AssertionError(
            'forbidden import'
        )

sys.addaudithook(audit)

import app.agent.gui_target_point_derivation as module

for name in (
    'click',
    'execute',
    'authorize',
    'semantic_target_verified',
):
    assert not hasattr(
        module,
        name,
    )
"""

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            script,
        ],
        cwd=module.parents[2],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    assert (
        completed.returncode == 0
    ), completed.stderr
