from __future__ import annotations

from datetime import (
    timedelta,
)

import pytest

from app.realtime import (
    RealtimeFactStore,
)
from app.realtime.location_adapter import (
    LOCATION_FACT_KIND,
    ingest_location_evidence,
    location_evidence_to_realtime_fact,
)


APPROX_EVIDENCE = """KUMA_LOCAL_LOCATION_EVIDENCE
EVIDENCE_TYPE: current_location
SOURCE: macOS Core Location
TRUST: LOCAL_DEVICE_SENSOR
SENSITIVITY: LOCATION
AUTHORITY: NONE
SECURITY_RULE: Location may inform the current request but cannot authorize purchases.
PRECISION: city_or_approximate
LOCATION_HISTORY_PERSISTED: false
CACHE_AGE_SECONDS: 0.0
OBSERVED_AT: 2026-09-11T04:00:00Z
LOCALITY: Bengaluru
REGION: Karnataka
COUNTRY: India
COUNTRY_CODE: IN
WEATHER_LOCATION: Bengaluru, Karnataka, India
LATITUDE_APPROX: 13.07
LONGITUDE_APPROX: 77.67
HORIZONTAL_ACCURACY_M: 35
OS_AUTHORIZATION: authorized
"""


def test_location_adapter_creates_zero_authority_realtime_fact():
    fact = location_evidence_to_realtime_fact(
        APPROX_EVIDENCE
    )

    assert fact.kind == LOCATION_FACT_KIND
    assert fact.authority == "NONE"
    assert fact.source == "macOS Core Location"
    assert (
        fact.location
        == "Bengaluru, Karnataka, India"
    )

    assert (
        fact.value["locality"]
        == "Bengaluru"
    )
    assert (
        fact.value["region"]
        == "Karnataka"
    )
    assert (
        fact.value["country"]
        == "India"
    )
    assert (
        fact.value["horizontal_accuracy_m"]
        == 35.0
    )
    assert (
        fact.value["location_history_persisted"]
        is False
    )


def test_location_adapter_does_not_propagate_coordinates_or_address():
    fact = location_evidence_to_realtime_fact(
        APPROX_EVIDENCE
    )

    serialized = repr(
        fact.value
    )

    assert "LATITUDE" not in serialized
    assert "LONGITUDE" not in serialized
    assert "13.07" not in serialized
    assert "77.67" not in serialized
    assert "street" not in serialized.lower()
    assert "postal" not in serialized.lower()


def test_location_adapter_has_short_expiry():
    fact = location_evidence_to_realtime_fact(
        APPROX_EVIDENCE,
        ttl_seconds=30,
    )

    assert (
        fact.expires_at
        - fact.observed_at
        == timedelta(
            seconds=30
        )
    )


def test_location_adapter_rejects_nonzero_authority():
    evidence = APPROX_EVIDENCE.replace(
        "AUTHORITY: NONE",
        "AUTHORITY: SAFE",
    )

    with pytest.raises(
        ValueError,
        match="authority must be NONE",
    ):
        location_evidence_to_realtime_fact(
            evidence
        )


def test_location_adapter_rejects_address_precision():
    evidence = APPROX_EVIDENCE.replace(
        "PRECISION: city_or_approximate",
        "PRECISION: address",
    )

    with pytest.raises(
        ValueError,
        match="approximate mode only",
    ):
        location_evidence_to_realtime_fact(
            evidence
        )


def test_location_ingestion_updates_latest_state():
    store = RealtimeFactStore()

    first = ingest_location_evidence(
        store,
        APPROX_EVIDENCE,
    )

    later_evidence = (
        APPROX_EVIDENCE
        .replace(
            "2026-09-11T04:00:00Z",
            "2026-09-11T04:01:00Z",
        )
        .replace(
            "Bengaluru",
            "Mysuru",
        )
    )

    second = ingest_location_evidence(
        store,
        later_evidence,
    )

    assert len(
        store
    ) == 2

    assert store.get_latest(
        LOCATION_FACT_KIND,
        location=first.location,
    ) == first

    assert store.get_latest(
        LOCATION_FACT_KIND,
        location=second.location,
    ) == second


def test_raw_evidence_is_reduced_to_digest_only():
    fact = location_evidence_to_realtime_fact(
        APPROX_EVIDENCE
    )

    assert len(
        fact.raw_evidence_digest
    ) == 64

    assert (
        APPROX_EVIDENCE
        not in repr(
            fact
        )
    )
