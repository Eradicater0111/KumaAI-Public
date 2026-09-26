from __future__ import annotations

from types import SimpleNamespace
import hashlib
import unittest
from unittest.mock import patch

from PIL import Image

from app.vision.gui_target_verifier import (
    GuiTargetAttestationStore,
    GuiTargetVerificationResult,
    GuiTargetVerifier,
    TARGET_STATUS_NOT_SATISFIED,
    TARGET_STATUS_SATISFIED,
    TARGET_STATUS_UNKNOWN,
    _parse_verifier_response,
    _prepare_current_image,
    _target_region_digest,
    current_screen_matches_attestation,
)


def fake_observation():
    return SimpleNamespace(
        observation_id="obs-1",
        capture_width=1200,
        capture_height=800,
        vision_width=600,
        vision_height=400,
        native_width=1200,
        native_height=800,
    )


def fake_response(
    text,
):
    return SimpleNamespace(
        text=text
    )


class FakeModels:

    def __init__(
        self,
        response,
    ):
        self.response = response
        self.calls = []

    def generate_content(
        self,
        **kwargs,
    ):
        self.calls.append(
            dict(kwargs)
        )

        return self.response


class FakeClient:

    def __init__(
        self,
        response,
    ):
        self.models = FakeModels(
            response
        )


class TestTargetVerifierParsing(
    unittest.TestCase
):

    def test_strict_satisfied_json(
        self,
    ):
        status, summary, evidence = (
            _parse_verifier_response(
                (
                    '{"status":"satisfied",'
                    '"summary":"Target matched.",'
                    '"evidence":"Marker is on Settings."}'
                )
            )
        )

        self.assertEqual(
            status,
            TARGET_STATUS_SATISFIED,
        )

        self.assertEqual(
            summary,
            "Target matched.",
        )

        self.assertEqual(
            evidence,
            "Marker is on Settings.",
        )

    def test_invalid_status_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            _parse_verifier_response(
                (
                    '{"status":"probably",'
                    '"summary":"x",'
                    '"evidence":"y"}'
                )
            )

    def test_extra_schema_rejected(
        self,
    ):
        with self.assertRaises(
            ValueError
        ):
            _parse_verifier_response(
                (
                    '{"status":"satisfied",'
                    '"summary":"x",'
                    '"evidence":"y",'
                    '"execute":true}'
                )
            )



class TestGuiTargetAttestationStore(
    unittest.TestCase
):

    @staticmethod
    def satisfied_result():
        return GuiTargetVerificationResult(
            status=TARGET_STATUS_SATISFIED,
            summary="matched",
            evidence="marker on target",
            observation_id="obs-1",
            x=100,
            y=200,
            goal_sha256="goal-digest",
            image_sha256="image-digest",
            target_region_sha256="region-digest",
        )

    def test_satisfied_result_without_target_region_is_rejected(
        self,
    ):
        store = GuiTargetAttestationStore()

        result = self.satisfied_result()
        result = GuiTargetVerificationResult(
            status=result.status,
            summary=result.summary,
            evidence=result.evidence,
            observation_id=result.observation_id,
            x=result.x,
            y=result.y,
            goal_sha256=result.goal_sha256,
            image_sha256=result.image_sha256,
            target_region_sha256="",
        )

        with self.assertRaises(ValueError):
            store.issue(
                result=result,
                button="left",
                clicks=1,
            )

    def test_exact_attestation_claim_succeeds(
        self,
    ):
        store = GuiTargetAttestationStore(
            max_age_seconds=5.0
        )

        store.issue(
            result=self.satisfied_result(),
            button="left",
            clicks=1,
        )

        result = store.claim(
            observation_id="obs-1",
            x=100,
            y=200,
            button="left",
            clicks=1,
        )

        self.assertEqual(
            result.observation_id,
            "obs-1",
        )

    def test_coordinate_substitution_rejected(
        self,
    ):
        store = GuiTargetAttestationStore()

        store.issue(
            result=self.satisfied_result(),
            button="left",
            clicks=1,
        )

        with self.assertRaises(
            ValueError
        ):
            store.claim(
                observation_id="obs-1",
                x=101,
                y=200,
                button="left",
                clicks=1,
            )

    def test_click_modifier_substitution_rejected(
        self,
    ):
        store = GuiTargetAttestationStore()

        store.issue(
            result=self.satisfied_result(),
            button="left",
            clicks=1,
        )

        with self.assertRaises(
            ValueError
        ):
            store.claim(
                observation_id="obs-1",
                x=100,
                y=200,
                button="right",
                clicks=1,
            )

    def test_attestation_is_single_use(
        self,
    ):
        store = GuiTargetAttestationStore()

        store.issue(
            result=self.satisfied_result(),
            button="left",
            clicks=1,
        )

        store.claim(
            observation_id="obs-1",
            x=100,
            y=200,
            button="left",
            clicks=1,
        )

        with self.assertRaises(
            ValueError
        ):
            store.claim(
                observation_id="obs-1",
                x=100,
                y=200,
                button="left",
                clicks=1,
            )


