from __future__ import annotations

import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from hashlib import sha256
from typing import Callable
from urllib.parse import urlparse

import httpx

from app.realtime.contracts import RealtimeFact
from app.realtime.location_adapter import LOCATION_FACT_KIND
from app.realtime.store import RealtimeFactStore


WEATHER_FACT_KIND = "weather.current"
WEATHER_DAILY_FACT_KIND = "weather.daily"
DEFAULT_WEATHER_TTL_SECONDS = 600

OPEN_METEO_SOURCE = "Open-Meteo"

OPEN_METEO_GEOCODING_URL = (
    "https://geocoding-api.open-meteo.com/v1/search"
)

OPEN_METEO_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

_ALLOWED_ENDPOINTS = {
    OPEN_METEO_GEOCODING_URL,
    OPEN_METEO_FORECAST_URL,
}

_MAX_RESPONSE_BYTES = 512 * 1024

FetchJson = Callable[
    [
        str,
        dict[str, object],
    ],
    dict,
]

Clock = Callable[
    [],
    datetime,
]


def _require_aware(
    name: str,
    value: datetime,
) -> None:
    if (
        value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(
            f"{name} must be timezone-aware."
        )


def _utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _default_fetch_json(
    url: str,
    params: dict[str, object],
) -> dict:
    """
    Fixed-endpoint, read-only JSON retrieval.

    No redirects, no proxy/environment inheritance, no arbitrary URLs.
    """

    if url not in _ALLOWED_ENDPOINTS:
        raise ValueError(
            "weather provider attempted a non-allowlisted endpoint."
        )

    parsed = urlparse(
        url
    )

    if (
        parsed.scheme != "https"
        or parsed.port not in (
            None,
            443,
        )
    ):
        raise ValueError(
            "weather endpoints must use HTTPS on port 443."
        )

    with httpx.Client(
        follow_redirects=False,
        trust_env=False,
        timeout=5.0,
        headers={
            "Accept": "application/json",
            "User-Agent": "KUMA-Realtime-Weather/1.0",
        },
    ) as client:
        with client.stream(
            "GET",
            url,
            params=params,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    "weather provider HTTP error: "
                    f"{response.status_code}"
                )

            content_type = (
                response.headers.get(
                    "content-type",
                    ""
                )
                .split(
                    ";",
                    1,
                )[0]
                .strip()
                .lower()
            )

            if content_type not in (
                "application/json",
                "application/geo+json",
            ):
                raise RuntimeError(
                    "weather provider received non-JSON content."
                )

            chunks = []
            size = 0

            for chunk in response.iter_bytes():
                size += len(
                    chunk
                )

                if size > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(
                        "weather provider response exceeded size limit."
                    )

                chunks.append(
                    chunk
                )

    payload = json.loads(
        b"".join(
            chunks
        ).decode(
            "utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "weather provider expected a JSON object."
        )

    return payload


def _source_timestamp(
    current_payload: dict,
    *,
    fallback: datetime,
) -> datetime:
    raw_time = current_payload.get(
        "time"
    )

    if isinstance(
        raw_time,
        (
            int,
            float,
        ),
    ):
        return datetime.fromtimestamp(
            raw_time,
            tz=timezone.utc,
        )

    if isinstance(
        raw_time,
        str,
    ):
        text = raw_time.strip()

        if text:
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
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

    return fallback


def _optional_number(
    payload: dict,
    key: str,
):
    value = payload.get(
        key
    )

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return int(
            value
        )

    if isinstance(
        value,
        (
            int,
            float,
        ),
    ):
        return value

    raise ValueError(
        f"weather field {key!r} must be numeric when present."
    )


class OpenMeteoWeatherProvider:
    """
    Account-free, read-only current-weather provider.

    The provider consumes the freshest unexpired approximate location
    fact, uses city-level geocoding transiently, and emits only a
    canonical AUTHORITY: NONE weather fact.

    Geocoded latitude/longitude are local variables only and are never
    placed in the realtime fact value.
    """

    def __init__(
        self,
        *,
        store: RealtimeFactStore,
        fetch_json: FetchJson | None = None,
        clock: Clock | None = None,
        ttl_seconds: int = DEFAULT_WEATHER_TTL_SECONDS,
    ) -> None:
        if not isinstance(
            store,
            RealtimeFactStore,
        ):
            raise TypeError(
                "store must be a RealtimeFactStore."
            )

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

        self._store = store
        self._fetch_json = (
            fetch_json
            or _default_fetch_json
        )
        self._clock = (
            clock
            or _utc_now
        )
        self._ttl_seconds = ttl_seconds

    def refresh(
        self,
    ) -> RealtimeFact | None:
        observed_at = self._clock()

        _require_aware(
            "clock result",
            observed_at,
        )

        location_fact = (
            self._latest_location_fact(
                at=observed_at
            )
        )

        if location_fact is None:
            return None

        location_label = str(
            location_fact.location
            or ""
        ).strip()

        if not location_label:
            return None

        geocoding = self._fetch_json(
            OPEN_METEO_GEOCODING_URL,
            {
                "name": location_label,
                "count": 1,
                "format": "json",
                "language": "en",
            },
        )

        results = geocoding.get(
            "results"
        )

        if not isinstance(
            results,
            list,
        ) or not results:
            return None

        candidate = results[
            0
        ]

        if not isinstance(
            candidate,
            dict,
        ):
            raise ValueError(
                "weather geocoding result must be an object."
            )

        latitude = candidate.get(
            "latitude"
        )
        longitude = candidate.get(
            "longitude"
        )

        if not isinstance(
            latitude,
            (
                int,
                float,
            ),
        ) or not isinstance(
            longitude,
            (
                int,
                float,
            ),
        ):
            raise ValueError(
                "weather geocoding result is missing coordinates."
            )

        forecast = self._fetch_json(
            OPEN_METEO_FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,"
                    "apparent_temperature,"
                    "relative_humidity_2m,"
                    "precipitation,"
                    "weather_code,"
                    "cloud_cover,"
                    "wind_speed_10m,"
                    "wind_direction_10m,"
                    "is_day"
                ),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "timezone": "UTC",
                "timeformat": "unixtime",
                "forecast_days": 1,
            },
        )

        current = forecast.get(
            "current"
        )

        if not isinstance(
            current,
            dict,
        ):
            raise ValueError(
                "weather response is missing current conditions."
            )

        source_timestamp = _source_timestamp(
            current,
            fallback=observed_at,
        )

        value = {
            "temperature_c": _optional_number(
                current,
                "temperature_2m",
            ),
            "apparent_temperature_c": _optional_number(
                current,
                "apparent_temperature",
            ),
            "relative_humidity_percent": _optional_number(
                current,
                "relative_humidity_2m",
            ),
            "precipitation_mm": _optional_number(
                current,
                "precipitation",
            ),
            "weather_code": _optional_number(
                current,
                "weather_code",
            ),
            "cloud_cover_percent": _optional_number(
                current,
                "cloud_cover",
            ),
            "wind_speed_kmh": _optional_number(
                current,
                "wind_speed_10m",
            ),
            "wind_direction_degrees": _optional_number(
                current,
                "wind_direction_10m",
            ),
            "is_day": _optional_number(
                current,
                "is_day",
            ),
        }

        digest_payload = json.dumps(
            forecast,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
        )

        return RealtimeFact(
            kind=WEATHER_FACT_KIND,
            value=value,
            source=OPEN_METEO_SOURCE,
            source_timestamp=source_timestamp,
            observed_at=observed_at,
            expires_at=(
                observed_at
                + timedelta(
                    seconds=self._ttl_seconds
                )
            ),
            confidence=0.9,
            location=location_label,
            raw_evidence_digest=sha256(
                digest_payload.encode(
                    "utf-8"
                )
            ).hexdigest(),
        )

    def refresh_daily(
        self,
        *,
        period: str,
    ) -> RealtimeFact | None:
        """
        Fetch deterministic daily weather for today or tomorrow.

        City-level geocoding coordinates remain transient and are never
        stored in the returned realtime fact.
        """

        normalized_period = str(
            period
            or ""
        ).strip().lower()

        if normalized_period not in {
            "today",
            "tomorrow",
        }:
            raise ValueError(
                "period must be 'today' or 'tomorrow'."
            )

        observed_at = self._clock()

        _require_aware(
            "clock result",
            observed_at,
        )

        location_fact = (
            self._latest_location_fact(
                at=observed_at
            )
        )

        if location_fact is None:
            return None

        location_label = str(
            location_fact.location
            or ""
        ).strip()

        if not location_label:
            return None

        geocoding = self._fetch_json(
            OPEN_METEO_GEOCODING_URL,
            {
                "name": location_label,
                "count": 1,
                "format": "json",
                "language": "en",
            },
        )

        results = geocoding.get(
            "results"
        )

        if not isinstance(
            results,
            list,
        ) or not results:
            return None

        candidate = results[0]

        if not isinstance(
            candidate,
            dict,
        ):
            raise ValueError(
                "weather geocoding result must be an object."
            )

        latitude = candidate.get(
            "latitude"
        )
        longitude = candidate.get(
            "longitude"
        )

        if not isinstance(
            latitude,
            (
                int,
                float,
            ),
        ) or not isinstance(
            longitude,
            (
                int,
                float,
            ),
        ):
            raise ValueError(
                "weather geocoding result is missing coordinates."
            )

        forecast = self._fetch_json(
            OPEN_METEO_FORECAST_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "daily": (
                    "weather_code,"
                    "temperature_2m_max,"
                    "temperature_2m_min,"
                    "apparent_temperature_max,"
                    "apparent_temperature_min,"
                    "precipitation_sum,"
                    "precipitation_probability_max,"
                    "wind_speed_10m_max"
                ),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "timezone": "auto",
                "forecast_days": 2,
            },
        )

        daily = forecast.get(
            "daily"
        )

        if not isinstance(
            daily,
            dict,
        ):
            raise ValueError(
                "weather response is missing daily forecast."
            )

        index = (
            0
            if normalized_period == "today"
            else 1
        )

        def daily_value(
            key: str,
        ):
            values = daily.get(
                key
            )

            if not isinstance(
                values,
                list,
            ):
                return None

            if index >= len(
                values
            ):
                return None

            return values[
                index
            ]

        date_value = daily_value(
            "time"
        )

        if not isinstance(
            date_value,
            str,
        ) or not date_value.strip():
            return None

        value = {
            "period": normalized_period,
            "date": date_value.strip(),
            "weather_code": daily_value(
                "weather_code"
            ),
            "temperature_max_c": daily_value(
                "temperature_2m_max"
            ),
            "temperature_min_c": daily_value(
                "temperature_2m_min"
            ),
            "apparent_temperature_max_c": daily_value(
                "apparent_temperature_max"
            ),
            "apparent_temperature_min_c": daily_value(
                "apparent_temperature_min"
            ),
            "precipitation_sum_mm": daily_value(
                "precipitation_sum"
            ),
            "precipitation_probability_max_percent": daily_value(
                "precipitation_probability_max"
            ),
            "wind_speed_max_kmh": daily_value(
                "wind_speed_10m_max"
            ),
        }

        digest_payload = json.dumps(
            forecast,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=False,
        )

        return RealtimeFact(
            kind=WEATHER_DAILY_FACT_KIND,
            value=value,
            source=OPEN_METEO_SOURCE,
            source_timestamp=observed_at,
            observed_at=observed_at,
            expires_at=(
                observed_at
                + timedelta(
                    seconds=self._ttl_seconds
                )
            ),
            confidence=0.9,
            location=location_label,
            raw_evidence_digest=sha256(
                digest_payload.encode(
                    "utf-8"
                )
            ).hexdigest(),
        )

    def _latest_location_fact(
        self,
        *,
        at: datetime,
    ) -> RealtimeFact | None:
        candidates = [
            fact
            for fact in self._store.snapshot(
                at=at,
            )
            if (
                fact.kind
                == LOCATION_FACT_KIND
            )
        ]

        if not candidates:
            return None

        return max(
            candidates,
            key=lambda fact: fact.observed_at,
        )
