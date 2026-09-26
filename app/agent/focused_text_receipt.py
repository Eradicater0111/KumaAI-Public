"""KUMA 8D3C-B — focused text receipt.

This module joins four independently established trust roots:

1. exact human text intent,
2. exact active runtime GUI-step authority provenance,
3. exact single-use B8G visual/semantic target consumption,
4. exact active focus-target provenance.

The join is deliberately non-executing.

It does not:
- derive typing text,
- create GUI action-class authority,
- choose a semantic target,
- establish focus,
- grant keyboard permission,
- call pyautogui,
- execute type_text.

The B8G consumption is performed inside the trusted producer so callers
cannot inject a preconstructed target-consumption receipt.

Semantic step intent is compared by canonical immutable VALUE because it
originates as planner data.

The B7 semantic revalidation graph is compared by exact Python OBJECT
IDENTITY because it is trusted runtime evidence.

A FocusedTextReceipt is therefore evidence that:

    authorized exact text
        +
    intended semantic target
        +
    human-goal-bound visual target
        +
    actually focused same semantic target

all agree at one short-lived process-local boundary.
"""

from __future__ import annotations

from dataclasses import (
    dataclass,
    field,
)
import hashlib
import math
import threading
import time

from app.agent.gui_target_evidence_carrier import (
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    StructuredUIVisualTargetEvidenceStore,
)
from app.agent.gui_target_evidence_consumption import (
    StructuredUIVisualTargetEvidenceConsumption,
    consume_structured_ui_visual_target_evidence,
)
from app.agent.gui_target_intent import (
    StructuredUITargetIntent,
)
from app.agent.text_intent_evidence import (
    ExactTextIntentEvidence,
)
from app.ui_observation.focus_target_provenance import (
    FOCUS_TARGET_PROVENANCE,
    FocusTargetProvenance,
)


FOCUSED_TEXT_RECEIPT_MAX_AGE_SECONDS = (
    1.0
)

FOCUSED_TEXT_RECEIPT_STATUS_MATCHED = (
    "matched"
)

FOCUSED_TEXT_RECEIPT_STATUS_UNKNOWN = (
    "unknown"
)

VALID_FOCUSED_TEXT_RECEIPT_STATUSES = (
    frozenset({
        FOCUSED_TEXT_RECEIPT_STATUS_MATCHED,
        FOCUSED_TEXT_RECEIPT_STATUS_UNKNOWN,
    })
)

FOCUSED_TEXT_RECEIPT_UNKNOWN_CODES = (
    frozenset({
        "production_busy",
        "clock_unavailable",
        "text_intent_unavailable",
        "step_target_unavailable",
        "focus_provenance_unavailable",
        "target_consumption_unavailable",
        "target_intent_mismatch",
        "focus_target_mismatch",
        "human_goal_mismatch",
        "receipt_composition_failed",
        "receipt_publication_failed",
    })
)


def _timestamp(
    value,
):
    return (
        type(value)
        in (
            int,
            float,
        )
        and math.isfinite(
            value
        )
        and value >= 0
    )


def _goal_digest(
    value,
):
    if type(value) is not str:
        return None

    value = value.strip()

    if not value:
        return None

    return hashlib.sha256(
        value.encode(
            "utf-8"
        )
    ).hexdigest()


def _target_graph(
    consumption,
):
    """Recover the exact B8C/B7 graph carried through B8G."""

    if (
        type(consumption)
        is not StructuredUIVisualTargetEvidenceConsumption
    ):
        return None

    try:
        evidence = (
            consumption.evidence
        )

        point_binding_result = (
            evidence
            .point_binding_result
        )

        point_binding = (
            point_binding_result
            .binding
        )

        orchestration = (
            point_binding
            .orchestration_result
        )

        semantic_result = (
            orchestration
            .revalidation_result
        )

    except Exception:
        return None

    if (
        orchestration is None
        or semantic_result is None
    ):
        return None

    return (
        orchestration,
        semantic_result,
    )


def _step_target_snapshot(
    text_evidence,
):
    if (
        type(text_evidence)
        is not ExactTextIntentEvidence
    ):
        return None

    try:
        provenance = (
            text_evidence
            .authority_provenance
        )

        snapshot = (
            provenance
            .semantic_target_intent_snapshot
        )

    except Exception:
        return None

    if (
        type(snapshot)
        is not StructuredUITargetIntent
    ):
        return None

    return snapshot