class TestTargetRegionContinuity(
    unittest.TestCase
):

    @staticmethod
    def observation():
        return SimpleNamespace(
            observation_id="obs-region",
            capture_width=1200,
            capture_height=800,
            vision_width=1200,
            vision_height=800,
            native_width=1200,
            native_height=800,
        )

    @staticmethod
    def attestation_for(image, *, x=400, y=300):
        _png, prepared = _prepare_current_image(
            image=image,
            vision_width=1200,
            vision_height=800,
        )

        result = GuiTargetVerificationResult(
            status=TARGET_STATUS_SATISFIED,
            summary="matched",
            evidence="controlled target region",
            observation_id="obs-region",
            x=x,
            y=y,
            goal_sha256=hashlib.sha256(b"goal").hexdigest(),
            image_sha256=hashlib.sha256(_png).hexdigest(),
            target_region_sha256=_target_region_digest(
                prepared=prepared,
                x=x,
                y=y,
            ),
        )

        store = GuiTargetAttestationStore()
        return store.issue(
            result=result,
            button="left",
            clicks=1,
        )

    def test_unrelated_pixels_outside_target_region_do_not_block(self):
        original = Image.new("RGB", (1200, 800), "white")
        attestation = self.attestation_for(original)

        changed = original.copy()
        changed.putpixel((1100, 700), (0, 0, 0))

        with patch(
            "app.vision.gui_target_verifier.pyautogui.size",
            return_value=(1200, 800),
        ), patch(
            "app.vision.gui_target_verifier.capture_screen",
            return_value=changed,
        ):
            matched, error = current_screen_matches_attestation(
                observation=self.observation(),
                attestation=attestation,
            )

        self.assertTrue(matched, error)

    def test_pixel_change_inside_target_region_blocks(self):
        original = Image.new("RGB", (1200, 800), "white")
        attestation = self.attestation_for(original)

        changed = original.copy()
        changed.putpixel((400, 300), (0, 0, 0))

        with patch(
            "app.vision.gui_target_verifier.pyautogui.size",
            return_value=(1200, 800),
        ), patch(
            "app.vision.gui_target_verifier.capture_screen",
            return_value=changed,
        ):
            matched, error = current_screen_matches_attestation(
                observation=self.observation(),
                attestation=attestation,
            )

        self.assertFalse(matched)
        self.assertIn("Target-region pixels changed", error)


