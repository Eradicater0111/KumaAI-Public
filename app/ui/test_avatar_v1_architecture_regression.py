from __future__ import annotations

import ast
from dataclasses import fields
import inspect
from pathlib import Path

import pytest

from app.ui.avatar_runtime import (
    AVATAR_AUTHORITY_NONE,
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
)
from app.ui.avatar_renderer_adapter import (
    AVATAR_RENDER_AUTHORITY_NONE,
    AvatarRenderProjection,
    project_avatar_snapshot,
)
from app.ui.avatar_visual_mechanics import (
    AVATAR_GAZE_PITCH_LIMIT_DEGREES,
    AVATAR_GAZE_YAW_LIMIT_DEGREES,
    AVATAR_VISUAL_AUTHORITY_NONE,
    AvatarVisualParameters,
    project_avatar_visual_parameters,
)
from app.ui.body_controller import KumaBodyController
from app.ui.body_state import KumaBodyState


ROOT = Path(__file__).parent

RUNTIME = ROOT / "avatar_runtime.py"
ADAPTER = ROOT / "avatar_renderer_adapter.py"
VISUAL = ROOT / "avatar_visual_mechanics.py"
CONTROLLER = ROOT / "body_controller.py"
FLOATING = ROOT / "floating_body.py"
VIEW = ROOT / "kuma_3d_view.py"
WINDOW = ROOT / "window.py"
QML = (
    ROOT
    / "assets"
    / "kuma_mini"
    / "KumaMiniBodyR1.qml"
)


EXPECTED_BODY_BY_MODE = {
    AvatarMode.IDLE: KumaBodyState.IDLE,
    AvatarMode.LISTENING: KumaBodyState.LISTENING,
    AvatarMode.THINKING: KumaBodyState.THINKING,
    AvatarMode.SPEAKING: KumaBodyState.SPEAKING,
    AvatarMode.ATTENTION: KumaBodyState.ALERT,
    AvatarMode.SUCCESS: KumaBodyState.HAPPY,
    AvatarMode.ERROR: KumaBodyState.ALERT,
    AvatarMode.SLEEP: KumaBodyState.SLEEP,
}


EXPECTED_GAZE = {
    AvatarGaze.FORWARD: (0.0, 0.0),
    AvatarGaze.USER: (0.0, -1.5),
    AvatarGaze.TARGET: (6.0, -1.0),
    AvatarGaze.AWAY: (-8.0, 2.0),
}


EXPECTED_TRANSITIONS = {
    "avatarMotionEnergy": (260, "Easing.InOutQuad"),
    "avatarExpressionIntensity": (220, "Easing.OutQuad"),
    "avatarGazeYaw": (320, "Easing.InOutQuad"),
    "avatarGazePitch": (320, "Easing.InOutQuad"),
}


class RecordingBody:

    def __init__(self):
        self.events = []

    def set_state(self, state):
        self.events.append(
            (
                "state",
                state,
            )
        )

    def set_avatar_visual_parameters(
        self,
        parameters,
    ):
        self.events.append(
            (
                "visual",
                parameters,
            )
        )
        return True


class LegacyBody:

    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(
            state
        )


def source(path):
    return path.read_text()


def parsed(path):
    return ast.parse(
        source(path),
        filename=str(path),
    )


def class_method_source(
    path,
    class_name,
    method_name,
):
    text = source(path)
    tree = ast.parse(
        text,
        filename=str(path),
    )

    cls = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.ClassDef,
            )
            and node.name
            == class_name
        )
    )

    method = next(
        node
        for node in cls.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == method_name
        )
    )

    return (
        ast.get_source_segment(
            text,
            method,
        )
        or ""
    )


def call_names(
    text,
):
    tree = ast.parse(
        text
    )

    names = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        func = node.func

        if isinstance(
            func,
            ast.Name,
        ):
            names.append(
                func.id
            )

        elif isinstance(
            func,
            ast.Attribute,
        ):
            names.append(
                func.attr
            )

    return names


