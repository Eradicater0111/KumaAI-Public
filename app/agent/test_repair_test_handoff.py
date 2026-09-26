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
from app.agent.repair_test_handoff import (
    RepairTestEvidence,
    RepairTestHandoff,
    RepairTestHandoffResult,
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


class TestRepairTestHandoff(
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
                    summary="Fix sample.",
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

    def prepare_candidate(
        self,
        workspace: RepairWorkspace,
    ) -> tuple[
        RepairValidationResult,
        RepairTestSelectionResult,
    ]:
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

        return (
            validation,
            selection,
        )

    def test_valid_handoff_contains_blob_evidence(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
            ) = self.prepare_candidate(
                workspace
            )

            result = (
                RepairTestHandoff().prepare(
                    workspace=workspace,
                    decision=self.decision,
                    validation=validation,
                    selection=selection,
                )
            )

            self.assertTrue(
                result.ready,
                result.reason,
            )

            self.assertEqual(
                result.source_head,
                workspace.source_head,
            )

            self.assertEqual(
                result.test_files,
                (
                    "app/agent/test_sample.py",
                ),
            )

            self.assertEqual(
                len(
                    result.validation_digest
                ),
                64,
            )

            self.assertEqual(
                len(
                    result.test_evidence
                ),
                1,
            )

            evidence = (
                result.test_evidence[0]
            )

            self.assertEqual(
                evidence.relative_path,
                "app/agent/test_sample.py",
            )

            self.assertEqual(
                evidence.committed_blob,
                evidence.working_blob,
            )

            self.assertIn(
                len(
                    evidence.committed_blob
                ),
                {
                    40,
                    64,
                },
            )

    def test_failed_selection_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                _,
            ) = self.prepare_candidate(
                workspace
            )

            result = (
                RepairTestHandoff().prepare(
                    workspace=workspace,
                    decision=self.decision,
                    validation=validation,
                    selection=(
                        RepairTestSelectionResult(
                            selected=False,
                            reason="blocked",
                        )
                    ),
                )
            )

            self.assertFalse(
                result.ready
            )

    def test_forged_different_test_path_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                _,
            ) = self.prepare_candidate(
                workspace
            )

            forged = (
                RepairTestSelectionResult(
                    selected=True,
                    reason="forged",
                    test_files=(
                        "app/agent/test_fake.py",
                    ),
                )
            )

            result = (
                RepairTestHandoff().prepare(
                    workspace=workspace,
                    decision=self.decision,
                    validation=validation,
                    selection=forged,
                )
            )

            self.assertFalse(
                result.ready
            )

            self.assertIn(
                "stale",
                result.reason.lower(),
            )

    def test_test_modified_after_selection_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
            ) = self.prepare_candidate(
                workspace
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
                RepairTestHandoff().prepare(
                    workspace=workspace,
                    decision=self.decision,
                    validation=validation,
                    selection=selection,
                )
            )

            self.assertFalse(
                result.ready
            )

    def test_candidate_modified_after_selection_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            (
                validation,
                selection,
            ) = self.prepare_candidate(
                workspace
            )

            self.candidate(
                workspace,
                "app/agent/sample.py",
            ).write_text(
                "VALUE = 3\n",
                encoding="utf-8",
            )

            result = (
                RepairTestHandoff().prepare(
                    workspace=workspace,
                    decision=self.decision,
                    validation=validation,
                    selection=selection,
                )
            )

            self.assertFalse(
                result.ready
            )

    def test_invalid_validation_is_rejected(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            result = (
                RepairTestHandoff().prepare(
                    workspace=workspace,
                    decision=self.decision,
                    validation=(
                        RepairValidationResult(
                            valid=False,
                            reason="invalid",
                        )
                    ),
                    selection=(
                        RepairTestSelectionResult(
                            selected=True,
                            reason="forged",
                            test_files=(
                                "app/agent/test_sample.py",
                            ),
                        )
                    ),
                )
            )

            self.assertFalse(
                result.ready
            )

    def test_inactive_workspace_is_rejected(
        self
    ):
        workspace = RepairWorkspace(
            self.repo
        )

        result = (
            RepairTestHandoff().prepare(
                workspace=workspace,
                decision=self.decision,
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
                selection=(
                    RepairTestSelectionResult(
                        selected=True,
                        reason="forged",
                        test_files=(
                            "app/agent/test_sample.py",
                        ),
                    )
                ),
            )
        )

        self.assertFalse(
            result.ready
        )

    def test_handoff_result_is_immutable(
        self
    ):
        result = (
            RepairTestHandoffResult(
                ready=False,
                reason="blocked",
            )
        )

        with self.assertRaises(
            Exception
        ):
            result.ready = True

    def test_test_evidence_is_immutable(
        self
    ):
        evidence = RepairTestEvidence(
            relative_path=(
                "app/agent/test_sample.py"
            ),
            committed_blob="a" * 40,
            working_blob="a" * 40,
        )

        with self.assertRaises(
            Exception
        ):
            evidence.relative_path = "other"

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
                    RepairTestHandoff(
                        git_timeout_seconds=value
                    )


if __name__ == "__main__":
    unittest.main()
