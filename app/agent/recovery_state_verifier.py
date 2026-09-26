from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StateVerificationResult:
    """
    Read-only observation about current system state.

    state_changed describes whether the operation being verified
    is known to have mutated filesystem state.

    The verifier itself never modifies system state.
    """

    known: bool
    state_changed: bool | None
    summary: str
    evidence: str = ""
    state: str = "unknown"
    contract_failure: bool = False

    def __post_init__(self) -> None:
        self.validate_contract()

    def validate_contract(self) -> None:
        if type(self.known) is not bool:
            raise ValueError(
                "StateVerificationResult.known must be boolean."
            )

        if (
            self.state_changed is not None
            and type(self.state_changed) is not bool
        ):
            raise ValueError(
                "StateVerificationResult.state_changed must be "
                "boolean or None."
            )

        if type(self.contract_failure) is not bool:
            raise ValueError(
                "StateVerificationResult.contract_failure must be boolean."
            )

        if not isinstance(self.summary, str):
            raise ValueError(
                "StateVerificationResult.summary must be a string."
            )

        if not isinstance(self.evidence, str):
            raise ValueError(
                "StateVerificationResult.evidence must be a string."
            )

        if not isinstance(self.state, str):
            raise ValueError(
                "StateVerificationResult.state must be a string."
            )

        if self.known and self.state_changed is None:
            raise ValueError(
                "Known state verification requires a known "
                "state_changed value."
            )

        if not self.known and self.state_changed is not None:
            raise ValueError(
                "Unknown state verification cannot claim whether "
                "state changed."
            )

        if self.contract_failure and self.known:
            raise ValueError(
                "Verifier contract failure cannot report known state."
            )


class RecoveryStateVerifier:
    """
    Read-only verifier for concrete filesystem state.

    Only tools that exist in the current KUMA runtime are handled.
    Unsupported or future tools remain unknown.
    """

    FILESYSTEM_TOOLS = {
        "open_file",
    }

    def verify(
        self,
        *,
        tool_name: str,
        arguments: dict | None = None,
        result: Any = None,
    ) -> StateVerificationResult:
        tool = str(tool_name or "").strip().lower()
        arguments = arguments or {}

        if tool not in self.FILESYSTEM_TOOLS:
            return StateVerificationResult(
                known=False,
                state_changed=None,
                summary=(
                    f"No filesystem state verifier is registered "
                    f"for tool '{tool}'."
                ),
                evidence="",
                state="unknown",
            )

        path = self._extract_path(arguments)

        if not path:
            return StateVerificationResult(
                known=False,
                state_changed=None,
                summary=(
                    "The filesystem target path could not be "
                    "determined from the tool arguments."
                ),
                evidence="",
                state="unknown",
            )

        try:
            target = Path(path).expanduser()
            exists = target.exists()

            # open_file is read-only with respect to filesystem
            # contents, so the operation itself is not considered
            # a filesystem mutation.
            return StateVerificationResult(
                known=True,
                state_changed=False,
                summary=(
                    "The target path exists."
                    if exists
                    else "The target path does not exist."
                ),
                evidence=f"Path: {target}; exists={exists}",
                state="present" if exists else "absent",
            )

        except (OSError, RuntimeError, ValueError) as error:
            return StateVerificationResult(
                known=False,
                state_changed=None,
                summary=(
                    "Filesystem state could not be "
                    "inspected safely."
                ),
                evidence=str(error),
                state="unknown",
            )

    @staticmethod
    def _extract_path(arguments: dict) -> str:
        for key in (
            "file_path",
            "path",
        ):
            value = arguments.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

        return ""


def safe_verify_state(
    verifier,
    *,
    tool_name: str,
    arguments: dict | None = None,
    result: Any = None,
) -> StateVerificationResult:
    # A broken verifier is never recovery authority.
    try:
        verification = verifier.verify(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
        )

        if not isinstance(verification, StateVerificationResult):
            raise TypeError(
                "State verifier returned an invalid result type."
            )

        verification.validate_contract()
        return verification

    except Exception as error:
        return StateVerificationResult(
            known=False,
            state_changed=None,
            summary=(
                "State verifier failed closed because its result "
                "contract could not be trusted. "
                f"Failure type: {type(error).__name__}."
            ),
            evidence="",
            state="unknown",
            contract_failure=True,
        )