def import_modules(
    path,
):
    modules = set()

    for node in ast.walk(
        parsed(path)
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.update(
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
            modules.add(
                node.module
            )

    return modules


def behavior_block(
    property_name,
):
    text = source(QML)

    marker = (
        f"Behavior on {property_name} {{"
    )

    start = text.index(
        marker
    )

    candidates = [
        text.find(
            "    Behavior on ",
            start + len(marker),
        ),
        text.find(
            "    NumberAnimation on phase {",
            start + len(marker),
        ),
    ]

    candidates = [
        value
        for value in candidates
        if value != -1
    ]

    assert candidates

    return text[
        start:min(candidates)
    ]


# =========================================================
# AVATAR V1 ZERO-AUTHORITY CONTRACT
# =========================================================


def test_v1_authority_constants_are_exact_none():
    assert AVATAR_AUTHORITY_NONE == "NONE"
    assert AVATAR_RENDER_AUTHORITY_NONE == "NONE"
    assert AVATAR_VISUAL_AUTHORITY_NONE == "NONE"


def test_v1_snapshot_authority_is_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            AvatarSnapshot
        ).parameters
    )


def test_v1_render_projection_authority_is_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            AvatarRenderProjection
        ).parameters
    )


def test_v1_visual_parameters_authority_is_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            AvatarVisualParameters
        ).parameters
    )


def test_v1_snapshot_fields_remain_exact():
    assert tuple(
        item.name
        for item in fields(
            AvatarSnapshot
        )
    ) == (
        "mode",
        "expression",
        "expression_intensity",
        "gaze",
        "motion_energy",
        "speech_active",
        "reason",
        "authority",
    )


def test_v1_render_projection_fields_remain_exact():
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


def test_v1_visual_parameter_fields_remain_exact():
    assert tuple(
        item.name
        for item in fields(
            AvatarVisualParameters
        )
    ) == (
        "motion_energy",
        "expression_intensity",
        "gaze_yaw_degrees",
        "gaze_pitch_degrees",
        "authority",
    )


@pytest.mark.parametrize(
    "mode",
    tuple(
        AvatarMode
    ),
)
def test_every_mode_remains_zero_authority(
    mode,
):
    snapshot = AvatarSnapshot(
        mode=mode,
        speech_active=(
            mode
            == AvatarMode.SPEAKING
        ),
    )

    discrete = project_avatar_snapshot(
        snapshot
    )

    visual = (
        project_avatar_visual_parameters(
            snapshot
        )
    )

    assert snapshot.authority == "NONE"
    assert discrete.authority == "NONE"
    assert visual.authority == "NONE"


# =========================================================
# SEMANTIC → DISCRETE → VISUAL COMPOSITION
# =========================================================


@pytest.mark.parametrize(
    (
        "mode",
        "expected_body",
    ),
    tuple(
        EXPECTED_BODY_BY_MODE.items()
    ),
)
def test_v1_lifecycle_modes_project_deterministically(
    mode,
    expected_body,
):
    snapshot = AvatarSnapshot(
        mode=mode,
        speech_active=(
            mode
            == AvatarMode.SPEAKING
        ),
    )

    result = project_avatar_snapshot(
        snapshot
    )

    assert (
        result.body_state
        == expected_body
    )

    assert (
        result.source_mode
        == mode
    )

    assert (
        result.authority
        == "NONE"
    )


@pytest.mark.parametrize(
    (
        "gaze",
        "expected",
    ),
    tuple(
        EXPECTED_GAZE.items()
    ),
)
def test_v1_gaze_is_fixed_presentation_pose_only(
    gaze,
    expected,
):
    result = (
        project_avatar_visual_parameters(
            AvatarSnapshot(
                gaze=gaze
            )
        )
    )

    assert (
        result.gaze_yaw_degrees,
        result.gaze_pitch_degrees,
    ) == expected


@pytest.mark.parametrize(
    "gaze",
    tuple(
        AvatarGaze
    ),
)
def test_v1_all_gaze_poses_remain_bounded(
    gaze,
):
    result = (
        project_avatar_visual_parameters(
            AvatarSnapshot(
                gaze=gaze
            )
        )
    )

    assert (
        abs(
            result.gaze_yaw_degrees
        )
        <= AVATAR_GAZE_YAW_LIMIT_DEGREES
    )

    assert (
        abs(
            result.gaze_pitch_degrees
        )
        <= AVATAR_GAZE_PITCH_LIMIT_DEGREES
    )