def _join_is_valid(
    text_evidence,
    target_consumption,
    focus_provenance,
    now,
):
    """Validate the complete four-root receipt join."""

    if (
        type(text_evidence)
        is not ExactTextIntentEvidence
        or type(target_consumption)
        is not StructuredUIVisualTargetEvidenceConsumption
        or type(focus_provenance)
        is not FocusTargetProvenance
        or not _timestamp(
            now
        )
    ):
        return False

    try:
        if not text_evidence.is_current(
            now
        ):
            return False

        if not target_consumption.is_current(
            now
        ):
            return False

        if not focus_provenance.is_fresh(
            now
        ):
            return False

    except Exception:
        return False

    snapshot = (
        _step_target_snapshot(
            text_evidence
        )
    )

    if snapshot is None:
        return False

    graph = (
        _target_graph(
            target_consumption
        )
    )

    if graph is None:
        return False

    (
        orchestration,
        semantic_result,
    ) = graph

    try:
        if (
            orchestration.intent
            != snapshot
        ):
            return False

        if (
            focus_provenance
            .semantic_result
            is not semantic_result
        ):
            return False

        expected_digest = (
            _goal_digest(
                text_evidence
                .source_human_goal
            )
        )

        if (
            expected_digest
            is None
            or target_consumption
            .human_goal_sha256
            != expected_digest
        ):
            return False

        authority = (
            text_evidence
            .authority_provenance
        )

        if (
            authority
            is not text_evidence
            .authority_provenance
            or authority
            .semantic_target_intent_snapshot
            is not snapshot
        ):
            return False

        if (
            authority.planned_tool
            != "type_text"
        ):
            return False

    except Exception:
        return False

    return True


def _expected_expiry(
    text_evidence,
    target_consumption,
    focus_provenance,
    issued,
):
    return min(
        text_evidence
        .expires_at_monotonic,
        target_consumption
        .carrier
        .expires_at_monotonic,
        focus_provenance
        .expires_at_monotonic,
        issued
        + FOCUSED_TEXT_RECEIPT_MAX_AGE_SECONDS,
    )


