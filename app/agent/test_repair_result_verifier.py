from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.repair_execution_sandbox import (
    RepairExecutionResult,
)
from app.agent.repair_policy import (
    RepairPolicy,
    RepairProposal,
)
from app.agent.repair_result_verifier import (
    RepairResultVerifier,
    RepairVerificationResult,
)
from app.agent.repair_test_executor import (
    RepairTestExecutionResult,
)
from app.agent.repair_test_handoff import (
    RepairTestHandoff,
)
from app.agent.repair_test_selector import (
    RepairTestSelector,
)
from app.agent.repair_validator import (
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
)


class TestRepairResultVerifier(
    unittest.TestCase
):

    def setUp(self):
        self.temp_dir = (
            tempfile.TemporaryDirectory()
        )

        self.root = Path(
            self.temp_dir.name
        )

        self.repo = (
            self.root
            / "source"
        )

        self.repo.mkdir()

        self.git(
            "init",
            "--quiet",
            cwd=self.repo,
        )

        agent = (
            self.repo
            / "app"
            / "agent"
        )

        agent.mkdir(
            parents=True
        )

        (
            self.repo
            / "app"
            / "__init__.py"
        ).write_text(
            "",
            encoding="utf-8",
        )

        (
            agent
            / "__init__.py"
        ).write_text(
            "",
            encoding="utf-8",
        )

        (
            agent
            / "sample.py"
        ).write_text(
            "VALUE = 1\n",
            encoding="utf-8",
        )

        (
            agent
            / "test_sample.py"
        ).write_text(
            (
                "import unittest\n"
                "\n"
                "class TestSample(unittest.TestCase):\n"
                "    def test_value(self):\n"
                "        self.assertTrue(True)\n"
            ),
            encoding="utf-8",
        )

        self.git(
            "add",
            ".",
            cwd=self.repo,
        )

        self.git(
            "-c",
            "user.name=KUMA Test",
            "-c",
            "user.email=kuma-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "initial",
            cwd=self.repo,
        )

        self.decision = (
            RepairPolicy().evaluate(
                RepairProposal(
                    summary="Repair sample.",
                    rationale=(
                        "Observed deterministic failure."
                    ),
                    target_files=(
                        "app/agent/sample.py",
                    ),
                    permission_level=(
                        PermissionLevel.SAFE
                    ),
                )
            )
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def git(
        *args: str,
        cwd: Path,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "git",
                *args,
            ],
            cwd=str(
                cwd
            ),
            capture_output=True,
            text=True,
            check=True,
            shell=False,
        )

    @staticmethod
    def candidate(
        workspace: RepairWorkspace,
        relative_path: str,
    ) -> Path:
        return (
            workspace.root
            / relative_path
        )

    def prepare(
        self,
        workspace: RepairWorkspace,
    ):
        self.candidate(
            workspace,
            "app/agent/sample.py",
        ).write_text(
            "VALUE = 2\n",
            encoding="utf-8",
        )

        validation = (
            RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )
        )

        self.assertTrue(
            validation.valid,
            validation.reason,
        )

        selection = (
            RepairTestSelector().select(
                workspace=workspace,
                decision=self.decision,
                validation=validation,
            )
        )

        self.assertTrue(
            selection.selected,
            selection.reason,
        )

        handoff = (
            RepairTestHandoff().prepare(
                workspace=workspace,
                decision=self.decision,
                validation=validation,
                selection=selection,
            )
        )

        self.assertTrue(
            handoff.ready,
            handoff.reason,
        )

        execution = RepairExecutionResult(
            executed=True,
            success=True,
            reason="contained success",
            relative_path=(
                "app/agent/sample.py"
            ),
            returncode=0,
        )

        test_result = (
            RepairTestExecutionResult(
                executed=True,
                passed=True,
                reason="tests passed",
                test_files=(
                    handoff.test_files
                ),
                tests_run=2,
                failures=0,
                errors=0,
                skipped=0,
                expected_failures=0,
                unexpected_successes=0,
                returncode=0,
            )
        )

        return (
            validation,
            selection,
            handoff,
            execution,
            test_result,
        )

    def verify(
        self,
        workspace,
        validation,
        selection,
        handoff,
        execution_results,
        test_result,
        *,
        decision=None,
    ):
        return RepairResultVerifier().verify(
            workspace=workspace,
            decision=(
                decision
                or self.decision
            ),
            validation=validation,
            selection=selection,
            handoff=handoff,
            execution_results=(
                execution_results
            ),
            test_result=test_result,
        )

    def test_valid_evidence_is_eligible_for_review(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertTrue(
                result.evidence_verified,
                result.reason,
            )

            self.assertTrue(
                result
                .eligible_for_apply_review
            )

            self.assertEqual(
                result.changed_files,
                (
                    "app/agent/sample.py",
                ),
            )

            self.assertEqual(
                result.executed_files,
                (
                    "app/agent/sample.py",
                ),
            )

            self.assertEqual(
                result.test_files,
                (
                    "app/agent/test_sample.py",
                ),
            )

            self.assertEqual(
                result.tests_run,
                2,
            )

            self.assertEqual(
                len(
                    result.evidence_digest
                ),
                64,
            )

            self.assertIn(
                "does not authorize",
                result.reason,
            )

    def test_failed_execution_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            execution = replace(
                execution,
                success=False,
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_missing_execution_coverage_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                _,
                test_result,
            ) = self.prepare(
                workspace
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_duplicate_execution_evidence_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_failed_tests_are_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            test_result = replace(
                test_result,
                passed=False,
                failures=1,
                returncode=1,
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_zero_tests_are_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            test_result = replace(
                test_result,
                tests_run=0,
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_test_limit_failure_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            test_result = replace(
                test_result,
                timed_out=True,
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_test_file_mismatch_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            test_result = replace(
                test_result,
                test_files=(
                    "app/agent/test_other.py",
                ),
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_candidate_modified_after_evidence_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            self.candidate(
                workspace,
                "app/agent/sample.py",
            ).write_text(
                "VALUE = 3\n",
                encoding="utf-8",
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_test_modified_after_evidence_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            self.candidate(
                workspace,
                "app/agent/test_sample.py",
            ).write_text(
                "import unittest\n",
                encoding="utf-8",
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_forged_handoff_digest_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            handoff = replace(
                handoff,
                validation_digest=(
                    "0" * 64
                ),
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_illegal_auto_apply_decision_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            unsafe_decision = replace(
                self.decision,
                automatic_main_checkout_apply=True,
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
                decision=unsafe_decision,
            )

            self.assertFalse(
                result.evidence_verified
            )

            self.assertFalse(
                result
                .eligible_for_apply_review
            )

    def test_boolean_test_count_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
                execution,
                test_result,
            ) = self.prepare(
                workspace
            )

            test_result = replace(
                test_result,
                tests_run=True,
            )

            result = self.verify(
                workspace,
                validation,
                selection,
                handoff,
                (
                    execution,
                ),
                test_result,
            )

            self.assertFalse(
                result.evidence_verified
            )

    def test_result_is_immutable(
        self
    ):
        result = RepairVerificationResult(
            evidence_verified=False,
            eligible_for_apply_review=False,
            reason="blocked",
        )

        with self.assertRaises(
            Exception
        ):
            result.evidence_verified = True

    def test_invalid_constructor_timeout_is_rejected(
        self
    ):
        for value in (
            0,
            -1,
            True,
            1.5,
            "30",
        ):
            with self.subTest(
                value=value
            ):
                with self.assertRaises(
                    ValueError
                ):
                    RepairResultVerifier(
                        git_timeout_seconds=value
                    )


if __name__ == "__main__":
    unittest.main()
