from __future__ import annotations

from app.integration_v2_live_turn_owner import (
    RealtimeTriggerAdmissionPolicy,
)
from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
)


# =========================================================
# KUMA INTEGRATION-V2F — PRODUCTION REALTIME TRACE POLICY
# =========================================================
#
# HIGH / 0.80 is an explicit production admission policy for attaching
# already-observed realtime evidence to an explicit user turn.
#
# Current detector semantics:
#   HIGH   -> 0.80 / 0.85 / 0.90
#   MEDIUM -> 0.55 / 0.60 / 0.65
#
# Therefore this policy admits all current HIGH detector changes and rejects
# current MEDIUM / LOW changes.
#
# TRACE ELIGIBILITY != WAKE
# TRACE ELIGIBILITY != ATTENTION SURFACING
# TRACE ELIGIBILITY != PERMISSION
# TRACE ELIGIBILITY != EXECUTION
# PRODUCTION POLICY != RAPHAEL POLICY
# AUTHORITY: NONE
# =========================================================


PRODUCTION_REALTIME_TRIGGER_POLICY = (
    RealtimeTriggerAdmissionPolicy(
        minimum_level=RealtimeRelevanceLevel.HIGH,
        minimum_score=0.80,
    )
)
