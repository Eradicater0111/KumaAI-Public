from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import inspect

import pytest

from app.realtime import (
    RealtimeEvent,
    RealtimeEventType,
    RealtimeFact,
    RealtimeRelevanceLevel,
    RealtimeSignal,
)
from app.realtime.change_detection import RealtimeChangeDetector

from app.agent.proactive_attention import (
    AttentionContext,
    AttentionCue,
    AttentionDecision,
    AttentionDisposition,
    ProactiveAttentionEngine,
    ProactiveEvent,
    freshness_factor,
    project_realtime_signal,
    realtime_signal_event_id,
)


UTC = timezone.utc
T0 = datetime(2026, 9, 11, 6, 0, tzinfo=UTC)


def fact(
    *,
    kind="weather.current",
    value=None,
    observed_at=T0,
    confidence=1.0,
    location="Example",
    digest="source-digest",
):
    if value is None:
        value = {
            "temperature_c": 25.0,
            "precipitation_mm": 1.2,
        }

    return RealtimeFact(
        kind=kind,
        value=value,
        source="test",
        observed_at=observed_at,
        source_timestamp=observed_at,
        expires_at=observed_at + timedelta(minutes=10),
        confidence=confidence,
        location=location,
        raw_evidence_digest=digest,
    )


def signal(
    *,
    kind="weather.current",
    level=RealtimeRelevanceLevel.HIGH,
    score=0.90,
    reason="precipitation started",
    current=None,
    previous=None,
):
    current = current or fact(kind=kind)

    return RealtimeSignal(
        kind=kind,
        level=level,
        score=score,
        reason=reason,
        fact=current,
        previous_fact=previous,
    )


def event_for(item=None):
    return project_realtime_signal(item or signal())


def cue_for(
    item=None,
    *,
    goal=0.0,
    time=0.0,
    consequence=0.0,
    reason="Structured test cue.",
):
    event = event_for(item)

    return AttentionCue(
        event_id=event.event_id,
        goal_relevance=goal,
        time_sensitivity=time,
        consequence_of_ignoring=consequence,
        reason=reason,
    )


def context_for(
    item=None,
    *,
    current_time=T0,
    goal="",
    remaining="",
    status="",
    seen=(),
    acknowledged=(),
    cue=None,
):
    cues = () if cue is None else (cue,)

    return AttentionContext(
        current_time=current_time,
        active_goal=goal,
        remaining_objective=remaining,
        mission_status=status,
        seen_event_ids=seen,
        acknowledged_event_ids=acknowledged,
        cues=cues,
    )


def engine():
    return ProactiveAttentionEngine()


def test_proactive_event_is_frozen_and_zero_authority():
    item = event_for()
    assert item.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        item.kind = "changed"


def test_attention_cue_is_frozen_and_zero_authority():
    item = cue_for()
    assert item.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        item.goal_relevance = 1.0


def test_attention_context_is_frozen_and_zero_authority():
    item = context_for()
    assert item.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        item.mission_status = "changed"


def test_attention_decision_is_frozen_and_zero_authority():
    result = engine().decide((signal(),), context_for())
    assert result.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"


def test_signal_event_id_is_deterministic():
    item = signal()
    assert realtime_signal_event_id(item) == realtime_signal_event_id(item)


def test_signal_event_id_changes_with_source_evidence():
    first = signal(current=fact(digest="first"))
    second = signal(current=fact(digest="second"))

    assert realtime_signal_event_id(first) != realtime_signal_event_id(second)


def test_projection_excludes_raw_value_and_location():
    item = signal(
        kind="location.current",
        reason="approximate location changed",
        current=fact(
            kind="location.current",
            value={
                "locality": "Sensitive Example",
                "secret": "must-not-copy",
            },
            location="Sensitive Exact-Looking Place",
        ),
    )

    projected = project_realtime_signal(item)
    representation = repr(projected)

    assert "must-not-copy" not in representation
    assert "Sensitive Example" not in representation
    assert "Sensitive Exact-Looking Place" not in representation

    for name in ("fact", "value", "location"):
        assert not hasattr(projected, name)


