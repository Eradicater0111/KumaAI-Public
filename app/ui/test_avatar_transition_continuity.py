from __future__ import annotations

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).parent
QML = ROOT / "assets" / "kuma_mini" / "KumaMiniBodyR1.qml"
RUNTIME = ROOT / "avatar_runtime.py"
VISUAL = ROOT / "avatar_visual_mechanics.py"
CONTROLLER = ROOT / "body_controller.py"
FLOATING = ROOT / "floating_body.py"
VIEW = ROOT / "kuma_3d_view.py"
WINDOW = ROOT / "window.py"

TRANSITIONS = {
    "avatarMotionEnergy": (260, "Easing.InOutQuad"),
    "avatarExpressionIntensity": (220, "Easing.OutQuad"),
    "avatarGazeYaw": (320, "Easing.InOutQuad"),
    "avatarGazePitch": (320, "Easing.InOutQuad"),
}


def qml_source():
    return QML.read_text()


def compact_qml():
    return " ".join(qml_source().split())


def method_source(path, class_name, method_name):
    text = path.read_text()
    parsed = ast.parse(text, filename=str(path))
    cls = next(
        node
        for node in parsed.body
        if isinstance(node, ast.ClassDef)
        and node.name == class_name
    )
    method = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == method_name
    )
    return ast.get_source_segment(text, method) or ""


def behavior_block(property_name):
    text = qml_source()
    marker = f"Behavior on {property_name} {{"
    start = text.index(marker)

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

    return text[start:min(candidates)]


def test_transition_block_documents_safety_boundaries():
    text = qml_source()

    for required in (
        "TARGET VALUE != CURRENT INTERPOLATED VALUE",
        "INTERPOLATION != SEMANTIC STATE",
        "EASING != COGNITION",
        "ANIMATION TIME != AUTHORITY",
        "VISUAL CONTINUITY != EXECUTION",
        "BODY STATE REMAINS IMMEDIATE",
        "Only Avatar-1D renderer mechanics ease between target values.",
    ):
        assert required in text


@pytest.mark.parametrize(
    "property_name",
    tuple(TRANSITIONS),
)
def test_each_avatar_visual_property_has_one_behavior(property_name):
    assert (
        qml_source().count(
            f"Behavior on {property_name} {{"
        )
        == 1
    )


@pytest.mark.parametrize(
    ("property_name", "duration", "easing"),
    tuple(
        (
            name,
            values[0],
            values[1],
        )
        for name, values in TRANSITIONS.items()
    ),
)
def test_visual_behavior_duration_and_easing(
    property_name,
    duration,
    easing,
):
    compact = " ".join(
        behavior_block(
            property_name
        ).split()
    )

    assert f"duration: {duration}" in compact
    assert f"easing.type: {easing}" in compact
    assert compact.count("NumberAnimation {") == 1


def test_body_state_is_not_eased():
    assert "Behavior on bodyState" not in qml_source()


def test_phase_is_not_eased_by_behavior():
    assert "Behavior on phase" not in qml_source()


def test_phase_driver_remains_single_direct_animation():
    assert (
        qml_source().count(
            "NumberAnimation on phase {"
        )
        == 1
    )


def test_existing_curiosity_behaviors_remain():
    text = qml_source()

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


def test_existing_ear_behaviors_remain():
    text = qml_source()

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


def test_avatar_1e_adds_no_timer():
    assert qml_source().count("Timer {") == 5


def test_no_shadow_visual_properties_are_created():
    text = qml_source()

    for forbidden in (
        "renderedAvatarMotionEnergy",
        "renderedAvatarExpressionIntensity",
        "renderedAvatarGazeYaw",
        "renderedAvatarGazePitch",
        "targetAvatarMotionEnergy",
        "targetAvatarExpressionIntensity",
        "targetAvatarGazeYaw",
        "targetAvatarGazePitch",
    ):
        assert forbidden not in text


def test_avatar_1d_root_properties_remain_exact():
    text = qml_source()

    for required in (
        "property real avatarMotionEnergy: 0.0",
        "property real avatarExpressionIntensity: 0.0",
        "property real avatarGazeYaw: 0.0",
        "property real avatarGazePitch: 0.0",
    ):
        assert required in text


def test_avatar_1d_head_gaze_projection_remains_intact():
    compact = compact_qml()

    assert "pitch + root.avatarGazePitch" in compact
    assert "yaw + root.avatarGazeYaw" in compact


def test_avatar_1d_motion_projection_remains_intact():
    text = qml_source()

    assert "root.avatarMotionEnergy" in text
    assert "* 1.6" in text
    assert "* 0.9" in text


def test_avatar_1d_expression_projection_remains_intact():
    text = qml_source()

    assert "root.avatarExpressionIntensity" in text
    assert "* 1.5" in text
    assert "* 4.0" in text


