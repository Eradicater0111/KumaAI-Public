from __future__ import annotations

import unittest

from app.agent.gui_argument_authority import (
    GUI_ARGUMENT_CONFIRMATION_TOOL,
    arguments_grounded_in_human_goal,
    authorize_runtime_gui_arguments,
)


class TestGuiArgumentGrounding(
    unittest.TestCase
):

    def test_exact_open_app_identity_is_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal="Open Chrome.",
                tool_name="open_app",
                arguments={
                    "app_name": "Google Chrome",
                },
            )
        )

    def test_open_app_alias_does_not_match_inside_other_word(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal="Open Decoder.",
                tool_name="open_app",
                arguments={
                    "app_name": "Visual Studio Code",
                },
            )
        )

    def test_wrong_open_app_identity_is_not_grounded(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal="Open Chrome.",
                tool_name="open_app",
                arguments={
                    "app_name": "Terminal",
                },
            )
        )

    def test_exact_type_payload_is_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal=(
                    "Type hello into the message box."
                ),
                tool_name="type_text",
                arguments={
                    "text": "hello",
                },
            )
        )

    def test_different_type_payload_is_not_grounded(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal=(
                    "Type hello into the message box."
                ),
                tool_name="type_text",
                arguments={
                    "text": "delete everything",
                },
            )
        )

    def test_unrelated_quoted_text_does_not_authorize_typing(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal=(
                    "Open the conversation named "
                    "'hello'."
                ),
                tool_name="type_text",
                arguments={
                    "text": "hello",
                },
            )
        )

    def test_quoted_type_payload_is_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal=(
                    'Type "Hello World" into the box.'
                ),
                tool_name="type_text",
                arguments={
                    "text": "Hello World",
                },
            )
        )

    def test_press_exact_key_is_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal="Press the Enter key.",
                tool_name="press_key",
                arguments={
                    "key": "enter",
                },
            )
        )

    def test_wrong_key_is_not_grounded(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal="Press Enter.",
                tool_name="press_key",
                arguments={
                    "key": "delete",
                },
            )
        )

    def test_exact_scroll_direction_and_amount_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal="Scroll down by 5.",
                tool_name="scroll",
                arguments={
                    "amount": -5,
                },
            )
        )

    def test_scroll_direction_without_exact_amount_not_grounded(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal="Scroll down.",
                tool_name="scroll",
                arguments={
                    "amount": -5,
                },
            )
        )

    def test_explicit_mouse_coordinates_are_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal=(
                    "Move the cursor to x=120 y=240."
                ),
                tool_name="move_mouse",
                arguments={
                    "x": 120,
                    "y": 240,
                    "duration": 0.15,
                },
            )
        )

    def test_explicit_raw_click_coordinates_are_grounded(
        self,
    ):
        self.assertTrue(
            arguments_grounded_in_human_goal(
                goal="Click at 120, 240.",
                tool_name="click",
                arguments={
                    "x": 120,
                    "y": 240,
                    "button": "left",
                    "clicks": 1,
                },
            )
        )

    def test_click_vision_is_not_semantically_grounded_by_observation(
        self,
    ):
        self.assertFalse(
            arguments_grounded_in_human_goal(
                goal="Click Settings.",
                tool_name="click_vision",
                arguments={
                    "x": 120,
                    "y": 240,
                    "observation_id": "obs-1",
                    "button": "left",
                    "clicks": 1,
                },
            )
        )


class TestSemanticVisionArgumentAuthorization(
    unittest.TestCase
):

    def test_semantically_verified_single_left_click_needs_no_coordinate_confirmation(
        self,
    ):
        calls = []

        decision = (
            authorize_runtime_gui_arguments(
                goal="Click Settings.",
                tool_name="click_vision",
                arguments={
                    "x": 100,
                    "y": 200,
                    "observation_id": "obs-1",
                    "button": "left",
                    "clicks": 1,
                },
                confirmation_fn=(
                    lambda *args: calls.append(
                        args
                    )
                ),
                semantic_target_verified=True,
            )
        )

        self.assertTrue(
            decision.allowed,
            decision.reason,
        )

        self.assertTrue(
            decision.semantic_target_verified
        )

        self.assertEqual(
            calls,
            [],
        )

    def test_semantic_target_does_not_authorize_stronger_click_modifier(
        self,
    ):
        decision = (
            authorize_runtime_gui_arguments(
                goal="Click Settings.",
                tool_name="click_vision",
                arguments={
                    "x": 100,
                    "y": 200,
                    "observation_id": "obs-1",
                    "button": "right",
                    "clicks": 1,
                },
                confirmation_fn=(
                    lambda *_args: False
                ),
                semantic_target_verified=True,
            )
        )

        self.assertFalse(
            decision.allowed
        )


class TestGuiArgumentAuthorization(
    unittest.TestCase
):

    def test_grounded_arguments_need_no_confirmation(
        self,
    ):
        calls = []

        decision = (
            authorize_runtime_gui_arguments(
                goal=(
                    "Type hello into the message box."
                ),
                tool_name="type_text",
                arguments={
                    "text": "hello",
                },
                confirmation_fn=(
                    lambda *args: calls.append(
                        args
                    )
                ),
            )
        )

        self.assertTrue(
            decision.allowed,
            decision.reason,
        )

        self.assertTrue(
            decision.grounded_in_goal
        )

        self.assertEqual(
            calls,
            [],
        )

    def test_mismatched_arguments_require_confirmation(
        self,
    ):
        calls = []

        def confirm(
            tool_name,
            arguments,
        ):
            calls.append(
                (
                    tool_name,
                    arguments,
                )
            )
            return True

        decision = (
            authorize_runtime_gui_arguments(
                goal=(
                    "Type hello into the message box."
                ),
                tool_name="type_text",
                arguments={
                    "text": "delete everything",
                },
                confirmation_fn=confirm,
            )
        )

        self.assertTrue(
            decision.allowed,
            decision.reason,
        )

        self.assertTrue(
            decision.confirmed
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            calls[0][0],
            GUI_ARGUMENT_CONFIRMATION_TOOL,
        )

        self.assertEqual(
            calls[0][1][
                "authority_scope"
            ],
            "exact_normalized_gui_arguments",
        )

        self.assertEqual(
            calls[0][1][
                "arguments"
            ],
            {
                "text": "delete everything",
            },
        )

    def test_denied_argument_expansion_fails_closed(
        self,
    ):
        decision = (
            authorize_runtime_gui_arguments(
                goal=(
                    "Type hello into the message box."
                ),
                tool_name="type_text",
                arguments={
                    "text": "delete everything",
                },
                confirmation_fn=(
                    lambda *_args: False
                ),
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_missing_confirmation_boundary_fails_closed(
        self,
    ):
        decision = (
            authorize_runtime_gui_arguments(
                goal="Click Settings.",
                tool_name="click_vision",
                arguments={
                    "x": 10,
                    "y": 20,
                    "observation_id": "obs-1",
                },
                confirmation_fn=None,
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_non_gui_tool_is_unchanged(
        self,
    ):
        decision = (
            authorize_runtime_gui_arguments(
                goal="List my files.",
                tool_name="list_files",
                arguments={},
                confirmation_fn=None,
            )
        )

        self.assertTrue(
            decision.allowed,
            decision.reason,
        )


if __name__ == "__main__":
    unittest.main()
