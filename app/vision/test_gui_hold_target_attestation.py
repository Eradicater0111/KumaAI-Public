from __future__ import annotations

from dataclasses import fields
from typing import get_args, get_type_hints
from unittest.mock import patch

import pytest

from app.vision.gui_target_verifier import (
    GUI_HOLD_TARGET_ATTESTATIONS,
    GuiHoldTargetAttestation,
    GuiHoldTargetAttestationStore,
    GuiSemanticTargetAttestation,
    GuiTargetAttestation,
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
    current_screen_matches_attestation,
)


def matching_result(
    **overrides,
):

    payload = {
        "status": TARGET_STATUS_SATISFIED,
        "summary": "Target matched.",
        "evidence": "Trusted semantic evidence.",
        "observation_id": "obs-hold",
        "x": 250,
        "y": 179,
        "goal_sha256": "goal-digest",
        "image_sha256": "image-digest",
        "target_region_sha256": "region-digest",
    }

    payload.update(
        overrides
    )

    return GuiTargetVerificationResult(
        **payload
    )


@pytest.fixture(
    autouse=True
)
def clear_global_store():

    GUI_HOLD_TARGET_ATTESTATIONS.clear()

    yield

    GUI_HOLD_TARGET_ATTESTATIONS.clear()


def test_hold_attestation_field_surface_is_exact():

    names = {
        field.name
        for field in fields(
            GuiHoldTargetAttestation
        )
    }

    assert names == {
        "observation_id",
        "x",
        "y",
        "button",
        "goal_sha256",
        "image_sha256",
        "target_region_sha256",
        "issued_at_monotonic",
    }

    assert "clicks" not in names
    assert "duration" not in names
    assert "permission" not in names
    assert "authorized" not in names
    assert "held" not in names


def test_issue_binds_exact_target_and_button():

    store = (
        GuiHoldTargetAttestationStore()
    )

    result = matching_result()

    with patch(
        "app.vision.gui_target_verifier."
        "time.monotonic",
        return_value=100.0,
    ):

        attestation = store.issue(
            result=result,
            button="left",
        )

    assert (
        attestation.observation_id
        == result.observation_id
    )

    assert attestation.x == result.x
    assert attestation.y == result.y
    assert attestation.button == "left"

    assert (
        attestation.goal_sha256
        == result.goal_sha256
    )

    assert (
        attestation.image_sha256
        == result.image_sha256
    )

    assert (
        attestation.target_region_sha256
        == result.target_region_sha256
    )

    assert (
        attestation.issued_at_monotonic
        == 100.0
    )


def test_issue_requires_exact_verification_result_type():

    store = (
        GuiHoldTargetAttestationStore()
    )

    class FakeSatisfied:

        satisfied = True

    with pytest.raises(
        ValueError,
        match="exact satisfied",
    ):
        store.issue(
            result=FakeSatisfied(),
            button="left",
        )


def test_unsatisfied_result_cannot_issue_hold_receipt():

    store = (
        GuiHoldTargetAttestationStore()
    )

    result = matching_result(
        status="unknown",
    )

    with pytest.raises(
        ValueError,
        match="satisfied",
    ):
        store.issue(
            result=result,
            button="left",
        )


@pytest.mark.parametrize(
    "button",
    (
        "",
        " left",
        "left ",
        "LEFT",
        "Right",
        "sideways",
        True,
        1,
        None,
    ),
)
def test_issue_button_identity_is_exact(
    button,
):

    store = (
        GuiHoldTargetAttestationStore()
    )

    with pytest.raises(
        ValueError,
        match="exactly one of",
    ):
        store.issue(
            result=matching_result(),
            button=button,
        )


@pytest.mark.parametrize(
    (
        "field_name",
        "bad_value",
    ),
    (
        ("observation_id", ""),
        ("observation_id", " obs-hold"),
        ("observation_id", "obs-hold "),
        ("x", -1),
        ("x", True),
        ("y", -1),
        ("y", False),
        ("goal_sha256", ""),
        ("image_sha256", ""),
        ("target_region_sha256", ""),
    ),
)
def test_issue_rejects_missing_or_malformed_target_evidence(
    field_name,
    bad_value,
):

    store = (
        GuiHoldTargetAttestationStore()
    )

    result = matching_result(
        **{
            field_name: bad_value,
        }
    )

    with pytest.raises(
        ValueError,
        match="trusted hold-target",
    ):
        store.issue(
            result=result,
            button="left",
        )


