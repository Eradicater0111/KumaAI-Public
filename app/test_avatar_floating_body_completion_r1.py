from __future__ import annotations

"""
KUMA FLOATING BODY COMPLETION R1 regression.

This phase is presentation-only.

VISUAL STATE != AUTHORITY
ANIMATION != COGNITION
POSE != INVOCATION
SYNCHRONIZATION != SCHEDULER
BODY STATE REMAINS IMMEDIATE
"""

from pathlib import Path
import re


RIG = Path(
    "app/ui/assets/kuma_mini/KumaMiniBodyR1.qml"
)


def _source() -> str:
    return RIG.read_text()


def test_body_rig_exists():
    assert RIG.is_file()


def test_body_completion_r1_marker_exists():
    assert (
        "BODY COMPLETION R1 — WHOLE-BODY STATE POSE"
        in _source()
    )


def test_body_completion_preserves_visual_authority_boundary():
    source = _source()

    for marker in (
        "VISUAL STATE != AUTHORITY",
        "ANIMATION != COGNITION",
        "POSE != INVOCATION",
        "BODY STATE REMAINS IMMEDIATE",
    ):
        assert marker in source


def test_canonical_body_parts_remain_loaded():
    source = _source()

    expected = (
        "torso.glb",
        "body_bottom.glb",
        "chest_badge.glb",
        "rear_panel.glb",
        "rear_light.glb",
        "neck.glb",
        "arm_left.glb",
        "arm_right.glb",
        "head_shell.glb",
        "ear_left.glb",
        "ear_right.glb",
        "pod_left.glb",
        "pod_right.glb",
    )

    for name in expected:
        assert (
            f'models/body_dev/parts/{name}'
            in source
        )


def test_every_referenced_body_glb_exists():
    source = _source()

    refs = sorted(
        set(
            re.findall(
                r'"(models/body_dev/parts/[^"]+\.glb)"',
                source,
            )
        )
    )

    assert refs

    for ref in refs:
        assert (
            RIG.parent / ref
        ).is_file()


def test_whole_body_pose_handles_core_states():
    source = _source()

    marker = (
        "BODY COMPLETION R1 — WHOLE-BODY STATE POSE"
    )

    start = source.index(marker)
    end = source.index(
        "// =============================================\n"
        "            // BODY-3A1 CANONICAL FLOATING BODY",
        start,
    )

    section = source[start:end]

    for state in (
        '"idle"',
        '"happy"',
        '"listening"',
        '"thinking"',
        '"observing"',
        '"alert"',
        '"sleep"',
    ):
        assert state in section


def test_head_pose_handles_core_states():
    source = _source()

    start = source.index(
        "id: headRig"
    )

    end = source.index(
        "// -----------------------------------------\n"
        "                // SHELL",
        start,
    )

    section = source[start:end]

    for state in (
        '"thinking"',
        '"observing"',
        '"listening"',
        '"alert"',
        '"focused"',
        '"happy"',
        '"sleep"',
        '"idle"',
    ):
        assert state in section


def test_arm_poses_handle_listening_thinking_observing_alert_sleep():
    source = _source()

    for arm_id in (
        "id: leftArm",
        "id: rightArm",
    ):
        start = source.index(
            arm_id
        )

        end = source.index(
            "RuntimeLoader {",
            start,
        )

        section = source[start:end]

        for state in (
            '"happy"',
            '"alert"',
            '"listening"',
            '"thinking"',
            '"observing"',
            '"sleep"',
        ):
            assert state in section


def test_ear_poses_handle_listening_alert_sleep_thinking_observing():
    source = _source()

    for ear_id in (
        "id: leftEar",
        "id: rightEar",
    ):
        start = source.index(
            ear_id
        )

        end = source.index(
            "RuntimeLoader {",
            start,
        )

        section = source[start:end]

        for state in (
            '"listening"',
            '"alert"',
            '"sleep"',
            '"thinking"',
            '"observing"',
        ):
            assert state in section


def test_observing_ears_remain_animated_by_phase():
    source = _source()

    assert (
        "root.phase * 1.15"
        in source
    )


def test_pose_layer_does_not_add_runtime_execution_symbols():
    source = _source()

    for forbidden in (
        "RuntimeInvocation",
        "KumaRuntimeInvocationDispatcher",
        "admit_realtime_observation",
        "pending_signals",
        "drain_signals",
        "ActionExecutor",
        "execute_command",
        "request_confirmation",
        "QThread",
        "create_task",
    ):
        assert forbidden not in source


def test_inspection_turntable_remains_present():
    source = _source()

    assert "id: inspectionTurntable" in source
    assert "root.inspectionPitch" in source
    assert "root.inspectionYaw" in source


def test_live_digital_visor_remains_head_attached():
    source = _source()

    head_start = source.index(
        "id: headRig"
    )

    face_start = source.index(
        "id: digitalFaceDisplay"
    )

    assert face_start > head_start


def test_physical_legacy_eyes_remain_hidden():
    source = _source()

    for eye_id in (
        "id: leftEye",
        "id: rightEye",
    ):
        start = source.index(
            eye_id
        )

        section = source[
            start:start + 220
        ]

        assert "visible: false" in section


def test_body_completion_does_not_duplicate_glb_references():
    source = _source()

    refs = re.findall(
        r'"models/body_dev/parts/([^"]+\.glb)"',
        source,
    )

    assert len(refs) == len(
        set(refs)
    )


def test_final_visual_polish_marker_exists():
    assert (
        "BODY COMPLETION R1 — FINAL VISUAL POLISH"
        in _source()
    )


def test_final_visual_polish_preserves_authority_boundary():
    source = _source()

    for marker in (
        "SILHOUETTE != AUTHORITY",
        "PROPORTION != COGNITION",
        "VISUAL POLISH != EXECUTION",
    ):
        assert marker in source


def test_head_has_final_body_clearance():
    source = _source()

    start = source.index(
        "id: headRig"
    )

    section = source[
        start:start + 220
    ]

    assert (
        "0,\n"
        "                        27,\n"
        "                        0"
        in section
    )


def test_final_ear_scale_is_integrated_not_horn_dominant():
    source = _source()

    for ear_id in (
        "id: leftEar\n",
        "id: rightEar\n",
    ):
        start = source.index(
            ear_id
        )

        section = source[
            start:start + 520
        ]

        assert "1.05" in section
        assert "1.12" not in section


def test_final_side_pods_are_reduced():
    source = _source()

    pod_section = source[
        source.index(
            "// SIDE PODS"
        ):
        source.index(
            "// EXPRESSIVE EYES"
        )
    ]

    assert "0.86" in pod_section
    assert "0.82" in pod_section
    assert "0.92" not in pod_section


def test_final_visor_is_seated_closer_to_shell():
    source = _source()

    start = source.index(
        "id: digitalFaceDisplay"
    )

    section = source[
        start:start + 320
    ]

    assert "54.5" in section
    assert "56.5" not in section


def test_final_arm_spacing_reads_as_independent_limbs():
    source = _source()

    left_start = source.index(
        "id: leftArm"
    )

    right_start = source.index(
        "id: rightArm"
    )

    left = source[
        left_start:right_start
    ]

    right = source[
        right_start:
        source.index(
            "// =============================================\n"
            "            // HEAD RIG",
            right_start,
        )
    ]

    assert "-57" in left
    assert "57" in right


def test_final_thinking_pose_is_refined():
    source = _source()

    assert "pitch = 1.3" in source
    assert "roll = -0.8" in source
    assert "3.3" in source
    assert "-3.8" in source
