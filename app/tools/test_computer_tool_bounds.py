from __future__ import annotations

import unittest
from unittest.mock import patch

import pyautogui

from app.tools.computer_tools import (
    MAX_CLICK_COUNT,
    MAX_MOUSE_MOVE_DURATION_SECONDS,
    MAX_SCROLL_UNITS,
    MAX_TYPE_ACTION_DURATION_SECONDS,
    MAX_TYPE_INTERVAL_SECONDS,
    MAX_TYPE_TEXT_CHARACTERS,
    PYAUTOGUI_PAUSE_SECONDS,
    click_at,
    move_mouse,
    press_key,
    scroll,
    type_text,
)


class TestMouseBounds(
    unittest.TestCase
):

    def test_move_mouse_accepts_bounded_values(
        self
    ):
        with (
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(1000, 800),
            ),
            patch(
                "app.tools.computer_tools.pyautogui.moveTo",
            ) as move_mock,
        ):
            result = move_mouse(
                100,
                200,
                duration=0.2,
            )

        self.assertTrue(
            result.success,
            result.error,
        )

        move_mock.assert_called_once_with(
            100,
            200,
            duration=0.2,
        )

    def test_move_mouse_rejects_string_coordinates(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.moveTo",
        ) as move_mock:
            result = move_mouse(
                "100",
                200,
            )

        self.assertFalse(
            result.success
        )

        move_mock.assert_not_called()

    def test_move_mouse_rejects_boolean_coordinate(
        self
    ):
        result = move_mouse(
            True,
            100,
        )

        self.assertFalse(
            result.success
        )

    def test_move_mouse_rejects_excessive_duration(
        self
    ):
        result = move_mouse(
            10,
            10,
            duration=(
                MAX_MOUSE_MOVE_DURATION_SECONDS
                + 0.01
            ),
        )

        self.assertFalse(
            result.success
        )

    def test_move_mouse_rejects_non_finite_duration(
        self
    ):
        result = move_mouse(
            10,
            10,
            duration=float("inf"),
        )

        self.assertFalse(
            result.success
        )

    def test_click_accepts_single_and_double_click_only(
        self
    ):
        for count in (
            1,
            MAX_CLICK_COUNT,
        ):
            with self.subTest(
                count=count
            ):
                with (
                    patch(
                        "app.tools.computer_tools.pyautogui.size",
                        return_value=(1000, 800),
                    ),
                    patch(
                        "app.tools.computer_tools.pyautogui.click",
                    ) as click_mock,
                ):
                    result = click_at(
                        100,
                        200,
                        clicks=count,
                    )

                self.assertTrue(
                    result.success,
                    result.error,
                )

                click_mock.assert_called_once()

    def test_click_rejects_click_storm(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.click",
        ) as click_mock:
            result = click_at(
                10,
                10,
                clicks=3,
            )

        self.assertFalse(
            result.success
        )

        click_mock.assert_not_called()

    def test_click_rejects_coercive_inputs(
        self
    ):
        cases = [
            {
                "x": "10",
                "y": 20,
                "clicks": 1,
            },
            {
                "x": 10,
                "y": 20,
                "clicks": "1",
            },
            {
                "x": 10,
                "y": 20,
                "clicks": True,
            },
        ]

        for arguments in cases:
            with self.subTest(
                arguments=arguments
            ):
                result = click_at(
                    **arguments
                )

                self.assertFalse(
                    result.success
                )


