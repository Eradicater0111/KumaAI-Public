from __future__ import annotations

from app.realtime.contracts import RealtimeFact
from app.realtime.weather_provider import (
    WEATHER_DAILY_FACT_KIND,
    WEATHER_FACT_KIND,
)

_WMO = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy with rime",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "heavy freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with light hail",
    99: "thunderstorm with heavy hail",
}


def _number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _fmt(value, decimals=1):
    rounded = round(float(value), decimals)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.{decimals}f}".rstrip("0").rstrip(".")


def weather_code_description(code):
    numeric = _number(code)
    if numeric is None:
        return None
    integer = int(numeric)
    if numeric != integer:
        return None
    return _WMO.get(integer)


def format_current_weather(fact: RealtimeFact) -> str:
    """Deterministically render a zero-authority current-weather fact."""

    if not isinstance(fact, RealtimeFact):
        raise TypeError("fact must be a RealtimeFact.")
    if fact.kind != WEATHER_FACT_KIND:
        raise ValueError("fact must be weather.current.")
    if fact.authority != "NONE":
        raise ValueError("weather fact authority must be NONE.")
    if not isinstance(fact.value, dict):
        raise ValueError("weather fact value must be a dictionary.")

    value = fact.value
    location = str(fact.location or "your current area").strip()

    temperature = _number(value.get("temperature_c"))
    apparent = _number(value.get("apparent_temperature_c"))
    humidity = _number(value.get("relative_humidity_percent"))
    precipitation = _number(value.get("precipitation_mm"))
    wind = _number(value.get("wind_speed_kmh"))
    condition = weather_code_description(value.get("weather_code"))

    details = []

    if temperature is not None:
        details.append(_fmt(temperature) + "°C")

    if (
        apparent is not None
        and (
            temperature is None
            or abs(apparent - temperature) >= 0.5
        )
    ):
        details.append("feels like " + _fmt(apparent) + "°C")

    if condition:
        details.append(condition)

    if humidity is not None:
        details.append("humidity " + _fmt(humidity, 0) + "%")

    if wind is not None:
        details.append("wind " + _fmt(wind) + " km/h")

    if precipitation is not None:
        details.append("precipitation " + _fmt(precipitation) + " mm")

    if not details:
        return (
            "I received a current-weather reading for "
            + location
            + ", but it did not contain usable conditions."
        )

    return (
        "Current weather in "
        + location
        + ": "
        + ", ".join(details)
        + "."
    )


def format_daily_weather(
    fact: RealtimeFact,
) -> str:
    """
    Deterministically render one today/tomorrow daily weather fact.
    """

    if not isinstance(
        fact,
        RealtimeFact,
    ):
        raise TypeError(
            "fact must be a RealtimeFact."
        )

    if fact.kind != WEATHER_DAILY_FACT_KIND:
        raise ValueError(
            "fact must be weather.daily."
        )

    if fact.authority != "NONE":
        raise ValueError(
            "weather fact authority must be NONE."
        )

    if not isinstance(
        fact.value,
        dict,
    ):
        raise ValueError(
            "weather fact value must be a dictionary."
        )

    value = fact.value

    period = str(
        value.get(
            "period"
        )
        or "daily"
    ).strip().lower()

    location = str(
        fact.location
        or "your current area"
    ).strip()

    date_value = str(
        value.get(
            "date"
        )
        or ""
    ).strip()

    condition = weather_code_description(
        value.get(
            "weather_code"
        )
    )

    high = _number(
        value.get(
            "temperature_max_c"
        )
    )

    low = _number(
        value.get(
            "temperature_min_c"
        )
    )

    precipitation = _number(
        value.get(
            "precipitation_sum_mm"
        )
    )

    probability = _number(
        value.get(
            "precipitation_probability_max_percent"
        )
    )

    wind = _number(
        value.get(
            "wind_speed_max_kmh"
        )
    )

    details = []

    if condition:
        details.append(
            condition
        )

    if (
        high is not None
        and low is not None
    ):
        details.append(
            "high "
            + _fmt(
                high
            )
            + "°C"
            + ", low "
            + _fmt(
                low
            )
            + "°C"
        )

    elif high is not None:
        details.append(
            "high "
            + _fmt(
                high
            )
            + "°C"
        )

    elif low is not None:
        details.append(
            "low "
            + _fmt(
                low
            )
            + "°C"
        )

    if probability is not None:
        details.append(
            "rain chance up to "
            + _fmt(
                probability,
                decimals=0,
            )
            + "%"
        )

    if precipitation is not None:
        details.append(
            "precipitation "
            + _fmt(
                precipitation
            )
            + " mm"
        )

    if wind is not None:
        details.append(
            "max wind "
            + _fmt(
                wind
            )
            + " km/h"
        )

    label = (
        period.capitalize()
        if period in {
            "today",
            "tomorrow",
        }
        else "Daily weather"
    )

    if date_value:
        label += (
            " ("
            + date_value
            + ")"
        )

    if not details:
        return (
            label
            + " in "
            + location
            + ": forecast data was available, but no usable conditions were returned."
        )

    return (
        label
        + " in "
        + location
        + ": "
        + ", ".join(
            details
        )
        + "."
    )
