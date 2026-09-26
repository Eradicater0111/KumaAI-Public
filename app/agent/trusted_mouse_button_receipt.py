from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.agent.body_button_state import (
    BODY_BUTTON_CLEAR,
    BODY_BUTTON_HELD,
    BODY_BUTTON_UNKNOWN,
    BODY_BUTTON_STATE,
    BodyButtonSnapshot,
)
from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
)
from app.agent.mouse_button_intent_evidence import (
    ExactMouseHoldIntentEvidence,
    ExactMouseReleaseIntentEvidence,
)
from app.agent.pointer_desktop_provenance import (
    PointerDesktopProvenance,
    revalidate_pointer_desktop_provenance,
)


TRUSTED_MOUSE_RECEIPT_MAX_AGE_SECONDS = 1.0

MOUSE_RECEIPT_STATUS_ISSUED = "issued"
MOUSE_RECEIPT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrustedMouseHoldReceipt:
    hold_evidence: ExactMouseHoldIntentEvidence
    pointer_provenance: PointerDesktopProvenance
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
class TrustedMouseReleaseReceipt:
    release_evidence: ExactMouseReleaseIntentEvidence
    body_snapshot: BodyButtonSnapshot
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
class TrustedMouseReceiptProduction:
    status: str
    receipt: object | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status
            == MOUSE_RECEIPT_STATUS_ISSUED
            and self.receipt is not None
        )


class TrustedMouseHoldReceiptStore:
    def __init__(
        self,
        *,
        clock=time.monotonic,
        pointer_revalidate=None,
        body_snapshot_get=None,
    ):
        self.clock = clock
        self.pointer_revalidate = (
            pointer_revalidate
            if pointer_revalidate is not None
            else revalidate_pointer_desktop_provenance
        )
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

        if type(receipt) is not TrustedMouseHoldReceipt:
            return False

        self._receipt = receipt
        return True

    def claim(self, receipt):
        if (
            type(receipt)
            is not TrustedMouseHoldReceipt
            or self._receipt is not receipt
        ):
            return None

        claimed = self._receipt

        # Single use BEFORE revalidation.
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
            active = (
                RUNTIME_GUI_STEP_AUTHORITY.get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            active = None

        if active is not authority:
            return None

        try:
            pointer_valid = (
                self.pointer_revalidate(
                    claimed.pointer_provenance
                )
            )
        except Exception:
            pointer_valid = False

        if pointer_valid is not True:
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


class TrustedMouseReleaseReceiptStore:
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
            is not TrustedMouseReleaseReceipt
        ):
            return False

        self._receipt = receipt
        return True

    def claim(self, receipt):
        if (
            type(receipt)
            is not TrustedMouseReleaseReceipt
            or self._receipt is not receipt
        ):
            return None

        claimed = self._receipt

        # Single use BEFORE revalidation.
        self._receipt = None

        try:
            now = self.clock()
        except Exception:
            return None

        if not claimed.is_fresh(now):
            return None

        authority = (
            claimed
            .release_evidence
            .authority_provenance
        )

        try:
            active = (
                RUNTIME_GUI_STEP_AUTHORITY.get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            active = None

        if active is not authority:
            return None

        try:
            body = self.body_snapshot_get()
        except Exception:
            return None

        if body is not claimed.body_snapshot:
            return None

        if body.status not in {
            BODY_BUTTON_HELD,
            BODY_BUTTON_UNKNOWN,
        }:
            return None

        if body.button is None:
            return None

        return claimed


class TrustedMouseHoldReceiptProducer:
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
            else TRUSTED_MOUSE_HOLD_RECEIPTS
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
        pointer_provenance,
    ):
        self.store.clear()

        def unknown(code):
            return TrustedMouseReceiptProduction(
                status=MOUSE_RECEIPT_STATUS_UNKNOWN,
                diagnostics=(code,),
            )

        if (
            type(hold_evidence)
            is not ExactMouseHoldIntentEvidence
            or type(pointer_provenance)
            is not PointerDesktopProvenance
        ):
            return unknown(
                "invalid_evidence"
            )

        try:
            now = self.clock()
            body = self.body_snapshot_get()
        except Exception:
            return unknown(
                "state_unavailable"
            )

        if (
            not hold_evidence.is_fresh(now)
            or not pointer_provenance.is_fresh(now)
        ):
            return unknown(
                "stale_evidence"
            )

        if (
            body.status
            != BODY_BUTTON_CLEAR
        ):
            return unknown(
                "button_state_not_clear"
            )

        receipt = TrustedMouseHoldReceipt(
            hold_evidence=hold_evidence,
            pointer_provenance=pointer_provenance,
            clear_snapshot=body,
            issued_at_monotonic=now,
            expires_at_monotonic=min(
                now
                + TRUSTED_MOUSE_RECEIPT_MAX_AGE_SECONDS,
                hold_evidence.expires_at_monotonic,
                pointer_provenance.expires_at_monotonic,
            ),
        )

        if not self.store.publish(receipt):
            return unknown(
                "receipt_publication_failed"
            )

        return TrustedMouseReceiptProduction(
            status=MOUSE_RECEIPT_STATUS_ISSUED,
            receipt=receipt,
        )


class TrustedMouseReleaseReceiptProducer:
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
            else TRUSTED_MOUSE_RELEASE_RECEIPTS
        )
        self.clock = clock
        self.body_snapshot_get = (
            body_snapshot_get
            if body_snapshot_get is not None
            else BODY_BUTTON_STATE.snapshot
        )

    def produce(
        self,
        release_evidence,
    ):
        self.store.clear()

        def unknown(code):
            return TrustedMouseReceiptProduction(
                status=MOUSE_RECEIPT_STATUS_UNKNOWN,
                diagnostics=(code,),
            )

        if (
            type(release_evidence)
            is not ExactMouseReleaseIntentEvidence
        ):
            return unknown(
                "invalid_evidence"
            )

        try:
            now = self.clock()
            body = self.body_snapshot_get()
        except Exception:
            return unknown(
                "state_unavailable"
            )

        if not release_evidence.is_fresh(now):
            return unknown(
                "stale_evidence"
            )

        if body.status not in {
            BODY_BUTTON_HELD,
            BODY_BUTTON_UNKNOWN,
        }:
            return unknown(
                "button_state_not_releasable"
            )

        receipt = TrustedMouseReleaseReceipt(
            release_evidence=release_evidence,
            body_snapshot=body,
            issued_at_monotonic=now,
            expires_at_monotonic=(
                now
                + TRUSTED_MOUSE_RECEIPT_MAX_AGE_SECONDS
            ),
        )

        if not self.store.publish(receipt):
            return unknown(
                "receipt_publication_failed"
            )

        return TrustedMouseReceiptProduction(
            status=MOUSE_RECEIPT_STATUS_ISSUED,
            receipt=receipt,
        )


TRUSTED_MOUSE_HOLD_RECEIPTS = (
    TrustedMouseHoldReceiptStore()
)

TRUSTED_MOUSE_RELEASE_RECEIPTS = (
    TrustedMouseReleaseReceiptStore()
)

TRUSTED_MOUSE_HOLD_RECEIPT_PRODUCER = (
    TrustedMouseHoldReceiptProducer(
        store=TRUSTED_MOUSE_HOLD_RECEIPTS
    )
)

TRUSTED_MOUSE_RELEASE_RECEIPT_PRODUCER = (
    TrustedMouseReleaseReceiptProducer(
        store=TRUSTED_MOUSE_RELEASE_RECEIPTS
    )
)