def test_v1_target_gaze_has_no_coordinate_input_surface():
    signature = inspect.signature(
        project_avatar_visual_parameters
    )

    assert tuple(
        signature.parameters
    ) == (
        "snapshot",
    )

    text = source(
        VISUAL
    )

    tree = ast.parse(
        text
    )

    identifiers = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Name,
        ):
            identifiers.add(
                node.id
            )

        elif isinstance(
            node,
            ast.Attribute,
        ):
            identifiers.add(
                node.attr
            )

        elif isinstance(
            node,
            ast.arg,
        ):
            identifiers.add(
                node.arg
            )

    for forbidden in (
        "screen_x",
        "screen_y",
        "target_id",
        "element_id",
        "native_point",
        "pointer",
        "AXUI",
    ):
        assert (
            forbidden
            not in identifiers
        ), forbidden


def test_v1_controller_orders_discrete_state_before_visual_parameters():
    body = RecordingBody()

    controller = KumaBodyController(
        body
    )

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=AvatarMode.THINKING,
            expression=AvatarExpression.FOCUSED,
            expression_intensity=0.65,
            gaze=AvatarGaze.USER,
            motion_energy=0.45,
        )
    )

    assert len(
        body.events
    ) == 2

    assert body.events[0] == (
        "state",
        KumaBodyState.THINKING,
    )

    assert body.events[1][0] == (
        "visual"
    )

    visual = body.events[1][1]

    assert isinstance(
        visual,
        AvatarVisualParameters,
    )

    assert visual.motion_energy == 0.45
    assert visual.expression_intensity == 0.65
    assert visual.gaze_yaw_degrees == 0.0
    assert visual.gaze_pitch_degrees == -1.5
    assert visual.authority == "NONE"


@pytest.mark.parametrize(
    (
        "mode",
        "body_state",
    ),
    tuple(
        EXPECTED_BODY_BY_MODE.items()
    ),
)
def test_v1_controller_reaches_expected_body_state_for_each_mode(
    mode,
    body_state,
):
    body = RecordingBody()

    controller = KumaBodyController(
        body
    )

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=mode,
            speech_active=(
                mode
                == AvatarMode.SPEAKING
            ),
        )
    )

    assert body.events[0] == (
        "state",
        body_state,
    )

    assert body.events[1][0] == (
        "visual"
    )


def test_v1_controller_remains_compatible_with_legacy_body_sink():
    body = LegacyBody()

    controller = KumaBodyController(
        body
    )

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=AvatarMode.SUCCESS,
            expression=AvatarExpression.HAPPY,
            expression_intensity=0.8,
            motion_energy=0.5,
        )
    )

    assert body.states == [
        KumaBodyState.HAPPY
    ]


# =========================================================
# SPEECH / LISTENING TRUTH BOUNDARY
# =========================================================


def test_v1_speaking_requires_active_speech():
    snapshot = AvatarSnapshot(
        mode=AvatarMode.SPEAKING,
        speech_active=True,
    )

    assert snapshot.speech_active is True


def test_v1_non_speaking_default_is_inactive():
    for mode in AvatarMode:
        if mode == AvatarMode.SPEAKING:
            continue

        snapshot = AvatarSnapshot(
            mode=mode
        )

        assert (
            snapshot.speech_active
            is False
        )


def test_v1_live_window_has_no_semantic_listening_snapshot_source():
    text = source(
        WINDOW
    )

    assert (
        "AvatarMode.LISTENING"
        not in text
    )


def test_v1_semantic_listening_exists_only_as_contract_and_projection_capability():
    runtime = source(
        RUNTIME
    )

    adapter = source(
        ADAPTER
    )

    assert (
        "LISTENING"
        in runtime
    )

    assert (
        "AvatarMode.LISTENING"
        in adapter
    )

    assert (
        "KumaBodyState.LISTENING"
        in adapter
    )


def test_v1_legacy_status_bridge_retains_listening_compatibility():
    method = class_method_source(
        CONTROLLER,
        "KumaBodyController",
        "handle_runtime_status",
    )

    assert '"listening"' in method
    assert '"hearing"' in method
    assert (
        "KumaBodyState.LISTENING"
        in method
    )


