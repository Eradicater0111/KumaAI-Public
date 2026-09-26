from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
import inspect
from pathlib import Path

import pytest

from app.ui.avatar_runtime import (
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
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
VISUAL = ROOT / "avatar_visual_mechanics.py"
FLOATING = ROOT / "floating_body.py"
VIEW = ROOT / "kuma_3d_view.py"
QML = ROOT / "assets" / "kuma_mini" / "KumaMiniBodyR1.qml"


class FakeVisualBody:
    def __init__(self):
        self.state_calls = []
        self.visual_calls = []

    def set_state(self, state):
        self.state_calls.append(state)

    def set_avatar_visual_parameters(self, parameters):
        self.visual_calls.append(parameters)
        return True


class FakeLegacyBody:
    def __init__(self):
        self.state_calls = []

    def set_state(self, state):
        self.state_calls.append(state)


def visual_source():
    return VISUAL.read_text()


def floating_source():
    return FLOATING.read_text()


def view_source():
    return VIEW.read_text()


def qml_source():
    return QML.read_text()


def imports_for(text):
    parsed = ast.parse(text)
    result = set()

    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            result.update(item.name for item in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)

    return result


def test_visual_authority_is_none():
    assert AVATAR_VISUAL_AUTHORITY_NONE == "NONE"


def test_visual_parameter_fields_are_exact():
    assert tuple(
        item.name
        for item in fields(AvatarVisualParameters)
    ) == (
        "motion_energy",
        "expression_intensity",
        "gaze_yaw_degrees",
        "gaze_pitch_degrees",
        "authority",
    )


def test_visual_authority_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(AvatarVisualParameters).parameters
    )


def test_visual_parameters_are_frozen():
    item = AvatarVisualParameters()

    with pytest.raises(FrozenInstanceError):
        item.motion_energy = 1.0


def test_visual_parameters_are_slotted():
    assert not hasattr(AvatarVisualParameters(), "__dict__")


def test_default_visual_parameters_are_neutral():
    item = AvatarVisualParameters()

    assert item.motion_energy == 0.0
    assert item.expression_intensity == 0.0
    assert item.gaze_yaw_degrees == 0.0
    assert item.gaze_pitch_degrees == 0.0
    assert item.authority == "NONE"


@pytest.mark.parametrize("value", (0, 0.25, 0.5, 0.75, 1))
def test_motion_energy_accepts_unit_interval(value):
    assert (
        AvatarVisualParameters(
            motion_energy=value
        ).motion_energy
        == float(value)
    )


@pytest.mark.parametrize("value", (0, 0.25, 0.5, 0.75, 1))
def test_expression_intensity_accepts_unit_interval(value):
    assert (
        AvatarVisualParameters(
            expression_intensity=value
        ).expression_intensity
        == float(value)
    )


@pytest.mark.parametrize(
    "value",
    (-0.01, 1.01, float("inf"), float("-inf"), float("nan")),
)
def test_motion_energy_rejects_out_of_bounds(value):
    with pytest.raises(ValueError):
        AvatarVisualParameters(motion_energy=value)


@pytest.mark.parametrize(
    "value",
    (-0.01, 1.01, float("inf"), float("-inf"), float("nan")),
)
def test_expression_intensity_rejects_out_of_bounds(value):
    with pytest.raises(ValueError):
        AvatarVisualParameters(expression_intensity=value)


@pytest.mark.parametrize("value", (True, False, "0.5", None, object()))
def test_motion_energy_rejects_non_numbers(value):
    with pytest.raises(TypeError):
        AvatarVisualParameters(motion_energy=value)


@pytest.mark.parametrize("value", (True, False, "0.5", None, object()))
def test_expression_intensity_rejects_non_numbers(value):
    with pytest.raises(TypeError):
        AvatarVisualParameters(expression_intensity=value)


def test_gaze_limits_are_small_renderer_angles():
    assert AVATAR_GAZE_YAW_LIMIT_DEGREES == 8.0
    assert AVATAR_GAZE_PITCH_LIMIT_DEGREES == 3.0


@pytest.mark.parametrize("value", (-8, -4, 0, 4, 8))
def test_yaw_accepts_bounded_angles(value):
    assert (
        AvatarVisualParameters(
            gaze_yaw_degrees=value
        ).gaze_yaw_degrees
        == float(value)
    )


@pytest.mark.parametrize("value", (-3, -1, 0, 1, 3))
def test_pitch_accepts_bounded_angles(value):
    assert (
        AvatarVisualParameters(
            gaze_pitch_degrees=value
        ).gaze_pitch_degrees
        == float(value)
    )


@pytest.mark.parametrize("value", (-8.01, 8.01, float("inf"), float("nan")))
def test_yaw_rejects_outside_limit(value):
    with pytest.raises(ValueError):
        AvatarVisualParameters(gaze_yaw_degrees=value)


