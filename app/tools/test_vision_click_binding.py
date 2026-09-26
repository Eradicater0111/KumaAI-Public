from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.kuma_agent import KumaAgent
from app.tools.computer_tools import (
    PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS,
    PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS,
    PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS,
    _revalidate_physical_vision_click_desktop_context,
    click_vision,
)
from app.vision.coordinates import CoordinateMapper
from app.vision.observation import (
    ScreenObservationError,
    ScreenObservationStore,
)

from app.vision.gui_target_verifier import (
    GUI_TARGET_ATTESTATIONS,
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
)


class TestVisionClickBinding(
    unittest.TestCase
):

    def setUp(
        self,
    ):
        GUI_TARGET_ATTESTATIONS.clear()

    def tearDown(
        self,
    ):
        GUI_TARGET_ATTESTATIONS.clear()

    def issue_target_attestation(
        self,
        *,
        observation,
        x,
        y,
        button="left",
        clicks=1,
    ):
        result = GuiTargetVerificationResult(
            status=TARGET_STATUS_SATISFIED,
            summary="Target matched.",
            evidence="Test semantic evidence.",
            observation_id=(
                observation.observation_id
            ),
            x=x,
            y=y,
            goal_sha256="test-goal-digest",
            image_sha256="test-image-digest",
            target_region_sha256="test-target-region-digest",
        )

        return GUI_TARGET_ATTESTATIONS.issue(
            result=result,
            button=button,
            clicks=clicks,
        )

    def make_store(
        self,
        *,
        max_age_seconds=30.0,
    ):
        return ScreenObservationStore(
            max_age_seconds=max_age_seconds,
        )

    def create_observation(
        self,
        store,
        *,
        captured_at=None,
    ):
        if captured_at is None:
            captured_at = time.monotonic()

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

    def test_valid_observation_maps_and_clicks_once(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
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

        expected_x, expected_y = (
            mapper.vision_to_screen(
                900,
                585,
            )
        )

        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.tools.computer_tools."
                "_revalidate_physical_vision_click_desktop_context",
                return_value=(
                    True,
                    "",
                ),
            ),
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
                return_value=(
                    True,
                    "",
                ),
            ),
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.clear",
            ) as provenance_clear,
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            from app.agent.tool_result import ToolResult

            click_mock.return_value = (
                ToolResult.ok(
                    "clicked"
                )
            )

            result = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertTrue(
            result.success,
            result.error,
        )

        click_mock.assert_called_once_with(
            expected_x,
            expected_y,
            button="left",
            clicks=1,
        )
        provenance_clear.assert_called_once_with()

        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                observation.observation_id
            )

    def test_replay_of_consumed_observation_fails(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )

        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.tools.computer_tools."
                "_revalidate_physical_vision_click_desktop_context",
                return_value=(
                    True,
                    "",
                ),
            ),
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
                return_value=(
                    True,
                    "",
                ),
            ),
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            from app.agent.tool_result import ToolResult

            click_mock.return_value = (
                ToolResult.ok(
                    "clicked"
                )
            )

            first = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

            second = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertTrue(
            first.success
        )

        self.assertFalse(
            second.success
        )

        self.assertEqual(
            click_mock.call_count,
            1,
        )

    def test_unknown_observation_fails_without_click(
        self
    ):
        store = self.make_store()

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            result = click_vision(
                x=10,
                y=10,
                observation_id=(
                    "unknown"
                ),
            )

        self.assertFalse(
            result.success
        )

        click_mock.assert_not_called()

    def test_stale_observation_fails_without_click(
        self
    ):
        store = self.make_store(
            max_age_seconds=1,
        )

        observation = self.create_observation(
            store,
            captured_at=(
                time.monotonic()
                - 5
            ),
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            result = click_vision(
                x=10,
                y=10,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

        click_mock.assert_not_called()

    def test_changed_native_geometry_fails_and_invalidates_observation(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1400,
                    900,
                ),
            ),
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            result = click_vision(
                x=100,
                y=100,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

        click_mock.assert_not_called()

        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                observation.observation_id
            )

    def test_out_of_bounds_coordinate_fails_without_consuming_observation(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            result = click_vision(
                x=1800,
                y=100,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

        click_mock.assert_not_called()

        self.assertIs(
            store.peek(
                observation.observation_id
            ),
            observation,
        )

    def test_invalid_button_fails_without_consuming_observation(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )

        result = click_vision(
            x=100,
            y=100,
            observation_id=(
                observation.observation_id
            ),
            button="sideways",
        )

        self.assertFalse(
            result.success
        )

        self.assertIs(
            store.peek(
                observation.observation_id
            ),
            observation,
        )

    def test_click_count_is_bounded(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )

        with patch(
            "app.vision.observation.SCREEN_OBSERVATIONS",
            store,
        ):
            result = click_vision(
                x=100,
                y=100,
                observation_id=(
                    observation.observation_id
                ),
                clicks=3,
            )

        self.assertFalse(
            result.success
        )

    def test_non_integer_coordinates_fail_closed(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )

        with patch(
            "app.vision.observation.SCREEN_OBSERVATIONS",
            store,
        ):
            result = click_vision(
                x=10.5,
                y=20,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

    def test_missing_semantic_attestation_rejects_physical_click(
        self
    ):
        store = self.make_store()

        observation = self.create_observation(
            store
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):

            result = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "semantic target attestation",
            result.error,
        )

        click_mock.assert_not_called()

        # Missing semantic authority must not consume the
        # trusted observation.
        self.assertIs(
            store.peek(
                observation.observation_id
            ),
            observation,
        )

    def test_semantic_attestation_coordinate_substitution_rejected(
        self
    ):
        store = self.make_store()

        observation = self.create_observation(
            store
        )

        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
            ) as pixel_mock,
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):

            result = click_vision(
                x=901,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "does not match",
            result.error,
        )

        # Candidate substitution dies before pixel
        # revalidation or physical execution.
        pixel_mock.assert_not_called()
        click_mock.assert_not_called()

        self.assertIs(
            store.peek(
                observation.observation_id
            ),
            observation,
        )

    def test_semantic_attestation_modifier_substitution_rejected(
        self
    ):
        store = self.make_store()

        observation = self.create_observation(
            store
        )

        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
            button="left",
            clicks=1,
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
            ) as pixel_mock,
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):

            result = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
                button="right",
                clicks=1,
            )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "does not match",
            result.error,
        )

        pixel_mock.assert_not_called()
        click_mock.assert_not_called()

        self.assertIs(
            store.peek(
                observation.observation_id
            ),
            observation,
        )

    def test_semantically_verified_pixels_must_still_match_before_click(
        self
    ):
        store = self.make_store()

        observation = self.create_observation(
            store
        )

        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.tools.computer_tools."
                "_revalidate_physical_vision_click_desktop_context",
                return_value=(
                    True,
                    "",
                ),
            ),
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
                return_value=(
                    False,
                    (
                        "Screen pixels changed after semantic "
                        "target verification."
                    ),
                ),
            ),
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.clear",
            ) as provenance_clear,
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):

            result = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(
            result.success
        )

        self.assertIn(
            "Screen pixels changed",
            result.error,
        )

        click_mock.assert_not_called()
        provenance_clear.assert_called_once_with()

        # Pixel drift invalidates the observation itself.
        # A fresh perceive → verify → click cycle is required.
        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                observation.observation_id
            )

    def test_physical_desktop_gate_requires_exact_provenance(
        self
    ):
        with (
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.get",
                return_value=None,
            ) as get_provenance,
            patch(
                "app.desktop.runtime.collect_desktop_context",
            ) as collect,
        ):
            allowed, reason = (
                _revalidate_physical_vision_click_desktop_context(
                    "a" * 32
                )
            )

        self.assertFalse(allowed)
        self.assertIn(
            "provenance is unavailable",
            reason,
        )
        get_provenance.assert_called_once_with(
            "a" * 32
        )
        collect.assert_not_called()

    def test_physical_desktop_gate_fails_closed_on_mismatch(
        self
    ):
        provenance = SimpleNamespace(
            binding=object(),
            desktop_before=object(),
            desktop_after=object(),
        )
        current = object()
        mismatch = SimpleNamespace(
            matched=False,
            status="mismatch",
            diagnostics=(
                "application_changed",
            ),
        )

        with (
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.get",
                return_value=provenance,
            ),
            patch(
                "app.desktop.runtime.collect_desktop_context",
                return_value=current,
            ),
            patch(
                "app.desktop.revalidation."
                "revalidate_desktop_context",
                return_value=mismatch,
            ),
        ):
            allowed, reason = (
                _revalidate_physical_vision_click_desktop_context(
                    "b" * 32
                )
            )

        self.assertFalse(allowed)
        self.assertIn(
            "mismatch (application_changed)",
            reason,
        )

    def test_physical_desktop_gate_match_uses_bounded_collection(
        self
    ):
        provenance = SimpleNamespace(
            binding=object(),
            desktop_before=object(),
            desktop_after=object(),
        )
        current = object()
        matched = SimpleNamespace(
            matched=True,
            status="matched",
            diagnostics=(),
        )

        with (
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.get",
                return_value=provenance,
            ) as get_provenance,
            patch(
                "app.desktop.runtime.collect_desktop_context",
                return_value=current,
            ) as collect,
            patch(
                "app.desktop.revalidation."
                "revalidate_desktop_context",
                return_value=matched,
            ) as revalidate,
        ):
            allowed, reason = (
                _revalidate_physical_vision_click_desktop_context(
                    "c" * 32
                )
            )

        self.assertTrue(allowed)
        self.assertEqual(reason, "")
        get_provenance.assert_called_once_with(
            "c" * 32
        )
        collect.assert_called_once_with(
            timeout_seconds=(
                PHYSICAL_DESKTOP_REVALIDATION_TIMEOUT_SECONDS
            ),
            max_windows=(
                PHYSICAL_DESKTOP_REVALIDATION_MAX_WINDOWS
            ),
        )
        revalidate.assert_called_once_with(
            provenance.binding,
            provenance.desktop_before,
            provenance.desktop_after,
            current,
            max_current_age_seconds=(
                PHYSICAL_DESKTOP_REVALIDATION_MAX_AGE_SECONDS
            ),
        )

    def test_physical_desktop_failure_invalidates_action_evidence_before_pixels(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )
        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
        )

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.tools.computer_tools."
                "_revalidate_physical_vision_click_desktop_context",
                return_value=(
                    False,
                    "Physical vision click desktop context changed.",
                ),
            ),
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.clear",
            ) as provenance_clear,
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
            ) as pixel_mock,
            patch(
                "app.tools.computer_tools.click_at",
            ) as click_mock,
        ):
            result = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertFalse(result.success)
        self.assertIn(
            "desktop context changed",
            result.error,
        )
        pixel_mock.assert_not_called()
        click_mock.assert_not_called()
        provenance_clear.assert_called_once_with()

        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                observation.observation_id
            )

    def test_physical_desktop_gate_runs_before_final_pixel_check(
        self
    ):
        store = self.make_store()
        observation = self.create_observation(
            store
        )
        self.issue_target_attestation(
            observation=observation,
            x=900,
            y=585,
        )
        order = []

        def desktop_gate(_observation_id):
            order.append("desktop")
            return True, ""

        def pixels(**_kwargs):
            order.append("pixels")
            return True, ""

        from app.agent.tool_result import ToolResult

        def click(*_args, **_kwargs):
            order.append("click")
            return ToolResult.ok("clicked")

        with (
            patch(
                "app.vision.observation.SCREEN_OBSERVATIONS",
                store,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(
                    1470,
                    956,
                ),
            ),
            patch(
                "app.tools.computer_tools."
                "_revalidate_physical_vision_click_desktop_context",
                side_effect=desktop_gate,
            ),
            patch(
                "app.vision.gui_target_verifier."
                "current_screen_matches_attestation",
                side_effect=pixels,
            ),
            patch(
                "app.desktop.provenance."
                "SCREEN_DESKTOP_PROVENANCE.clear",
            ),
            patch(
                "app.tools.computer_tools.click_at",
                side_effect=click,
            ),
        ):
            result = click_vision(
                x=900,
                y=585,
                observation_id=(
                    observation.observation_id
                ),
            )

        self.assertTrue(result.success, result.error)
        self.assertEqual(
            order,
            [
                "desktop",
                "pixels",
                "click",
            ],
        )

    def test_legacy_model_geometry_arguments_are_rejected(
        self
    ):
        agent = KumaAgent.__new__(
            KumaAgent
        )

        agent.tool_registry = {
            "click_vision":
            click_vision,
        }

        valid, _ = (
            agent.validate_tool_arguments(
                "click_vision",
                {
                    "x": 100,
                    "y": 100,
                    "vision_width": 1800,
                    "vision_height": 1171,
                    "observation_id": (
                        "abc"
                    ),
                },
            )
        )

        self.assertFalse(
            valid
        )

    def test_new_click_contract_validates_structurally(
        self
    ):
        agent = KumaAgent.__new__(
            KumaAgent
        )

        agent.tool_registry = {
            "click_vision":
            click_vision,
        }

        valid, error = (
            agent.validate_tool_arguments(
                "click_vision",
                {
                    "x": 100,
                    "y": 100,
                    "observation_id": (
                        "abc"
                    ),
                },
            )
        )

        self.assertTrue(
            valid,
            error,
        )

    def test_direct_click_intent_can_ground_click_vision(
        self
    ):
        agent = KumaAgent.__new__(
            KumaAgent
        )

        grounded = (
            agent.explicitly_requests_tool_action(
                "click the login button",
                "click_vision",
                {
                    "x": 100,
                    "y": 100,
                    "observation_id": (
                        "abc"
                    ),
                },
            )
        )

        self.assertTrue(
            grounded
        )

    def test_observation_only_request_does_not_ground_click_vision(
        self
    ):
        agent = KumaAgent.__new__(
            KumaAgent
        )

        grounded = (
            agent.explicitly_requests_tool_action(
                "look at my screen",
                "click_vision",
                {
                    "x": 100,
                    "y": 100,
                    "observation_id": (
                        "abc"
                    ),
                },
            )
        )

        self.assertFalse(
            grounded
        )


if __name__ == "__main__":
    unittest.main()