class TestKeyboardBounds(
    unittest.TestCase
):

    def test_type_text_accepts_normal_payload(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.write",
        ) as write_mock:
            result = type_text(
                "hello kuma",
                interval=0.01,
            )

        self.assertTrue(
            result.success,
            result.error,
        )

        write_mock.assert_called_once_with(
            "hello kuma",
            interval=0.01,
        )

    def test_type_text_rejects_non_string_payload(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.write",
        ) as write_mock:
            result = type_text(
                12345
            )

        self.assertFalse(
            result.success
        )

        write_mock.assert_not_called()

    def test_type_text_rejects_empty_payload(
        self
    ):
        result = type_text(
            ""
        )

        self.assertFalse(
            result.success
        )

    def test_type_text_rejects_oversized_payload(
        self
    ):
        payload = (
            "x"
            * (
                MAX_TYPE_TEXT_CHARACTERS
                + 1
            )
        )

        with patch(
            "app.tools.computer_tools.pyautogui.write",
        ) as write_mock:
            result = type_text(
                payload
            )

        self.assertFalse(
            result.success
        )

        write_mock.assert_not_called()

    def test_type_text_accepts_exact_limit(
        self
    ):
        payload = (
            "x"
            * MAX_TYPE_TEXT_CHARACTERS
        )

        with patch(
            "app.tools.computer_tools.pyautogui.write",
        ):
            result = type_text(
                payload,
                interval=0.0,
            )

        self.assertTrue(
            result.success,
            result.error,
        )

    def test_type_text_rejects_excessive_interval(
        self
    ):
        result = type_text(
            "hello",
            interval=(
                MAX_TYPE_INTERVAL_SECONDS
                + 0.01
            ),
        )

        self.assertFalse(
            result.success
        )

    def test_type_text_rejects_excessive_total_duration(
        self
    ):
        payload = (
            "x" * 200
        )

        interval = (
            MAX_TYPE_INTERVAL_SECONDS
        )

        self.assertGreater(
            (
                len(payload)
                * interval
                + PYAUTOGUI_PAUSE_SECONDS
            ),
            MAX_TYPE_ACTION_DURATION_SECONDS,
        )

        with patch(
            "app.tools.computer_tools.pyautogui.write",
        ) as write_mock:
            result = type_text(
                payload,
                interval=interval,
            )

        self.assertFalse(
            result.success
        )

        write_mock.assert_not_called()

    def test_type_text_rejects_non_finite_interval(
        self
    ):
        result = type_text(
            "hello",
            interval=float("nan"),
        )

        self.assertFalse(
            result.success
        )

    def test_press_key_accepts_known_key(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.press",
        ) as press_mock:
            result = press_key(
                "enter"
            )

        self.assertTrue(
            result.success,
            result.error,
        )

        press_mock.assert_called_once_with(
            "enter"
        )

    def test_press_key_rejects_unknown_key(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.press",
        ) as press_mock:
            result = press_key(
                "kuma-super-key"
            )

        self.assertFalse(
            result.success
        )

        press_mock.assert_not_called()

    def test_press_key_rejects_non_string(
        self
    ):
        result = press_key(
            123
        )

        self.assertFalse(
            result.success
        )


class TestScrollBounds(
    unittest.TestCase
):

    def test_scroll_accepts_positive_and_negative_limit(
        self
    ):
        for amount in (
            MAX_SCROLL_UNITS,
            -MAX_SCROLL_UNITS,
        ):
            with self.subTest(
                amount=amount
            ):
                with patch(
                    "app.tools.computer_tools.pyautogui.scroll",
                ) as scroll_mock:
                    result = scroll(
                        amount
                    )

                self.assertTrue(
                    result.success,
                    result.error,
                )

                scroll_mock.assert_called_once_with(
                    amount
                )

    def test_scroll_rejects_excessive_magnitude(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.scroll",
        ) as scroll_mock:
            result = scroll(
                MAX_SCROLL_UNITS + 1
            )

        self.assertFalse(
            result.success
        )

        scroll_mock.assert_not_called()

    def test_scroll_rejects_string_and_boolean(
        self
    ):
        for amount in (
            "5",
            True,
        ):
            with self.subTest(
                amount=amount
            ):
                result = scroll(
                    amount
                )

                self.assertFalse(
                    result.success
                )

    def test_zero_scroll_is_noop(
        self
    ):
        with patch(
            "app.tools.computer_tools.pyautogui.scroll",
        ) as scroll_mock:
            result = scroll(
                0
            )

        self.assertTrue(
            result.success
        )

        scroll_mock.assert_not_called()


class TestPyAutoGuiSafetyPolicy(
    unittest.TestCase
):

    def test_physical_action_restores_failsafe_and_pause(
        self
    ):
        with (
            patch.object(
                pyautogui,
                "FAILSAFE",
                False,
            ),
            patch.object(
                pyautogui,
                "PAUSE",
                999.0,
            ),
            patch(
                "app.tools.computer_tools.pyautogui.size",
                return_value=(1000, 800),
            ),
            patch(
                "app.tools.computer_tools.pyautogui.moveTo",
            ),
        ):
            result = move_mouse(
                100,
                100,
            )

            self.assertTrue(
                result.success,
                result.error,
            )

            self.assertTrue(
                pyautogui.FAILSAFE
            )

            self.assertEqual(
                pyautogui.PAUSE,
                PYAUTOGUI_PAUSE_SECONDS,
            )


if __name__ == "__main__":
    unittest.main()
