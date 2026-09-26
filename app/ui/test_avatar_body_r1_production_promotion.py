from pathlib import Path


ROOT = Path(__file__).parent

VIEW = (
    ROOT
    / "kuma_3d_view.py"
)

BODY_R1 = (
    ROOT
    / "assets"
    / "kuma_mini"
    / "KumaMiniBodyR1.qml"
)

REFERENCE = (
    ROOT
    / "assets"
    / "kuma_mini"
    / "KumaMiniReferenceRig.qml"
)


def source():
    return VIEW.read_text()


def test_body_r1_production_rig_exists():
    assert BODY_R1.is_file()


def test_legacy_reference_rig_remains_available_for_explicit_fallback():
    assert REFERENCE.is_file()


def test_body_r1_is_normal_production_default():
    text = source()

    assert (
        '"KumaMiniBodyR1.qml"'
        in text
    )

    assert (
        'rig_label = "production Body R1"'
        in text
    )


def test_reference_rig_requires_explicit_reference_fallback():
    text = source()

    assert (
        '"KUMA_BODY_REFERENCE"'
        in text
    )

    assert (
        '"KumaMiniReferenceRig.qml"'
        in text
    )

    assert (
        'rig_label = "reference fallback rig"'
        in text
    )


def test_procedural_override_remains_explicit():
    text = source()

    assert (
        '"KUMA_BODY_PROCEDURAL"'
        in text
    )

    assert (
        '"procedural/KumaMiniViewport.qml"'
        in text
    )


def test_obsolete_body_dev_selector_is_removed_from_production_view():
    text = source()

    for forbidden in (
        "KUMA_BODY_DEV",
        "body_dev_enabled",
        "KumaMiniBodyDevRig.qml",
        "KUMA_BODY_YAW",
        "KUMA_BODY_PITCH",
    ):
        assert forbidden not in text


def test_production_rig_selection_is_presentation_only():
    text = source()

    for marker in (
        "PRODUCTION BODY != AUTHORITY",
        "RIG SELECTION != INVOCATION",
        "VISUAL FALLBACK != CONTROL",
    ):
        assert marker in text

    for forbidden in (
        "RuntimeInvocation",
        "KumaRuntimeInvocationDispatcher",
        "admit_realtime_observation",
        "request_confirmation",
        "execute_command",
        "ActionExecutor",
    ):
        assert forbidden not in text


def test_production_view_does_not_write_inspection_orientation():
    text = source()

    for forbidden in (
        '"inspectionYaw"',
        '"inspectionPitch"',
    ):
        assert forbidden not in text


def test_body_r1_frozen_contract_markers_survive_promotion():
    text = BODY_R1.read_text()

    for marker in (
        "BODY COMPLETION R1 — WHOLE-BODY STATE POSE",
        "BODY COMPLETION R1 — FINAL VISUAL POLISH",
        "VISUAL STATE != AUTHORITY",
        "ANIMATION != COGNITION",
        "POSE != INVOCATION",
        "SILHOUETTE != AUTHORITY",
        "VISUAL POLISH != EXECUTION",
    ):
        assert marker in text
