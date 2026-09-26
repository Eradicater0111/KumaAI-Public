from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agent.kuma_agent import (
    KumaAgent,
)
from app.agent.repair_apply_executor import (
    RepairApplyExecutor,
    RepairApplyResult,
)


class TestRepairApplyIntegration(
    unittest.TestCase
):

    @staticmethod
    def agent(
        *,
        confirmation_callback=None,
    ):
        """
        Construct only the narrow KumaAgent surface required by
        this integration test. Avoid database/model initialization.
        """

        agent = KumaAgent.__new__(
            KumaAgent
        )

        agent.confirmation_callback = (
            confirmation_callback
        )

        agent.tool_registry = {}

        return agent

    @staticmethod
    def evidence():
        """
        Opaque sentinels are intentional here.

        RepairApplyExecutor's own adversarial suite proves the real
        contracts and mutation behavior. These tests prove only the
        KumaAgent -> confirmation -> executor integration boundary.
        """

        return {
            "workspace": object(),
            "decision": object(),
            "validation": object(),
            "selection": object(),
            "handoff": object(),
            "execution_results": (
                object(),
            ),
            "test_result": object(),
            "verification": object(),
            "request": object(),
        }

    @staticmethod
    def result(
        *,
        approved: bool,
    ):
        return RepairApplyResult(
            attempted=approved,
            approved=approved,
            applied=approved,
            rolled_back=False,
            rollback_failed=False,
            reason=(
                "integration-test result"
            ),
        )

    def invoke_with_fake_executor(
        self,
        *,
        agent,
        evidence,
        action=(
            "apply_verified_repair"
        ),
        arguments=None,
    ):
        if arguments is None:
            arguments = {
                "request_digest":
                "a" * 64,
                "changed_files": [
                    "app/agent/sample.py",
                ],
            }

        observations = {
            "executor_calls": 0,
            "confirmation_results": [],
        }

        def fake_apply(
            _executor,
            **kwargs,
        ):
            observations[
                "executor_calls"
            ] += 1

            confirmation = kwargs[
                "confirmation_requester"
            ]

            approved = confirmation(
                action,
                arguments,
            )

            observations[
                "confirmation_results"
            ].append(
                approved
            )

            return self.result(
                approved=approved
            )

        with patch.object(
            RepairApplyExecutor,
            "apply",
            autospec=True,
            side_effect=fake_apply,
        ) as mocked_apply:
            result = (
                agent
                .apply_verified_repair(
                    **evidence
                )
            )

        return (
            result,
            observations,
            mocked_apply,
        )

    def test_missing_confirmation_callback_denies(
        self
    ):
        agent = self.agent()

        (
            result,
            observations,
            mocked_apply,
        ) = self.invoke_with_fake_executor(
            agent=agent,
            evidence=self.evidence(),
        )

        self.assertFalse(
            result.approved
        )

        self.assertEqual(
            observations[
                "confirmation_results"
            ],
            [
                False,
            ],
        )

        self.assertEqual(
            observations[
                "executor_calls"
            ],
            1,
        )

        mocked_apply.assert_called_once()

    def test_confirmation_callback_exception_denies(
        self
    ):
        def broken_callback(
            tool_name,
            arguments,
        ):
            raise RuntimeError(
                "confirmation failed"
            )

        agent = self.agent(
            confirmation_callback=(
                broken_callback
            )
        )

        (
            result,
            observations,
            mocked_apply,
        ) = self.invoke_with_fake_executor(
            agent=agent,
            evidence=self.evidence(),
        )

        self.assertFalse(
            result.approved
        )

        self.assertEqual(
            observations[
                "confirmation_results"
            ],
            [
                False,
            ],
        )

        mocked_apply.assert_called_once()

    def test_explicit_approval_reaches_executor_once(
        self
    ):
        confirmations = []

        def approve(
            tool_name,
            arguments,
        ):
            confirmations.append(
                (
                    tool_name,
                    arguments,
                )
            )

            return True

        agent = self.agent(
            confirmation_callback=approve
        )

        arguments = {
            "request_digest":
            "b" * 64,
            "changed_files": [
                "app/agent/sample.py",
            ],
        }

        (
            result,
            observations,
            mocked_apply,
        ) = self.invoke_with_fake_executor(
            agent=agent,
            evidence=self.evidence(),
            arguments=arguments,
        )

        self.assertTrue(
            result.approved
        )

        self.assertTrue(
            result.applied
        )

        self.assertEqual(
            observations[
                "executor_calls"
            ],
            1,
        )

        self.assertEqual(
            len(confirmations),
            1,
        )

        self.assertEqual(
            confirmations[0][0],
            "apply_verified_repair",
        )

        self.assertEqual(
            confirmations[0][1],
            arguments,
        )

        mocked_apply.assert_called_once()

    def test_user_denial_is_forwarded_once(
        self
    ):
        confirmations = []

        def deny(
            tool_name,
            arguments,
        ):
            confirmations.append(
                (
                    tool_name,
                    arguments,
                )
            )

            return False

        agent = self.agent(
            confirmation_callback=deny
        )

        (
            result,
            observations,
            mocked_apply,
        ) = self.invoke_with_fake_executor(
            agent=agent,
            evidence=self.evidence(),
        )

        self.assertFalse(
            result.approved
        )

        self.assertEqual(
            observations[
                "executor_calls"
            ],
            1,
        )

        self.assertEqual(
            len(confirmations),
            1,
        )

        mocked_apply.assert_called_once()

    def test_exact_evidence_objects_are_forwarded(
        self
    ):
        agent = self.agent(
            confirmation_callback=(
                lambda tool, arguments:
                True
            )
        )

        evidence = self.evidence()

        captured = {}

        def fake_apply(
            _executor,
            **kwargs,
        ):
            captured.update(
                kwargs
            )

            return self.result(
                approved=True
            )

        with patch.object(
            RepairApplyExecutor,
            "apply",
            autospec=True,
            side_effect=fake_apply,
        ) as mocked_apply:
            result = (
                agent
                .apply_verified_repair(
                    **evidence
                )
            )

        self.assertTrue(
            result.applied
        )

        for key, value in (
            evidence.items()
        ):
            self.assertIs(
                captured[key],
                value,
            )

        self.assertTrue(
            callable(
                captured[
                    "confirmation_requester"
                ]
            )
        )

        mocked_apply.assert_called_once()

    def test_repair_apply_is_not_registered_as_model_tool(
        self
    ):
        agent = self.agent(
            confirmation_callback=(
                lambda tool, arguments:
                True
            )
        )

        self.assertTrue(
            hasattr(
                agent,
                "apply_verified_repair",
            )
        )

        self.assertNotIn(
            "apply_verified_repair",
            agent.tool_registry,
        )


if __name__ == "__main__":
    unittest.main()
