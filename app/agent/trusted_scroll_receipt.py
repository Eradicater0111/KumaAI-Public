from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
)
from app.agent.pointer_desktop_provenance import (
    PointerDesktopProvenance,
    revalidate_pointer_desktop_provenance,
)
from app.agent.scroll_intent_evidence import (
    ExactScrollIntentEvidence,
)


TRUSTED_SCROLL_RECEIPT_MAX_AGE_SECONDS = 1.0

SCROLL_RECEIPT_STATUS_ISSUED = "issued"
SCROLL_RECEIPT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrustedScrollReceipt:
    scroll_evidence: ExactScrollIntentEvidence
    pointer_provenance: PointerDesktopProvenance
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(
        self,
        now,
    ):
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class TrustedScrollReceiptProduction:
    status: str
    receipt: TrustedScrollReceipt | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status == SCROLL_RECEIPT_STATUS_ISSUED
            and self.receipt is not None
        )


class TrustedScrollReceiptStore:
    def __init__(
        self,
        *,
        clock=time.monotonic,
        revalidate_fn=None,
    ):
        self.clock = clock
        self.revalidate_fn = (
            revalidate_fn
            if revalidate_fn is not None
            else revalidate_pointer_desktop_provenance
        )
        self._receipt = None

    def clear(
        self,
    ):
        self._receipt = None

    def publish(
        self,
        receipt,
    ):
        self.clear()

        if (
            type(receipt)
            is not TrustedScrollReceipt
        ):
            return False

        try:
            now = self.clock()
        except Exception:
            return False

        if not receipt.is_fresh(
            now
        ):
            return False

        self._receipt = receipt

        return True

    def claim(
        self,
        receipt,
    ):
        if (
            type(receipt)
            is not TrustedScrollReceipt
            or self._receipt is not receipt
        ):
            return None

        claimed = self._receipt

        self._receipt = None

        try:
            now = self.clock()
        except Exception:
            return None

        if not claimed.is_fresh(
            now
        ):
            return None

        authority = (
            claimed
            .scroll_evidence
            .authority_provenance
        )

        try:
            current_authority = (
                RUNTIME_GUI_STEP_AUTHORITY
                .get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            current_authority = None

        if current_authority is not authority:
            return None

        try:
            valid_pointer = (
                self.revalidate_fn(
                    claimed.pointer_provenance
                )
            )
        except Exception:
            valid_pointer = False

        if valid_pointer is not True:
            return None

        return claimed


class TrustedScrollReceiptProducer:
    def __init__(
        self,
        *,
        receipt_store=None,
        clock=time.monotonic,
    ):
        self.receipt_store = (
            receipt_store
            if receipt_store is not None
            else TRUSTED_SCROLL_RECEIPTS
        )
        self.clock = clock

    def produce(
        self,
        scroll_evidence,
        pointer_provenance,
    ):
        self.receipt_store.clear()

        def unknown(code):
            return TrustedScrollReceiptProduction(
                status=SCROLL_RECEIPT_STATUS_UNKNOWN,
                diagnostics=(code,),
            )

        if (
            type(scroll_evidence)
            is not ExactScrollIntentEvidence
        ):
            return unknown(
                "invalid_scroll_evidence"
            )

        if (
            type(pointer_provenance)
            is not PointerDesktopProvenance
        ):
            return unknown(
                "invalid_pointer_provenance"
            )

        try:
            now = self.clock()
        except Exception:
            return unknown(
                "clock_unavailable"
            )

        if not scroll_evidence.is_fresh(
            now
        ):
            return unknown(
                "stale_scroll_evidence"
            )

        if not pointer_provenance.is_fresh(
            now
        ):
            return unknown(
                "stale_pointer_provenance"
            )

        authority = (
            scroll_evidence
            .authority_provenance
        )

        try:
            current_authority = (
                RUNTIME_GUI_STEP_AUTHORITY
                .get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            current_authority = None

        if current_authority is not authority:
            return unknown(
                "authority_not_current"
            )

        receipt = TrustedScrollReceipt(
            scroll_evidence=scroll_evidence,
            pointer_provenance=pointer_provenance,
            issued_at_monotonic=now,
            expires_at_monotonic=min(
                now
                + TRUSTED_SCROLL_RECEIPT_MAX_AGE_SECONDS,
                scroll_evidence.expires_at_monotonic,
                pointer_provenance.expires_at_monotonic,
            ),
        )

        if not self.receipt_store.publish(
            receipt
        ):
            return unknown(
                "receipt_publication_failed"
            )

        return TrustedScrollReceiptProduction(
            status=SCROLL_RECEIPT_STATUS_ISSUED,
            receipt=receipt,
        )


TRUSTED_SCROLL_RECEIPTS = (
    TrustedScrollReceiptStore()
)

TRUSTED_SCROLL_RECEIPT_PRODUCER = (
    TrustedScrollReceiptProducer(
        receipt_store=TRUSTED_SCROLL_RECEIPTS
    )
)
