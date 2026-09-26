from __future__ import annotations

import inspect
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agent.tool_result import ToolResult

from app.tools.computer_tools import (
    MAX_MOUSE_MOVE_DURATION_SECONDS,
    PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS,
    PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS,
    PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS,
    _revalidate_physical_vision_move_desktop_context,
    move_mouse_vision,
)

from app.vision.coordinates import (
    CoordinateMapper,
)

from app.vision.observation import (
    ScreenObservationError,
    ScreenObservationStore,
)

from app.vision.gui_target_verifier import (
    GUI_SEMANTIC_TARGET_ATTESTATIONS,
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
    current_screen_matches_attestation,
)


@pytest.fixture(
    autouse=True
)
def clear_target_attestation():

    GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()

    yield

    GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()


def make_store(
    *,
    max_age_seconds=30.0,
):
    return ScreenObservationStore(
        max_age_seconds=max_age_seconds,
    )


def create_observation(
    store,
    *,
    captured_at=None,
):
    if captured_at is None:
        captured_at = (
            time.monotonic()
        )

    return store.create(
        captured_at_monotonic=(
            captured_at
        ),
        capture_width=2940,
        capture_height=1912,
        vision_width=1800,
        vision_height=1171,
        native_width=1470,
        native_height=956,
        vision_scale=(
            1800 / 2940
        ),
        analysis=(
            "VISIBLE_TARGETS:\n"
            "- name: button\n"
            "  coordinate: (900, 585)"
        ),
    )


def issue_target(
    observation,
    *,
    x=900,
    y=585,
):

    result = (
        GuiTargetVerificationResult(
            status=(
                TARGET_STATUS_SATISFIED
            ),
            summary="Target matched.",
            evidence=(
                "Visible semantic target matched."
            ),
            observation_id=(
                observation.observation_id
            ),
            x=x,
            y=y,
            goal_sha256="1" * 64,
            image_sha256="2" * 64,
            target_region_sha256="3" * 64,
        )
    )

    return (
        GUI_SEMANTIC_TARGET_ATTESTATIONS.issue(
            result=result
        )
    )


def success_environment(
    store,
    *,
    desktop=(True, ""),
    pixels=(True, ""),
):

    return (
        patch(
            "app.vision.observation."
            "SCREEN_OBSERVATIONS",
            store,
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1470,
                956,
            ),
        ),
        patch(
            "app.tools.computer_tools."
            "_revalidate_physical_vision_move_desktop_context",
            return_value=desktop,
        ),
        patch(
            "app.vision.gui_target_verifier."
            "current_screen_matches_attestation",
            return_value=pixels,
        ),
        patch(
            "app.desktop.provenance."
            "SCREEN_DESKTOP_PROVENANCE.clear",
        ),
        patch(
            "app.tools.computer_tools."
            "move_mouse",
            return_value=(
                ToolResult.ok(
                    "move ok"
                )
            ),
        ),
    )


def test_valid_trusted_target_maps_and_moves():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    issue_target(
        observation
    )

    mapper = CoordinateMapper(
        vision_width=(
            observation.vision_width
        ),
        vision_height=(
            observation.vision_height
        ),
        screen_width=(
            observation.native_width
        ),
        screen_height=(
            observation.native_height
        ),
    )

    expected = (
        mapper.vision_to_screen(
            900,
            585,
        )
    )

    (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch,
    ) = success_environment(
        store
    )

    with (
        store_patch,
        size_patch,
        desktop_patch as desktop_gate,
        pixels_patch as pixel_gate,
        provenance_patch as provenance_clear,
        move_patch as move,
    ):

        result = move_mouse_vision(
            900,
            585,
            observation.observation_id,
            duration=0.2,
        )

    assert result.success, result.error

    move.assert_called_once_with(
        expected[0],
        expected[1],
        duration=0.2,
    )

    desktop_gate.assert_called_once_with(
        observation.observation_id
    )

    pixel_gate.assert_called_once()

    provenance_clear.assert_called_once()

    with pytest.raises(
        ScreenObservationError
    ):
        store.peek(
            observation.observation_id
        )

    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
        )


def test_missing_target_attestation_never_moves():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch,
    ) = success_environment(
        store
    )

    with (
        store_patch,
        size_patch,
        desktop_patch as desktop_gate,
        pixels_patch as pixel_gate,
        provenance_patch,
        move_patch as move,
    ):

        result = move_mouse_vision(
            900,
            585,
            observation.observation_id,
        )

    assert not result.success

    assert (
        "attestation"
        in result.error.lower()
    )

    desktop_gate.assert_not_called()
    pixel_gate.assert_not_called()
    move.assert_not_called()


def test_wrong_target_claim_consumes_attestation():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    issue_target(
        observation,
        x=900,
        y=585,
    )

    (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch,
    ) = success_environment(
        store
    )

    with (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch as move,
    ):

        result = move_mouse_vision(
            901,
            585,
            observation.observation_id,
        )

    assert not result.success
    move.assert_not_called()

    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
        )


