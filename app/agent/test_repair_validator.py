from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from app.agent.permissions import PermissionLevel
from app.agent.repair_policy import (
    RepairDecision,
    RepairPolicy,
    RepairProposal,
)
from app.agent.repair_validator import (
    RepairValidationResult,
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
)


class TestRepairValidator(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "source"
        self.repo.mkdir()

        self.git(
            "init",
            "--quiet",
            cwd=self.repo,
        )

        agent_dir = (
            self.repo
            / "app"
            / "agent"
        )
        agent_dir.mkdir(parents=True)

        (
            agent_dir
            / "sample.py"
        ).write_text(
            "VALUE = 1\n"
        )

        (
            agent_dir
            / "other.py"
        ).write_text(
            "OTHER = 1\n"
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

        proposal = RepairProposal(
            summary="Fix sample.",
            rationale="Observed deterministic failure.",
            target_files=(
                "app/agent/sample.py",
            ),
            permission_level=PermissionLevel.SAFE,
        )

        self.decision = RepairPolicy().evaluate(
            proposal
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
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=check,
            shell=False,
        )

    def candidate_file(
        self,
        workspace: RepairWorkspace,
        name: str = "sample.py",
    ) -> Path:
        return (
            workspace.root
            / "app"
            / "agent"
            / name
        )

    def test_valid_tracked_python_change_passes_static_validation(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = 2\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertTrue(
                result.valid
            )
            self.assertEqual(
                result.changed_files,
                (
                    "app/agent/sample.py",
                ),
            )
            self.assertIn(
                "VALUE = 2",
                result.diff,
            )
            self.assertIn(
                "not been executed",
                result.reason,
            )

    def test_no_change_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_change_outside_approved_scope_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace,
                "other.py",
            ).write_text(
                "OTHER = 2\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )
            self.assertIn(
                "app/agent/other.py",
                result.changed_files,
            )

    def test_untracked_file_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            (
                workspace.root
                / "app"
                / "agent"
                / "new.py"
            ).write_text(
                "NEW = True\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_deleted_target_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).unlink()

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_symlink_target_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            target = self.candidate_file(
                workspace
            )
            target.unlink()

            outside = (
                self.root
                / "outside.py"
            )
            outside.write_text(
                "VALUE = 999\n"
            )

            target.symlink_to(
                outside
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_syntax_error_is_rejected_without_execution(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            marker = (
                self.root
                / "should-not-exist"
            )

            self.candidate_file(
                workspace
            ).write_text(
                "def broken(:\n"
                f"    open({str(marker)!r}, 'w').write('x')\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )
            self.assertFalse(
                marker.exists()
            )

    def test_valid_candidate_code_is_compiled_but_not_executed(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            marker = (
                self.root
                / "should-not-exist"
            )

            self.candidate_file(
                workspace
            ).write_text(
                f"open({str(marker)!r}, 'w').write('x')\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertTrue(
                result.valid
            )
            self.assertFalse(
                marker.exists()
            )

    def test_candidate_commit_changes_head_and_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = 2\n"
            )

            self.git(
                "add",
                ".",
                cwd=workspace.root,
            )

            self.git(
                "-c",
                "user.name=KUMA Test",
                "-c",
                "user.email=kuma-test@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "candidate commit",
                cwd=workspace.root,
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )
            self.assertIn(
                "HEAD changed",
                result.reason,
            )

    def test_attached_branch_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.git(
                "switch",
                "--quiet",
                "-c",
                "candidate-branch",
                cwd=workspace.root,
            )

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = 2\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_inactive_workspace_is_rejected(self):
        workspace = RepairWorkspace(
            self.repo
        )

        result = RepairValidator().validate(
            workspace=workspace,
            decision=self.decision,
        )

        self.assertFalse(
            result.valid
        )

    def test_non_authorizing_decision_is_rejected(self):
        decision = RepairDecision(
            eligible_for_isolated_evaluation=False,
            automatic_main_checkout_apply=False,
            requires_human_approval=True,
            reason="Blocked.",
            normalized_target_files=(
                "app/agent/sample.py",
            ),
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = 2\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_illegal_apply_authority_is_rejected(self):
        decision = RepairDecision(
            eligible_for_isolated_evaluation=True,
            automatic_main_checkout_apply=True,
            requires_human_approval=False,
            reason="Malformed authority.",
            normalized_target_files=(
                "app/agent/sample.py",
            ),
        )

        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = 2\n"
            )

            result = RepairValidator().validate(
                workspace=workspace,
                decision=decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_oversized_source_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = " + repr("x" * 200)
            )

            result = RepairValidator(
                max_file_bytes=50
            ).validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_oversized_diff_is_rejected(self):
        with RepairWorkspace(
            self.repo
        ) as workspace:

            self.candidate_file(
                workspace
            ).write_text(
                "VALUE = " + repr("x" * 500)
            )

            result = RepairValidator(
                max_diff_chars=100
            ).validate(
                workspace=workspace,
                decision=self.decision,
            )

            self.assertFalse(
                result.valid
            )

    def test_invalid_limits_fail_closed(self):
        for kwargs in (
            {
                "git_timeout_seconds": 0,
            },
            {
                "max_file_bytes": True,
            },
            {
                "max_diff_chars": -1,
            },
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(
                    ValueError
                ):
                    RepairValidator(
                        **kwargs
                    )

    def test_result_contract_is_frozen(self):
        result = RepairValidationResult(
            valid=False,
            reason="Blocked.",
        )

        with self.assertRaises(Exception):
            result.reason = "Changed."


if __name__ == "__main__":
    unittest.main()
