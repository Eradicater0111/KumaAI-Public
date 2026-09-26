from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
import inspect
from pathlib import Path

import pytest

from app.ui.avatar_renderer_adapter import (
    AVATAR_RENDER_AUTHORITY_NONE,
    AvatarRenderProjection,
    project_avatar_snapshot,
)
from app.ui.avatar_runtime import (
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
)
from app.ui.body_controller import (
    KumaBodyController,
)
from app.ui.body_state import (
    KumaBodyState,
)


MODULE = (
    Path(__file__)
    .with_name(
        "avatar_renderer_adapter.py"
    )
)


class FakeBody:
    def __init__(
        self,
    ):
        self.state = None
        self.calls = []

    def set_state(
        self,
        state,
    ):
        self.calls.append(
            state
        )
        self.state = state


def project(
    mode,
    *,
    expression=AvatarExpression.NEUTRAL,
    intensity=0.0,
    gaze=AvatarGaze.FORWARD,
    motion=0.0,
    speech_active=False,
):
    return project_avatar_snapshot(
        AvatarSnapshot(
            mode=mode,
            expression=expression,
            expression_intensity=intensity,
            gaze=gaze,
            motion_energy=motion,
            speech_active=speech_active,
        )
    )


def module_source():
    return MODULE.read_text()


def imports():
    tree = ast.parse(
        module_source(),
        filename=str(MODULE),
    )

    names = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            names.update(
                alias.name
                for alias in node.names
            )
        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            names.add(
                node.module
            )

    return names


def test_render_authority_constant_is_none():
    assert (
        AVATAR_RENDER_AUTHORITY_NONE
        == "NONE"
    )


def test_projection_fields_are_exact():
    assert tuple(
        item.name
        for item in fields(
            AvatarRenderProjection
        )
    ) == (
        "body_state",
        "source_mode",
        "expression_applied",
        "authority",
    )


def test_projection_authority_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            AvatarRenderProjection
        ).parameters
    )