@pytest.mark.parametrize("value", (-3.01, 3.01, float("inf"), float("nan")))
def test_pitch_rejects_outside_limit(value):
    with pytest.raises(ValueError):
        AvatarVisualParameters(gaze_pitch_degrees=value)


@pytest.mark.parametrize(
    ("gaze", "yaw", "pitch"),
    (
        (AvatarGaze.FORWARD, 0.0, 0.0),
        (AvatarGaze.USER, 0.0, -1.5),
        (AvatarGaze.TARGET, 6.0, -1.0),
        (AvatarGaze.AWAY, -8.0, 2.0),
    ),
)
def test_semantic_gaze_maps_to_fixed_pose(gaze, yaw, pitch):
    item = project_avatar_visual_parameters(
        AvatarSnapshot(gaze=gaze)
    )

    assert item.gaze_yaw_degrees == yaw
    assert item.gaze_pitch_degrees == pitch


def test_projection_copies_motion_and_expression():
    item = project_avatar_visual_parameters(
        AvatarSnapshot(
            mode=AvatarMode.THINKING,
            expression=AvatarExpression.FOCUSED,
            expression_intensity=0.65,
            gaze=AvatarGaze.USER,
            motion_energy=0.45,
        )
    )

    assert item.motion_energy == 0.45
    assert item.expression_intensity == 0.65
    assert item.authority == "NONE"


def test_projection_rejects_non_snapshot():
    with pytest.raises(TypeError, match="AvatarSnapshot"):
        project_avatar_visual_parameters(object())


def test_target_gaze_is_fixed_pose_not_target_identity():
    target = project_avatar_visual_parameters(
        AvatarSnapshot(gaze=AvatarGaze.TARGET)
    )

    assert target == AvatarVisualParameters(
        gaze_yaw_degrees=6.0,
        gaze_pitch_degrees=-1.0,
    )


def test_projection_signature_accepts_snapshot_only():
    assert tuple(
        inspect.signature(
            project_avatar_visual_parameters
        ).parameters
    ) == ("snapshot",)


def test_visual_module_has_no_coordinate_or_identity_inputs():
    parsed = ast.parse(
        visual_source()
    )

    identifiers = set()

    for node in ast.walk(
        parsed
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
        "native_point",
        "pointer",
        "accessibility",
        "AXUI",
        "target_id",
        "element_id",
    ):
        assert (
            forbidden
            not in identifiers
        ), forbidden


def test_visual_module_import_surface_is_pure():
    assert imports_for(visual_source()) == {
        "__future__",
        "dataclasses",
        "math",
        "app.ui.avatar_runtime",
    }


def test_visual_module_has_no_agent_tool_voice_memory_or_qt():
    loaded = imports_for(visual_source())

    assert not any(
        name.startswith(
            (
                "app.agent",
                "app.tools",
                "app.voice",
                "app.memory",
                "PySide",
                "PyQt",
            )
        )
        for name in loaded
    )


def test_visual_module_has_no_background_runtime():
    loaded = imports_for(visual_source())

    for forbidden in (
        "threading",
        "asyncio",
        "subprocess",
        "socket",
        "requests",
        "httpx",
    ):
        assert forbidden not in loaded


def test_visual_module_has_no_while_or_async():
    parsed = ast.parse(visual_source())

    assert not any(
        isinstance(
            node,
            (
                ast.While,
                ast.AsyncFunctionDef,
            ),
        )
        for node in ast.walk(parsed)
    )


def test_visual_module_documents_boundaries():
    text = visual_source()

    for required in (
        "VISUAL GAZE != DESKTOP TARGET",
        "GAZE POSE != TARGET IDENTITY",
        "MOTION ENERGY != COGNITIVE ENERGY",
        "EXPRESSION INTENSITY != FACT CONFIDENCE",
        "VISUAL PARAMETERS != AUTHORITY",
        "RENDER MECHANICS != EXECUTION",
    ):
        assert required in text


def test_controller_forwards_state_and_visual_parameters():
    body = FakeVisualBody()
    controller = KumaBodyController(body)

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=AvatarMode.THINKING,
            expression=AvatarExpression.FOCUSED,
            expression_intensity=0.65,
            gaze=AvatarGaze.TARGET,
            motion_energy=0.45,
        )
    )

    assert body.state_calls == [KumaBodyState.THINKING]
    assert len(body.visual_calls) == 1

    visual = body.visual_calls[0]

    assert isinstance(visual, AvatarVisualParameters)
    assert visual.motion_energy == 0.45
    assert visual.expression_intensity == 0.65
    assert visual.gaze_yaw_degrees == 6.0
    assert visual.gaze_pitch_degrees == -1.0
    assert visual.authority == "NONE"


def test_controller_remains_compatible_with_legacy_body():
    body = FakeLegacyBody()
    controller = KumaBodyController(body)

    controller.present_avatar_snapshot(
        AvatarSnapshot(
            mode=AvatarMode.SUCCESS,
            expression=AvatarExpression.HAPPY,
            expression_intensity=0.8,
            motion_energy=0.5,
        )
    )

    assert body.state_calls == [KumaBodyState.HAPPY]