def test_body_state_is_presented_before_visual_target_update():
    method = method_source(
        CONTROLLER,
        "KumaBodyController",
        "present_avatar_snapshot",
    )

    assert (
        method.index("self.body.set_state(")
        < method.index(
            "project_avatar_visual_parameters("
        )
    )


def test_controller_owns_no_animation_clock():
    method = method_source(
        CONTROLLER,
        "KumaBodyController",
        "present_avatar_snapshot",
    )

    for forbidden in (
        "QTimer",
        "threading",
        "sleep(",
        "while ",
        "NumberAnimation",
        "easing",
        "duration",
    ):
        assert forbidden not in method


def test_floating_body_owns_no_avatar_transition_loop():
    method = method_source(
        FLOATING,
        "KumaMiniBody",
        "set_avatar_visual_parameters",
    )

    for forbidden in (
        "QTimer",
        "while ",
        "sleep(",
        "lerp",
        "interpolate",
        "easing",
        "duration",
    ):
        assert forbidden not in method


def test_3d_view_remains_target_writer_only():
    method = method_source(
        VIEW,
        "Kuma3DView",
        "set_avatar_visual_parameters",
    )

    assert "root.setProperty(" in method

    for forbidden in (
        "QTimer",
        "while ",
        "sleep(",
        "lerp",
        "interpolate",
        "NumberAnimation",
        "Easing",
        "duration",
    ):
        assert forbidden not in method


def test_3d_view_still_writes_exact_four_targets():
    method = method_source(
        VIEW,
        "Kuma3DView",
        "set_avatar_visual_parameters",
    )

    for name in TRANSITIONS:
        assert method.count(f'"{name}"') == 1


def test_no_renderer_readback_path_is_added():
    method = method_source(
        VIEW,
        "Kuma3DView",
        "set_avatar_visual_parameters",
    )

    for forbidden in (
        "root.property(",
        "self.property(",
        "propertyChanged",
        "valueChanged",
    ):
        assert forbidden not in method


def test_avatar_runtime_has_no_transition_fields():
    text = RUNTIME.read_text()

    for forbidden in (
        "transition_duration",
        "rendered_gaze",
        "rendered_motion",
        "rendered_expression",
    ):
        assert forbidden not in text


def test_visual_mechanics_contract_has_no_transition_clock():
    text = VISUAL.read_text()

    for forbidden in (
        "QTimer",
        "threading",
        "asyncio",
        "time.sleep",
        "transition_duration",
    ):
        assert forbidden not in text


def test_window_has_no_avatar_1e_animation_logic():
    text = WINDOW.read_text()

    for forbidden in (
        "avatar_transition",
        "avatar_easing",
        "avatar_interpolation",
        "renderedAvatar",
    ):
        assert forbidden not in text


def test_qml_transition_layer_has_no_targeting_terms():
    text = qml_source()

    for forbidden in (
        "screenX",
        "screenY",
        "targetId",
        "elementId",
        "AXUI",
        "mouseX",
        "mouseY",
    ):
        assert forbidden not in text


def test_qml_transition_layer_has_no_authority_hook():
    text = qml_source()

    for forbidden in (
        "requestConfirmation",
        "permissionLevel",
        "executeCommand",
        "toolRegistry",
        "pendingSignals",
    ):
        assert forbidden not in text


def test_inspection_turntable_remains_independent():
    text = qml_source()

    assert "root.inspectionPitch" in text
    assert "root.inspectionYaw" in text

    assert (
        text.index("id: inspectionTurntable")
        < text.index("id: kumaRig")
        < text.index("id: headRig")
    )


def test_transition_durations_are_positive_and_bounded():
    for duration, _ in TRANSITIONS.values():
        assert 1 <= duration <= 500


def test_gaze_axes_share_duration_and_easing():
    assert (
        TRANSITIONS["avatarGazeYaw"]
        == TRANSITIONS["avatarGazePitch"]
    )


def test_expression_settles_faster_than_gaze():
    assert (
        TRANSITIONS["avatarExpressionIntensity"][0]
        < TRANSITIONS["avatarGazeYaw"][0]
    )


def test_motion_settles_faster_than_gaze():
    assert (
        TRANSITIONS["avatarMotionEnergy"][0]
        < TRANSITIONS["avatarGazeYaw"][0]
    )


def test_transition_layer_uses_no_secondary_animation_system():
    text = qml_source()

    for forbidden in (
        "SmoothedAnimation",
        "SpringAnimation",
        "PropertyAnimation",
        "SequentialAnimation",
        "ParallelAnimation",
        "RotationAnimation",
        "Vector3dAnimation",
    ):
        assert forbidden not in text
