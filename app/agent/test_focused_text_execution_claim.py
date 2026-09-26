from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest

from app.agent.focused_text_receipt import (
    FocusedTextReceipt,
    FocusedTextReceiptStore,
)


def skeletal_receipt():
    receipt = object.__new__(
        FocusedTextReceipt
    )

    focus = object()

    object.__setattr__(
        receipt,
        "focus_provenance",
        focus,
    )

    return (
        receipt,
        focus,
    )


def store_for(
    focus,
    *,
    clock=None,
    focus_active=None,
):
    if clock is None:
        clock = lambda: 100.0

    if focus_active is None:
        focus_active = [True]

    def focus_get(
        provenance,
    ):
        if (
            focus_active[0]
            and provenance
            is focus
        ):
            return provenance

        return None

    return FocusedTextReceiptStore(
        clock=clock,
        focus_get=focus_get,
    )


def publish(
    store,
    receipt,
):
    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert (
            store._publish(
                receipt
            )
            is True
        )


def test_exact_active_receipt_claims_once():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        claimed = store.claim(
            receipt
        )

    assert claimed is receipt
    assert len(store) == 0
    assert store.get(
        receipt
    ) is None


def test_second_claim_is_rejected():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        assert store.claim(
            receipt
        ) is receipt

        with pytest.raises(
            ValueError,
            match="unavailable",
        ):
            store.claim(
                receipt
            )

    assert len(store) == 0


def test_wrong_receipt_identity_burns_real_pending_receipt():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    (
        substituted,
        _other_focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        with pytest.raises(
            ValueError,
            match="substituted",
        ):
            store.claim(
                substituted
            )

    assert len(store) == 0
    assert store.get(
        receipt
    ) is None


def test_malformed_claim_attempt_burns_pending_receipt():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    publish(
        store,
        receipt,
    )

    with pytest.raises(
        ValueError,
        match="substituted",
    ):
        store.claim(
            object()
        )

    assert len(store) == 0


def test_claim_removes_receipt_before_currentness_validation():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

    def current(
        _self,
        _now,
    ):
        assert len(store) == 0
        return True

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        new=current,
    ):
        assert store.claim(
            receipt
        ) is receipt

    assert len(store) == 0


def test_stale_receipt_is_consumed_even_when_claim_fails():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ) as current:
        assert store._publish(
            receipt
        )

        current.return_value = False

        with pytest.raises(
            ValueError,
            match="stale",
        ):
            store.claim(
                receipt
            )

    assert len(store) == 0


def test_focus_replacement_burns_pending_receipt():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    focus_active = [
        True
    ]

    store = store_for(
        focus,
        focus_active=focus_active,
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        focus_active[0] = False

        with pytest.raises(
            ValueError,
            match="focus provenance",
        ):
            store.claim(
                receipt
            )

    assert len(store) == 0


def test_clock_failure_burns_pending_receipt():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    calls = [
        0
    ]

    def clock():
        calls[0] += 1

        if calls[0] == 1:
            return 100.0

        raise RuntimeError(
            "clock failed"
        )

    store = store_for(
        focus,
        clock=clock,
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        with pytest.raises(
            ValueError,
            match="unavailable",
        ):
            store.claim(
                receipt
            )

    assert len(store) == 0


def test_concurrent_claim_has_exactly_one_winner():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    barrier = Barrier(
        2
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        def attempt():
            barrier.wait(
                timeout=3
            )

            try:
                value = store.claim(
                    receipt
                )
            except ValueError:
                return False

            return (
                value is receipt
            )

        with ThreadPoolExecutor(
            max_workers=2
        ) as pool:
            futures = [
                pool.submit(
                    attempt
                )
                for _index
                in range(2)
            ]

            outcomes = [
                future.result(
                    timeout=3
                )
                for future
                in futures
            ]

    assert sorted(
        outcomes
    ) == [
        False,
        True,
    ]

    assert len(store) == 0


def test_claim_has_no_keyboard_execution_surface():
    path = (
        __import__(
            "pathlib"
        )
        .Path(
            __file__
        )
        .with_name(
            "focused_text_receipt.py"
        )
    )

    source = path.read_text(
        encoding="utf-8"
    )

    assert "pyautogui.write(" not in source
    assert "keyboard.write(" not in source
    assert "type_text(" not in source


def test_claim_returns_existing_receipt_not_new_authority_object():
    (
        receipt,
        focus,
    ) = skeletal_receipt()

    store = store_for(
        focus
    )

    with patch.object(
        FocusedTextReceipt,
        "is_current",
        return_value=True,
    ):
        assert store._publish(
            receipt
        )

        claimed = store.claim(
            receipt
        )

    assert claimed is receipt

    assert type(
        claimed
    ) is FocusedTextReceipt
