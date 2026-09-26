from __future__ import annotations

from datetime import (
    datetime,
    timedelta,
    timezone,
)
from hashlib import sha256

from app.realtime.contracts import RealtimeFact
from app.realtime.store import RealtimeFactStore


LOCATION_FACT_KIND = "location.current"
DEFAULT_LOCATION_TTL_SECONDS = 30


def _parse_key_value_evidence(
    evidence: str,
) -> dict[str, str]:
    parsed: dict[str, str] = {}

    for raw_line in str(
        evidence
        or ""
    ).splitlines():
        line = raw_line.strip()

        if (
            not line
            or ":" not in line
        ):
            continue

        key, value = line.split(
            ":",
            1,
        )

        key = key.strip()
        value = value.strip()

        if not key:
            continue

        parsed[key] = value

    return parsed


def _parse_utc_timestamp(
    value: str,
) -> datetime:
    text = value.strip()

    if text.endswith(
        "Z"
    ):
        text = (
            text[:-1]
            + "+00:00"
        )

    parsed = datetime.fromisoformat(
        text
    )

    if (
        parsed.tzinfo is None
        or parsed.utcoffset() is None
    ):
        raise ValueError(
            "OBSERVED_AT must be timezone-aware."
        )

    return parsed.astimezone(
        timezone.utc
    )


def _optional_float(
    value: str | None,
) -> float | None:
    if value is None:
        return None

    text = value.strip()

    if not text:
        return None

    return float(
        text
    )


def location_evidence_to_realtime_fact(
    evidence: str,
    *,
    ttl_seconds: int = DEFAULT_LOCATION_TTL_SECONDS,
) -> RealtimeFact:
    """
    Convert KUMA's approximate Core Location evidence envelope into the
    canonical realtime fact model.

    Privacy boundary:
    - approximate/city mode only
    - no latitude or longitude is copied into the fact value
    - no street/postal/address fields are copied
    - only a SHA-256 digest of the raw evidence is retained
    """

    if (
        not isinstance(
            ttl_seconds,
            int,
        )
        or ttl_seconds <= 0
    ):
        raise ValueError(
            "ttl_seconds must be a positive integer."
        )

    raw = str(
        evidence
        or ""
    ).strip()

    if not raw:
        raise ValueError(
            "location evidence cannot be blank."
        )

    if (
        "KUMA_LOCAL_LOCATION_EVIDENCE"
        not in raw
    ):
        raise ValueError(
            "not a KUMA local location evidence envelope."
        )

    fields = _parse_key_value_evidence(
        raw
    )

    if (
        fields.get(
            "EVIDENCE_TYPE"
        )
        != "current_location"
    ):
        raise ValueError(
            "location evidence must have EVIDENCE_TYPE: current_location."
        )

    if (
        fields.get(
            "AUTHORITY"
        )
        != "NONE"
    ):
        raise ValueError(
            "location evidence authority must be NONE."
        )

    precision = fields.get(
        "PRECISION",
        "",
    )

    if precision != "city_or_approximate":
        raise ValueError(
            "realtime location ingestion accepts approximate mode only."
        )

    observed_at_text = fields.get(
        "OBSERVED_AT"
    )

    if not observed_at_text:
        raise ValueError(
            "location evidence is missing OBSERVED_AT."
        )

    observed_at = _parse_utc_timestamp(
        observed_at_text
    )

    source = fields.get(
        "SOURCE",
        "",
    ).strip()

    if not source:
        raise ValueError(
            "location evidence is missing SOURCE."
        )

    weather_location = fields.get(
        "WEATHER_LOCATION",
        "",
    ).strip()

    locality = fields.get(
        "LOCALITY",
        "",
    ).strip()

    region = fields.get(
        "REGION",
        "",
    ).strip()

    country = fields.get(
        "COUNTRY",
        "",
    ).strip()

    location_label = (
        weather_location
        or ", ".join(
            part
            for part in (
                locality,
                region,
                country,
            )
            if part
        )
    )

    if not location_label:
        raise ValueError(
            "location evidence has no usable approximate location label."
        )

    value = {
        "locality": locality or None,
        "region": region or None,
        "country": country or None,
        "country_code": (
            fields.get(
                "COUNTRY_CODE",
                "",
            ).strip()
            or None
        ),
        "precision": precision,
        "horizontal_accuracy_m": _optional_float(
            fields.get(
                "HORIZONTAL_ACCURACY_M"
            )
        ),
        "os_authorization": (
            fields.get(
                "OS_AUTHORIZATION",
                "",
            ).strip()
            or None
        ),
        "location_history_persisted": False,
    }

    digest = sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()

    return RealtimeFact(
        kind=LOCATION_FACT_KIND,
        value=value,
        source=source,
        source_timestamp=observed_at,
        observed_at=observed_at,
        expires_at=(
            observed_at
            + timedelta(
                seconds=ttl_seconds
            )
        ),
        confidence=1.0,
        location=location_label,
        raw_evidence_digest=digest,
    )


def ingest_location_evidence(
    store: RealtimeFactStore,
    evidence: str,
    *,
    ttl_seconds: int = DEFAULT_LOCATION_TTL_SECONDS,
) -> RealtimeFact:
    if not isinstance(
        store,
        RealtimeFactStore,
    ):
        raise TypeError(
            "store must be a RealtimeFactStore."
        )

    fact = location_evidence_to_realtime_fact(
        evidence,
        ttl_seconds=ttl_seconds,
    )

    store.put(
        fact
    )

    return fact