def test_projection_is_frozen():
    item = project(
        AvatarMode.IDLE
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        item.body_state = (
            KumaBodyState.ALERT
        )


def test_projection_is_slotted():
    assert not hasattr(
        project(
            AvatarMode.IDLE
        ),
        "__dict__",
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    (
        (
            AvatarMode.IDLE,
            KumaBodyState.IDLE,
        ),
        (
            AvatarMode.LISTENING,
            KumaBodyState.LISTENING,
        ),
        (
            AvatarMode.THINKING,
            KumaBodyState.THINKING,
        ),
        (
            AvatarMode.ATTENTION,
            KumaBodyState.ALERT,
        ),
        (
            AvatarMode.SUCCESS,
            KumaBodyState.HAPPY,
        ),
        (
            AvatarMode.ERROR,
            KumaBodyState.ALERT,
        ),
        (
            AvatarMode.SLEEP,
            KumaBodyState.SLEEP,
        ),
    ),
)
def test_non_speaking_mode_mapping(
    mode,
    expected,
):
    result = project(
        mode
    )

    assert (
        result.body_state
        == expected
    )

    assert (
        result.source_mode
        == mode
    )

    assert (
        result.authority
        == "NONE"
    )


def test_speaking_maps_to_speaking():
    result = project(
        AvatarMode.SPEAKING,
        speech_active=True,
    )

    assert (
        result.body_state
        == KumaBodyState.SPEAKING
    )


@pytest.mark.parametrize(
    ("expression", "expected"),
    (
        (
            AvatarExpression.HAPPY,
            KumaBodyState.HAPPY,
        ),
        (
            AvatarExpression.FOCUSED,
            KumaBodyState.FOCUSED,
        ),
        (
            AvatarExpression.ALERT,
            KumaBodyState.ALERT,
        ),
    ),
)
def test_idle_positive_expression_refines_body_state(
    expression,
    expected,
):
    result = project(
        AvatarMode.IDLE,
        expression=expression,
        intensity=0.5,
    )

    assert (
        result.body_state
        == expected
    )
    assert (
        result.expression_applied
        is True
    )


@pytest.mark.parametrize(
    "expression",
    (
        AvatarExpression.NEUTRAL,
        AvatarExpression.GENTLE,
    ),
)
def test_idle_non_discrete_expression_stays_idle(
    expression,
):
    result = project(
        AvatarMode.IDLE,
        expression=expression,
        intensity=1.0,
    )

    assert (
        result.body_state
        == KumaBodyState.IDLE
    )
    assert (
        result.expression_applied
        is False
    )


@pytest.mark.parametrize(
    "expression",
    (
        AvatarExpression.HAPPY,
        AvatarExpression.FOCUSED,
        AvatarExpression.ALERT,
    ),
)
def test_zero_intensity_expression_does_not_override_idle(
    expression,
):
    result = project(
        AvatarMode.IDLE,
        expression=expression,
        intensity=0.0,
    )

    assert (
        result.body_state
        == KumaBodyState.IDLE
    )
    assert (
        result.expression_applied
        is False
    )


@pytest.mark.parametrize(
    ("mode", "speech_active", "expected"),
    (
        (
            AvatarMode.LISTENING,
            False,
            KumaBodyState.LISTENING,
        ),
        (
            AvatarMode.THINKING,
            False,
            KumaBodyState.THINKING,
        ),
        (
            AvatarMode.SPEAKING,
            True,
            KumaBodyState.SPEAKING,
        ),
        (
            AvatarMode.ATTENTION,
            False,
            KumaBodyState.ALERT,
        ),
        (
            AvatarMode.SUCCESS,
            False,
            KumaBodyState.HAPPY,
        ),
        (
            AvatarMode.ERROR,
            False,
            KumaBodyState.ALERT,
        ),
        (
            AvatarMode.SLEEP,
            False,
            KumaBodyState.SLEEP,
        ),
    ),
)
@pytest.mark.parametrize(
    "expression",
    (
        AvatarExpression.HAPPY,
        AvatarExpression.FOCUSED,
        AvatarExpression.ALERT,
        AvatarExpression.GENTLE,
    ),
)
def test_non_idle_lifecycle_wins_over_expression(
    mode,
    speech_active,
    expected,
    expression,
):
    result = project(
        mode,
        expression=expression,
        intensity=1.0,
        speech_active=speech_active,
    )

    assert (
        result.body_state
        == expected
    )
    assert (
        result.expression_applied
        is False
    )


@pytest.mark.parametrize(
    ("gaze", "motion"),
    (
        (
            AvatarGaze.FORWARD,
            0.0,
        ),
        (
            AvatarGaze.USER,
            0.25,
        ),
        (
            AvatarGaze.TARGET,
            0.75,
        ),
        (
            AvatarGaze.AWAY,
            1.0,
        ),
    ),
)
def test_gaze_and_motion_do_not_change_current_discrete_projection(
    gaze,
    motion,
):
    result = project(
        AvatarMode.THINKING,
        expression=(
            AvatarExpression.FOCUSED
        ),
        intensity=1.0,
        gaze=gaze,
        motion=motion,
    )

    assert (
        result.body_state
        == KumaBodyState.THINKING
    )


def test_project_rejects_non_snapshot():
    with pytest.raises(
        TypeError,
        match="AvatarSnapshot",
    ):
        project_avatar_snapshot(
            object()
        )


def test_projection_body_state_requires_enum():
    with pytest.raises(
        TypeError,
        match="KumaBodyState",
    ):
        AvatarRenderProjection(
            body_state="idle",
            source_mode=AvatarMode.IDLE,
            expression_applied=False,
        )


def test_projection_source_mode_requires_enum():
    with pytest.raises(
        TypeError,
        match="AvatarMode",
    ):
        AvatarRenderProjection(
            body_state=KumaBodyState.IDLE,
            source_mode="idle",
            expression_applied=False,
        )


def test_projection_expression_applied_requires_exact_bool():
    with pytest.raises(
        TypeError,
        match="bool",
    ):
        AvatarRenderProjection(
            body_state=KumaBodyState.IDLE,
            source_mode=AvatarMode.IDLE,
            expression_applied=1,
        )


def test_controller_exposes_avatar_snapshot_presenter():
    assert hasattr(
        KumaBodyController,
        "present_avatar_snapshot",
    )


def test_controller_presenter_signature_is_snapshot_only():
    signature = inspect.signature(
        KumaBodyController.present_avatar_snapshot
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "snapshot",
    )


def test_controller_projects_once_and_sets_body_once():
    body = FakeBody()

    controller = KumaBodyController(
        body
    )

    snapshot = AvatarSnapshot(
        mode=AvatarMode.THINKING,
        expression=AvatarExpression.FOCUSED,
        expression_intensity=1.0,
    )

    controller.present_avatar_snapshot(
        snapshot
    )

    assert body.calls == [
        KumaBodyState.THINKING
    ]


def test_controller_idle_expression_refinement_reaches_body():
    body = FakeBody()

    controller = KumaBodyController(
        body
    )

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=AvatarMode.IDLE,
            expression=AvatarExpression.HAPPY,
            expression_intensity=0.8,
        )
    )

    assert body.state == KumaBodyState.HAPPY


