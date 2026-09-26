from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import subprocess

from app.agent.repair_policy import RepairDecision
from app.agent.repair_test_selector import (
    RepairTestSelectionResult,
    RepairTestSelector,
)
from app.agent.repair_validator import (
    RepairValidationResult,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairTestEvidence:
    """
    Immutable integrity evidence for one selected verification test.
    """

    relative_path: str
    committed_blob: str
    working_blob: str


@dataclass(frozen=True)
class RepairTestHandoffResult:
    """
    Immutable evidence prepared immediately before future contained
    repair-test execution.

    ready=True does not execute tests and does not authorize repair
    application to KUMA's main checkout.
    """

    ready: bool
    reason: str
    source_head: str = ""
    validation_digest: str = ""
    test_files: tuple[str, ...] = ()
    test_evidence: tuple[
        RepairTestEvidence,
        ...,
    ] = ()


class RepairTestHandoff:
    """
    Fail-closed 6C.5B integrity boundary.

    It:
    - requires an active RepairWorkspace
    - requires a valid RepairDecision
    - requires successful static validation evidence
    - requires a successful deterministic test selection
    - independently re-runs RepairTestSelector
    - requires exact selected-test agreement
    - fingerprints the candidate diff
    - verifies every selected test against committed HEAD content
    - records exact committed and working-tree Git blob identities
    - executes no candidate code
    - executes no tests
    - performs no main-checkout mutation
    """

    def __init__(
        self,
        *,
        git_timeout_seconds: int = 30,
    ):
        if (
            type(git_timeout_seconds) is not int
            or git_timeout_seconds < 1
        ):
            raise ValueError(
                "git_timeout_seconds must be a positive integer."
            )

        self.git_timeout_seconds = (
            git_timeout_seconds
        )

    @staticmethod
    def _reject(
        reason: str,
    ) -> RepairTestHandoffResult:
        return RepairTestHandoffResult(
            ready=False,
            reason=reason,
        )

    def _run_git(
        self,
        root: Path,
        *args: str,
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    *args,
                ],
                capture_output=True,
                text=True,
                timeout=self.git_timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RepairWorkspaceError(
                "Git operation timed out during "
                "repair-test integrity handoff."
            ) from error
        except OSError as error:
            raise RepairWorkspaceError(
                "Could not execute Git during "
                f"repair-test integrity handoff: {error}"
            ) from error

    @staticmethod
    def _git_output(
        result: subprocess.CompletedProcess,
    ) -> str:
        return (
            (result.stdout or "").strip()
            or (result.stderr or "").strip()
        )

    def _require_git_success(
        self,
        result: subprocess.CompletedProcess,
        *,
        operation: str,
    ) -> str:
        if result.returncode != 0:
            detail = (
                self._git_output(
                    result
                )
                or "unknown Git error"
            )

            raise RepairWorkspaceError(
                f"{operation} failed: {detail}"
            )

        payload = (
            result.stdout
            or ""
        ).strip()

        if not payload:
            raise RepairWorkspaceError(
                f"{operation} returned no evidence."
            )

        return payload

    @staticmethod
    def _valid_blob_oid(
        value: str,
    ) -> bool:
        if (
            type(value) is not str
            or len(value) not in {
                40,
                64,
            }
        ):
            return False

        return all(
            character
            in "0123456789abcdef"
            for character in value
        )

    def prepare(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        selection: RepairTestSelectionResult,
    ) -> RepairTestHandoffResult:
        if not isinstance(
            workspace,
            RepairWorkspace,
        ):
            return self._reject(
                "Repair workspace contract is invalid."
            )

        if not isinstance(
            decision,
            RepairDecision,
        ):
            return self._reject(
                "Repair decision contract is invalid."
            )

        if not isinstance(
            validation,
            RepairValidationResult,
        ):
            return self._reject(
                "Repair validation contract is invalid."
            )

        if not isinstance(
            selection,
            RepairTestSelectionResult,
        ):
            return self._reject(
                "Repair test-selection contract is invalid."
            )

        if (
            not decision
            .eligible_for_isolated_evaluation
        ):
            return self._reject(
                "Repair decision does not authorize "
                "isolated candidate evaluation."
            )

        if (
            decision
            .automatic_main_checkout_apply
        ):
            return self._reject(
                "Repair decision illegally claims "
                "automatic main-checkout authority."
            )

        if validation.valid is not True:
            return self._reject(
                "Repair-test handoff requires successful "
                "static validation."
            )

        if (
            type(validation.diff) is not str
            or not validation.diff.strip()
        ):
            return self._reject(
                "Repair-test handoff requires immutable "
                "candidate diff evidence."
            )

        if selection.selected is not True:
            return self._reject(
                "Repair-test handoff requires successful "
                "deterministic test selection."
            )

        if (
            type(selection.test_files) is not tuple
            or not selection.test_files
        ):
            return self._reject(
                "Repair-test handoff contains no immutable "
                "selected-test evidence."
            )

        try:
            info = workspace.info
        except RepairWorkspaceError as error:
            return self._reject(
                "Repair workspace is not active: "
                f"{error}"
            )

        root = (
            info.workspace_root
            .resolve()
        )

        current_selection = (
            RepairTestSelector(
                git_timeout_seconds=(
                    self.git_timeout_seconds
                )
            ).select(
                workspace=workspace,
                decision=decision,
                validation=validation,
            )
        )

        if current_selection.selected is not True:
            return self._reject(
                "Current deterministic test selection "
                "no longer passes integrity checks."
            )

        if (
            selection.test_files
            != current_selection.test_files
        ):
            return self._reject(
                "Provided repair-test selection is stale "
                "or does not match current deterministic "
                "selection."
            )

        validation_digest = hashlib.sha256(
            validation.diff.encode(
                "utf-8",
                errors="strict",
            )
        ).hexdigest()

        evidence: list[
            RepairTestEvidence
        ] = []

        try:
            for relative_path in (
                current_selection.test_files
            ):
                committed_blob = (
                    self._require_git_success(
                        self._run_git(
                            root,
                            "rev-parse",
                            f"HEAD:{relative_path}",
                        ),
                        operation=(
                            "Committed test-blob "
                            "verification"
                        ),
                    )
                )

                working_blob = (
                    self._require_git_success(
                        self._run_git(
                            root,
                            "hash-object",
                            "--no-filters",
                            "--",
                            relative_path,
                        ),
                        operation=(
                            "Working test-blob "
                            "verification"
                        ),
                    )
                )

                committed_blob = (
                    committed_blob.lower()
                )
                working_blob = (
                    working_blob.lower()
                )

                if (
                    not self._valid_blob_oid(
                        committed_blob
                    )
                    or not self._valid_blob_oid(
                        working_blob
                    )
                ):
                    return self._reject(
                        "Repair-test Git blob evidence "
                        "is malformed."
                    )

                if (
                    committed_blob
                    != working_blob
                ):
                    return self._reject(
                        "Selected verification test does "
                        "not exactly match committed HEAD."
                    )

                evidence.append(
                    RepairTestEvidence(
                        relative_path=(
                            relative_path
                        ),
                        committed_blob=(
                            committed_blob
                        ),
                        working_blob=(
                            working_blob
                        ),
                    )
                )

        except RepairWorkspaceError as error:
            return self._reject(
                "Repair-test handoff failed closed: "
                f"{error}"
            )

        return RepairTestHandoffResult(
            ready=True,
            reason=(
                "Repair-test handoff passed current "
                "selection and exact Git blob-integrity "
                "verification. Tests have not been "
                "executed and main-checkout application "
                "is not authorized."
            ),
            source_head=(
                info.source_head
            ),
            validation_digest=(
                validation_digest
            ),
            test_files=(
                current_selection.test_files
            ),
            test_evidence=tuple(
                evidence
            ),
        )
