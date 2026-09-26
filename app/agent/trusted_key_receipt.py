from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.agent.key_intent_evidence import (
    ExactKeyIntentEvidence,
)
from app.agent.gui_step_authority_provenance import (
    RUNTIME_GUI_STEP_AUTHORITY,
)
from app.ui_observation.focus_provenance import (
    FOCUS_DESKTOP_PROVENANCE,
    FocusDesktopProvenance,
)


TRUSTED_KEY_RECEIPT_MAX_AGE_SECONDS = 1.0

KEY_RECEIPT_STATUS_ISSUED = "issued"
KEY_RECEIPT_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrustedKeyReceipt:
    key_evidence: ExactKeyIntentEvidence
    focus_provenance: FocusDesktopProvenance
    application_pid: int
    application_bundle_id: str
    issued_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(
        self,
        now,
    ) -> bool:
        return (
            type(now) in (int, float)
            and self.issued_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class TrustedKeyReceiptProduction:
    status: str
    receipt: TrustedKeyReceipt | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def issued(self):
        return (
            self.status == KEY_RECEIPT_STATUS_ISSUED
            and self.receipt is not None
        )


class TrustedKeyReceiptStore:
    def __init__(
        self,
        *,
        clock=time.monotonic,
        focus_get=None,
    ):
        self.clock = clock
        self.focus_get = (
            focus_get
            if focus_get is not None
            else FOCUS_DESKTOP_PROVENANCE.get
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

        if type(receipt) is not TrustedKeyReceipt:
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
            type(receipt) is not TrustedKeyReceipt
            or self._receipt is not receipt
        ):
            return None

        # -------------------------------------------------
        # SINGLE-USE BOUNDARY
        # -------------------------------------------------
        #
        # Consume BEFORE freshness/authority/focus checks.
        # Any failed attempt permanently destroys this receipt.
        # -------------------------------------------------

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

        # -------------------------------------------------
        # EXACT ACTIVE PLAN/STEP AUTHORITY
        # -------------------------------------------------

        authority = (
            claimed
            .key_evidence
            .authority_provenance
        )

        try:
            active_authority = (
                RUNTIME_GUI_STEP_AUTHORITY
                .get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            active_authority = None

        if active_authority is not authority:
            return None

        # -------------------------------------------------
        # EXACT CURRENT FOCUS PROVENANCE
        # -------------------------------------------------

        focus_provenance = (
            claimed.focus_provenance
        )

        try:
            focus_observation_id = (
                focus_provenance
                .binding
                .focus_observation_id
            )

            active_focus = (
                self.focus_get(
                    focus_observation_id
                )
            )
        except Exception:
            active_focus = None

        if active_focus is not focus_provenance:
            return None

        return claimed


class TrustedKeyReceiptProducer:
    def __init__(
        self,
        *,
        receipt_store=None,
        focus_store=FOCUS_DESKTOP_PROVENANCE,
        clock=time.monotonic,
    ):
        self.receipt_store = (
            receipt_store
            if receipt_store is not None
            else TRUSTED_KEY_RECEIPTS
        )
        self.focus_store = focus_store
        self.clock = clock

    def produce(
        self,
        key_evidence,
        focus_provenance,
    ):
        self.receipt_store.clear()

        def unknown(code):
            return TrustedKeyReceiptProduction(
                status=KEY_RECEIPT_STATUS_UNKNOWN,
                diagnostics=(code,),
            )

        if (
            type(key_evidence)
            is not ExactKeyIntentEvidence
        ):
            return unknown(
                "invalid_key_evidence"
            )

        try:
            now = self.clock()
        except Exception:
            return unknown(
                "clock_unavailable"
            )

        if not key_evidence.is_fresh(
            now
        ):
            return unknown(
                "stale_key_evidence"
            )

        authority = (
            key_evidence.authority_provenance
        )

        try:
            active_authority = (
                RUNTIME_GUI_STEP_AUTHORITY
                .get_current(
                    authority.plan,
                    authority.step,
                )
            )
        except Exception:
            active_authority = None

        if active_authority is not authority:
            return unknown(
                "authority_not_current"
            )

        if (
            type(focus_provenance)
            is not FocusDesktopProvenance
        ):
            return unknown(
                "invalid_focus_provenance"
            )

        binding = focus_provenance.binding

        focus_observation_id = (
            binding.focus_observation_id
        )

        try:
            active_focus = (
                self.focus_store.get(
                    focus_observation_id
                )
            )
        except Exception:
            active_focus = None

        if active_focus is not focus_provenance:
            return unknown(
                "focus_provenance_not_current"
            )

        if (
            type(binding.expires_at_monotonic)
            not in (int, float)
            or now
            > binding.expires_at_monotonic
        ):
            return unknown(
                "stale_focus_provenance"
            )

        if (
            type(binding.application_pid) is not int
            or binding.application_pid <= 0
            or type(binding.application_bundle_id)
            is not str
            or not binding.application_bundle_id.strip()
        ):
            return unknown(
                "invalid_application_identity"
            )

        receipt = TrustedKeyReceipt(
            key_evidence=key_evidence,
            focus_provenance=focus_provenance,
            application_pid=(
                binding.application_pid
            ),
            application_bundle_id=(
                binding.application_bundle_id.strip()
            ),
            issued_at_monotonic=now,
            expires_at_monotonic=min(
                now
                + TRUSTED_KEY_RECEIPT_MAX_AGE_SECONDS,
                key_evidence.expires_at_monotonic,
                binding.expires_at_monotonic,
            ),
        )

        if not self.receipt_store.publish(
            receipt
        ):
            return unknown(
                "receipt_publication_failed"
            )

        return TrustedKeyReceiptProduction(
            status=KEY_RECEIPT_STATUS_ISSUED,
            receipt=receipt,
        )


TRUSTED_KEY_RECEIPTS = (
    TrustedKeyReceiptStore()
)

TRUSTED_KEY_RECEIPT_PRODUCER = (
    TrustedKeyReceiptProducer(
        receipt_store=TRUSTED_KEY_RECEIPTS
    )
)
