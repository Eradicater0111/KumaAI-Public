from dataclasses import dataclass

from app.agent.permissions import PermissionLevel


@dataclass(frozen=True)
class RepairProposal:
    """
    Inert description of a possible KUMA source repair.

    A proposal is not authorization to edit files, run commands,
    apply a patch, commit, merge, or modify the main checkout.
    """

    summary: str
    rationale: str
    target_files: tuple[str, ...]
    permission_level: PermissionLevel


@dataclass(frozen=True)
class RepairDecision:
    """
    Pure policy result for a repair proposal.

    6C.1 authorizes isolated evaluation only. It never grants
    authority to apply changes to KUMA's main checkout.
    """

    eligible_for_isolated_evaluation: bool
    automatic_main_checkout_apply: bool
    requires_human_approval: bool
    reason: str
    normalized_target_files: tuple[str, ...] = ()


class RepairPolicy:
    """
    Fail-closed policy boundary for self-repair proposals.

    This class performs no filesystem writes, subprocess calls,
    Git operations, model calls, or tool execution.
    """

    def __init__(
        self,
        *,
        max_target_files: int = 5,
    ):
        if (
            type(max_target_files) is not int
            or max_target_files < 1
        ):
            raise ValueError(
                "max_target_files must be a positive integer."
            )

        self.max_target_files = max_target_files

    @staticmethod
    def _reject(
        reason: str,
    ) -> RepairDecision:
        return RepairDecision(
            eligible_for_isolated_evaluation=False,
            automatic_main_checkout_apply=False,
            requires_human_approval=True,
            reason=reason,
            normalized_target_files=(),
        )

    @staticmethod
    def _normalize_target(
        target: str,
    ) -> str | None:
        if type(target) is not str:
            return None

        target = target.strip()

        if not target:
            return None

        # KUMA currently targets a POSIX/macOS repository. Reject
        # alternate separators rather than trying to reinterpret
        # untrusted model output.
        if "\\" in target:
            return None

        if target.startswith("/"):
            return None

        raw_parts = target.split("/")

        if any(
            part in {"", ".", ".."}
            for part in raw_parts
        ):
            return None

        if raw_parts[0] != "app":
            return None

        if any(
            part == ".git"
            or part in {".venv", "venv", "env"}
            or part == ".env"
            or part.startswith(".env.")
            for part in raw_parts
        ):
            return None

        if not raw_parts[-1].endswith(".py"):
            return None

        return "/".join(raw_parts)

    def evaluate(
        self,
        proposal: RepairProposal,
    ) -> RepairDecision:
        """
        Decide whether a proposal may proceed to a future isolated
        evaluation stage.

        No decision returned here authorizes main-checkout mutation.
        """

        if not isinstance(
            proposal,
            RepairProposal,
        ):
            return self._reject(
                "Repair proposal has an invalid contract."
            )

        if (
            type(proposal.summary) is not str
            or not proposal.summary.strip()
        ):
            return self._reject(
                "Repair proposal summary is required."
            )

        if (
            type(proposal.rationale) is not str
            or not proposal.rationale.strip()
        ):
            return self._reject(
                "Repair proposal rationale is required."
            )

        if not isinstance(
            proposal.permission_level,
            PermissionLevel,
        ):
            return self._reject(
                "Repair proposal permission level is invalid."
            )

        if type(proposal.target_files) is not tuple:
            return self._reject(
                "Repair target_files must be an immutable tuple."
            )

        if not proposal.target_files:
            return self._reject(
                "Repair proposal must target at least one file."
            )

        if (
            len(proposal.target_files)
            > self.max_target_files
        ):
            return self._reject(
                "Repair proposal exceeds the bounded file scope."
            )

        normalized = []

        for target in proposal.target_files:
            parsed = self._normalize_target(
                target
            )

            if parsed is None:
                return self._reject(
                    "Repair proposal contains an unsafe or "
                    "unsupported target path."
                )

            if parsed in normalized:
                return self._reject(
                    "Repair proposal contains duplicate targets."
                )

            normalized.append(
                parsed
            )

        requires_human_approval = (
            proposal.permission_level
            != PermissionLevel.SAFE
        )

        return RepairDecision(
            eligible_for_isolated_evaluation=True,
            automatic_main_checkout_apply=False,
            requires_human_approval=(
                requires_human_approval
            ),
            reason=(
                "Proposal is eligible for isolated evaluation "
                "only. Main-checkout application is not "
                "authorized by 6C.1."
            ),
            normalized_target_files=tuple(
                normalized
            ),
        )
