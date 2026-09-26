from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from app.agent.repair_policy import RepairDecision
from app.agent.repair_validator import (
    RepairValidationResult,
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairTestSelectionResult:
    """
    Immutable evidence describing deterministic verification tests
    selected for one statically validated repair candidate.

    selected=True does not execute tests and does not authorize
    application to KUMA's main checkout.
    """

    selected: bool
    reason: str
    test_files: tuple[str, ...] = ()


class RepairTestSelector:
    """
    Fail-closed deterministic test selection for 6C.5A.

    Selection policy:
    - accepts only a current valid repair candidate
    - each changed production module must have an exact sibling test
    - foo.py maps only to test_foo.py
    - changed files may not themselves be test modules
    - selected tests must already be tracked by Git
    - selected tests must be unchanged from candidate HEAD
    - selected tests may not be part of the repair
    - no model decides test commands
    - no tests are executed here
    - no shell=True
    - no main-checkout mutation
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
    ) -> RepairTestSelectionResult:
        return RepairTestSelectionResult(
            selected=False,
            reason=reason,
            test_files=(),
        )

    @staticmethod
    def _path_is_within(
        path: Path,
        root: Path,
    ) -> bool:
        try:
            path.relative_to(
                root
            )
            return True
        except ValueError:
            return False

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
                "repair test selection."
            ) from error
        except OSError as error:
            raise RepairWorkspaceError(
                "Could not execute Git during "
                f"repair test selection: {error}"
            ) from error

    @staticmethod
    def _git_error(
        result: subprocess.CompletedProcess,
    ) -> str:
        return (
            (result.stderr or "").strip()
            or (result.stdout or "").strip()
            or "unknown Git error"
        )

    @staticmethod
    def _validation_matches(
        expected: RepairValidationResult,
        current: RepairValidationResult,
    ) -> bool:
        return (
            expected.valid is True
            and current.valid is True
            and (
                expected.changed_files
                == current.changed_files
            )
            and (
                expected.diff
                == current.diff
            )
        )

    @staticmethod
    def _sibling_test_path(
        source_path: str,
    ) -> str | None:
        if (
            type(source_path) is not str
            or not source_path
            or not source_path.startswith("app/")
            or not source_path.endswith(".py")
        ):
            return None

        path = Path(
            source_path
        )

        if (
            path.name.startswith(
                "test_"
            )
            or path.name == "__init__.py"
        ):
            return None

        return (
            path.parent
            / f"test_{path.name}"
        ).as_posix()

    def _validate_contracts(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
    ) -> RepairTestSelectionResult | None:
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
                "Repair tests may be selected only after "
                "successful static validation."
            )

        if (
            type(validation.changed_files) is not tuple
            or not validation.changed_files
        ):
            return self._reject(
                "Static validation contains no immutable "
                "changed-file evidence."
            )

        if (
            type(validation.diff) is not str
            or not validation.diff.strip()
        ):
            return self._reject(
                "Static validation contains no candidate "
                "diff evidence."
            )

        return None

    def select(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
    ) -> RepairTestSelectionResult:
        contract_failure = (
            self._validate_contracts(
                workspace=workspace,
                decision=decision,
                validation=validation,
            )
        )

        if contract_failure is not None:
            return contract_failure

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

        if (
            not root.exists()
            or not root.is_dir()
        ):
            return self._reject(
                "Repair workspace root is unavailable."
            )

        current_validation = (
            RepairValidator().validate(
                workspace=workspace,
                decision=decision,
            )
        )

        if not self._validation_matches(
            validation,
            current_validation,
        ):
            return self._reject(
                "Static validation evidence is stale "
                "or no longer matches the candidate."
            )

        changed_files = (
            validation.changed_files
        )

        selected_tests: list[str] = []

        try:
            for source_path in changed_files:
                test_path = (
                    self._sibling_test_path(
                        source_path
                    )
                )

                if test_path is None:
                    return self._reject(
                        "Repair candidate contains a source "
                        "that has no deterministic independent "
                        "sibling-test mapping."
                    )

                if test_path in changed_files:
                    return self._reject(
                        "A verification test may not be modified "
                        "by the repair candidate it verifies."
                    )

                candidate_test = (
                    root
                    / test_path
                )

                if (
                    candidate_test.is_symlink()
                    or not candidate_test.exists()
                    or not candidate_test.is_file()
                ):
                    return self._reject(
                        "Deterministic sibling test is unavailable "
                        "or unsafe."
                    )

                resolved_test = (
                    candidate_test.resolve()
                )

                if not self._path_is_within(
                    resolved_test,
                    root,
                ):
                    return self._reject(
                        "Selected repair test escaped the "
                        "isolated workspace."
                    )

                tracked_result = self._run_git(
                    root,
                    "ls-files",
                    "--error-unmatch",
                    "--",
                    test_path,
                )

                if tracked_result.returncode != 0:
                    return self._reject(
                        "Selected repair test is not trusted "
                        "tracked repository evidence."
                    )

                unchanged_result = self._run_git(
                    root,
                    "diff",
                    "--quiet",
                    "HEAD",
                    "--",
                    test_path,
                )

                if unchanged_result.returncode == 1:
                    return self._reject(
                        "Selected repair test was modified and "
                        "cannot independently verify the repair."
                    )

                if unchanged_result.returncode != 0:
                    raise RepairWorkspaceError(
                        "Could not verify selected test integrity: "
                        f"{self._git_error(unchanged_result)}"
                    )

                if test_path not in selected_tests:
                    selected_tests.append(
                        test_path
                    )

        except RepairWorkspaceError as error:
            return self._reject(
                "Repair test selection failed closed: "
                f"{error}"
            )

        if not selected_tests:
            return self._reject(
                "No deterministic independent repair "
                "tests were selected."
            )

        return RepairTestSelectionResult(
            selected=True,
            reason=(
                "Deterministic tracked sibling tests were "
                "selected and verified unchanged from candidate "
                "HEAD. Tests have not been executed."
            ),
            test_files=tuple(
                sorted(
                    selected_tests
                )
            ),
        )