def test_controller_uses_optional_visual_sink():
    text = inspect.getsource(
        KumaBodyController.present_avatar_snapshot
    )

    assert "set_avatar_visual_parameters" in text
    assert "callable(" in text


def test_controller_does_not_read_renderer_state_back():
    text = inspect.getsource(
        KumaBodyController.present_avatar_snapshot
    )

    for forbidden in (
        "self.body.state",
        "self.body._state",
        "state_changed",
        "rootObject(",
        ".property(",
    ):
        assert forbidden not in text


def test_floating_body_exposes_visual_sink():
    assert (
        "def set_avatar_visual_parameters("
        in floating_source()
    )


def test_floating_body_visual_sink_forwards_to_3d_only():
    text = floating_source()
    start = text.index(
        "    def set_avatar_visual_parameters("
    )
    end = text.index(
        "    # =====================================================\n"
        "    # POSITION",
        start,
    )
    method = text[start:end]

    assert (
        "self._three_d_view"
        in method
    )

    assert (
        ".set_avatar_visual_parameters("
        in method
    )

    for forbidden in (
        "request_confirmation",
        "executor",
        "emit_status",
        "runtime.run",
        "speech",
    ):
        assert forbidden not in method


def test_3d_view_exposes_visual_bridge():
    assert (
        "def set_avatar_visual_parameters("
        in view_source()
    )


def test_3d_view_writes_exact_qml_properties():
    text = view_source()

    for name in (
        "avatarMotionEnergy",
        "avatarExpressionIntensity",
        "avatarGazeYaw",
        "avatarGazePitch",
    ):
        assert f'"{name}"' in text


def test_3d_view_never_reads_visual_properties_back():
    text = view_source()
    start = text.index(
        "    def set_avatar_visual_parameters("
    )
    end = text.index(
        "    def set_body_state(",
        start,
    )
    method = text[start:end]

    assert "root.setProperty(" in method
    assert "root.property(" not in method
    assert "request_confirmation" not in method
    assert "executor" not in method


def test_active_qml_declares_avatar_visual_properties():
    text = qml_source()

    for required in (
        "property real avatarMotionEnergy: 0.0",
        "property real avatarExpressionIntensity: 0.0",
        "property real avatarGazeYaw: 0.0",
        "property real avatarGazePitch: 0.0",
    ):
        assert required in text


def test_qml_adds_semantic_gaze_to_head_pose():
    text = qml_source()

    normalized = " ".join(
        text.split()
    )

    assert (
        "pitch + root.avatarGazePitch"
        in normalized
    )

    assert (
        "yaw + root.avatarGazeYaw"
        in normalized
    )


def test_qml_motion_energy_controls_extra_bob_and_roll():
    text = qml_source()

    assert "root.avatarMotionEnergy" in text
    assert "* 1.6" in text
    assert "* 0.9" in text


def test_qml_expression_intensity_controls_existing_motion():
    text = qml_source()

    assert "root.avatarExpressionIntensity" in text
    assert "* 1.5" in text
    assert "* 4.0" in text


def test_qml_defaults_preserve_legacy_behavior():
    text = qml_source()

    assert "property real avatarMotionEnergy: 0.0" in text
    assert "property real avatarExpressionIntensity: 0.0" in text
    assert "property real avatarGazeYaw: 0.0" in text
    assert "property real avatarGazePitch: 0.0" in text


def test_inspection_turntable_remains_separate():
    text = qml_source()

    assert "root.inspectionPitch" in text
    assert "root.inspectionYaw" in text
    assert text.index("id: inspectionTurntable") < text.index("id: headRig")


def test_visual_mechanics_do_not_expand_avatar_1a_contract():
    runtime = (ROOT / "avatar_runtime.py").read_text()

    assert "AvatarVisualParameters" not in runtime
    assert "gaze_yaw_degrees" not in runtime
    assert "gaze_pitch_degrees" not in runtime


def test_visual_mechanics_do_not_expand_avatar_1b_projection():
    adapter = (ROOT / "avatar_renderer_adapter.py").read_text()

    assert "AvatarVisualParameters" not in adapter
    assert "avatarGazeYaw" not in adapter


@pytest.mark.parametrize("gaze", tuple(AvatarGaze))
def test_all_gaze_poses_remain_within_renderer_limits(gaze):
    item = project_avatar_visual_parameters(
        AvatarSnapshot(gaze=gaze)
    )

    assert (
        abs(item.gaze_yaw_degrees)
        <= AVATAR_GAZE_YAW_LIMIT_DEGREES
    )
    assert (
        abs(item.gaze_pitch_degrees)
        <= AVATAR_GAZE_PITCH_LIMIT_DEGREES
    )
