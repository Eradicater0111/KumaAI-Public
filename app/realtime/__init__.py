"""KUMA realtime nervous-system core.

REALTIME-1A..1F provide the zero-authority realtime nervous system.
WEATHER-1A adds deterministic current-weather rendering.
"""

from app.realtime.change_detection import (
    RealtimeChangeDetector,
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.contracts import (
    RealtimeEvent,
    RealtimeEventType,
    RealtimeFact,
)
from app.realtime.event_bus import RealtimeEventBus
from app.realtime.location_adapter import (
    DEFAULT_LOCATION_TTL_SECONDS,
    LOCATION_FACT_KIND,
    ingest_location_evidence,
    location_evidence_to_realtime_fact,
)
from app.realtime.runtime import (
    RealtimeRuntime,
    get_realtime_runtime,
)
from app.realtime.scheduler import (
    RefreshExecution,
    RealtimeScheduler,
)
from app.realtime.store import RealtimeFactStore
from app.realtime.weather_provider import (
    DEFAULT_WEATHER_TTL_SECONDS,
    WEATHER_DAILY_FACT_KIND,
    WEATHER_FACT_KIND,
    OpenMeteoWeatherProvider,
)
from app.realtime.weather_render import (
    format_current_weather,
    format_daily_weather,
    weather_code_description,
)

__all__ = [
    "DEFAULT_LOCATION_TTL_SECONDS",
    "DEFAULT_WEATHER_TTL_SECONDS",
    "LOCATION_FACT_KIND",
    "OpenMeteoWeatherProvider",
    "RealtimeChangeDetector",
    "RealtimeEvent",
    "RealtimeEventBus",
    "RealtimeEventType",
    "RealtimeFact",
    "RealtimeFactStore",
    "RealtimeRelevanceLevel",
    "RealtimeRuntime",
    "RealtimeScheduler",
    "RealtimeSignal",
    "RefreshExecution",
    "WEATHER_DAILY_FACT_KIND",
    "WEATHER_FACT_KIND",
    "format_current_weather",
    "format_daily_weather",
    "get_realtime_runtime",
    "ingest_location_evidence",
    "location_evidence_to_realtime_fact",
    "weather_code_description",
]