def test_v1_live_speech_snapshot_is_bound_to_actual_playback_signal():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "_on_kuma_speech_started",
    )

    assert (
        "AvatarMode.SPEAKING"
        in method
    )

    assert (
        "speech_active=True"
        in method
    )


def test_v1_speech_failure_remains_presentation_only():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "_on_kuma_speech_error",
    )

    assert (
        "AvatarMode.ERROR"
        in method
    )

    for forbidden in (
        "request_confirmation(",
        "execute(",
        "executor",
        "TaskState",
        "mark_finished",
        "record_failure",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


# =========================================================
# LIVE LIFECYCLE ARCHITECTURE
# =========================================================


def test_v1_live_window_has_exactly_eight_semantic_snapshot_sinks():
    assert (
        source(
            WINDOW
        ).count(
            "self.body_controller.present_avatar_snapshot("
        )
        == 8
    )


def test_v1_live_window_has_exactly_eight_snapshot_constructions():
    assert (
        source(
            WINDOW
        ).count(
            "AvatarSnapshot("
        )
        == 8
    )


def test_v1_live_window_has_no_direct_floating_body_state_write():
    assert (
        "self.floating_body.set_state("
        not in source(
            WINDOW
        )
    )


def test_v1_window_does_not_bypass_renderer_adapter():
    text = source(
        WINDOW
    )

    assert (
        "avatar_renderer_adapter"
        not in text
    )

    assert (
        "project_avatar_snapshot("
        not in text
    )

    assert (
        "project_avatar_visual_parameters("
        not in text
    )


def test_v1_request_start_remains_thinking_before_worker_start():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "submit_user_turn_text",
    )

    assert (
        "AvatarMode.THINKING"
        in method
    )

    assert (
        method.index(
            "present_avatar_snapshot("
        )
        < method.index(
            "worker.start()"
        )
    )


def test_v1_idle_restore_retains_generation_guard():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "_restore_body_idle_if_current",
    )

    assert (
        "self._body_idle_generation"
        in method
    )

    assert (
        "AvatarMode.IDLE"
        in method
    )

    assert (
        "AvatarGaze.FORWARD"
        in method
    )

    assert (
        "motion_energy=0.0"
        in method
    )


def test_v1_speech_finish_retains_pending_emotion_priority():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "_on_kuma_speech_finished",
    )

    assert (
        "self._present_pending_emotion()"
        in method
    )

    assert (
        method.index(
            "self._present_pending_emotion()"
        )
        < method.index(
            "present_avatar_snapshot("
        )
    )


def test_v1_response_success_and_error_are_presentation_classification():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "on_response",
    )

    assert (
        "self._response_indicates_failure("
        in method
    )

    assert (
        "AvatarMode.ERROR"
        in method
    )

    assert (
        "AvatarMode.SUCCESS"
        in method
    )

    assert (
        "elif not speech_active:"
        in method
    )


