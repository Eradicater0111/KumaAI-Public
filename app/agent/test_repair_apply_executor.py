from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.repair_apply_executor import (
    RepairApplyExecutor,
)
from app.agent.repair_apply_request import (
    RepairApplyRequestBuilder,
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
    RepairWorkspaceError,
)


class FailSecondReplaceExecutor(
    RepairApplyExecutor
):
    """
    Inject one failure after the first real source replacement.

    Later calls are allowed so rollback itself can proceed.
    """

    def __init__(self):
        super().__init__()
        self.replace_calls = 0
        self.injected = False

    def _atomic_replace(
        self,
        *,
        target: Path,
        content: bytes,
        mode: int,
    ) -> None:
        self.replace_calls += 1

        if (
            self.replace_calls == 2
            and not self.injected
        ):
            self.injected = True

            raise OSError(
                "injected mid-transaction failure"
            )

        return (
            RepairApplyExecutor
            ._atomic_replace(
                target=target,
                content=content,
                mode=mode,
            )
        )


class FailPostApplyVerifyExecutor(
    RepairApplyExecutor
):

    def _post_apply_verify(
        self,
        *,
        source_root: Path,
        expected_head: str,
        candidate_payloads: dict[
            str,
            bytes,
        ],
        changed_files: tuple[str, ...],
    ) -> None:
        raise RepairWorkspaceError(
            "injected post-apply verification failure"
        )


