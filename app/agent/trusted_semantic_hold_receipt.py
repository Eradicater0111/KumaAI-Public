from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_STATE,
    BodyButtonSnapshot,
)
from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
)
from app.agent.mouse_button_intent_evidence import (
    ExactMouseHoldVisionIntentEvidence,
)


TRUSTED_SEMANTIC_HOLD_RECEIPT_MAX_AGE_SECONDS = 1.0

SEMANTIC_HOLD_RECEIPT_STATUS_ISSUED = "issued"
SEMANTIC_HOLD_RECEIPT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrustedSemanticHoldReceipt:
    hold_evidence: ExactMouseHoldVisionIntentEvidence
    target_verification: object
    observation_id: str
    vision_x: int
    vision_y: int
    button: str
    clear_snapshot: BodyButtonSnapshot
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(self, now):
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class TrustedSemanticHoldReceiptProduction:
    status: str
    receipt: TrustedSemanticHoldReceipt | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status
            == SEMANTIC_HOLD_RECEIPT_STATUS_ISSUED
            and self.receipt is not None
        )


class TrustedSemanticHoldReceiptStore:
    def __init__(
        self,
        *,
        clock=time.monotonic,
        body_snapshot_get=None,
    ):
        self.clock = clock
        self.body_snapshot_get = (
            body_snapshot_get
            if body_snapshot_get is not None
            else BODY_BUTTON_STATE.snapshot
        )
        self._receipt = None

    def clear(self):
        self._receipt = None

    def publish(self, receipt):
        self.clear()

        if (
            type(receipt)
            is not TrustedSemanticHoldReceipt
        ):
            return False

        self._receipt = receipt
        return True

    def claim(self, receipt):
        if (
            type(receipt)
            is not TrustedSemanticHoldReceipt
            or self._receipt is not receipt
        ):
            return None

        claimed = self._receipt

        # Single-use before any revalidation.
        self._receipt = None

        try:
            now = self.clock()
        except Exception:
            return None

        if not claimed.is_fresh(now):
            return None

        authority = (
            claimed
            .hold_evidence
            .authority_provenance
        )

        try:
            current = (
                RUNTIME_GUI_STEP_AUTHORITY.get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            current = None

        if current is not authority:
            return None

        if (
            getattr(
                claimed.target_verification,
                "satisfied",
                False,
            )
            is not True
        ):
            return None

        try:
            body = self.body_snapshot_get()
        except Exception:
            return None

        if (
            body is not claimed.clear_snapshot
            or body.status
            != BODY_BUTTON_CLEAR
        ):
            return None

        return claimed


class TrustedSemanticHoldReceiptProducer:
    def __init__(
        self,
        *,
        store=None,
        clock=time.monotonic,
        body_snapshot_get=None,
    ):
        self.store = (
            store
            if store is not None
            else TRUSTED_SEMANTIC_HOLD_RECEIPTS
        )

        self.clock = clock

        self.body_snapshot_get = (
            body_snapshot_get
            if body_snapshot_get is not None
            else BODY_BUTTON_STATE.snapshot
        )

    def produce(
        self,
        hold_evidence,
        target_verification,
        *,
        observation_id,
        vision_x,
        vision_y,
        button,
    ):
        self.store.clear()

        def unknown(code):
            return TrustedSemanticHoldReceiptProduction(
                status=SEMANTIC_HOLD_RECEIPT_STATUS_UNKNOWN,
                diagnostics=(code,),
            )

        if (
            type(hold_evidence)
            is not ExactMouseHoldVisionIntentEvidence
        ):
            return unknown(
                "invalid_hold_evidence"
            )

        if (
            getattr(
                target_verification,
                "satisfied",
                False,
            )
            is not True
        ):
            return unknown(
                "target_not_verified"
            )

        if (
            type(observation_id) is not str
            or not observation_id
            or observation_id
            != observation_id.strip()
        ):
            return unknown(
                "invalid_observation_id"
            )

        if (
            type(vision_x) is not int
            or type(vision_y) is not int
        ):
            return unknown(
                "invalid_target_coordinates"
            )

        if (
            type(button) is not str
            or button
            != hold_evidence.button
        ):
            return unknown(
                "button_identity_mismatch"
            )

        try:
            now = self.clock()
            body = self.body_snapshot_get()
        except Exception:
            return unknown(
                "runtime_state_unavailable"
            )

        if not hold_evidence.is_fresh(
            now
        ):
            return unknown(
                "stale_hold_evidence"
            )

        authority = (
            hold_evidence
            .authority_provenance
        )

        try:
            current = (
                RUNTIME_GUI_STEP_AUTHORITY.get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            current = None

        if current is not authority:
            return unknown(
                "authority_not_current"
            )

        if (
            body.status
            != BODY_BUTTON_CLEAR
        ):
            return unknown(
                "button_state_not_clear"
            )

        receipt = TrustedSemanticHoldReceipt(
            hold_evidence=hold_evidence,
            target_verification=target_verification,
            observation_id=observation_id,
            vision_x=vision_x,
            vision_y=vision_y,
            button=button,
            clear_snapshot=body,
            issued_at_monotonic=now,
            expires_at_monotonic=min(
                now
                + TRUSTED_SEMANTIC_HOLD_RECEIPT_MAX_AGE_SECONDS,
                hold_evidence.expires_at_monotonic,
            ),
        )

        if not self.store.publish(
            receipt
        ):
            return unknown(
                "receipt_publication_failed"
            )

        return TrustedSemanticHoldReceiptProduction(
            status=SEMANTIC_HOLD_RECEIPT_STATUS_ISSUED,
            receipt=receipt,
        )


TRUSTED_SEMANTIC_HOLD_RECEIPTS = (
    TrustedSemanticHoldReceiptStore()
)

TRUSTED_SEMANTIC_HOLD_RECEIPT_PRODUCER = (
    TrustedSemanticHoldReceiptProducer(
        store=TRUSTED_SEMANTIC_HOLD_RECEIPTS
    )
)
