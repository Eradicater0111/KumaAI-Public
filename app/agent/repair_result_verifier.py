from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from app.agent.repair_execution_sandbox import (
    RepairExecutionResult,
)
from app.agent.repair_policy import (
    RepairDecision,
)
from app.agent.repair_test_executor import (
    RepairTestExecutionResult,
)
from app.agent.repair_test_handoff import (
    RepairTestHandoff,
    RepairTestHandoffResult,
)
from app.agent.repair_test_selector import (
    RepairTestSelectionResult,
)
from app.agent.repair_validator import (
    RepairValidationResult,
    RepairValidator,
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairVerificationResult:
    """
    Immutable 6C.6 verification evidence.

    evidence_verified=True means the supplied repair evidence is
    internally consistent with the current isolated candidate.

    eligible_for_apply_review=True means only that 6C.7 may consider
    the candidate. It never authorizes main-checkout mutation.
    """

    evidence_verified: bool
    eligible_for_apply_review: bool
    reason: str
    source_head: str = ""
    validation_digest: str = ""
    changed_files: tuple[str, ...] = ()
    executed_files: tuple[str, ...] = ()
    test_files: tuple[str, ...] = ()
    tests_run: int = 0
    evidence_digest: str = ""


class RepairResultVerifier:
    """
    6C.6 fail-closed repair-result verification.

    This verifier executes no candidate code and runs no tests.

    It:
    - requires an active isolated RepairWorkspace
    - requires a current eligible RepairDecision
    - independently repeats static candidate validation
    - independently rebuilds the trusted test-integrity handoff
    - verifies source HEAD and candidate diff identity
    - requires successful contained execution evidence for every
      changed Python file
    - requires successful contained independent-test evidence
    - rejects impossible or malformed result contracts
    - builds a deterministic audit fingerprint
    - grants only eligibility for future 6C.7 apply review
    - never authorizes automatic main-checkout application
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
    ) -> RepairVerificationResult:
        return RepairVerificationResult(
            evidence_verified=False,
            eligible_for_apply_review=False,
            reason=reason,
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
    def _handoff_matches(
        expected: RepairTestHandoffResult,
        current: RepairTestHandoffResult,
    ) -> bool:
        return (
            expected.ready is True
            and current.ready is True
            and (
                expected.source_head
                == current.source_head
            )
            and (
                expected.validation_digest
                == current.validation_digest
            )
            and (
                expected.test_files
                == current.test_files
            )
            and (
                expected.test_evidence
                == current.test_evidence
            )
        )

    @staticmethod
    def _nonnegative_int(
        value: object,
    ) -> bool:
        return (
            type(value) is int
            and value >= 0
        )

    @classmethod
    def _execution_is_successful(
        cls,
        result: RepairExecutionResult,
    ) -> bool:
        return (
            isinstance(
                result,
                RepairExecutionResult,
            )
            and result.executed is True
            and result.success is True
            and type(result.relative_path) is str
            and bool(result.relative_path)
            and result.returncode == 0
            and result.timed_out is False
            and (
                result.output_limit_exceeded
                is False
            )
            and (
                result.memory_limit_exceeded
                is False
            )
        )

    @classmethod
    def _test_result_is_successful(
        cls,
        result: RepairTestExecutionResult,
    ) -> bool:
        if not isinstance(
            result,
            RepairTestExecutionResult,
        ):
            return False

        if (
            result.executed is not True
            or result.passed is not True
            or result.returncode != 0
            or result.timed_out is not False
            or (
                result.output_limit_exceeded
                is not False
            )
            or (
                result.memory_limit_exceeded
                is not False
            )
        ):
            return False

        if (
            type(result.test_files) is not tuple
            or not result.test_files
        ):
            return False

        for value in (
            result.tests_run,
            result.failures,
            result.errors,
            result.skipped,
            result.expected_failures,
            result.unexpected_successes,
        ):
            if not cls._nonnegative_int(
                value
            ):
                return False

        if result.tests_run < 1:
            return False

        if (
            result.failures != 0
            or result.errors != 0
            or (
                result.unexpected_successes
                != 0
            )
        ):
            return False

        classified = (
            result.failures
            + result.errors
            + result.skipped
            + result.expected_failures
            + result.unexpected_successes
        )

        if classified > result.tests_run:
            return False

        return True

    @staticmethod
    def _digest(
        payload: dict,
    ) -> str:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
        ).encode(
            "utf-8"
        )

        return hashlib.sha256(
            encoded
        ).hexdigest()

    def verify(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        selection: RepairTestSelectionResult,
        handoff: RepairTestHandoffResult,
        execution_results: tuple[
            RepairExecutionResult,
            ...,
        ],
        test_result: RepairTestExecutionResult,
    ) -> RepairVerificationResult:
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

        if not isinstance(
            handoff,
            RepairTestHandoffResult,
        ):
            return self._reject(
                "Repair test-handoff contract is invalid."
            )

        if (
            type(execution_results) is not tuple
            or not execution_results
        ):
            return self._reject(
                "Repair verification requires immutable "
                "contained-execution evidence."
            )

        if not isinstance(
            test_result,
            RepairTestExecutionResult,
        ):
            return self._reject(
                "Repair test-execution contract is invalid."
            )

        if (
            not decision
            .eligible_for_isolated_evaluation
        ):
            return self._reject(
                "Repair decision is not eligible for "
                "isolated evaluation."
            )

        if (
            decision
            .automatic_main_checkout_apply
        ):
            return self._reject(
                "Repair decision illegally claims automatic "
                "main-checkout application authority."
            )

        if validation.valid is not True:
            return self._reject(
                "Repair verification requires successful "
                "static validation."
            )

        if (
            type(validation.changed_files) is not tuple
            or not validation.changed_files
        ):
            return self._reject(
                "Repair validation contains no immutable "
                "changed-file evidence."
            )

        if (
            type(validation.diff) is not str
            or not validation.diff.strip()
        ):
            return self._reject(
                "Repair validation contains no candidate "
                "diff evidence."
            )

        try:
            info = workspace.info
        except RepairWorkspaceError as error:
            return self._reject(
                "Repair workspace is not active: "
                f"{error}"
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

        current_handoff = (
            RepairTestHandoff(
                git_timeout_seconds=(
                    self.git_timeout_seconds
                )
            ).prepare(
                workspace=workspace,
                decision=decision,
                validation=validation,
                selection=selection,
            )
        )

        if not self._handoff_matches(
            handoff,
            current_handoff,
        ):
            return self._reject(
                "Repair test-integrity handoff is stale, "
                "forged, or no longer matches current evidence."
            )

        if (
            current_handoff.source_head
            != info.source_head
        ):
            return self._reject(
                "Repair source HEAD no longer matches "
                "the isolated workspace origin."
            )

        expected_validation_digest = (
            hashlib.sha256(
                validation.diff.encode(
                    "utf-8",
                    errors="strict",
                )
            ).hexdigest()
        )

        if (
            current_handoff.validation_digest
            != expected_validation_digest
        ):
            return self._reject(
                "Repair candidate diff fingerprint "
                "does not match current validation."
            )

        changed_files = (
            validation.changed_files
        )

        execution_by_file: dict[
            str,
            RepairExecutionResult,
        ] = {}

        for result in execution_results:
            if not self._execution_is_successful(
                result
            ):
                return self._reject(
                    "Contained candidate execution evidence "
                    "is unsuccessful or malformed."
                )

            if (
                result.relative_path
                not in changed_files
            ):
                return self._reject(
                    "Contained execution evidence refers to "
                    "a file outside the validated repair."
                )

            if (
                result.relative_path
                in execution_by_file
            ):
                return self._reject(
                    "Duplicate contained execution evidence "
                    "is not accepted."
                )

            execution_by_file[
                result.relative_path
            ] = result

        if (
            set(
                execution_by_file
            )
            != set(
                changed_files
            )
            or len(
                execution_by_file
            )
            != len(
                changed_files
            )
        ):
            return self._reject(
                "Contained execution evidence does not "
                "cover every validated changed file."
            )

        if not self._test_result_is_successful(
            test_result
        ):
            return self._reject(
                "Contained independent repair-test evidence "
                "is unsuccessful or malformed."
            )

        if (
            test_result.test_files
            != current_handoff.test_files
        ):
            return self._reject(
                "Repair-test execution evidence does not "
                "match the trusted selected tests."
            )

        executed_files = tuple(
            sorted(
                execution_by_file
            )
        )

        audit_payload = {
            "source_head": (
                current_handoff.source_head
            ),
            "validation_digest": (
                current_handoff.validation_digest
            ),
            "changed_files": list(
                changed_files
            ),
            "executed_files": list(
                executed_files
            ),
            "execution_results": [
                {
                    "relative_path": (
                        execution_by_file[
                            relative_path
                        ].relative_path
                    ),
                    "returncode": (
                        execution_by_file[
                            relative_path
                        ].returncode
                    ),
                    "success": (
                        execution_by_file[
                            relative_path
                        ].success
                    ),
                }
                for relative_path
                in executed_files
            ],
            "test_files": list(
                current_handoff.test_files
            ),
            "test_evidence": [
                {
                    "relative_path": (
                        evidence.relative_path
                    ),
                    "committed_blob": (
                        evidence.committed_blob
                    ),
                    "working_blob": (
                        evidence.working_blob
                    ),
                }
                for evidence
                in current_handoff.test_evidence
            ],
            "test_result": {
                "passed": (
                    test_result.passed
                ),
                "tests_run": (
                    test_result.tests_run
                ),
                "failures": (
                    test_result.failures
                ),
                "errors": (
                    test_result.errors
                ),
                "skipped": (
                    test_result.skipped
                ),
                "expected_failures": (
                    test_result.expected_failures
                ),
                "unexpected_successes": (
                    test_result.unexpected_successes
                ),
                "returncode": (
                    test_result.returncode
                ),
            },
        }

        evidence_digest = (
            self._digest(
                audit_payload
            )
        )

        return RepairVerificationResult(
            evidence_verified=True,
            eligible_for_apply_review=True,
            reason=(
                "Repair evidence is internally consistent "
                "with the current isolated candidate and "
                "passed contained execution plus independent "
                "tests. The candidate is eligible only for "
                "6C.7 apply review; this result does not "
                "authorize main-checkout mutation."
            ),
            source_head=(
                current_handoff.source_head
            ),
            validation_digest=(
                current_handoff.validation_digest
            ),
            changed_files=(
                changed_files
            ),
            executed_files=(
                executed_files
            ),
            test_files=(
                current_handoff.test_files
            ),
            tests_run=(
                test_result.tests_run
            ),
            evidence_digest=(
                evidence_digest
            ),
        )
