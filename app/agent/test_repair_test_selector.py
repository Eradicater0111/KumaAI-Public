from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from app.agent.permissions import PermissionLevel
from app.agent.repair_policy import (
    RepairPolicy,
    RepairProposal,
)
from app.agent.repair_test_selector import (
    RepairTestSelectionResult,
    RepairTestSelector,
)
from app.agent.repair_validator import (
    RepairValidationResult,
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
)


class TestRepairTestSelector(
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

        (
            agent
            / "other.py"
        ).write_text(
            "OTHER = 1\n",
            encoding="utf-8",
        )

        (
            agent
            / "test_other.py"
        ).write_text(
            (
                "import unittest\n"
                "\n"
                "class TestOther(unittest.TestCase):\n"
                "    def test_other(self):\n"
                "        self.assertTrue(True)\n"
            ),
            encoding="utf-8",
        )

        (
            agent
            / "orphan.py"
        ).write_text(
            "ORPHAN = 1\n",
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
    def decision_for(
        *targets: str,
    ):
        return RepairPolicy().evaluate(
            RepairProposal(
                summary="Repair candidate.",
                rationale=(
                    "Observed deterministic failure."
                ),
                target_files=tuple(
                    targets
                ),
                permission_level=(
                    PermissionLevel.SAFE
                ),
            )
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
        decision,
        changes: dict[str, str],
    ) -> RepairValidationResult:
        for path, source in changes.items():
            self.candidate(
                workspace,
                path,
            ).write_text(
                source,
                encoding="utf-8",
            )

        validation = (
            RepairValidator().validate(
                workspace=workspace,
                decision=decision,
            )
        )

        self.assertTrue(
            validation.valid,
            validation.reason,
        )

        return validation

    def test_exact_sibling_test_is_selected(
        self
    ):
        decision = self.decision_for(
            "app/agent/sample.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                decision,
                {
                    "app/agent/sample.py":
                    "VALUE = 2\n",
                },
            )

            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=validation,
                )
            )

            self.assertTrue(
                result.selected,
                result.reason,
            )

            self.assertEqual(
                result.test_files,
                (
                    "app/agent/test_sample.py",
                ),
            )

            self.assertIn(
                "not been executed",
                result.reason,
            )

    def test_multiple_sources_select_multiple_tests(
        self
    ):
        decision = self.decision_for(
            "app/agent/sample.py",
            "app/agent/other.py",
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                decision,
                {
                    "app/agent/sample.py":
                    "VALUE = 2\n",
                    "app/agent/other.py":
                    "OTHER = 2\n",
                },
            )

            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=validation,
                )
            )

            self.assertTrue(
                result.selected,
                result.reason,
            )

            self.assertEqual(
                result.test_files,
                (
                    "app/agent/test_other.py",
                    "app/agent/test_sample.py",
                ),
            )

    def test_missing_direct_test_fails_closed(
        self
    ):
        decision = self.decision_for(
            "app/agent/orphan.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                decision,
                {
                    "app/agent/orphan.py":
                    "ORPHAN = 2\n",
                },
            )

            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=validation,
                )
            )

            self.assertFalse(
                result.selected
            )

            self.assertEqual(
                result.test_files,
                (),
            )

    def test_modified_verification_test_is_rejected(
        self
    ):
        decision = self.decision_for(
            "app/agent/sample.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                decision,
                {
                    "app/agent/sample.py":
                    "VALUE = 2\n",
                },
            )

            self.candidate(
                workspace,
                "app/agent/test_sample.py",
            ).write_text(
                (
                    "import unittest\n"
                    "class T(unittest.TestCase):\n"
                    "    pass\n"
                ),
                encoding="utf-8",
            )

            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=validation,
                )
            )

            self.assertFalse(
                result.selected
            )

    def test_repair_of_test_module_is_rejected(
        self
    ):
        decision = self.decision_for(
            "app/agent/test_sample.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                decision,
                {
                    "app/agent/test_sample.py":
                    (
                        "import unittest\n"
                        "\n"
                        "VALUE = 2\n"
                    ),
                },
            )

            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=validation,
                )
            )

            self.assertFalse(
                result.selected
            )

    def test_stale_validation_is_rejected(
        self
    ):
        decision = self.decision_for(
            "app/agent/sample.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            validation = self.prepare(
                workspace,
                decision,
                {
                    "app/agent/sample.py":
                    "VALUE = 2\n",
                },
            )

            self.candidate(
                workspace,
                "app/agent/sample.py",
            ).write_text(
                "VALUE = 3\n",
                encoding="utf-8",
            )

            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=validation,
                )
            )

            self.assertFalse(
                result.selected
            )

            self.assertIn(
                "stale",
                result.reason.lower(),
            )

    def test_invalid_validation_is_rejected(
        self
    ):
        decision = self.decision_for(
            "app/agent/sample.py"
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:
            result = (
                RepairTestSelector().select(
                    workspace=workspace,
                    decision=decision,
                    validation=(
                        RepairValidationResult(
                            valid=False,
                            reason="invalid",
                        )
                    ),
                )
            )

            self.assertFalse(
                result.selected
            )

    def test_inactive_workspace_is_rejected(
        self
    ):
        decision = self.decision_for(
            "app/agent/sample.py"
        )

        workspace = RepairWorkspace(
            self.repo
        )

        result = (
            RepairTestSelector().select(
                workspace=workspace,
                decision=decision,
                validation=(
                    RepairValidationResult(
                        valid=True,
                        reason="forged",
                        changed_files=(
                            "app/agent/sample.py",
                        ),
                        diff="forged",
                    )
                ),
            )
        )

        self.assertFalse(
            result.selected
        )

    def test_result_contract_is_immutable(
        self
    ):
        result = RepairTestSelectionResult(
            selected=False,
            reason="blocked",
        )

        with self.assertRaises(
            Exception
        ):
            result.selected = True

    def test_constructor_rejects_invalid_timeout(
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
                    RepairTestSelector(
                        git_timeout_seconds=value
                    )


if __name__ == "__main__":
    unittest.main()