def test_projection_preserves_bounded_signal_metadata():
    item = signal(
        kind="location.current",
        score=0.85,
        reason="approximate location changed",
        current=fact(
            kind="location.current",
            confidence=0.92,
            digest="location-digest",
        ),
    )

    projected = project_realtime_signal(item)

    assert projected.kind == "location.current"
    assert projected.reason == "approximate location changed"
    assert projected.realtime_level == RealtimeRelevanceLevel.HIGH
    assert projected.realtime_score == 0.85
    assert projected.confidence == 0.92
    assert projected.source_evidence_digest == "location-digest"


def test_projection_preserves_previous_digest_without_previous_value():
    previous = fact(
        digest="previous-digest",
        value={"secret": "old-secret"},
    )
    projected = event_for(signal(previous=previous))

    assert projected.previous_evidence_digest == "previous-digest"
    assert "old-secret" not in repr(projected)


def test_projection_rejects_non_signal():
    with pytest.raises(TypeError, match="RealtimeSignal"):
        project_realtime_signal(object())


def test_tampered_signal_authority_fails_closed():
    item = signal()
    object.__setattr__(item, "authority", "AUTHORIZED")

    with pytest.raises(ValueError, match="authority"):
        project_realtime_signal(item)


def test_tampered_fact_authority_fails_closed():
    item = signal()
    object.__setattr__(item.fact, "authority", "AUTHORIZED")

    with pytest.raises(ValueError, match="authority"):
        project_realtime_signal(item)


def test_tampered_previous_fact_authority_fails_closed():
    previous = fact(digest="previous")
    item = signal(previous=previous)
    object.__setattr__(previous, "authority", "AUTHORIZED")

    with pytest.raises(ValueError, match="authority"):
        project_realtime_signal(item)


def test_cue_factors_are_bounded():
    event = event_for()

    with pytest.raises(ValueError, match="between"):
        AttentionCue(event_id=event.event_id, goal_relevance=1.01)

    with pytest.raises(ValueError, match="between"):
        AttentionCue(event_id=event.event_id, time_sensitivity=-0.01)


def test_cue_factor_rejects_bool():
    event = event_for()

    with pytest.raises(TypeError, match="numeric"):
        AttentionCue(event_id=event.event_id, goal_relevance=True)


def test_context_rejects_duplicate_cue_ids():
    item = signal()
    first = cue_for(item)
    second = cue_for(item, goal=1.0)

    with pytest.raises(ValueError, match="duplicate"):
        AttentionContext(
            current_time=T0,
            cues=(first, second),
        )


def test_context_rejects_malformed_seen_id():
    with pytest.raises(ValueError, match="SHA-256"):
        AttentionContext(
            current_time=T0,
            seen_event_ids=("not-a-digest",),
        )


def test_freshness_is_one_at_observation_time():
    assert freshness_factor(T0, now=T0) == 1.0


def test_future_timestamp_gets_no_freshness_bonus():
    future = T0 + timedelta(hours=4)
    assert freshness_factor(future, now=T0) == 1.0


def test_freshness_decays_with_age():
    recent = freshness_factor(T0, now=T0 + timedelta(hours=1))
    old = freshness_factor(T0, now=T0 + timedelta(hours=24))

    assert recent > old
    assert 0.0 < old < 1.0


def test_new_event_has_full_novelty():
    item = signal()
    projected = event_for(item)

    result = engine().assess(projected, context_for(item))
    assert result.novelty == 1.0


def test_seen_event_has_half_novelty():
    item = signal()
    projected = event_for(item)

    result = engine().assess(
        projected,
        context_for(item, seen=(projected.event_id,)),
    )

    assert result.novelty == 0.50


def test_acknowledged_event_is_suppressed():
    item = signal()
    projected = event_for(item)

    result = engine().assess(
        projected,
        context_for(
            item,
            acknowledged=(projected.event_id,),
        ),
    )

    assert result.novelty == 0.0
    assert result.attention_score == 0.0
    assert result.disposition == AttentionDisposition.IGNORE


def test_ignore_realtime_signal_cannot_be_promoted_by_maximal_cue():
    item = signal(
        level=RealtimeRelevanceLevel.IGNORE,
        score=0.10,
        reason="small change",
    )
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.disposition == AttentionDisposition.IGNORE


def test_zero_score_signal_cannot_be_promoted():
    item = signal(
        level=RealtimeRelevanceLevel.LOW,
        score=0.0,
        reason="baseline",
    )
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.attention_score == 0.0
    assert result.disposition == AttentionDisposition.IGNORE