@dataclass(frozen=True)
class FocusedTextReceipt:
    """Short-lived non-executing evidence that text and focus agree."""

    text_evidence: (
        ExactTextIntentEvidence
    ) = field(
        repr=False
    )

    target_consumption: (
        StructuredUIVisualTargetEvidenceConsumption
    ) = field(
        repr=False
    )

    focus_provenance: (
        FocusTargetProvenance
    ) = field(
        repr=False
    )

    target_intent_snapshot: (
        StructuredUITargetIntent
    ) = field(
        repr=False
    )

    semantic_result: object = field(
        repr=False
    )

    application_pid: int

    application_bundle_id: str

    issued_at_monotonic: float

    expires_at_monotonic: float

    def __post_init__(
        self,
    ):
        if (
            type(self.text_evidence)
            is not ExactTextIntentEvidence
        ):
            raise ValueError(
                "Focused text receipt requires "
                "exact text-intent evidence."
            )

        if (
            type(self.target_consumption)
            is not StructuredUIVisualTargetEvidenceConsumption
        ):
            raise ValueError(
                "Focused text receipt requires "
                "exact B8G target consumption."
            )

        if (
            type(self.focus_provenance)
            is not FocusTargetProvenance
        ):
            raise ValueError(
                "Focused text receipt requires "
                "exact focus-target provenance."
            )

        if (
            type(self.target_intent_snapshot)
            is not StructuredUITargetIntent
        ):
            raise ValueError(
                "Focused text receipt requires "
                "one canonical semantic target snapshot."
            )

        authority = (
            self.text_evidence
            .authority_provenance
        )

        if (
            authority
            .semantic_target_intent_snapshot
            is not self.target_intent_snapshot
        ):
            raise ValueError(
                "Focused text receipt must preserve "
                "the exact runtime target snapshot."
            )

        graph = (
            _target_graph(
                self.target_consumption
            )
        )

        if graph is None:
            raise ValueError(
                "Focused text receipt target graph "
                "is unavailable."
            )

        (
            orchestration,
            semantic_result,
        ) = graph

        if (
            orchestration.intent
            != self.target_intent_snapshot
        ):
            raise ValueError(
                "Typing step target does not match "
                "the consumed semantic target."
            )

        if (
            semantic_result
            is not self.semantic_result
        ):
            raise ValueError(
                "Focused text receipt must preserve "
                "the exact B7 semantic result."
            )

        if (
            self.focus_provenance
            .semantic_result
            is not self.semantic_result
        ):
            raise ValueError(
                "Focused target is not the exact "
                "consumed semantic target."
            )

        expected_digest = (
            _goal_digest(
                self.text_evidence
                .source_human_goal
            )
        )

        if (
            expected_digest
            is None
            or self.target_consumption
            .human_goal_sha256
            != expected_digest
        ):
            raise ValueError(
                "Text and target evidence belong "
                "to different human goals."
            )

        if (
            type(self.application_pid)
            is not int
            or isinstance(
                self.application_pid,
                bool,
            )
            or self.application_pid <= 0
            or self.application_pid
            != self.focus_provenance
            .application_pid
        ):
            raise ValueError(
                "Focused text application PID "
                "is invalid."
            )

        if (
            type(self.application_bundle_id)
            is not str
            or not self.application_bundle_id
            or self.application_bundle_id
            != self.focus_provenance
            .application_bundle_id
        ):
            raise ValueError(
                "Focused text application bundle "
                "is invalid."
            )

        if not (
            _timestamp(
                self.issued_at_monotonic
            )
            and _timestamp(
                self.expires_at_monotonic
            )
        ):
            raise ValueError(
                "Focused text receipt times "
                "are invalid."
            )

        if not _join_is_valid(
            self.text_evidence,
            self.target_consumption,
            self.focus_provenance,
            self.issued_at_monotonic,
        ):
            raise ValueError(
                "Focused text receipt sources "
                "are not jointly current."
            )

        expected_expiry = (
            _expected_expiry(
                self.text_evidence,
                self.target_consumption,
                self.focus_provenance,
                self.issued_at_monotonic,
            )
        )

        if (
            self.expires_at_monotonic
            != expected_expiry
        ):
            raise ValueError(
                "Focused text receipt lifetime "
                "does not match its shortest source."
            )

        if not (
            self.issued_at_monotonic
            < self.expires_at_monotonic
        ):
            raise ValueError(
                "Focused text receipt is "
                "already expired."
            )

    @property
    def raw_text(
        self,
    ):
        return (
            self.text_evidence
            .raw_text
        )

    @property
    def selector(
        self,
    ):
        return (
            self.focus_provenance
            .selector
        )

    @property
    def focus_observation_id(
        self,
    ):
        return (
            self.focus_provenance
            .focus_observation_id
        )

    def is_current(
        self,
        now,
    ):
        if not (
            _timestamp(
                now
            )
            and self.issued_at_monotonic
            <= now
            < self.expires_at_monotonic
        ):
            return False

        return _join_is_valid(
            self.text_evidence,
            self.target_consumption,
            self.focus_provenance,
            now,
        )


@dataclass(frozen=True)
class FocusedTextReceiptProduction:
    """Non-executing result of one trusted receipt-production attempt."""

    status: str

    receipt: (
        FocusedTextReceipt
        | None
    ) = field(
        default=None,
        repr=False,
    )

    target_consumption: (
        StructuredUIVisualTargetEvidenceConsumption
        | None
    ) = field(
        default=None,
        repr=False,
    )

    diagnostics: tuple[str, ...] = ()

    def __post_init__(
        self,
    ):
        if (
            type(self.status)
            is not str
            or self.status
            not in VALID_FOCUSED_TEXT_RECEIPT_STATUSES
        ):
            raise ValueError(
                "Invalid focused-text receipt "
                "production status."
            )

        if (
            type(self.diagnostics)
            is not tuple
            or any(
                type(code)
                is not str
                for code
                in self.diagnostics
            )
            or len(
                set(
                    self.diagnostics
                )
            )
            != len(
                self.diagnostics
            )
        ):
            raise ValueError(
                "Focused-text diagnostics must "
                "be immutable and unique."
            )

        if (
            self.status
            == FOCUSED_TEXT_RECEIPT_STATUS_MATCHED
        ):
            if (
                type(self.receipt)
                is not FocusedTextReceipt
                or type(self.target_consumption)
                is not StructuredUIVisualTargetEvidenceConsumption
                or self.receipt.target_consumption
                is not self.target_consumption
                or self.diagnostics
            ):
                raise ValueError(
                    "Matched focused-text production "
                    "requires one exact receipt graph."
                )

            return

        if (
            self.receipt is not None
            or self.target_consumption
            is not None
        ):
            raise ValueError(
                "Unknown focused-text production "
                "cannot carry trusted evidence."
            )

        if (
            len(
                self.diagnostics
            )
            != 1
            or self.diagnostics[
                0
            ]
            not in FOCUSED_TEXT_RECEIPT_UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown focused-text production "
                "requires one structured diagnostic."
            )

    @property
    def matched(
        self,
    ):
        return (
            self.status
            == FOCUSED_TEXT_RECEIPT_STATUS_MATCHED
            and self.receipt
            is not None
        )