def test_duration_is_action_state_not_target_state():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    issued = issue_target(
        observation
    )

    with patch(
        "app.vision.observation."
        "SCREEN_OBSERVATIONS",
        store,
    ), patch(
        "app.tools.computer_tools."
        "move_mouse",
    ) as move:

        result = move_mouse_vision(
            900,
            585,
            observation.observation_id,
            duration=(
                MAX_MOUSE_MOVE_DURATION_SECONDS
                + 0.01
            ),
        )

    assert not result.success
    move.assert_not_called()

    # Invalid movement duration fails before target-proof
    # consumption. The target receipt itself contains no
    # duration authority.
    claimed = (
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
        )
    )

    assert claimed is issued


def test_desktop_mismatch_blocks_after_consuming_target():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    issue_target(
        observation
    )

    (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch,
    ) = success_environment(
        store,
        desktop=(
            False,
            "desktop changed",
        ),
    )

    with (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch as pixels,
        provenance_patch,
        move_patch as move,
    ):

        result = move_mouse_vision(
            900,
            585,
            observation.observation_id,
        )

    assert not result.success
    assert "desktop changed" in result.error

    pixels.assert_not_called()
    move.assert_not_called()

    with pytest.raises(
        ValueError
    ):
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
        )


def test_target_region_change_blocks_move():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    issue_target(
        observation
    )

    (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch,
    ) = success_environment(
        store,
        pixels=(
            False,
            "target pixels changed",
        ),
    )

    with (
        store_patch,
        size_patch,
        desktop_patch,
        pixels_patch,
        provenance_patch,
        move_patch as move,
    ):

        result = move_mouse_vision(
            900,
            585,
            observation.observation_id,
        )

    assert not result.success

    assert (
        "target pixels changed"
        in result.error
    )

    move.assert_not_called()


def test_display_geometry_change_invalidates_target_evidence():

    store = make_store()

    observation = (
        create_observation(
            store
        )
    )

    issue_target(
        observation
    )

    with (
        patch(
            "app.vision.observation."
            "SCREEN_OBSERVATIONS",
            store,
        ),
        patch(
            "app.tools.computer_tools."
            "pyautogui.size",
            return_value=(
                1400,
                900,
            ),
        ),
        patch(
            "app.desktop.provenance."
            "SCREEN_DESKTOP_PROVENANCE.clear",
        ),
        patch(
            "app.tools.computer_tools."
            "move_mouse",
        ) as move,
    ):

        result = move_mouse_vision(
            900,
            585,
            observation.observation_id,
        )

    assert not result.success
    move.assert_not_called()

    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id=(
                observation.observation_id
            ),
            x=900,
            y=585,
        )


@pytest.mark.parametrize(
    "x,y",
    [
        (True, 585),
        (900, False),
        ("900", 585),
        (900, "585"),
    ],
)
def test_coercive_coordinates_are_rejected(
    x,
    y,
):

    with patch(
        "app.tools.computer_tools."
        "move_mouse",
    ) as move:

        result = move_mouse_vision(
            x,
            y,
            "obs-1",
        )

    assert not result.success
    move.assert_not_called()


def provenance():
    return SimpleNamespace(
        binding=object(),
        desktop_before=object(),
        desktop_after=object(),
    )


def test_move_desktop_guard_missing_provenance_fails_before_collection():

    with patch(
        "app.desktop.provenance."
        "SCREEN_DESKTOP_PROVENANCE.get",
        return_value=None,
    ), patch(
        "app.desktop.runtime."
        "collect_desktop_context",
    ) as collect:

        allowed, reason = (
            _revalidate_physical_vision_move_desktop_context(
                "obs-1"
            )
        )

    assert not allowed
    assert "provenance is unavailable" in reason
    collect.assert_not_called()


def test_move_desktop_guard_matched_uses_bounded_collection():

    source = provenance()
    current = object()

    matched = SimpleNamespace(
        matched=True,
        status="matched",
        diagnostics=(),
    )

    with patch(
        "app.desktop.provenance."
        "SCREEN_DESKTOP_PROVENANCE.get",
        return_value=source,
    ), patch(
        "app.desktop.runtime."
        "collect_desktop_context",
        return_value=current,
    ) as collect, patch(
        "app.desktop.revalidation."
        "revalidate_desktop_context",
        return_value=matched,
    ) as revalidate:

        allowed, reason = (
            _revalidate_physical_vision_move_desktop_context(
                "obs-1"
            )
        )

    assert allowed
    assert reason == ""

    collect.assert_called_once_with(
        timeout_seconds=(
            PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS
        ),
        max_windows=(
            PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS
        ),
    )

    revalidate.assert_called_once_with(
        source.binding,
        source.desktop_before,
        source.desktop_after,
        current,
        max_current_age_seconds=(
            PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS
        ),
    )


def test_target_region_continuity_contract_has_no_click_modifiers():

    source = inspect.getsource(
        current_screen_matches_attestation
    )

    assert ".button" not in source
    assert ".clicks" not in source