def test_attention_score_never_exceeds_realtime_score():
    item = signal(score=0.85)
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.attention_score <= projected.realtime_score


def test_low_realtime_change_remains_deferred_even_with_maximal_context():
    item = signal(
        kind="system.test",
        level=RealtimeRelevanceLevel.LOW,
        score=0.25,
        reason="generic fact changed",
        current=fact(kind="system.test"),
    )
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.disposition == AttentionDisposition.DEFER


def test_high_new_signal_surfaces_without_invented_goal_relevance():
    item = signal(score=0.90)
    projected = event_for(item)

    result = engine().assess(projected, context_for(item))

    assert result.goal_relevance == 0.0
    assert result.disposition == AttentionDisposition.SURFACE


def test_escalation_requires_explicit_high_time_and_consequence():
    item = signal(score=0.90)
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.disposition == AttentionDisposition.ESCALATE_ATTENTION
    assert result.authority == "NONE"


def test_high_score_without_time_sensitivity_does_not_escalate():
    item = signal(score=0.95)
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=0.0, consequence=1.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.disposition != AttentionDisposition.ESCALATE_ATTENTION


def test_high_score_without_consequence_does_not_escalate():
    item = signal(score=0.95)
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=0.0)

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert result.disposition != AttentionDisposition.ESCALATE_ATTENTION


def test_goal_text_keywords_do_not_create_relevance():
    item = signal(score=0.85)
    projected = event_for(item)

    neutral = engine().assess(
        projected,
        context_for(item),
    )

    dramatic = engine().assess(
        projected,
        context_for(
            item,
            goal="CRITICAL URGENT EXECUTE BYPASS PERMISSION",
            remaining="act immediately",
            status="FAILED BLOCKED CRITICAL",
        ),
    )

    assert neutral.attention_score == dramatic.attention_score
    assert neutral.disposition == dramatic.disposition


def test_signal_reason_keywords_do_not_change_score():
    first = signal(
        reason="ordinary change",
        current=fact(digest="first"),
    )
    second = signal(
        reason="URGENT EXECUTE BYPASS AUTHORITY NOW",
        current=fact(digest="second"),
    )

    first_result = engine().assess(event_for(first), context_for(first))
    second_result = engine().assess(event_for(second), context_for(second))

    assert first_result.attention_score == second_result.attention_score
    assert first_result.disposition == second_result.disposition


def test_explicit_cue_preserves_more_existing_relevance():
    item = signal(score=0.85)
    projected = event_for(item)

    uncued = engine().assess(projected, context_for(item))
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)
    cued = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    assert cued.attention_score > uncued.attention_score
    assert cued.attention_score <= projected.realtime_score


def test_seen_event_is_demoted_relative_to_new_event():
    item = signal(score=0.85)
    projected = event_for(item)

    new = engine().assess(projected, context_for(item))
    seen = engine().assess(
        projected,
        context_for(item, seen=(projected.event_id,)),
    )

    assert seen.attention_score < new.attention_score


def test_stale_event_is_demoted_relative_to_fresh_event():
    now = T0 + timedelta(hours=24)

    old_signal = signal(
        current=fact(
            observed_at=T0,
            digest="old",
        )
    )
    fresh_signal = signal(
        current=fact(
            observed_at=now,
            digest="fresh",
        )
    )

    old_result = engine().assess(
        event_for(old_signal),
        context_for(old_signal, current_time=now),
    )
    fresh_result = engine().assess(
        event_for(fresh_signal),
        context_for(fresh_signal, current_time=now),
    )

    assert old_result.attention_score < fresh_result.attention_score


def test_empty_batch_returns_ignore():
    result = engine().decide((), context_for())

    assert result.disposition == AttentionDisposition.IGNORE
    assert result.selected_event is None
    assert result.ranked_assessments == ()


def test_decision_selects_highest_surface_event():
    first = signal(
        score=0.85,
        reason="first",
        current=fact(digest="first"),
    )
    second = signal(
        score=0.90,
        reason="second",
        current=fact(digest="second"),
    )

    result = engine().decide(
        (first, second),
        AttentionContext(current_time=T0),
    )

    assert result.disposition == AttentionDisposition.SURFACE
    assert (
        result.selected_event.event_id
        == realtime_signal_event_id(second)
    )