class FocusedTextReceiptStore:
    """One exact active focused-text receipt.

    Publication is intentionally private.

    8D4 adds one atomic single-use execution claim. Every claim
    attempt burns the pending receipt before validation so stale,
    substituted, malformed, or interrupted attempts cannot leave
    reusable keyboard evidence behind.
    """

    def __init__(
        self,
        *,
        clock=time.monotonic,
        focus_get=None,
    ):
        if not callable(
            clock
        ):
            raise TypeError(
                "clock must be callable."
            )

        if focus_get is None:
            focus_get = (
                FOCUS_TARGET_PROVENANCE
                .get
            )

        if not callable(
            focus_get
        ):
            raise TypeError(
                "focus_get must be callable."
            )

        self._clock = (
            clock
        )

        self._focus_get = (
            focus_get
        )

        self._lock = (
            threading.RLock()
        )

        self._active = None

    def _now(
        self,
    ):
        try:
            now = (
                self._clock()
            )
        except Exception:
            raise ValueError(
                "Focused-text receipt clock "
                "is unavailable."
            ) from None

        if not _timestamp(
            now
        ):
            raise ValueError(
                "Focused-text receipt clock "
                "is unavailable."
            )

        return now

    def _focus_is_active(
        self,
        provenance,
    ):
        try:
            active = (
                self._focus_get(
                    provenance
                )
            )
        except Exception:
            return False

        return (
            active
            is provenance
        )

    def _publish(
        self,
        receipt,
    ):
        if (
            type(receipt)
            is not FocusedTextReceipt
        ):
            raise TypeError(
                "Expected exact FocusedTextReceipt."
            )

        with self._lock:
            self._active = None

            now = (
                self._now()
            )

            if not receipt.is_current(
                now
            ):
                return False

            if not self._focus_is_active(
                receipt.focus_provenance
            ):
                return False

            self._active = (
                receipt
            )

            return True

    def get(
        self,
        receipt,
    ):
        if (
            type(receipt)
            is not FocusedTextReceipt
        ):
            return None

        with self._lock:
            active = (
                self._active
            )

            if (
                active is None
                or active
                is not receipt
            ):
                return None

            try:
                now = (
                    self._now()
                )
            except Exception:
                self._active = None
                return None

            if not active.is_current(
                now
            ):
                self._active = None
                return None

            if not self._focus_is_active(
                active.focus_provenance
            ):
                self._active = None
                return None

            return active

    def claim(
        self,
        receipt,
    ):
        """Atomically consume one exact receipt for keyboard execution.

        This is the irreversible evidence boundary for trusted typing.

        The active receipt is removed before any validation that may
        fail. Therefore every claim attempt is single-use, including:

        - wrong-object substitution,
        - stale evidence,
        - focus replacement,
        - clock failure,
        - validation failure.

        No keyboard effect occurs here.
        """

        with self._lock:
            active = (
                self._active
            )

            self._active = None

            if active is None:
                raise ValueError(
                    "Focused-text receipt is unavailable."
                )

            if (
                type(receipt)
                is not FocusedTextReceipt
                or active
                is not receipt
            ):
                raise ValueError(
                    "Focused-text receipt is unavailable "
                    "or substituted."
                )

            try:
                now = (
                    self._now()
                )
            except Exception:
                raise ValueError(
                    "Focused-text receipt is unavailable."
                ) from None

            try:
                current = (
                    active.is_current(
                        now
                    )
                )
            except Exception:
                current = False

            if not current:
                raise ValueError(
                    "Focused-text receipt is stale "
                    "or invalid."
                )

            if not self._focus_is_active(
                active.focus_provenance
            ):
                raise ValueError(
                    "Focused-text focus provenance "
                    "is unavailable."
                )

            return active

    def clear(
        self,
    ):
        with self._lock:
            self._active = None

    def __len__(
        self,
    ):
        with self._lock:
            return (
                1
                if self._active
                is not None
                else 0
            )