def test_exact_claim_succeeds_once():

    store = (
        GuiHoldTargetAttestationStore()
    )

    result = matching_result()

    store.issue(
        result=result,
        button="middle",
    )

    claimed = store.claim(
        observation_id="obs-hold",
        x=250,
        y=179,
        button="middle",
    )

    assert (
        claimed.button
        == "middle"
    )

    with pytest.raises(
        ValueError,
        match="No semantic hold",
    ):
        store.claim(
            observation_id="obs-hold",
            x=250,
            y=179,
            button="middle",
        )


@pytest.mark.parametrize(
    "claim_overrides",
    (
        {
            "observation_id": "obs-other",
        },
        {
            "x": 251,
        },
        {
            "y": 180,
        },
        {
            "button": "right",
        },
        {
            "button": "LEFT",
        },
        {
            "x": True,
        },
    ),
)
def test_mismatched_claim_consumes_receipt(
    claim_overrides,
):

    store = (
        GuiHoldTargetAttestationStore()
    )

    store.issue(
        result=matching_result(),
        button="left",
    )

    claim = {
        "observation_id": "obs-hold",
        "x": 250,
        "y": 179,
        "button": "left",
    }

    claim.update(
        claim_overrides
    )

    with pytest.raises(
        ValueError,
        match="exact target and button",
    ):
        store.claim(
            **claim
        )

    with pytest.raises(
        ValueError,
        match="No semantic hold",
    ):
        store.claim(
            observation_id="obs-hold",
            x=250,
            y=179,
            button="left",
        )


def test_expired_claim_consumes_receipt():

    store = (
        GuiHoldTargetAttestationStore(
            max_age_seconds=5.0,
        )
    )

    with patch(
        "app.vision.gui_target_verifier."
        "time.monotonic",
        side_effect=(
            100.0,
            106.0,
        ),
    ):

        store.issue(
            result=matching_result(),
            button="left",
        )

        with pytest.raises(
            ValueError,
            match="expired",
        ):
            store.claim(
                observation_id="obs-hold",
                x=250,
                y=179,
                button="left",
            )

    with pytest.raises(
        ValueError,
        match="No semantic hold",
    ):
        store.claim(
            observation_id="obs-hold",
            x=250,
            y=179,
            button="left",
        )


def test_negative_age_fails_closed_and_consumes_receipt():

    store = (
        GuiHoldTargetAttestationStore(
            max_age_seconds=5.0,
        )
    )

    with patch(
        "app.vision.gui_target_verifier."
        "time.monotonic",
        side_effect=(
            100.0,
            99.0,
        ),
    ):

        store.issue(
            result=matching_result(),
            button="right",
        )

        with pytest.raises(
            ValueError,
            match="expired",
        ):
            store.claim(
                observation_id="obs-hold",
                x=250,
                y=179,
                button="right",
            )


def test_clear_invalidates_pending_receipt():

    store = (
        GuiHoldTargetAttestationStore()
    )

    store.issue(
        result=matching_result(),
        button="left",
    )

    store.clear()

    with pytest.raises(
        ValueError,
        match="No semantic hold",
    ):
        store.claim(
            observation_id="obs-hold",
            x=250,
            y=179,
            button="left",
        )


def test_global_store_has_hold_specific_type():

    assert isinstance(
        GUI_HOLD_TARGET_ATTESTATIONS,
        GuiHoldTargetAttestationStore,
    )


def test_pixel_continuity_contract_accepts_all_target_receipt_types():

    annotation = get_type_hints(
        current_screen_matches_attestation
    )[
        "attestation"
    ]

    assert set(
        get_args(
            annotation
        )
    ) == {
        GuiTargetAttestation,
        GuiSemanticTargetAttestation,
        GuiHoldTargetAttestation,
    }


def test_hold_receipt_has_no_body_state_or_execution_authority():

    attestation = (
        GuiHoldTargetAttestationStore()
        .issue(
            result=matching_result(),
            button="left",
        )
    )

    for name in (
        "held",
        "button_state",
        "permission",
        "authorized",
        "approved",
        "executed",
        "clicks",
        "duration",
    ):
        assert not hasattr(
            attestation,
            name,
        )