def test_v1_response_presentation_does_not_claim_verified_completion():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "on_response",
    )

    for forbidden in (
        "GoalStatus.COMPLETE",
        "VerifiedLoopCompletion",
        "mark_finished",
        "verified_goal",
        "goal_verified",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


def test_v1_worker_error_remains_visual_error_not_authority():
    method = class_method_source(
        WINDOW,
        "KumaWindow",
        "on_error",
    )

    assert (
        "AvatarMode.ERROR"
        in method
    )

    for forbidden in (
        "request_confirmation(",
        "executor.execute",
        "mark_finished",
        "TaskState",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


# =========================================================
# ONE-WAY RENDERER BRIDGE
# =========================================================


def test_v1_controller_presenter_is_snapshot_only():
    signature = inspect.signature(
        KumaBodyController.present_avatar_snapshot
    )

    assert tuple(
        signature.parameters
    ) == (
        "self",
        "snapshot",
    )


def test_v1_controller_presenter_has_no_renderer_readback():
    method = class_method_source(
        CONTROLLER,
        "KumaBodyController",
        "present_avatar_snapshot",
    )

    for forbidden in (
        "self.body.state",
        "self.body._state",
        "state_changed",
        "rootObject(",
        ".property(",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


def test_v1_floating_visual_sink_forwards_to_3d_only():
    method = class_method_source(
        FLOATING,
        "KumaMiniBody",
        "set_avatar_visual_parameters",
    )

    assert (
        ".set_avatar_visual_parameters("
        in method
    )

    for forbidden in (
        "request_confirmation",
        "executor",
        "runtime.run",
        "emit_status",
        "speech",
        "TaskState",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


def test_v1_3d_visual_bridge_writes_exact_four_renderer_targets():
    method = class_method_source(
        VIEW,
        "Kuma3DView",
        "set_avatar_visual_parameters",
    )

    for name in (
        "avatarMotionEnergy",
        "avatarExpressionIntensity",
        "avatarGazeYaw",
        "avatarGazePitch",
    ):
        assert (
            method.count(
                f'"{name}"'
            )
            == 1
        )

    assert (
        "root.setProperty("
        in method
    )


def test_v1_3d_visual_bridge_never_reads_qml_state_back():
    method = class_method_source(
        VIEW,
        "Kuma3DView",
        "set_avatar_visual_parameters",
    )

    for forbidden in (
        "root.property(",
        "self.property(",
        "valueChanged",
        "propertyChanged",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


def test_v1_3d_body_state_bridge_remains_separate():
    method = class_method_source(
        VIEW,
        "Kuma3DView",
        "set_body_state",
    )

    assert (
        '"bodyState"'
        in method
    )

    for name in (
        "avatarMotionEnergy",
        "avatarExpressionIntensity",
        "avatarGazeYaw",
        "avatarGazePitch",
    ):
        assert (
            name
            not in method
        )


# =========================================================
# QML MECHANICS + CONTINUITY
# =========================================================


def test_v1_qml_declares_exact_four_avatar_visual_targets():
    text = source(
        QML
    )

    for required in (
        "property real avatarMotionEnergy: 0.0",
        "property real avatarExpressionIntensity: 0.0",
        "property real avatarGazeYaw: 0.0",
        "property real avatarGazePitch: 0.0",
    ):
        assert (
            text.count(
                required
            )
            == 1
        )


@pytest.mark.parametrize(
    (
        "property_name",
        "duration",
        "easing",
    ),
    tuple(
        (
            name,
            values[0],
            values[1],
        )
        for (
            name,
            values,
        ) in EXPECTED_TRANSITIONS.items()
    ),
)
def test_v1_qml_visual_targets_have_exact_transition_contract(
    property_name,
    duration,
    easing,
):
    block = behavior_block(
        property_name
    )

    compact = " ".join(
        block.split()
    )

    assert (
        f"duration: {duration}"
        in compact
    )

    assert (
        f"easing.type: {easing}"
        in compact
    )

    assert (
        compact.count(
            "NumberAnimation {"
        )
        == 1
    )


def test_v1_qml_body_state_remains_immediate():
    text = source(
        QML
    )

    assert (
        "Behavior on bodyState"
        not in text
    )

    assert (
        "BODY STATE REMAINS IMMEDIATE"
        in text
    )


def test_v1_qml_keeps_single_phase_driver():
    assert (
        source(
            QML
        ).count(
            "NumberAnimation on phase {"
        )
        == 1
    )


def test_v1_qml_keeps_audited_five_timers():
    assert (
        source(
            QML
        ).count(
            "Timer {"
        )
        == 5
    )


def test_v1_qml_keeps_existing_curiosity_behaviors():
    text = source(
        QML
    )

    for name in (
        "curiosityYaw",
        "curiosityPitch",
    ):
        assert (
            text.count(
                f"Behavior on {name} {{"
            )
            == 1
        )


def test_v1_qml_keeps_existing_ear_twitch_behaviors():
    text = source(
        QML
    )

    for name in (
        "leftEarTwitch",
        "rightEarTwitch",
    ):
        assert (
            text.count(
                f"Behavior on {name} {{"
            )
            == 1
        )


def test_v1_qml_gaze_applies_only_as_head_pose_offset():
    compact = " ".join(
        source(
            QML
        ).split()
    )

    assert (
        "pitch + root.avatarGazePitch"
        in compact
    )

    assert (
        "yaw + root.avatarGazeYaw"
        in compact
    )


def test_v1_qml_motion_energy_remains_bounded_multiplier_input():
    text = source(
        QML
    )

    assert (
        "root.avatarMotionEnergy"
        in text
    )

    assert (
        "* 1.6"
        in text
    )

    assert (
        "* 0.9"
        in text
    )


def test_v1_qml_expression_intensity_remains_renderer_only_multiplier():
    text = source(
        QML
    )

    assert (
        "root.avatarExpressionIntensity"
        in text
    )

    assert (
        "* 1.5"
        in text
    )

    assert (
        "* 4.0"
        in text
    )


def test_v1_qml_inspection_turntable_remains_separate():
    text = source(
        QML
    )

    assert (
        "root.inspectionPitch"
        in text
    )

    assert (
        "root.inspectionYaw"
        in text
    )

    assert (
        text.index(
            "id: inspectionTurntable"
        )
        < text.index(
            "id: kumaRig"
        )
        < text.index(
            "id: headRig"
        )
    )


def test_v1_qml_transition_boundaries_are_documented():
    text = source(
        QML
    )

    for required in (
        "TARGET VALUE != CURRENT INTERPOLATED VALUE",
        "INTERPOLATION != SEMANTIC STATE",
        "EASING != COGNITION",
        "ANIMATION TIME != AUTHORITY",
        "VISUAL CONTINUITY != EXECUTION",
        "BODY STATE REMAINS IMMEDIATE",
    ):
        assert (
            required
            in text
        )


# =========================================================
# DEPENDENCY / AUTHORITY BOUNDARY REGRESSION
# =========================================================


@pytest.mark.parametrize(
    "path",
    (
        RUNTIME,
        ADAPTER,
        VISUAL,
    ),
)
def test_v1_semantic_projection_modules_have_no_agent_dependency(
    path,
):
    loaded = import_modules(
        path
    )

    assert not any(
        name.startswith(
            "app.agent"
        )
        for name in loaded
    )


@pytest.mark.parametrize(
    "path",
    (
        RUNTIME,
        ADAPTER,
        VISUAL,
    ),
)
def test_v1_semantic_projection_modules_have_no_tool_dependency(
    path,
):
    loaded = import_modules(
        path
    )

    assert not any(
        name.startswith(
            "app.tools"
        )
        for name in loaded
    )


@pytest.mark.parametrize(
    "path",
    (
        RUNTIME,
        ADAPTER,
        VISUAL,
    ),
)
def test_v1_semantic_projection_modules_have_no_voice_dependency(
    path,
):
    loaded = import_modules(
        path
    )

    assert not any(
        name.startswith(
            "app.voice"
        )
        for name in loaded
    )


@pytest.mark.parametrize(
    "path",
    (
        RUNTIME,
        ADAPTER,
        VISUAL,
    ),
)
def test_v1_semantic_projection_modules_have_no_memory_dependency(
    path,
):
    loaded = import_modules(
        path
    )

    assert not any(
        name.startswith(
            "app.memory"
        )
        for name in loaded
    )


@pytest.mark.parametrize(
    (
        "path",
        "class_name",
        "method_name",
    ),
    (
        (
            CONTROLLER,
            "KumaBodyController",
            "present_avatar_snapshot",
        ),
        (
            FLOATING,
            "KumaMiniBody",
            "set_avatar_visual_parameters",
        ),
        (
            VIEW,
            "Kuma3DView",
            "set_avatar_visual_parameters",
        ),
        (
            VIEW,
            "Kuma3DView",
            "set_body_state",
        ),
    ),
)
def test_v1_renderer_path_has_no_permission_confirmation_or_execution_calls(
    path,
    class_name,
    method_name,
):
    method = class_method_source(
        path,
        class_name,
        method_name,
    )

    names = set(
        call_names(
            method
        )
    )

    for forbidden in (
        "request_confirmation",
        "requires_confirmation",
        "confirm_dangerous_action",
        "execute",
        "execute_command",
        "register_tool",
        "drain_signals",
        "pending_signals",
    ):
        assert (
            forbidden
            not in names
        ), forbidden


def test_v1_visual_contract_documents_target_boundary():
    text = source(
        VISUAL
    )

    for required in (
        "VISUAL GAZE != DESKTOP TARGET",
        "GAZE POSE != TARGET IDENTITY",
        "MOTION ENERGY != COGNITIVE ENERGY",
        "EXPRESSION INTENSITY != FACT CONFIDENCE",
        "VISUAL PARAMETERS != AUTHORITY",
        "RENDER MECHANICS != EXECUTION",
    ):
        assert (
            required
            in text
        )


def test_v1_runtime_contract_documents_zero_authority_boundary():
    text = source(
        RUNTIME
    )

    for required in (
        "AVATAR STATE != COGNITIVE STATE",
        "AVATAR EXPRESSION != FACT",
        "AVATAR ATTENTION != PERMISSION",
        "SPEAKING != AUTHORITY",
        "ANIMATION != ACTION",
        "PRESENTATION != EXECUTION",
    ):
        assert (
            required
            in text
        )


def test_v1_adapter_documents_one_way_renderer_boundary():
    text = source(
        ADAPTER
    )

    for required in (
        "RENDER PROJECTION != COGNITION",
        "BODY STATE != FACT",
        "EXPRESSION != PERMISSION",
        "RENDERER OUTPUT != EXECUTION",
        "PRESENTATION SINK != CONTROL LOOP",
    ):
        assert (
            required
            in text
        )


# =========================================================
# FINAL ARCHITECTURE INVARIANTS
# =========================================================


def test_v1_no_background_loop_in_semantic_avatar_modules():
    for path in (
        RUNTIME,
        ADAPTER,
        VISUAL,
    ):
        tree = parsed(
            path
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


def test_v1_no_renderer_target_coordinates_in_avatar_semantic_modules():
    for path in (
        RUNTIME,
        ADAPTER,
        VISUAL,
    ):
        text = source(
            path
        )

        for forbidden in (
            "screen_x",
            "screen_y",
            "native_point",
            "AXUIElement",
            "mouse_x",
            "mouse_y",
        ):
            assert (
                forbidden
                not in text
            ), (
                str(path),
                forbidden,
            )


def test_v1_qml_contains_no_desktop_targeting_channel():
    text = source(
        QML
    )

    for forbidden in (
        "screenX",
        "screenY",
        "targetId",
        "elementId",
        "AXUI",
        "mouseX",
        "mouseY",
    ):
        assert (
            forbidden
            not in text
        ), forbidden


def test_v1_qml_contains_no_permission_or_execution_hook():
    text = source(
        QML
    )

    for forbidden in (
        "requestConfirmation",
        "permissionLevel",
        "executeCommand",
        "toolRegistry",
        "pendingSignals",
        "drainSignals",
    ):
        assert (
            forbidden
            not in text
        ), forbidden


def test_v1_architecture_is_one_way_presentation_pipeline():
    controller = class_method_source(
        CONTROLLER,
        "KumaBodyController",
        "present_avatar_snapshot",
    )

    floating = class_method_source(
        FLOATING,
        "KumaMiniBody",
        "set_avatar_visual_parameters",
    )

    view = class_method_source(
        VIEW,
        "Kuma3DView",
        "set_avatar_visual_parameters",
    )

    assert (
        "project_avatar_snapshot("
        in controller
    )

    assert (
        "project_avatar_visual_parameters("
        in controller
    )

    assert (
        "self.body.set_state("
        in controller
    )

    assert (
        "set_avatar_visual_parameters"
        in controller
    )

    assert (
        ".set_avatar_visual_parameters("
        in floating
    )

    assert (
        "root.setProperty("
        in view
    )

    assert (
        "root.property("
        not in view
    )


def test_v1_architecture_retains_explicit_listening_caveat():
    window = source(
        WINDOW
    )

    controller = class_method_source(
        CONTROLLER,
        "KumaBodyController",
        "handle_runtime_status",
    )

    assert (
        "AvatarMode.LISTENING"
        not in window
    )

    assert (
        '"listening"'
        in controller
    )

    assert (
        '"hearing"'
        in controller
    )

    assert (
        "KumaBodyState.LISTENING"
        in controller
    )
