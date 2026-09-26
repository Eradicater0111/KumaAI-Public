from __future__ import annotations

import unittest

from app.agent.goal_plan import (
    GoalPlan,
    GoalStep,
)
from app.agent.gui_intent_authority import (
    GUI_AUTHORITY_CONFIRMED,
    GUI_AUTHORITY_EXPLICIT,
    authorize_plan_gui_actions,
    explicitly_authorizes_gui_action_class,
    validate_runtime_gui_authority,
)


class TestExplicitGuiAuthority(
    unittest.TestCase
):

    def test_explicit_click_is_grounded(
        self
    ):
        self.assertTrue(
            explicitly_authorizes_gui_action_class(
                "Click the Settings button.",
                "click",
            )
        )

    def test_observation_only_goal_does_not_authorize_click(
        self
    ):
        self.assertFalse(
            explicitly_authorizes_gui_action_class(
                "Look at my screen and tell me what you see.",
                "click",
            )
        )

    def test_write_me_email_does_not_directly_authorize_typing(
        self
    ):
        self.assertFalse(
            explicitly_authorizes_gui_action_class(
                "Write me an email to my professor.",
                "type_text",
            )
        )

    def test_explicit_type_into_field_is_grounded(
        self
    ):
        self.assertTrue(
            explicitly_authorizes_gui_action_class(
                "Type hello into the message box.",
                "type_text",
            )
        )

    def test_scroll_is_grounded(
        self
    ):
        self.assertTrue(
            explicitly_authorizes_gui_action_class(
                "Scroll down the page.",
                "scroll",
            )
        )

    def test_known_application_open_is_grounded(
        self
    ):
        self.assertTrue(
            explicitly_authorizes_gui_action_class(
                "Open Chrome.",
                "open_app",
            )
        )


class TestRuntimeGuiAuthority(
    unittest.TestCase
):

    def test_gui_tool_requires_authority(
        self
    ):
        valid, _ = (
            validate_runtime_gui_authority(
                "click",
                "",
            )
        )

        self.assertFalse(
            valid
        )

    def test_explicit_authority_is_valid(
        self
    ):
        valid, error = (
            validate_runtime_gui_authority(
                "click",
                GUI_AUTHORITY_EXPLICIT,
            )
        )

        self.assertTrue(
            valid,
            error,
        )

    def test_confirmed_authority_is_valid(
        self
    ):
        valid, error = (
            validate_runtime_gui_authority(
                "click",
                GUI_AUTHORITY_CONFIRMED,
            )
        )

        self.assertTrue(
            valid,
            error,
        )

    def test_fake_authority_is_rejected(
        self
    ):
        valid, _ = (
            validate_runtime_gui_authority(
                "click",
                "planner_says_ok",
            )
        )

        self.assertFalse(
            valid
        )

    def test_non_gui_step_accepts_blank_authority(
        self
    ):
        valid, error = (
            validate_runtime_gui_authority(
                "list_files",
                "",
            )
        )

        self.assertTrue(
            valid,
            error,
        )


class TestPlanGuiAuthority(
    unittest.TestCase
):

    @staticmethod
    def make_plan(
        *,
        planned_tool,
    ):
        return GoalPlan(
            goal="test",
            steps=[
                GoalStep(
                    id="step-1",
                    objective="Perform step.",
                    required_capabilities=[
                        "mouse_control",
                    ],
                    planned_tool=planned_tool,
                )
            ],
        )

    def test_explicit_goal_needs_no_confirmation(
        self
    ):
        plan = self.make_plan(
            planned_tool="click"
        )

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
            return False

        decision = (
            authorize_plan_gui_actions(
                goal=(
                    "Click the Settings button."
                ),
                plan=plan,
                confirmation_fn=confirm,
            )
        )

        self.assertTrue(
            decision.allowed,
            decision.reason,
        )

        self.assertEqual(
            calls,
            [],
        )

        self.assertEqual(
            plan.steps[0].gui_authority,
            GUI_AUTHORITY_EXPLICIT,
        )

    def test_planner_expansion_requires_confirmation(
        self
    ):
        plan = self.make_plan(
            planned_tool="click"
        )

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
            authorize_plan_gui_actions(
                goal=(
                    "Look at the Settings page."
                ),
                plan=plan,
                confirmation_fn=confirm,
            )
        )

        self.assertTrue(
            decision.allowed,
            decision.reason,
        )

        self.assertEqual(
            len(calls),
            1,
        )

        self.assertEqual(
            plan.steps[0].gui_authority,
            GUI_AUTHORITY_CONFIRMED,
        )

    def test_denied_expansion_rejects_plan(
        self
    ):
        plan = self.make_plan(
            planned_tool="click"
        )

        decision = (
            authorize_plan_gui_actions(
                goal=(
                    "Look at the Settings page."
                ),
                plan=plan,
                confirmation_fn=(
                    lambda *_args: False
                ),
            )
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertEqual(
            plan.steps[0].gui_authority,
            "",
        )

    def test_missing_confirmation_boundary_fails_closed(
        self
    ):
        plan = self.make_plan(
            planned_tool="click"
        )

        decision = (
            authorize_plan_gui_actions(
                goal=(
                    "Look at the Settings page."
                ),
                plan=plan,
                confirmation_fn=None,
            )
        )

        self.assertFalse(
            decision.allowed
        )

    def test_planner_cannot_preseed_authority(
        self
    ):
        plan = self.make_plan(
            planned_tool="click"
        )

        plan.steps[0].gui_authority = (
            "confirmed_expansion"
        )

        decision = (
            authorize_plan_gui_actions(
                goal=(
                    "Look at the Settings page."
                ),
                plan=plan,
                confirmation_fn=(
                    lambda *_args: False
                ),
            )
        )

        self.assertFalse(
            decision.allowed
        )

        self.assertEqual(
            plan.steps[0].gui_authority,
            "",
        )

    def test_authority_does_not_survive_goalstep_roundtrip(
        self
    ):
        step = GoalStep(
            id="step-1",
            objective="Click Settings.",
            planned_tool="click",
            gui_authority=(
                GUI_AUTHORITY_EXPLICIT
            ),
            gui_authority_goal=(
                "Click Settings."
            ),
        )

        payload = step.to_dict()

        self.assertNotIn(
            "gui_authority",
            payload,
        )
        self.assertNotIn(
            "gui_authority_goal",
            payload,
        )

        restored = GoalStep.from_dict(
            payload
        )

        self.assertEqual(
            restored.gui_authority,
            "",
        )
        self.assertEqual(
            restored.gui_authority_goal,
            "",
        )

    def test_legacy_persisted_authority_is_ignored(
        self
    ):
        restored = GoalStep.from_dict(
            {
                "id": "step-1",
                "objective": "Look at Settings.",
                "planned_tool": "click",
                "gui_authority": (
                    GUI_AUTHORITY_CONFIRMED
                ),
                "gui_authority_goal": (
                    "Click Delete."
                ),
            }
        )

        self.assertEqual(
            restored.gui_authority,
            "",
        )
        self.assertEqual(
            restored.gui_authority_goal,
            "",
        )


if __name__ == "__main__":
    unittest.main()
