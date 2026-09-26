from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import secrets

from app.agent.repair_execution_sandbox import (
    RepairExecutionSandbox,
)
from app.agent.repair_policy import (
    RepairDecision,
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
)
from app.agent.repair_workspace import (
    RepairWorkspace,
    RepairWorkspaceError,
)


@dataclass(frozen=True)
class RepairTestExecutionResult:
    """
    Immutable contained unittest evidence for one repair candidate.

    passed=True is test evidence only. It never authorizes
    main-checkout application.
    """

    executed: bool
    passed: bool
    reason: str
    test_files: tuple[str, ...] = ()
    tests_run: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    expected_failures: int = 0
    unexpected_successes: int = 0
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    output_limit_exceeded: bool = False
    memory_limit_exceeded: bool = False


class RepairTestExecutor:
    """
    6C.5C contained unittest execution.

    Security boundary:
    - requires current static validation
    - requires deterministic test selection
    - requires current test-integrity handoff
    - independently rebuilds the handoff before execution
    - maps only trusted selected test files to Python modules
    - executes unittest through RepairExecutionSandbox's shared
      containment primitive
    - accepts no shell command or arbitrary argv
    - requires a complete trusted harness report
    - exit code 0 without that report fails closed
    - independently rebuilds handoff after execution
    - grants no repair application authority
    """

    _MODULE_COMPONENT = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_]*$"
    )

    _UNITTEST_HARNESS = r"""
import json
import sys
import unittest

if len(payload) < 2:
    raise RuntimeError(
        "Contained unittest payload is incomplete."
    )

report_marker = payload[0]
test_modules = payload[1:]

if not report_marker:
    raise RuntimeError(
        "Contained unittest report marker is invalid."
    )

if not test_modules:
    raise RuntimeError(
        "Contained unittest execution has no modules."
    )

sys.argv = [
    "kuma-repair-tests",
]

loader = unittest.TestLoader()

suite = loader.loadTestsFromNames(
    test_modules
)

runner = unittest.TextTestRunner(
    stream=sys.stderr,
    verbosity=2,
)

result = runner.run(
    suite
)

report = {
    "passed": bool(
        result.wasSuccessful()
    ),
    "tests_run": int(
        result.testsRun
    ),
    "failures": len(
        result.failures
    ),
    "errors": len(
        result.errors
    ),
    "skipped": len(
        getattr(
            result,
            "skipped",
            (),
        )
    ),
    "expected_failures": len(
        getattr(
            result,
            "expectedFailures",
            (),
        )
    ),
    "unexpected_successes": len(
        getattr(
            result,
            "unexpectedSuccesses",
            (),
        )
    ),
}

print(
    report_marker
    + json.dumps(
        report,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    ),
    flush=True,
)

raise SystemExit(
    0
    if report["passed"]
    else 1
)
"""

    def __init__(
        self,
        *,
        sandbox: RepairExecutionSandbox | None = None,
        git_timeout_seconds: int = 30,
    ):
        if (
            sandbox is not None
            and not isinstance(
                sandbox,
                RepairExecutionSandbox,
            )
        ):
            raise ValueError(
                "sandbox must be a RepairExecutionSandbox."
            )

        if (
            type(git_timeout_seconds) is not int
            or git_timeout_seconds < 1
        ):
            raise ValueError(
                "git_timeout_seconds must be a positive integer."
            )

        self.sandbox = (
            sandbox
            or RepairExecutionSandbox()
        )

        self.git_timeout_seconds = (
            git_timeout_seconds
        )

    @staticmethod
    def _reject(
        reason: str,
        *,
        test_files: tuple[str, ...] = (),
    ) -> RepairTestExecutionResult:
        return RepairTestExecutionResult(
            executed=False,
            passed=False,
            reason=reason,
            test_files=test_files,
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

    @classmethod
    def _test_module_name(
        cls,
        relative_path: str,
    ) -> str | None:
        if (
            type(relative_path) is not str
            or not relative_path.startswith(
                "app/"
            )
            or not relative_path.endswith(
                ".py"
            )
        ):
            return None

        path = Path(
            relative_path
        )

        if (
            not path.name.startswith(
                "test_"
            )
            or path.name == "__init__.py"
        ):
            return None

        parts = relative_path.split(
            "/"
        )

        if any(
            part in {
                "",
                ".",
                "..",
            }
            for part in parts
        ):
            return None

        module_parts = [
            *parts[:-1],
            parts[-1][:-3],
        ]

        if any(
            not cls._MODULE_COMPONENT.fullmatch(
                part
            )
            for part in module_parts
        ):
            return None

        return ".".join(
            module_parts
        )

    @staticmethod
    def _parse_report(
        *,
        stdout: str,
        marker: str,
    ) -> dict[str, int | bool] | None:
        if (
            type(stdout) is not str
            or type(marker) is not str
            or not marker
        ):
            return None

        nonempty_lines = [
            line
            for line in stdout.splitlines()
            if line.strip()
        ]

        matching = [
            line
            for line in nonempty_lines
            if line.startswith(
                marker
            )
        ]

        if len(matching) != 1:
            return None

        if (
            not nonempty_lines
            or nonempty_lines[-1]
            != matching[0]
        ):
            return None

        payload = matching[0][
            len(marker):
        ]

        try:
            parsed = json.loads(
                payload
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return None

        if type(parsed) is not dict:
            return None

        expected_keys = {
            "passed",
            "tests_run",
            "failures",
            "errors",
            "skipped",
            "expected_failures",
            "unexpected_successes",
        }

        if set(parsed) != expected_keys:
            return None

        if type(parsed["passed"]) is not bool:
            return None

        for key in (
            "tests_run",
            "failures",
            "errors",
            "skipped",
            "expected_failures",
            "unexpected_successes",
        ):
            value = parsed[key]

            if (
                type(value) is not int
                or value < 0
            ):
                return None

        return parsed

    def execute(
        self,
        *,
        workspace: RepairWorkspace,
        decision: RepairDecision,
        validation: RepairValidationResult,
        selection: RepairTestSelectionResult,
        handoff: RepairTestHandoffResult,
    ) -> RepairTestExecutionResult:
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

        if handoff.ready is not True:
            return self._reject(
                "Contained repair tests require a ready "
                "integrity handoff."
            )

        try:
            workspace.info
        except RepairWorkspaceError as error:
            return self._reject(
                "Repair workspace is not active: "
                f"{error}"
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
                "Repair-test handoff is stale, forged, "
                "or no longer matches current evidence.",
                test_files=(
                    current_handoff.test_files
                    if current_handoff.ready
                    else ()
                ),
            )

        test_modules: list[str] = []

        for test_file in (
            current_handoff.test_files
        ):
            module_name = (
                self._test_module_name(
                    test_file
                )
            )

            if module_name is None:
                return self._reject(
                    "Selected repair test cannot be "
                    "mapped to a safe unittest module.",
                    test_files=(
                        current_handoff.test_files
                    ),
                )

            test_modules.append(
                module_name
            )

        if not test_modules:
            return self._reject(
                "Contained repair execution has no "
                "trusted unittest modules."
            )

        marker = (
            "KUMA_TEST_RESULT_"
            + secrets.token_hex(
                16
            )
            + ":"
        )

        try:
            (
                returncode,
                stdout,
                stderr,
                timed_out,
                output_limit_exceeded,
                memory_limit_exceeded,
            ) = self.sandbox._run_contained_python(
                candidate_root=(
                    workspace.root
                ),
                harness_body=(
                    self._UNITTEST_HARNESS
                ),
                payload_args=(
                    marker,
                    *test_modules,
                ),
            )

        except RepairWorkspaceError as error:
            return self._reject(
                "Contained repair-test execution "
                "could not start safely: "
                f"{error}",
                test_files=(
                    current_handoff.test_files
                ),
            )

        post_handoff = (
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
            current_handoff,
            post_handoff,
        ):
            return RepairTestExecutionResult(
                executed=True,
                passed=False,
                reason=(
                    "Repair evidence changed during "
                    "contained unittest execution."
                ),
                test_files=(
                    current_handoff.test_files
                ),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
                output_limit_exceeded=(
                    output_limit_exceeded
                ),
                memory_limit_exceeded=(
                    memory_limit_exceeded
                ),
            )

        if memory_limit_exceeded:
            return RepairTestExecutionResult(
                executed=True,
                passed=False,
                reason=(
                    "Contained repair tests exceeded "
                    "the resident-memory limit."
                ),
                test_files=(
                    current_handoff.test_files
                ),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                memory_limit_exceeded=True,
            )

        if timed_out:
            return RepairTestExecutionResult(
                executed=True,
                passed=False,
                reason=(
                    "Contained repair tests exceeded "
                    "the wall-clock limit."
                ),
                test_files=(
                    current_handoff.test_files
                ),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                timed_out=True,
            )

        if output_limit_exceeded:
            return RepairTestExecutionResult(
                executed=True,
                passed=False,
                reason=(
                    "Contained repair tests exceeded "
                    "the output limit."
                ),
                test_files=(
                    current_handoff.test_files
                ),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
                output_limit_exceeded=True,
            )

        report = self._parse_report(
            stdout=stdout,
            marker=marker,
        )

        if report is None:
            return RepairTestExecutionResult(
                executed=True,
                passed=False,
                reason=(
                    "Contained unittest process did not "
                    "produce one complete trusted "
                    "completion report."
                ),
                test_files=(
                    current_handoff.test_files
                ),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )

        tests_run = int(
            report["tests_run"]
        )

        failures = int(
            report["failures"]
        )

        errors = int(
            report["errors"]
        )

        skipped = int(
            report["skipped"]
        )

        expected_failures = int(
            report[
                "expected_failures"
            ]
        )

        unexpected_successes = int(
            report[
                "unexpected_successes"
            ]
        )

        reported_passed = (
            report["passed"] is True
        )

        if tests_run < 1:
            return RepairTestExecutionResult(
                executed=True,
                passed=False,
                reason=(
                    "Contained unittest execution ran "
                    "zero tests and cannot verify a repair."
                ),
                test_files=(
                    current_handoff.test_files
                ),
                tests_run=tests_run,
                failures=failures,
                errors=errors,
                skipped=skipped,
                expected_failures=(
                    expected_failures
                ),
                unexpected_successes=(
                    unexpected_successes
                ),
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )

        passed = (
            reported_passed
            and returncode == 0
            and failures == 0
            and errors == 0
            and unexpected_successes == 0
        )

        return RepairTestExecutionResult(
            executed=True,
            passed=passed,
            reason=(
                "Contained independent repair tests "
                "passed. This is verification evidence "
                "only and does not authorize repair "
                "application."
                if passed
                else
                "Contained independent repair tests "
                "did not pass."
            ),
            test_files=(
                current_handoff.test_files
            ),
            tests_run=tests_run,
            failures=failures,
            errors=errors,
            skipped=skipped,
            expected_failures=(
                expected_failures
            ),
            unexpected_successes=(
                unexpected_successes
            ),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
        )
