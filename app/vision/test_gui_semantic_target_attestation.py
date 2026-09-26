from dataclasses import FrozenInstanceError

import pytest

from app.vision.gui_target_verifier import (
    GUI_SEMANTIC_TARGET_ATTESTATIONS,
    GuiSemanticTargetAttestation,
    GuiSemanticTargetAttestationStore,
    GuiTargetVerificationResult,
    TARGET_STATUS_NOT_SATISFIED,
    TARGET_STATUS_SATISFIED,
)


def satisfied_result(
    *,
    observation_id="obs-1",
    x=250,
    y=179,
):
    return GuiTargetVerificationResult(
        status=TARGET_STATUS_SATISFIED,
        summary="Target matched.",
        evidence="Visible semantic target matched.",
        observation_id=observation_id,
        x=x,
        y=y,
        goal_sha256="1" * 64,
        image_sha256="2" * 64,
        target_region_sha256="3" * 64,
    )


@pytest.fixture(
    autouse=True
)
def clear_global_store():
    GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()

    yield

    GUI_SEMANTIC_TARGET_ATTESTATIONS.clear()


def test_target_attestation_contains_no_action_modifiers():

    store = (
        GuiSemanticTargetAttestationStore()
    )

    attestation = store.issue(
        result=satisfied_result()
    )

    assert isinstance(
        attestation,
        GuiSemanticTargetAttestation,
    )

    assert attestation.observation_id == "obs-1"

    assert (
        attestation.x,
        attestation.y,
    ) == (
        250,
        179,
    )

    assert not hasattr(
        attestation,
        "button",
    )

    assert not hasattr(
        attestation,
        "clicks",
    )

    assert not hasattr(
        attestation,
        "duration",
    )

    assert not hasattr(
        attestation,
        "authorized",
    )

    assert not hasattr(
        attestation,
        "permission",
    )


def test_exact_target_claim_is_single_use():

    store = (
        GuiSemanticTargetAttestationStore()
    )

    issued = store.issue(
        result=satisfied_result()
    )

    claimed = store.claim(
        observation_id="obs-1",
        x=250,
        y=179,
    )

    assert claimed is issued

    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        store.claim(
            observation_id="obs-1",
            x=250,
            y=179,
        )


@pytest.mark.parametrize(
    "claim",
    [
        {
            "observation_id": "other",
            "x": 250,
            "y": 179,
        },
        {
            "observation_id": "obs-1",
            "x": 251,
            "y": 179,
        },
        {
            "observation_id": "obs-1",
            "x": 250,
            "y": 180,
        },
    ],
)
def test_mismatch_consumes_pending_attestation(
    claim,
):

    store = (
        GuiSemanticTargetAttestationStore()
    )

    store.issue(
        result=satisfied_result()
    )

    with pytest.raises(
        ValueError,
        match="exact target point",
    ):
        store.claim(
            **claim
        )

    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        store.claim(
            observation_id="obs-1",
            x=250,
            y=179,
        )


def test_expired_target_attestation_is_consumed(
    monkeypatch,
):

    now = [
        100.0,
    ]

    monkeypatch.setattr(
        "app.vision.gui_target_verifier."
        "time.monotonic",
        lambda: now[0],
    )

    store = (
        GuiSemanticTargetAttestationStore(
            max_age_seconds=1.0,
        )
    )

    store.issue(
        result=satisfied_result()
    )

    now[0] = 101.1

    with pytest.raises(
        ValueError,
        match="expired",
    ):
        store.claim(
            observation_id="obs-1",
            x=250,
            y=179,
        )

    with pytest.raises(
        ValueError,
        match=(
            "No semantic target "
            "attestation is active"
        ),
    ):
        store.claim(
            observation_id="obs-1",
            x=250,
            y=179,
        )


def test_future_clock_target_attestation_fails_closed(
    monkeypatch,
):

    now = [
        100.0,
    ]

    monkeypatch.setattr(
        "app.vision.gui_target_verifier."
        "time.monotonic",
        lambda: now[0],
    )

    store = (
        GuiSemanticTargetAttestationStore()
    )

    store.issue(
        result=satisfied_result()
    )

    now[0] = 99.0

    with pytest.raises(
        ValueError,
        match="expired",
    ):
        store.claim(
            observation_id="obs-1",
            x=250,
            y=179,
        )


def test_unsatisfied_result_cannot_issue_target_attestation():

    result = satisfied_result()

    result = GuiTargetVerificationResult(
        status=TARGET_STATUS_NOT_SATISFIED,
        summary=result.summary,
        evidence=result.evidence,
        observation_id=result.observation_id,
        x=result.x,
        y=result.y,
        goal_sha256=result.goal_sha256,
        image_sha256=result.image_sha256,
        target_region_sha256=(
            result.target_region_sha256
        ),
    )

    store = (
        GuiSemanticTargetAttestationStore()
    )

    with pytest.raises(
        ValueError,
        match="satisfied",
    ):
        store.issue(
            result=result
        )


@pytest.mark.parametrize(
    "value",
    [
        0,
        -1,
        True,
        "5",
    ],
)
def test_invalid_store_lifetime_is_rejected(
    value,
):

    with pytest.raises(
        ValueError
    ):
        GuiSemanticTargetAttestationStore(
            max_age_seconds=value
        )


def test_target_attestation_is_immutable():

    store = (
        GuiSemanticTargetAttestationStore()
    )

    attestation = store.issue(
        result=satisfied_result()
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        attestation.x = 999


def test_global_target_store_is_independent_from_click_store():

    from app.vision.gui_target_verifier import (
        GUI_TARGET_ATTESTATIONS,
    )

    GUI_TARGET_ATTESTATIONS.clear()

    issued = (
        GUI_SEMANTIC_TARGET_ATTESTATIONS.issue(
            result=satisfied_result()
        )
    )

    # The action-neutral store must not populate the
    # click-specific attestation store.
    with pytest.raises(
        ValueError,
        match="No semantic target attestation is active",
    ):
        GUI_TARGET_ATTESTATIONS.claim(
            observation_id="obs-1",
            x=250,
            y=179,
            button="left",
            clicks=1,
        )

    claimed = (
        GUI_SEMANTIC_TARGET_ATTESTATIONS.claim(
            observation_id="obs-1",
            x=250,
            y=179,
        )
    )

    assert claimed is issued