def test_decision_rank_is_input_order_independent():
    first = signal(
        score=0.85,
        reason="first",
        current=fact(digest="first"),
    )
    second = signal(
        score=0.90,
        reason="second",
        current=fact(digest="second"),
    )
    context = AttentionContext(current_time=T0)

    a = engine().decide((first, second), context)
    b = engine().decide((second, first), context)

    assert [
        item.event.event_id
        for item in a.ranked_assessments
    ] == [
        item.event.event_id
        for item in b.ranked_assessments
    ]


def test_duplicate_signal_identity_is_rejected():
    item = signal()

    with pytest.raises(ValueError, match="duplicate"):
        engine().decide(
            (item, item),
            AttentionContext(current_time=T0),
        )


def test_cue_must_bind_to_current_signal_batch():
    current = signal(current=fact(digest="current"))
    other = signal(current=fact(digest="other"))
    foreign_cue = cue_for(other, goal=1.0)

    with pytest.raises(ValueError, match="absent"):
        engine().decide(
            (current,),
            context_for(current, cue=foreign_cue),
        )


def test_acknowledged_high_event_cannot_win_again():
    high = signal(
        score=0.90,
        current=fact(digest="high"),
    )
    low = signal(
        kind="system.test",
        level=RealtimeRelevanceLevel.LOW,
        score=0.25,
        reason="generic fact changed",
        current=fact(
            kind="system.test",
            digest="low",
        ),
    )
    high_event = event_for(high)

    result = engine().decide(
        (high, low),
        AttentionContext(
            current_time=T0,
            acknowledged_event_ids=(high_event.event_id,),
        ),
    )

    assert (
        result.ranked_assessments[0].event.event_id
        == realtime_signal_event_id(low)
    )
    assert result.disposition == AttentionDisposition.DEFER


def test_escalated_decision_remains_zero_authority():
    item = signal(score=0.90)
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().decide(
        (item,),
        context_for(item, cue=cue),
    )

    assert result.disposition == AttentionDisposition.ESCALATE_ATTENTION
    assert result.authority == "NONE"
    assert result.selected_event.authority == "NONE"
    assert result.ranked_assessments[0].authority == "NONE"


def test_defer_decision_has_no_selected_event():
    item = signal(
        kind="system.test",
        level=RealtimeRelevanceLevel.LOW,
        score=0.25,
        reason="generic fact changed",
        current=fact(kind="system.test"),
    )

    result = engine().decide((item,), context_for(item))

    assert result.disposition == AttentionDisposition.DEFER
    assert result.selected_event is None


def test_realtime_change_detector_signal_feeds_1j_directly():
    detector = RealtimeChangeDetector()

    before = fact(
        value={
            "temperature_c": 25.0,
            "precipitation_mm": 0.0,
            "weather_code": 2,
            "wind_speed_kmh": 10.0,
        },
        digest="before",
    )
    after = fact(
        value={
            "temperature_c": 25.0,
            "precipitation_mm": 1.2,
            "weather_code": 61,
            "wind_speed_kmh": 12.0,
        },
        observed_at=T0 + timedelta(minutes=1),
        digest="after",
    )

    realtime = detector.evaluate(
        RealtimeEvent(
            event_type=RealtimeEventType.UPDATED,
            fact=after,
            previous_fact=before,
        )
    )

    result = engine().decide(
        (realtime,),
        AttentionContext(current_time=after.observed_at),
    )

    assert realtime.level == RealtimeRelevanceLevel.HIGH
    assert result.disposition == AttentionDisposition.SURFACE


def test_initial_baseline_signal_cannot_become_proactive_attention():
    detector = RealtimeChangeDetector()
    current = fact(digest="baseline")

    realtime = detector.evaluate(
        RealtimeEvent(
            event_type=RealtimeEventType.ADDED,
            fact=current,
            previous_fact=None,
        )
    )
    projected = project_realtime_signal(realtime)
    maximal = AttentionCue(
        event_id=projected.event_id,
        goal_relevance=1.0,
        time_sensitivity=1.0,
        consequence_of_ignoring=1.0,
        reason="Maximal structured cue.",
    )

    result = engine().decide(
        (realtime,),
        AttentionContext(
            current_time=T0,
            cues=(maximal,),
        ),
    )

    assert realtime.level == RealtimeRelevanceLevel.IGNORE
    assert result.disposition == AttentionDisposition.IGNORE


