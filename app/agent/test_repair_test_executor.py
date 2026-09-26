from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import pytest

from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.repair_execution_sandbox import (
    RepairExecutionSandbox,
)
from app.agent.repair_policy import (
    RepairPolicy,
    RepairProposal,
)
from app.agent.repair_test_executor import (
    RepairTestExecutionResult,
    RepairTestExecutor,
)
from app.agent.repair_test_handoff import (
    RepairTestHandoff,
    RepairTestHandoffResult,
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


class TestRepairTestExecutor(
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
            """
import unittest

import pytest

from app.agent import sample


class TestSample(unittest.TestCase):

    def test_optional_trigger(self):
        trigger = getattr(
            sample,
            "trigger",
            None,
        )

        if trigger is not None:
            trigger()

        self.assertTrue(True)

    def test_value_is_positive(self):
        self.assertGreaterEqual(
            sample.VALUE,
            1,
        )
""".lstrip(),
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
        check: bool = True,
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
            check=check,
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
        source: str,
    ):
        self.candidate(
            workspace,
            "app/agent/sample.py",
        ).write_text(
            source,
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

        return (
            validation,
            selection,
            handoff,
        )

    def execute(
        self,
        workspace: RepairWorkspace,
        validation,
        selection,
        handoff,
        *,
        sandbox=None,
    ):
        return RepairTestExecutor(
            sandbox=sandbox
        ).execute(
            workspace=workspace,
            decision=self.decision,
            validation=validation,
            selection=selection,
            handoff=handoff,
        )

    @pytest.mark.native_sandbox
    def test_passing_candidate_tests_pass(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                "VALUE = 2\n",
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertTrue(
                result.passed,
                result.stderr,
            )

            self.assertEqual(
                result.tests_run,
                2,
            )

            self.assertEqual(
                result.failures,
                0,
            )

            self.assertEqual(
                result.errors,
                0,
            )

            self.assertIn(
                "does not authorize",
                result.reason,
            )

    @pytest.mark.native_sandbox
    def test_failing_candidate_tests_fail(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                "VALUE = 0\n",
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertFalse(
                result.passed
            )

            self.assertEqual(
                result.tests_run,
                2,
            )

            self.assertGreaterEqual(
                result.failures,
                1,
            )

    def test_not_ready_handoff_never_executes(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                _,
            ) = self.prepare(
                workspace,
                "VALUE = 2\n",
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                RepairTestHandoffResult(
                    ready=False,
                    reason="blocked",
                ),
            )

            self.assertFalse(
                result.executed
            )

    def test_forged_handoff_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                "VALUE = 2\n",
            )

            forged = (
                RepairTestHandoffResult(
                    ready=True,
                    reason="forged",
                    source_head=(
                        handoff.source_head
                    ),
                    validation_digest=(
                        "0" * 64
                    ),
                    test_files=(
                        handoff.test_files
                    ),
                    test_evidence=(
                        handoff.test_evidence
                    ),
                )
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                forged,
            )

            self.assertFalse(
                result.executed
            )

            self.assertIn(
                "stale",
                result.reason.lower(),
            )

    def test_test_modified_after_handoff_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                "VALUE = 2\n",
            )

            self.candidate(
                workspace,
                "app/agent/test_sample.py",
            ).write_text(
                "import unittest\n",
                encoding="utf-8",
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
            )

            self.assertFalse(
                result.executed
            )

    def test_candidate_modified_after_handoff_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                "VALUE = 2\n",
            )

            self.candidate(
                workspace,
                "app/agent/sample.py",
            ).write_text(
                "VALUE = 3\n",
                encoding="utf-8",
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
            )

            self.assertFalse(
                result.executed
            )

    @pytest.mark.native_sandbox
    def test_clean_exit_without_report_fails_closed(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                """
import os

VALUE = 2


def trigger():
    os._exit(0)
""".lstrip(),
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertFalse(
                result.passed
            )

            self.assertEqual(
                result.returncode,
                0,
            )

            self.assertIn(
                "completion report",
                result.reason,
            )

    @pytest.mark.native_sandbox
    def test_timeout_fails_closed(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                """
VALUE = 2


def trigger():
    while True:
        pass
""".lstrip(),
            )

            sandbox = (
                RepairExecutionSandbox(
                    wall_timeout_seconds=2,
                    cpu_timeout_seconds=1,
                )
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
                sandbox=sandbox,
            )

            self.assertTrue(
                result.executed,
                result.reason,
            )

            self.assertFalse(
                result.passed
            )

            self.assertTrue(
                result.timed_out
                or (
                    result.returncode
                    is not None
                    and result.returncode
                    != 0
                )
            )

    @pytest.mark.native_sandbox
    def test_main_checkout_remains_unchanged(
        self
    ):
        source_file = (
            self.repo
            / "app"
            / "agent"
            / "sample.py"
        )

        original = (
            source_file.read_text(
                encoding="utf-8"
            )
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
                handoff,
            ) = self.prepare(
                workspace,
                "VALUE = 999\n",
            )

            result = self.execute(
                workspace,
                validation,
                selection,
                handoff,
            )

            self.assertTrue(
                result.passed,
                result.stderr,
            )

        self.assertEqual(
            source_file.read_text(
                encoding="utf-8"
            ),
            original,
        )

    def test_result_contract_is_immutable(
        self
    ):
        result = (
            RepairTestExecutionResult(
                executed=False,
                passed=False,
                reason="blocked",
            )
        )

        with self.assertRaises(
            Exception
        ):
            result.passed = True


class TestRepairTestExecutorContracts(
    unittest.TestCase
):

    def test_invalid_sandbox_is_rejected(
        self
    ):
        with self.assertRaises(
            ValueError
        ):
            RepairTestExecutor(
                sandbox="unsafe"
            )

    def test_invalid_git_timeout_is_rejected(
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
                    RepairTestExecutor(
                        git_timeout_seconds=value
                    )


if __name__ == "__main__":
    unittest.main()