def compose_focused_text_receipt(
    text_evidence,
    target_consumption,
    focus_provenance,
    *,
    clock=time.monotonic,
):
    """Compose already-established roots without external effects."""

    if not callable(
        clock
    ):
        raise TypeError(
            "clock must be callable."
        )

    try:
        now = (
            clock()
        )
    except Exception:
        raise ValueError(
            "Focused-text receipt clock "
            "is unavailable."
        ) from None

    if not _timestamp(
        now
    ):
        raise ValueError(
            "Focused-text receipt clock "
            "is unavailable."
        )

    if not _join_is_valid(
        text_evidence,
        target_consumption,
        focus_provenance,
        now,
    ):
        raise ValueError(
            "Focused-text receipt sources "
            "do not form one trusted join."
        )

    snapshot = (
        _step_target_snapshot(
            text_evidence
        )
    )

    graph = (
        _target_graph(
            target_consumption
        )
    )

    if (
        snapshot is None
        or graph is None
    ):
        raise ValueError(
            "Focused-text target graph "
            "is unavailable."
        )

    (
        _orchestration,
        semantic_result,
    ) = graph

    expires = (
        _expected_expiry(
            text_evidence,
            target_consumption,
            focus_provenance,
            now,
        )
    )

    return FocusedTextReceipt(
        text_evidence=(
            text_evidence
        ),
        target_consumption=(
            target_consumption
        ),
        focus_provenance=(
            focus_provenance
        ),
        target_intent_snapshot=(
            snapshot
        ),
        semantic_result=(
            semantic_result
        ),
        application_pid=(
            focus_provenance
            .application_pid
        ),
        application_bundle_id=(
            focus_provenance
            .application_bundle_id
        ),
        issued_at_monotonic=(
            now
        ),
        expires_at_monotonic=(
            expires
        ),
    )


FOCUSED_TEXT_RECEIPTS = (
    FocusedTextReceiptStore()
)