def test_engine_has_no_runtime_or_execution_surface():
    item = engine()

    for name in (
        "tick",
        "poll",
        "refresh",
        "refresh_weather",
        "observe_location_tool_result",
        "pending_signals",
        "drain_signals",
        "execute",
        "run_tool",
        "register",
        "authorize",
        "approve",
        "notify",
        "send_message",
        "persist",
    ):
        assert not hasattr(item, name)


def test_decision_has_no_permission_execution_or_notification_fields():
    result = engine().decide((signal(),), context_for())

    for name in (
        "required_permission",
        "permission",
        "approved",
        "authorized",
        "tool_name",
        "arguments",
        "execute",
        "notification",
        "message",
        "user_message",
    ):
        assert not hasattr(result, name)


def test_event_has_no_tool_execution_or_raw_fact_fields():
    item = event_for()

    for name in (
        "tool_name",
        "arguments",
        "required_permission",
        "approved",
        "authorized",
        "execute",
        "fact",
        "previous_fact",
        "value",
        "location",
    ):
        assert not hasattr(item, name)


def test_module_does_not_import_runtime_executor_or_permissions():
    import app.agent.proactive_attention as module

    source = inspect.getsource(module)

    forbidden = (
        "from app.agent.executor",
        "from app.agent.permissions",
        "from app.agent.kuma_agent",
        "from app.agent.kuma_runtime",
        "from app.agent.mission_service",
        "from app.agent.mission_state",
        "from app.agent.task_state",
        "from app.realtime.runtime",
        "get_realtime_runtime(",
        "PermissionLevel",
        "require_explicit_permission",
        "register_tool(",
        "request_confirmation(",
        "confirmation_callback",
        ".execute(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_does_not_drain_poll_or_refresh_realtime_runtime():
    import app.agent.proactive_attention as module

    source = inspect.getsource(module)

    forbidden = (
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
        "observe_location_tool_result(",
        "get_current_location(",
        ".tick(",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_model_memory_sensor_network_or_persistence_surface():
    import app.agent.proactive_attention as module

    source = inspect.getsource(module)

    forbidden = (
        "model_call",
        "ask_model(",
        "generate_content(",
        "ollama",
        "app.memory",
        "retrieve_memories",
        "get_memory_context",
        "pyautogui",
        "requests",
        "urllib",
        "web_search(",
        "fetch_webpage(",
        "sqlite",
        "write_text(",
        "write_bytes(",
        "subprocess",
    )

    for marker in forbidden:
        assert marker not in source


def test_module_has_no_dynamic_code_execution_surface():
    import app.agent.proactive_attention as module

    source = inspect.getsource(module)

    for marker in (
        "exec(",
        "eval(",
        "compile(",
        "importlib",
        "pickle",
        "marshal",
    ):
        assert marker not in source


def test_module_has_no_user_surfacing_side_effect_calls():
    import app.agent.proactive_attention as module

    source = inspect.getsource(module)

    for marker in (
        ".notify(",
        "notify_user(",
        ".send_message(",
        "emit_message(",
        "toast(",
        "banner(",
    ):
        assert marker not in source


def test_attention_score_formula_is_auditable():
    item = signal(
        score=0.80,
        current=fact(confidence=0.80),
    )
    projected = event_for(item)
    cue = cue_for(
        item,
        goal=0.50,
        time=0.25,
        consequence=0.75,
    )

    result = engine().assess(
        projected,
        context_for(item, cue=cue),
    )

    expected_quality = (
        0.20 * result.novelty
        + 0.20 * 0.50
        + 0.20 * 0.25
        + 0.20 * 0.75
        + 0.10 * 0.80
        + 0.10 * result.freshness
    )
    expected_multiplier = 0.50 + 0.50 * expected_quality
    expected_score = 0.80 * expected_multiplier

    assert result.context_quality == pytest.approx(expected_quality)
    assert result.multiplier == pytest.approx(expected_multiplier)
    assert result.attention_score == pytest.approx(expected_score)


def test_maximum_attention_and_confidence_still_authority_none():
    item = signal(
        score=1.0,
        current=fact(confidence=1.0),
    )
    projected = event_for(item)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    assessment = engine().assess(
        projected,
        context_for(item, cue=cue),
    )
    decision = engine().decide(
        (item,),
        context_for(item, cue=cue),
    )

    assert assessment.attention_score == 1.0
    assert assessment.authority == "NONE"
    assert decision.authority == "NONE"
    assert decision.selected_event.authority == "NONE"


def test_context_does_not_accept_task_or_mission_objects():
    signature = inspect.signature(AttentionContext)

    assert "task_state" not in signature.parameters
    assert "mission_state" not in signature.parameters
    assert "controller" not in signature.parameters


def test_engine_decide_signature_is_narrow():
    signature = inspect.signature(ProactiveAttentionEngine.decide)

    assert tuple(signature.parameters) == (
        "self",
        "signals",
        "context",
    )


def test_authority_is_not_constructor_input():
    for contract in (
        ProactiveEvent,
        AttentionCue,
        AttentionContext,
        AttentionDecision,
    ):
        assert "authority" not in inspect.signature(contract).parameters


def test_disposition_has_no_action_or_execution_member():
    names = {member.name for member in AttentionDisposition}

    assert names == {
        "IGNORE",
        "DEFER",
        "SURFACE",
        "ESCALATE_ATTENTION",
    }


def test_assessment_rejects_tampered_event_authority():
    projected = event_for()
    object.__setattr__(projected, "authority", "AUTHORIZED")

    with pytest.raises(ValueError, match="authority"):
        engine().assess(projected, context_for())


def test_assessment_rejects_tampered_context_authority():
    item = signal()
    projected = event_for(item)
    context = context_for(item)
    object.__setattr__(context, "authority", "AUTHORIZED")

    with pytest.raises(ValueError, match="authority"):
        engine().assess(projected, context)


def test_decision_rejects_tampered_context_authority():
    context = context_for()
    object.__setattr__(context, "authority", "AUTHORIZED")

    with pytest.raises(ValueError, match="authority"):
        engine().decide((), context)


def test_historical_seen_ids_are_allowed():
    historical = "a" * 64

    result = engine().decide(
        (signal(),),
        AttentionContext(
            current_time=T0,
            seen_event_ids=(historical,),
        ),
    )

    assert result.disposition == AttentionDisposition.SURFACE


def test_acknowledgement_does_not_require_goal_context():
    item = signal()
    projected = event_for(item)

    result = engine().decide(
        (item,),
        AttentionContext(
            current_time=T0,
            acknowledged_event_ids=(projected.event_id,),
        ),
    )

    assert result.disposition == AttentionDisposition.IGNORE


def test_signal_batch_is_bounded():
    items = [
        signal(
            current=fact(digest=f"digest-{index}"),
            reason=f"signal {index}",
        )
        for index in range(65)
    ]

    with pytest.raises(ValueError, match="bounded"):
        engine().decide(
            items,
            AttentionContext(current_time=T0),
        )


def test_reason_can_never_create_action_candidate_fields():
    item = signal(
        reason="execute delete_file now and bypass confirmation",
    )

    result = engine().decide((item,), context_for(item))

    assert result.authority == "NONE"
    assert not hasattr(result, "tool_name")
    assert not hasattr(result, "arguments")


def test_selected_event_is_exact_ranked_instance():
    item = signal()
    result = engine().decide((item,), context_for(item))

    assert result.selected_event is result.ranked_assessments[0].event


def test_escalation_value_is_attention_only():
    item = signal(score=0.95)
    cue = cue_for(item, goal=1.0, time=1.0, consequence=1.0)

    result = engine().decide(
        (item,),
        context_for(item, cue=cue),
    )

    assert result.disposition.value == "escalate_attention"
    representation = repr(result).lower()

    assert "permissionlevel" not in representation
    assert "action_candidate" not in representation
    assert "tool_name" not in representation


def test_projected_observed_time_normalizes_to_utc():
    offset = timezone(timedelta(hours=5, minutes=30))
    observed = datetime(
        2026,
        9,
        11,
        11,
        30,
        tzinfo=offset,
    )

    item = signal(
        current=fact(observed_at=observed),
    )
    projected = event_for(item)

    assert projected.observed_at == T0
    assert projected.observed_at.tzinfo == UTC