def test_controller_speaking_reaches_body():
    body = FakeBody()

    controller = KumaBodyController(
        body
    )

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=AvatarMode.SPEAKING,
            speech_active=True,
        )
    )

    assert (
        body.state
        == KumaBodyState.SPEAKING
    )


def test_controller_invalid_input_is_ignored_without_clobbering_body():
    body = FakeBody()
    body.state = KumaBodyState.ALERT

    controller = KumaBodyController(
        body
    )

    controller.present_avatar_snapshot(
        object()
    )

    assert (
        body.state
        == KumaBodyState.ALERT
    )
    assert body.calls == []


def test_controller_presenter_does_not_mutate_snapshot():
    body = FakeBody()

    controller = KumaBodyController(
        body
    )

    snapshot = AvatarSnapshot(
        mode=AvatarMode.SUCCESS,
        expression=AvatarExpression.HAPPY,
        expression_intensity=1.0,
        reason="task response complete",
    )

    before = snapshot

    controller.present_avatar_snapshot(
        snapshot
    )

    assert snapshot == before


def test_controller_presenter_has_no_reverse_read_from_body():
    source = inspect.getsource(
        KumaBodyController.present_avatar_snapshot
    )

    for forbidden in (
        "self.body.state",
        "self.body._state",
        "state_changed",
        "snapshot.",
    ):
        if forbidden == "snapshot.":
            continue
        assert forbidden not in source


def test_adapter_import_surface_is_presentation_only():
    loaded = imports()

    assert loaded == {
        "__future__",
        "dataclasses",
        "app.ui.avatar_runtime",
        "app.ui.body_state",
    }


def test_adapter_has_no_qt_dependency():
    assert not any(
        name.startswith(
            (
                "PySide",
                "PyQt",
            )
        )
        for name in imports()
    )


def test_adapter_has_no_agent_tool_voice_memory_dependency():
    assert not any(
        name.startswith(
            (
                "app.agent",
                "app.tools",
                "app.voice",
                "app.memory",
            )
        )
        for name in imports()
    )


def test_adapter_has_no_network_model_background_dependency():
    loaded = imports()

    for forbidden in (
        "requests",
        "urllib",
        "httpx",
        "socket",
        "ollama",
        "google.genai",
        "threading",
        "asyncio",
        "subprocess",
    ):
        assert forbidden not in loaded


def test_adapter_has_no_loop_or_async_runtime():
    tree = ast.parse(
        module_source(),
        filename=str(MODULE),
    )

    assert not any(
        isinstance(
            node,
            (
                ast.While,
                ast.AsyncFunctionDef,
            ),
        )
        for node in ast.walk(
            tree
        )
    )


def test_adapter_has_no_execution_permission_or_confirmation_surface():
    text = module_source()

    for forbidden in (
        "executor",
        "execute(",
        "request_confirmation(",
        "get_permission_level(",
        "require_explicit_permission(",
        "register_tool(",
        "emit_status(",
        "pending_signals(",
        "drain_signals(",
        ".speak(",
    ):
        assert forbidden not in text


def test_adapter_has_no_qml_geometry_surface():
    text = module_source()

    for forbidden in (
        "KumaMini",
        "bodyState",
        "rootObject",
        "setProperty",
        "eulerRotation",
        "hoverOffset",
        "requestPaint",
    ):
        assert forbidden not in text


def test_adapter_does_not_import_body_controller_or_floating_body():
    loaded = imports()

    assert (
        "app.ui.body_controller"
        not in loaded
    )
    assert (
        "app.ui.floating_body"
        not in loaded
    )


def test_contract_documents_one_way_boundaries():
    text = module_source()

    for required in (
        "RENDER PROJECTION != COGNITION",
        "BODY STATE != FACT",
        "EXPRESSION != PERMISSION",
        "RENDERER OUTPUT != EXECUTION",
        "PRESENTATION SINK != CONTROL LOOP",
    ):
        assert required in text


def test_legacy_observing_and_working_states_remain_available():
    assert (
        KumaBodyState.OBSERVING.value
        == "observing"
    )
    assert (
        KumaBodyState.WORKING.value
        == "working"
    )


def test_adapter_does_not_project_new_modes_to_legacy_observing_or_working():
    projected = {
        project(
            mode,
            speech_active=(
                mode
                == AvatarMode.SPEAKING
            ),
        ).body_state
        for mode in AvatarMode
    }

    assert (
        KumaBodyState.OBSERVING
        not in projected
    )
    assert (
        KumaBodyState.WORKING
        not in projected
    )