class TestGuiTargetVerifier(
    unittest.TestCase
):

    def setUp(
        self,
    ):
        self.verifier = (
            GuiTargetVerifier()
        )

    def test_out_of_bounds_fails_unknown(
        self,
    ):
        with patch(
            "app.vision.gui_target_verifier."
            "SCREEN_OBSERVATIONS.peek",
            return_value=fake_observation(),
        ):
            result = self.verifier.verify(
                goal="Click Settings.",
                observation_id="obs-1",
                x=700,
                y=200,
            )

        self.assertEqual(
            result.status,
            TARGET_STATUS_UNKNOWN,
        )

    def test_capture_geometry_change_fails_unknown(
        self,
    ):
        with patch(
            "app.vision.gui_target_verifier."
            "SCREEN_OBSERVATIONS.peek",
            return_value=fake_observation(),
        ), patch(
            "app.vision.gui_target_verifier."
            "pyautogui.size",
            return_value=(1200, 800),
        ), patch(
            "app.vision.gui_target_verifier."
            "capture_screen",
            return_value=Image.new(
                "RGB",
                (1000, 800),
            ),
        ):
            result = self.verifier.verify(
                goal="Click Settings.",
                observation_id="obs-1",
                x=100,
                y=200,
            )

        self.assertEqual(
            result.status,
            TARGET_STATUS_UNKNOWN,
        )

    def test_geometry_change_before_capture_fails_unknown(
        self,
    ):
        with patch(
            "app.vision.gui_target_verifier."
            "SCREEN_OBSERVATIONS.peek",
            return_value=fake_observation(),
        ), patch(
            "app.vision.gui_target_verifier."
            "pyautogui.size",
            return_value=(1400, 900),
        ):
            result = self.verifier.verify(
                goal="Click Settings.",
                observation_id="obs-1",
                x=100,
                y=200,
            )

        self.assertEqual(
            result.status,
            TARGET_STATUS_UNKNOWN,
        )

    def test_satisfied_result_is_bound_to_exact_candidate(
        self,
    ):
        response = fake_response(
            (
                '{"status":"satisfied",'
                '"summary":"Settings matched.",'
                '"evidence":"Marker is on Settings."}'
            )
        )

        fake_client = FakeClient(
            response
        )

        with patch(
            "app.vision.gui_target_verifier."
            "SCREEN_OBSERVATIONS.peek",
            return_value=fake_observation(),
        ), patch(
            "app.vision.gui_target_verifier."
            "pyautogui.size",
            return_value=(1200, 800),
        ), patch(
            "app.vision.gui_target_verifier."
            "capture_screen",
            return_value=Image.new(
                "RGB",
                (1200, 800),
            ),
        ), patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY":
                "test-key",
            },
        ), patch(
            "app.vision.gui_target_verifier."
            "genai.Client",
            return_value=fake_client,
        ):

            result = self.verifier.verify(
                goal="Click Settings.",
                observation_id="obs-1",
                x=100,
                y=200,
            )

        self.assertTrue(
            result.satisfied
        )

        self.assertEqual(
            result.observation_id,
            "obs-1",
        )

        self.assertEqual(
            (
                result.x,
                result.y,
            ),
            (
                100,
                200,
            ),
        )

        self.assertTrue(
            result.goal_sha256
        )

        self.assertTrue(
            result.image_sha256
        )

        self.assertTrue(
            result.target_region_sha256
        )

        self.assertEqual(
            len(
                fake_client.models.calls
            ),
            1,
        )

    def test_not_satisfied_is_preserved(
        self,
    ):
        response = fake_response(
            (
                '{"status":"not_satisfied",'
                '"summary":"Wrong control.",'
                '"evidence":"Marker is on Cancel."}'
            )
        )

        with patch(
            "app.vision.gui_target_verifier."
            "SCREEN_OBSERVATIONS.peek",
            return_value=fake_observation(),
        ), patch(
            "app.vision.gui_target_verifier."
            "pyautogui.size",
            return_value=(1200, 800),
        ), patch(
            "app.vision.gui_target_verifier."
            "capture_screen",
            return_value=Image.new(
                "RGB",
                (1200, 800),
            ),
        ), patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY":
                "test-key",
            },
        ), patch(
            "app.vision.gui_target_verifier."
            "genai.Client",
            return_value=FakeClient(
                response
            ),
        ):

            result = self.verifier.verify(
                goal="Click Settings.",
                observation_id="obs-1",
                x=100,
                y=200,
            )

        self.assertEqual(
            result.status,
            TARGET_STATUS_NOT_SATISFIED,
        )

        self.assertFalse(
            result.satisfied
        )

    def test_malformed_model_output_fails_unknown(
        self,
    ):
        with patch(
            "app.vision.gui_target_verifier."
            "SCREEN_OBSERVATIONS.peek",
            return_value=fake_observation(),
        ), patch(
            "app.vision.gui_target_verifier."
            "pyautogui.size",
            return_value=(1200, 800),
        ), patch(
            "app.vision.gui_target_verifier."
            "capture_screen",
            return_value=Image.new(
                "RGB",
                (1200, 800),
            ),
        ), patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY":
                "test-key",
            },
        ), patch(
            "app.vision.gui_target_verifier."
            "genai.Client",
            return_value=FakeClient(
                fake_response(
                    "yes click it"
                )
            ),
        ):

            result = self.verifier.verify(
                goal="Click Settings.",
                observation_id="obs-1",
                x=100,
                y=200,
            )

        self.assertEqual(
            result.status,
            TARGET_STATUS_UNKNOWN,
        )


if __name__ == "__main__":
    unittest.main()
