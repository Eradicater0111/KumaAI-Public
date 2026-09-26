from __future__ import annotations

import math
import unicodedata

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContinuationReplayDecision:
    """
    Pure replay-safety decision.

    This object does not execute tools or grant permission.
    """

    allowed: bool
    exact_replay: bool
    reason: str


class ContinuationReplayGuard:
    """
    Prevent a recovery continuation from silently becoming
    an exact replay of the operation that produced the
    resumable partial state.

    The guard accepts only durable JSON-shaped argument data.
    Malformed or ambiguous provenance fails closed.
    """

    MAX_DEPTH = 32
    MAX_NODES = 4096

    def assess_context(
        self,
        *,
        proposed_tool: str,
        proposed_arguments: dict[str, Any] | None,
        context: Any,
    ) -> ContinuationReplayDecision:
        """
        Validate the transient replay context without coercing it.
        """

        if type(context) is not dict:
            return self._blocked(
                "Continuation replay context is malformed; "
                "replay safety cannot be established."
            )

        required = {
            "known",
            "tool",
            "arguments",
        }

        missing = sorted(
            required.difference(
                context.keys()
            )
        )

        if missing:
            return self._blocked(
                "Continuation replay context is missing "
                "required provenance fields: "
                f"{', '.join(missing)}."
            )

        return self.assess(
            proposed_tool=proposed_tool,
            proposed_arguments=proposed_arguments,
            previous_known=context["known"],
            previous_tool=context["tool"],
            previous_arguments=context["arguments"],
        )

    def assess(
        self,
        *,
        proposed_tool: str,
        proposed_arguments: dict[str, Any] | None,
        previous_known: bool,
        previous_tool: str,
        previous_arguments: dict[str, Any] | None,
    ) -> ContinuationReplayDecision:

        if type(proposed_tool) is not str:
            return self._blocked(
                "Continuation proposal has a malformed "
                "tool identity."
            )

        proposed_tool = unicodedata.normalize(
            "NFC",
            proposed_tool.strip(),
        )

        if not proposed_tool:
            return self._blocked(
                "Continuation proposal has no tool identity."
            )

        if type(previous_known) is not bool:
            return self._blocked(
                "Previous partial-operation provenance has a "
                "malformed known/unknown marker."
            )

        if not previous_known:
            return self._blocked(
                "Previous partial-operation provenance "
                "is unavailable, so replay safety cannot "
                "be established."
            )

        if type(previous_tool) is not str:
            return self._blocked(
                "Previous partial-operation provenance has a "
                "malformed tool identity."
            )

        previous_tool = unicodedata.normalize(
            "NFC",
            previous_tool.strip(),
        )

        if not previous_tool:
            return self._blocked(
                "Previous partial-operation provenance "
                "has no tool identity, so replay safety "
                "cannot be established."
            )

        try:
            proposed_canonical = self._canonicalize_arguments(
                proposed_arguments,
                label="Proposed",
            )
            previous_canonical = self._canonicalize_arguments(
                previous_arguments,
                label="Previous",
            )
        except ValueError as error:
            return self._blocked(
                "Replay safety cannot be established from "
                f"the argument provenance. {error}"
            )

        exact_replay = (
            proposed_tool == previous_tool
            and proposed_canonical == previous_canonical
        )

        if exact_replay:
            return ContinuationReplayDecision(
                allowed=False,
                exact_replay=True,
                reason=(
                    "Continuation would exactly replay the "
                    "operation associated with the verified "
                    "partial state."
                ),
            )

        return ContinuationReplayDecision(
            allowed=True,
            exact_replay=False,
            reason=(
                "Continuation differs from the protected "
                "partial-state operation."
            ),
        )

    @classmethod
    def _canonicalize_arguments(
        cls,
        arguments: Any,
        *,
        label: str,
    ):
        """
        Build a deterministic replay identity.

        Only durable JSON-shaped values are accepted. Numeric
        equivalents such as 1, 1.0, and True intentionally share
        one conservative replay identity.
        """

        if type(arguments) is not dict:
            raise ValueError(
                f"{label} arguments must be a dictionary."
            )

        active: set[int] = set()
        budget = [0]

        return cls._canonicalize_value(
            arguments,
            label=label,
            depth=0,
            active=active,
            budget=budget,
        )

    @classmethod
    def _canonicalize_value(
        cls,
        value: Any,
        *,
        label: str,
        depth: int,
        active: set[int],
        budget: list[int],
    ):
        if depth > cls.MAX_DEPTH:
            raise ValueError(
                f"{label} arguments exceed the maximum "
                "replay-comparison depth."
            )

        budget[0] += 1

        if budget[0] > cls.MAX_NODES:
            raise ValueError(
                f"{label} arguments exceed the maximum "
                "replay-comparison size."
            )

        if value is None:
            return ("none",)

        if type(value) is bool:
            return (
                "number",
                int(value),
                1,
            )

        if type(value) is int:
            return (
                "number",
                value,
                1,
            )

        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError(
                    f"{label} arguments contain a "
                    "non-finite numeric value."
                )

            numerator, denominator = value.as_integer_ratio()

            return (
                "number",
                numerator,
                denominator,
            )

        if type(value) is str:
            return (
                "string",
                unicodedata.normalize(
                    "NFC",
                    value,
                ),
            )

        if type(value) is list:
            identity = id(value)

            if identity in active:
                raise ValueError(
                    f"{label} arguments contain a cycle."
                )

            active.add(identity)

            try:
                return (
                    "list",
                    tuple(
                        cls._canonicalize_value(
                            item,
                            label=label,
                            depth=depth + 1,
                            active=active,
                            budget=budget,
                        )
                        for item in value
                    ),
                )
            finally:
                active.remove(identity)

        if type(value) is dict:
            identity = id(value)

            if identity in active:
                raise ValueError(
                    f"{label} arguments contain a cycle."
                )

            active.add(identity)
            normalized_items = []

            try:
                for key, item in value.items():
                    if type(key) is not str:
                        raise ValueError(
                            f"{label} arguments contain a "
                            "non-string dictionary key."
                        )

                    normalized_key = unicodedata.normalize(
                        "NFC",
                        key,
                    )

                    normalized_items.append(
                        (
                            normalized_key,
                            cls._canonicalize_value(
                                item,
                                label=label,
                                depth=depth + 1,
                                active=active,
                                budget=budget,
                            ),
                        )
                    )
            finally:
                active.remove(identity)

            normalized_keys = [
                key
                for key, _ in normalized_items
            ]

            if len(normalized_keys) != len(set(normalized_keys)):
                raise ValueError(
                    f"{label} arguments contain dictionary "
                    "keys that collide after Unicode "
                    "normalization."
                )

            return (
                "dict",
                tuple(
                    sorted(
                        normalized_items,
                        key=lambda item: item[0],
                    )
                ),
            )

        raise ValueError(
            f"{label} arguments contain unsupported "
            f"value type '{type(value).__name__}'."
        )

    @staticmethod
    def _blocked(
        reason: str,
    ) -> ContinuationReplayDecision:
        return ContinuationReplayDecision(
            allowed=False,
            exact_replay=False,
            reason=reason,
        )