class FocusedTextReceiptProducer:
    """Trusted producer owning B8G consumption and receipt publication."""

    def __init__(
        self,
        *,
        receipt_store=FOCUSED_TEXT_RECEIPTS,
        target_store=(
            STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE
        ),
        focus_get=None,
        clock=time.monotonic,
    ):
        if (
            type(receipt_store)
            is not FocusedTextReceiptStore
        ):
            raise TypeError(
                "Expected FocusedTextReceiptStore."
            )

        if (
            type(target_store)
            is not StructuredUIVisualTargetEvidenceStore
        ):
            raise TypeError(
                "Expected StructuredUIVisualTargetEvidenceStore."
            )

        if focus_get is None:
            focus_get = (
                FOCUS_TARGET_PROVENANCE
                .get
            )

        if not callable(
            focus_get
        ):
            raise TypeError(
                "focus_get must be callable."
            )

        if not callable(
            clock
        ):
            raise TypeError(
                "clock must be callable."
            )

        self._receipt_store = (
            receipt_store
        )

        self._target_store = (
            target_store
        )

        self._focus_get = (
            focus_get
        )

        self._clock = (
            clock
        )

        self._lock = (
            threading.Lock()
        )

    def _unknown(
        self,
        code,
    ):
        return FocusedTextReceiptProduction(
            status=(
                FOCUSED_TEXT_RECEIPT_STATUS_UNKNOWN
            ),
            diagnostics=(
                code,
            ),
        )

    def _now(
        self,
    ):
        try:
            now = (
                self._clock()
            )
        except Exception:
            return None

        return (
            now
            if _timestamp(
                now
            )
            else None
        )

    def _focus_is_active(
        self,
        provenance,
    ):
        try:
            active = (
                self._focus_get(
                    provenance
                )
            )
        except Exception:
            return False

        return (
            active
            is provenance
        )

    def produce(
        self,
        text_evidence,
        focus_provenance,
        visual_verification,
    ):
        """Produce one focused-text receipt without keyboard execution.

        Callers cannot inject:
        - human goal,
        - B8G consumption,
        - target intent,
        - semantic B7 result,
        - application identity,
        - receipt publication.

        B8G consumption is owned here and is single-use.
        """

        if not self._lock.acquire(
            blocking=False
        ):
            return self._unknown(
                "production_busy"
            )

        try:
            self._receipt_store.clear()

            now = (
                self._now()
            )

            if now is None:
                return self._unknown(
                    "clock_unavailable"
                )

            if (
                type(text_evidence)
                is not ExactTextIntentEvidence
            ):
                return self._unknown(
                    "text_intent_unavailable"
                )

            try:
                text_current = (
                    text_evidence
                    .is_current(
                        now
                    )
                )
            except Exception:
                text_current = False

            if not text_current:
                return self._unknown(
                    "text_intent_unavailable"
                )

            snapshot = (
                _step_target_snapshot(
                    text_evidence
                )
            )

            if snapshot is None:
                return self._unknown(
                    "step_target_unavailable"
                )

            if (
                type(focus_provenance)
                is not FocusTargetProvenance
                or not self._focus_is_active(
                    focus_provenance
                )
            ):
                return self._unknown(
                    "focus_provenance_unavailable"
                )

            try:
                focus_current = (
                    focus_provenance
                    .is_fresh(
                        now
                    )
                )
            except Exception:
                focus_current = False

            if not focus_current:
                return self._unknown(
                    "focus_provenance_unavailable"
                )

            observation_id = getattr(
                visual_verification,
                "observation_id",
                "",
            )

            x = getattr(
                visual_verification,
                "x",
                -1,
            )

            y = getattr(
                visual_verification,
                "y",
                -1,
            )

            try:
                consumed = (
                    consume_structured_ui_visual_target_evidence(
                        visual_verification,
                        human_goal=(
                            text_evidence
                            .source_human_goal
                        ),
                        observation_id=(
                            observation_id
                        ),
                        x=x,
                        y=y,
                        store=(
                            self._target_store
                        ),
                        clock=lambda: now,
                    )
                )
            except Exception:
                consumed = None

            if (
                consumed is None
                or not getattr(
                    consumed,
                    "matched",
                    False,
                )
                or consumed.consumption
                is None
            ):
                return self._unknown(
                    "target_consumption_unavailable"
                )

            target_consumption = (
                consumed.consumption
            )

            graph = (
                _target_graph(
                    target_consumption
                )
            )

            if graph is None:
                return self._unknown(
                    "receipt_composition_failed"
                )

            (
                orchestration,
                semantic_result,
            ) = graph

            if (
                orchestration.intent
                != snapshot
            ):
                return self._unknown(
                    "target_intent_mismatch"
                )

            if (
                focus_provenance
                .semantic_result
                is not semantic_result
            ):
                return self._unknown(
                    "focus_target_mismatch"
                )

            expected_digest = (
                _goal_digest(
                    text_evidence
                    .source_human_goal
                )
            )

            if (
                expected_digest
                is None
                or target_consumption
                .human_goal_sha256
                != expected_digest
            ):
                return self._unknown(
                    "human_goal_mismatch"
                )

            try:
                receipt = (
                    compose_focused_text_receipt(
                        text_evidence,
                        target_consumption,
                        focus_provenance,
                        clock=lambda: now,
                    )
                )
            except Exception:
                return self._unknown(
                    "receipt_composition_failed"
                )

            try:
                published = (
                    self._receipt_store
                    ._publish(
                        receipt
                    )
                )
            except Exception:
                published = False

            if not published:
                self._receipt_store.clear()

                return self._unknown(
                    "receipt_publication_failed"
                )

            active = (
                self._receipt_store
                .get(
                    receipt
                )
            )

            if (
                active
                is not receipt
            ):
                self._receipt_store.clear()

                return self._unknown(
                    "receipt_publication_failed"
                )

            return FocusedTextReceiptProduction(
                status=(
                    FOCUSED_TEXT_RECEIPT_STATUS_MATCHED
                ),
                receipt=receipt,
                target_consumption=(
                    target_consumption
                ),
                diagnostics=(),
            )

        finally:
            self._lock.release()


FOCUSED_TEXT_RECEIPT_PRODUCER = (
    FocusedTextReceiptProducer()
)