class TestRepairApplyExecutor(
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
            / "other.py"
        ).write_text(
            "OTHER = 1\n",
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
                "    def test_sample(self):\n"
                "        self.assertTrue(True)\n"
            ),
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

        # Preserve a non-default executable mode through
        # successful application and rollback testing.
        os.chmod(
            agent / "sample.py",
            0o744,
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
                    summary="Repair sample and other.",
                    rationale=(
                        "Verified isolated repair."
                    ),
                    target_files=(
                        "app/agent/sample.py",
                        "app/agent/other.py",
                    ),
                    permission_level=(
                        PermissionLevel.SAFE
                    ),
                )
            )
        )

        self.original_bytes = {
            path: (
                self.repo
                / path
            ).read_bytes()
            for path in (
                "app/agent/sample.py",
                "app/agent/other.py",
            )
        }

        self.original_modes = {
            path: stat.S_IMODE(
                (
                    self.repo
                    / path
                ).stat().st_mode
            )
            for path in (
                "app/agent/sample.py",
                "app/agent/other.py",
            )
        }

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

    def status(
        self,
    ) -> str:
        return (
            self.git(
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                cwd=self.repo,
            )
            .stdout
        )

    def head(
        self,
    ) -> str:
        return (
            self.git(
                "rev-parse",
                "--verify",
                "HEAD",
                cwd=self.repo,
            )
            .stdout
            .strip()
        )

    def active_journal(
        self,
    ) -> Path:
        return (
            self.repo
            / ".git"
            / "kuma-repair-rollback"
            / "active"
        )

    def assert_original_source(
        self,
    ):
        for (
            relative_path,
            original,
        ) in self.original_bytes.items():
            target = (
                self.repo
                / relative_path
            )

            self.assertEqual(
                target.read_bytes(),
                original,
            )

            self.assertEqual(
                stat.S_IMODE(
                    target.stat().st_mode
                ),
                self.original_modes[
                    relative_path
                ],
            )

    def prepare(
        self,
        workspace: RepairWorkspace,
    ):
        (
            workspace.root
            / "app"
            / "agent"
            / "sample.py"
        ).write_text(
            "VALUE = 2\n",
            encoding="utf-8",
        )

        (
            workspace.root
            / "app"
            / "agent"
            / "other.py"
        ).write_text(
            "OTHER = 2\n",
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

        execution_results = tuple(
            RepairExecutionResult(
                executed=True,
                success=True,
                reason="contained success",
                relative_path=relative_path,
                returncode=0,
            )
            for relative_path
            in validation.changed_files
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

        verification = (
            RepairResultVerifier().verify(
                workspace=workspace,
                decision=self.decision,
                validation=validation,
                selection=selection,
                handoff=handoff,
                execution_results=(
                    execution_results
                ),
                test_result=test_result,
            )
        )

        self.assertTrue(
            verification.evidence_verified,
            verification.reason,
        )

        request_result = (
            RepairApplyRequestBuilder().build(
                decision=self.decision,
                verification=verification,
            )
        )

        self.assertTrue(
            request_result
            .ready_for_confirmation,
            request_result.reason,
        )

        self.assertIsNotNone(
            request_result.request
        )

        return (
            validation,
            selection,
            handoff,
            execution_results,
            test_result,
            verification,
            request_result.request,
        )

    def apply(
        self,
        *,
        workspace,
        evidence,
        confirmation_requester,
        executor=None,
        request=None,
    ):
        (
            validation,
            selection,
            handoff,
            execution_results,
            test_result,
            verification,
            real_request,
        ) = evidence

        return (
            executor
            or RepairApplyExecutor()
        ).apply(
            workspace=workspace,
            decision=self.decision,
            validation=validation,
            selection=selection,
            handoff=handoff,
            execution_results=(
                execution_results
            ),
            test_result=test_result,
            verification=verification,
            request=(
                request
                if request is not None
                else real_request
            ),
            confirmation_requester=(
                confirmation_requester
            ),
        )

    def prime_prepared_journal(
        self,
        *,
        executor: RepairApplyExecutor,
        workspace: RepairWorkspace,
        request,
    ):
        source_root = (
            workspace.source_root
            .resolve()
        )

        candidate_payloads = (
            executor._candidate_bytes(
                workspace_root=(
                    workspace.root.resolve()
                ),
                changed_files=(
                    request.changed_files
                ),
            )
        )

        snapshots = (
            executor._snapshot_source(
                source_root=source_root,
                changed_files=(
                    request.changed_files
                ),
            )
        )

        executor._write_journal(
            source_root=source_root,
            request=request,
            snapshots=snapshots,
            candidate_payloads=(
                candidate_payloads
            ),
        )

        return (
            source_root,
            candidate_payloads,
            snapshots,
        )

    def test_denial_performs_zero_source_writes(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            calls = []

            def deny(
                action,
                arguments,
            ):
                calls.append(
                    (
                        action,
                        arguments,
                    )
                )
                return False

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=deny,
            )

            self.assertFalse(
                result.applied
            )

            self.assertFalse(
                result.attempted
            )

            self.assertEqual(
                len(calls),
                1,
            )

            self.assert_original_source()

            self.assertEqual(
                self.status(),
                "",
            )

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_missing_confirmation_requester_performs_zero_writes(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=None,
            )

            self.assertFalse(
                result.applied
            )

            self.assertFalse(
                result.attempted
            )

            self.assert_original_source()

            self.assertEqual(
                self.status(),
                "",
            )

    def test_dirty_source_blocks_before_confirmation(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            (
                self.repo
                / "unexpected.txt"
            ).write_text(
                "dirty\n",
                encoding="utf-8",
            )

            calls = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    calls.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertEqual(
                calls,
                [],
            )

            self.assert_original_source()

    def test_changed_head_blocks_before_confirmation(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            old_head = self.head()

            (
                self.repo
                / "README.md"
            ).write_text(
                "new commit\n",
                encoding="utf-8",
            )

            self.git(
                "add",
                "README.md",
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
                "move head",
                cwd=self.repo,
            )

            self.assertNotEqual(
                self.head(),
                old_head,
            )

            calls = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    calls.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertEqual(
                calls,
                [],
            )

    def test_changed_candidate_blocks_before_confirmation(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            (
                workspace.root
                / "app"
                / "agent"
                / "sample.py"
            ).write_text(
                "VALUE = 999\n",
                encoding="utf-8",
            )

            calls = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    calls.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertEqual(
                calls,
                [],
            )

            self.assert_original_source()

    def test_forged_request_blocks_before_confirmation(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            request = evidence[-1]

            forged = replace(
                request,
                request_digest=(
                    "0" * 64
                ),
            )

            calls = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                request=forged,
                confirmation_requester=(
                    lambda action, arguments:
                    calls.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertEqual(
                calls,
                [],
            )

            self.assert_original_source()

    def test_source_change_while_user_decides_invalidates_approval(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            def approve_but_edit_source(
                action,
                arguments,
            ):
                (
                    self.repo
                    / "app"
                    / "agent"
                    / "sample.py"
                ).write_text(
                    "USER_EDIT = 1\n",
                    encoding="utf-8",
                )

                return True

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    approve_but_edit_source
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertTrue(
                result.approved
            )

            self.assertEqual(
                (
                    self.repo
                    / "app"
                    / "agent"
                    / "sample.py"
                ).read_text(
                    encoding="utf-8"
                ),
                "USER_EDIT = 1\n",
            )

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_candidate_change_while_user_decides_invalidates_approval(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            def approve_but_change_candidate(
                action,
                arguments,
            ):
                (
                    workspace.root
                    / "app"
                    / "agent"
                    / "sample.py"
                ).write_text(
                    "VALUE = 777\n",
                    encoding="utf-8",
                )

                return True

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    approve_but_change_candidate
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertTrue(
                result.approved
            )

            self.assert_original_source()

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_successful_approved_apply_is_exact_and_uncommitted(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            request = evidence[-1]

            candidate_bytes = {
                relative_path: (
                    workspace.root
                    / relative_path
                ).read_bytes()
                for relative_path
                in request.changed_files
            }

            old_head = self.head()

            confirmations = []

            def approve(
                action,
                arguments,
            ):
                confirmations.append(
                    (
                        action,
                        arguments,
                    )
                )

                return True

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=approve,
            )

            self.assertTrue(
                result.applied,
                result.reason,
            )

            self.assertTrue(
                result.approved
            )

            self.assertTrue(
                result.attempted
            )

            self.assertFalse(
                result.rolled_back
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
                confirmations[0][1][
                    "request_digest"
                ],
                request.request_digest,
            )

            for (
                relative_path,
                payload,
            ) in candidate_bytes.items():
                self.assertEqual(
                    (
                        self.repo
                        / relative_path
                    ).read_bytes(),
                    payload,
                )

            self.assertEqual(
                self.head(),
                old_head,
            )

            changed = set(
                filter(
                    None,
                    self.git(
                        "diff",
                        "--name-only",
                        "HEAD",
                        "--",
                        cwd=self.repo,
                    )
                    .stdout
                    .splitlines(),
                )
            )

            self.assertEqual(
                changed,
                set(
                    request.changed_files
                ),
            )

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_mid_transaction_failure_restores_exact_snapshot(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    True
                ),
                executor=(
                    FailSecondReplaceExecutor()
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertTrue(
                result.rolled_back
            )

            self.assertFalse(
                result.rollback_failed
            )

            self.assert_original_source()

            self.assertEqual(
                self.status(),
                "",
            )

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_post_apply_verification_failure_rolls_back(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    True
                ),
                executor=(
                    FailPostApplyVerifyExecutor()
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertTrue(
                result.rolled_back
            )

            self.assertFalse(
                result.rollback_failed
            )

            self.assert_original_source()

            self.assertEqual(
                self.status(),
                "",
            )

    def test_prepared_crash_journal_is_rolled_back_on_restart(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            request = evidence[-1]

            executor = (
                RepairApplyExecutor()
            )

            (
                source_root,
                candidate_payloads,
                snapshots,
            ) = self.prime_prepared_journal(
                executor=executor,
                workspace=workspace,
                request=request,
            )

            first = (
                request.changed_files[0]
            )

            snapshot_by_path = {
                snapshot.relative_path:
                snapshot
                for snapshot in snapshots
            }

            RepairApplyExecutor._atomic_replace(
                target=(
                    source_root
                    / first
                ),
                content=(
                    candidate_payloads[
                        first
                    ]
                ),
                mode=(
                    snapshot_by_path[
                        first
                    ].mode
                ),
            )

            confirmations = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    confirmations.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
                executor=(
                    RepairApplyExecutor()
                ),
            )

            self.assertTrue(
                result
                .recovered_interrupted_apply
            )

            self.assertTrue(
                result.rolled_back
            )

            self.assertFalse(
                result.applied
            )

            self.assertFalse(
                result.recovery_blocked
            )

            self.assertEqual(
                confirmations,
                [],
            )

            self.assert_original_source()

            self.assertEqual(
                self.status(),
                "",
            )

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_applied_crash_journal_preserves_verified_repair(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            request = evidence[-1]

            executor = (
                RepairApplyExecutor()
            )

            (
                source_root,
                candidate_payloads,
                snapshots,
            ) = self.prime_prepared_journal(
                executor=executor,
                workspace=workspace,
                request=request,
            )

            snapshot_by_path = {
                snapshot.relative_path:
                snapshot
                for snapshot in snapshots
            }

            for relative_path in (
                request.changed_files
            ):
                RepairApplyExecutor._atomic_replace(
                    target=(
                        source_root
                        / relative_path
                    ),
                    content=(
                        candidate_payloads[
                            relative_path
                        ]
                    ),
                    mode=(
                        snapshot_by_path[
                            relative_path
                        ].mode
                    ),
                )

            executor._post_apply_verify(
                source_root=source_root,
                expected_head=(
                    request.source_head
                ),
                candidate_payloads=(
                    candidate_payloads
                ),
                changed_files=(
                    request.changed_files
                ),
            )

            executor._mark_journal_applied(
                source_root=source_root
            )

            self.assertTrue(
                self.active_journal()
                .exists()
            )

            confirmations = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    confirmations.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
                executor=(
                    RepairApplyExecutor()
                ),
            )

            self.assertTrue(
                result
                .recovered_interrupted_apply
            )

            self.assertTrue(
                result.applied
            )

            self.assertFalse(
                result.rolled_back
            )

            self.assertFalse(
                result.recovery_blocked
            )

            self.assertEqual(
                confirmations,
                [],
            )

            for (
                relative_path,
                payload,
            ) in candidate_payloads.items():
                self.assertEqual(
                    (
                        self.repo
                        / relative_path
                    ).read_bytes(),
                    payload,
                )

            self.assertFalse(
                self.active_journal()
                .exists()
            )

    def test_ambiguous_prepared_recovery_refuses_to_overwrite(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            request = evidence[-1]

            executor = (
                RepairApplyExecutor()
            )

            (
                source_root,
                _,
                _,
            ) = self.prime_prepared_journal(
                executor=executor,
                workspace=workspace,
                request=request,
            )

            first = (
                request.changed_files[0]
            )

            ambiguous = (
                b"USER_OR_UNKNOWN_EDIT = 1\n"
            )

            (
                source_root
                / first
            ).write_bytes(
                ambiguous
            )

            confirmations = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    confirmations.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
                executor=(
                    RepairApplyExecutor()
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertTrue(
                result.recovery_blocked
            )

            self.assertFalse(
                result.rolled_back
            )

            self.assertEqual(
                confirmations,
                [],
            )

            self.assertEqual(
                (
                    source_root
                    / first
                ).read_bytes(),
                ambiguous,
            )

            self.assertTrue(
                self.active_journal()
                .exists()
            )

    def test_corrupt_journal_fails_closed_without_source_mutation(
        self
    ):
        with RepairWorkspace(
            self.repo
        ) as workspace:
            evidence = self.prepare(
                workspace
            )

            request = evidence[-1]

            executor = (
                RepairApplyExecutor()
            )

            self.prime_prepared_journal(
                executor=executor,
                workspace=workspace,
                request=request,
            )

            (
                self.active_journal()
                / "state"
            ).write_text(
                "corrupt-state\n",
                encoding="utf-8",
            )

            confirmations = []

            result = self.apply(
                workspace=workspace,
                evidence=evidence,
                confirmation_requester=(
                    lambda action, arguments:
                    confirmations.append(
                        (
                            action,
                            arguments,
                        )
                    )
                    or True
                ),
                executor=(
                    RepairApplyExecutor()
                ),
            )

            self.assertFalse(
                result.applied
            )

            self.assertTrue(
                result.recovery_blocked
            )

            self.assertEqual(
                confirmations,
                [],
            )

            self.assert_original_source()

            self.assertTrue(
                self.active_journal()
                .exists()
            )


class TestRepairApplyExecutorContracts(
    unittest.TestCase
):

    def test_invalid_constructor_limits_are_rejected(
        self
    ):
        for keyword in (
            "git_timeout_seconds",
            "max_file_bytes",
        ):
            for value in (
                0,
                -1,
                True,
                1.5,
                "10",
            ):
                with self.subTest(
                    keyword=keyword,
                    value=value,
                ):
                    with self.assertRaises(
                        ValueError
                    ):
                        RepairApplyExecutor(
                            **{
                                keyword:
                                value
                            }
                        )


if __name__ == "__main__":
    unittest.main()
