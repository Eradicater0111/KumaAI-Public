from __future__ import annotations

import unittest

from app.vision.observation import (
    ScreenObservationError,
    ScreenObservationStore,
)


class TestScreenObservationStore(
    unittest.TestCase
):

    def make_store(
        self,
    ):
        return ScreenObservationStore(
            max_age_seconds=30,
        )

    def create(
        self,
        store,
        *,
        captured_at=100.0,
        capture_width=2940,
        capture_height=1912,
        vision_width=1800,
        vision_height=1171,
        native_width=1470,
        native_height=956,
        scale=1800 / 2940,
        analysis="VISIBLE_TARGETS:\n- none",
    ):
        return store.create(
            captured_at_monotonic=(
                captured_at
            ),
            capture_width=(
                capture_width
            ),
            capture_height=(
                capture_height
            ),
            vision_width=(
                vision_width
            ),
            vision_height=(
                vision_height
            ),
            native_width=(
                native_width
            ),
            native_height=(
                native_height
            ),
            vision_scale=scale,
            analysis=analysis,
        )

    def test_create_preserves_trusted_geometry(
        self
    ):
        store = self.make_store()

        observation = self.create(
            store
        )

        self.assertEqual(
            observation.capture_width,
            2940,
        )

        self.assertEqual(
            observation.capture_height,
            1912,
        )

        self.assertEqual(
            observation.vision_width,
            1800,
        )

        self.assertEqual(
            observation.vision_height,
            1171,
        )

        self.assertEqual(
            observation.native_width,
            1470,
        )

        self.assertEqual(
            observation.native_height,
            956,
        )

    def test_model_facing_string_contains_id_but_not_native_geometry(
        self
    ):
        store = self.make_store()

        observation = self.create(
            store
        )

        rendered = str(
            observation
        )

        self.assertIn(
            observation.observation_id,
            rendered,
        )

        self.assertIn(
            "vision_size: 1800x1171",
            rendered,
        )

        self.assertNotIn(
            "1470x956",
            rendered,
        )

    def test_new_observation_replaces_previous(
        self
    ):
        store = self.make_store()

        first = self.create(
            store,
            captured_at=100,
        )

        second = self.create(
            store,
            captured_at=101,
        )

        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                first.observation_id,
                now=102,
            )

        self.assertIs(
            store.peek(
                second.observation_id,
                now=102,
            ),
            second,
        )

    def test_stale_observation_fails_closed(
        self
    ):
        store = self.make_store()

        observation = self.create(
            store,
            captured_at=100,
        )

        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                observation.observation_id,
                now=131,
            )

    def test_claim_is_single_use(
        self
    ):
        store = self.make_store()

        observation = self.create(
            store,
            captured_at=100,
        )

        claimed = store.claim(
            observation.observation_id,
            now=110,
        )

        self.assertIs(
            claimed,
            observation,
        )

        with self.assertRaises(
            ScreenObservationError
        ):
            store.claim(
                observation.observation_id,
                now=111,
            )

    def test_unknown_observation_fails_closed(
        self
    ):
        store = self.make_store()

        self.create(
            store
        )

        with self.assertRaises(
            ScreenObservationError
        ):
            store.peek(
                "not-the-active-id",
                now=101,
            )

    def test_capture_native_aspect_mismatch_is_rejected(
        self
    ):
        store = self.make_store()

        with self.assertRaises(
            ScreenObservationError
        ):
            self.create(
                store,
                native_width=1000,
                native_height=1000,
            )

    def test_invalid_dimensions_are_rejected(
        self
    ):
        store = self.make_store()

        for field in (
            "capture_width",
            "capture_height",
            "vision_width",
            "vision_height",
            "native_width",
            "native_height",
        ):
            with self.subTest(
                field=field
            ):
                kwargs = {
                    field: 0,
                }

                with self.assertRaises(
                    ScreenObservationError
                ):
                    self.create(
                        store,
                        **kwargs,
                    )

    def test_boolean_dimension_is_rejected(
        self
    ):
        store = self.make_store()

        with self.assertRaises(
            ScreenObservationError
        ):
            self.create(
                store,
                vision_width=True,
            )

    def test_empty_analysis_is_rejected(
        self
    ):
        store = self.make_store()

        with self.assertRaises(
            ScreenObservationError
        ):
            self.create(
                store,
                analysis="   ",
            )

    def test_invalid_max_age_is_rejected(
        self
    ):
        for value in (
            0,
            -1,
            True,
            float("inf"),
            "30",
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    ScreenObservationStore(
                        max_age_seconds=value
                    )


if __name__ == "__main__":
    unittest.main()
