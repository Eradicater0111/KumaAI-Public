from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    replace,
)
from datetime import (
    datetime,
    timezone,
)
import inspect

import pytest

from app.agent.cognitive_contracts import (
    TacticalDecision,
    TacticalDisposition,
    TacticalOption,
    TacticalRisk,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.permissions import (
    PermissionLevel,
)
from app.agent.proactive_attention import (
    AttentionAssessment,
    AttentionDecision,
    AttentionDisposition,
    ProactiveEvent,
)
from app.agent.tactical_loop import (
    BLOCK_REPEAT_THRESHOLD,
    MAX_LOOP_ITERATIONS,
    WAIT_REPEAT_THRESHOLD,
    ContinuousTacticalLoop,
    LoopDisposition,
    TacticalLoopFrame,
    TacticalLoopIteration,
    TacticalLoopState,
    VerifiedLoopCompletion,
    cognitive_state_digest,
)


NOW_TEXT = "2026-09-13T00:00:00+00:00"
NOW = datetime(
    2026,
    9,
    13,
    0,
    0,
    tzinfo=timezone.utc,
)


def world(
    *,
    goal="Inspect safely.",
    system_state=("system: ready",),
    desktop_state=("desktop: editor",),
    realtime_state=(),
    task_state=(),
    mission_state=(),
    relevant_memory=(),
):
    return WorldStateSnapshot(
        timestamp=NOW_TEXT,
        task_goal=goal,
        system_state=system_state,
        desktop_state=desktop_state,
        realtime_state=realtime_state,
        task_state=task_state,
        mission_state=mission_state,
        relevant_memory=relevant_memory,
    )


def situation(
    snapshot=None,
    *,
    goal=None,
    observed_state=("editor visible",),
    known_facts=("system ready",),
    uncertainties=(),
    constraints=(),
    available_capabilities=("system_inspection",),
):
    snapshot = snapshot or world()

    return TacticalSituation(
        goal=(
            goal
            if goal is not None
            else snapshot.task_goal
        ),
        observed_state=observed_state,
        known_facts=known_facts,
        uncertainties=uncertainties,
        constraints=constraints,
        available_capabilities=available_capabilities,
        world_state=snapshot,
    )


def option(
    option_id="inspect",
    *,
    objective="Inspect current state.",
    capability="system_inspection",
    confidence=0.75,
    risk=TacticalRisk.LOW,
    permission=PermissionLevel.SAFE,
    reversible=True,
    cost=0.10,
):
    return TacticalOption(
        option_id=option_id,
        objective=objective,
        rationale="Grounded test rationale.",
        expected_outcome="Fresh state is available.",
        confidence=confidence,
        risk=risk,
        required_permission=permission,
        reversible=reversible,
        capability=capability,
        cost=cost,
    )


def tactical_decision(
    disposition=TacticalDisposition.ADVISE,
    *,
    chosen=None,
    rejected=(),
    uncertainties=(),
    reason="Bounded test decision.",
    confidence=0.75,
):
    return TacticalDecision(
        disposition=disposition,
        reason=reason,
        confidence=confidence,
        chosen_option=chosen,
        rejected_options=rejected,
        remaining_uncertainties=uncertainties,
    )


def proactive_event(
    *,
    event_id="a" * 64,
    score=0.90,
):
    return ProactiveEvent(
        event_id=event_id,
        kind="weather.current",
        reason="precipitation started",
        realtime_level=None if False else __import__(
            "app.realtime",
            fromlist=["RealtimeRelevanceLevel"],
        ).RealtimeRelevanceLevel.HIGH,
        realtime_score=score,
        observed_at=NOW,
        confidence=1.0,
        source_evidence_digest="weather-digest",
    )


def attention_assessment(
    event,
    disposition=AttentionDisposition.SURFACE,
    *,
    score=0.63,
):
    return AttentionAssessment(
        event=event,
        disposition=disposition,
        novelty=1.0,
        goal_relevance=0.0,
        time_sensitivity=0.0,
        consequence_of_ignoring=0.0,
        confidence=1.0,
        freshness=1.0,
        context_quality=0.40,
        multiplier=0.70,
        attention_score=score,
        reason="Bounded attention assessment.",
    )


def attention_ignore():
    return AttentionDecision(
        disposition=AttentionDisposition.IGNORE,
        reason="No proactive surfacing required.",
        selected_event=None,
        ranked_assessments=(),
    )


def attention_defer():
    return AttentionDecision(
        disposition=AttentionDisposition.DEFER,
        reason="Attention deferred.",
        selected_event=None,
        ranked_assessments=(),
    )


def attention_surface():
    event = proactive_event()

    assessment = attention_assessment(
        event,
        disposition=AttentionDisposition.SURFACE,
    )

    return AttentionDecision(
        disposition=AttentionDisposition.SURFACE,
        reason="Surface cognitively.",
        selected_event=event,
        ranked_assessments=(assessment,),
    )


def attention_escalate():
    event = proactive_event(
        event_id="b" * 64,
        score=0.95,
    )

    assessment = AttentionAssessment(
        event=event,
        disposition=AttentionDisposition.ESCALATE_ATTENTION,
        novelty=1.0,
        goal_relevance=1.0,
        time_sensitivity=1.0,
        consequence_of_ignoring=1.0,
        confidence=1.0,
        freshness=1.0,
        context_quality=1.0,
        multiplier=1.0,
        attention_score=0.95,
        reason="Escalated attention only.",
    )

    return AttentionDecision(
        disposition=AttentionDisposition.ESCALATE_ATTENTION,
        reason="Escalate cognitive attention only.",
        selected_event=event,
        ranked_assessments=(assessment,),
    )


def completion(
    *,
    verified=False,
    digest="",
    reason="",
):
    return VerifiedLoopCompletion(
        verified_complete=verified,
        evidence_digest=digest,
        reason=reason,
    )


def frame(
    *,
    snapshot=None,
    sit=None,
    candidates=None,
    decision=None,
    attention=None,
    completion_evidence=None,
):
    snapshot = snapshot or world()
    sit = sit or situation(snapshot)

    if candidates is None:
        candidates = ()

    if decision is None:
        decision = tactical_decision()

    if attention is None:
        attention = attention_ignore()

    if completion_evidence is None:
        completion_evidence = completion()

    return TacticalLoopFrame(
        world_state=snapshot,
        situation=sit,
        candidate_options=candidates,
        tactical_decision=decision,
        attention_decision=attention,
        completion=completion_evidence,
    )


def initial_state():
    return TacticalLoopState()


def loop():
    return ContinuousTacticalLoop()


def test_loop_disposition_exact_surface():
    assert {
        member.name
        for member in LoopDisposition
    } == {
        "CONTINUE_REASONING",
        "WAIT_FOR_EVIDENCE",
        "SURFACE_ADVICE",
        "ACTION_CANDIDATE",
        "COMPLETE",
        "BLOCKED",
    }


def test_completion_contract_is_frozen_and_zero_authority():
    item = completion()
    assert item.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        item.reason = "changed"


def test_state_is_frozen_and_zero_authority():
    item = initial_state()
    assert item.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        item.iterations_seen = 1


def test_frame_is_frozen_and_zero_authority():
    item = frame()
    assert item.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        item.candidate_options = ()


def test_iteration_is_frozen_and_zero_authority():
    result = loop().evaluate_iteration(
        frame(),
        initial_state(),
    )

    assert result.authority == "NONE"

    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"


def test_verified_completion_requires_sha256_digest():
    with pytest.raises(ValueError, match="SHA-256"):
        completion(
            verified=True,
            digest="not-a-digest",
            reason="Verified.",
        )


def test_verified_completion_requires_reason():
    with pytest.raises(ValueError, match="reason"):
        completion(
            verified=True,
            digest="c" * 64,
            reason="",
        )


def test_noncomplete_cannot_carry_completion_digest():
    with pytest.raises(ValueError, match="cannot carry"):
        completion(
            verified=False,
            digest="c" * 64,
        )


def test_initial_state_is_zeroed():
    state = initial_state()

    assert state.iterations_seen == 0
    assert state.previous_cognitive_digest == ""
    assert state.repeated_state_count == 0


def test_initial_state_rejects_previous_digest():
    with pytest.raises(ValueError, match="initial"):
        TacticalLoopState(
            iterations_seen=0,
            previous_cognitive_digest="a" * 64,
            repeated_state_count=0,
        )


def test_initial_state_rejects_repeat_count():
    with pytest.raises(ValueError, match="initial"):
        TacticalLoopState(
            iterations_seen=0,
            repeated_state_count=1,
        )


def test_noninitial_state_requires_previous_digest():
    with pytest.raises(ValueError, match="requires"):
        TacticalLoopState(
            iterations_seen=1,
            repeated_state_count=0,
        )


def test_state_rejects_malformed_previous_digest():
    with pytest.raises(ValueError, match="SHA-256"):
        TacticalLoopState(
            iterations_seen=1,
            previous_cognitive_digest="bad",
            repeated_state_count=0,
        )


def test_state_repeat_count_cannot_exceed_history():
    with pytest.raises(ValueError, match="cannot exceed"):
        TacticalLoopState(
            iterations_seen=1,
            previous_cognitive_digest="a" * 64,
            repeated_state_count=1,
        )


def test_state_iteration_budget_is_bounded():
    with pytest.raises(ValueError, match="between"):
        TacticalLoopState(
            iterations_seen=MAX_LOOP_ITERATIONS + 1,
            previous_cognitive_digest="a" * 64,
        )


def test_state_repeat_budget_is_bounded():
    with pytest.raises(ValueError, match="between"):
        TacticalLoopState(
            iterations_seen=10,
            previous_cognitive_digest="a" * 64,
            repeated_state_count=BLOCK_REPEAT_THRESHOLD + 1,
        )


def test_frame_requires_world_state():
    with pytest.raises(TypeError, match="WorldStateSnapshot"):
        TacticalLoopFrame(
            world_state=object(),
            situation=situation(),
            candidate_options=(),
            tactical_decision=tactical_decision(),
            attention_decision=attention_ignore(),
        )


def test_frame_requires_situation():
    snapshot = world()

    with pytest.raises(TypeError, match="TacticalSituation"):
        TacticalLoopFrame(
            world_state=snapshot,
            situation=object(),
            candidate_options=(),
            tactical_decision=tactical_decision(),
            attention_decision=attention_ignore(),
        )


def test_frame_binds_situation_to_exact_world_value():
    snapshot = world()
    other = world(
        system_state=("different",),
    )

    with pytest.raises(ValueError, match="bound"):
        frame(
            snapshot=snapshot,
            sit=situation(other),
        )


def test_frame_requires_goal_binding_when_world_has_goal():
    snapshot = world(
        goal="Goal A",
    )

    sit = situation(
        snapshot,
        goal="Goal B",
    )

    with pytest.raises(ValueError, match="goal"):
        frame(
            snapshot=snapshot,
            sit=sit,
        )


def test_frame_accepts_world_without_task_goal():
    snapshot = WorldStateSnapshot(
        timestamp=NOW_TEXT,
        task_goal=None,
    )

    sit = TacticalSituation(
        goal="Caller tactical goal.",
        world_state=snapshot,
    )

    item = frame(
        snapshot=snapshot,
        sit=sit,
    )

    assert item.situation.goal == "Caller tactical goal."


def test_candidate_options_are_canonicalized_by_option_id():
    first = option("b")
    second = option("a")

    item = frame(
        candidates=(
            first,
            second,
        )
    )

    assert [
        candidate.option_id
        for candidate in item.candidate_options
    ] == [
        "a",
        "b",
    ]


def test_candidate_options_reject_duplicates():
    first = option("same")
    second = option("same")

    with pytest.raises(ValueError, match="duplicate"):
        frame(
            candidates=(
                first,
                second,
            )
        )


def test_candidate_options_reject_non_options():
    with pytest.raises(TypeError, match="TacticalOption"):
        frame(
            candidates=(
                object(),
            )
        )


def test_frame_rejects_tampered_world_authority():
    snapshot = world()
    object.__setattr__(
        snapshot,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        frame(
            snapshot=snapshot,
            sit=situation(snapshot),
        )


def test_frame_rejects_tampered_situation_authority():
    snapshot = world()
    sit = situation(snapshot)
    object.__setattr__(
        sit,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        frame(
            snapshot=snapshot,
            sit=sit,
        )


def test_frame_rejects_tampered_candidate_authority():
    candidate = option()
    object.__setattr__(
        candidate,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        frame(
            candidates=(candidate,),
        )


def test_frame_requires_tactical_decision():
    snapshot = world()
    sit = situation(snapshot)

    with pytest.raises(TypeError, match="TacticalDecision"):
        TacticalLoopFrame(
            world_state=snapshot,
            situation=sit,
            candidate_options=(),
            tactical_decision=object(),
            attention_decision=attention_ignore(),
        )


def test_frame_rejects_tampered_tactical_decision_authority():
    decision = tactical_decision()
    object.__setattr__(
        decision,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        frame(
            decision=decision,
        )


def test_action_candidate_requires_chosen_option():
    decision = tactical_decision(
        TacticalDisposition.ACTION_CANDIDATE,
        chosen=None,
    )

    with pytest.raises(ValueError, match="requires"):
        frame(
            decision=decision,
        )


def test_blocked_decision_cannot_carry_chosen_option():
    chosen = option()

    decision = tactical_decision(
        TacticalDisposition.BLOCKED,
        chosen=chosen,
    )

    with pytest.raises(ValueError, match="cannot carry"):
        frame(
            candidates=(chosen,),
            decision=decision,
        )


def test_chosen_option_must_be_in_candidate_set():
    chosen = option("chosen")

    decision = tactical_decision(
        TacticalDisposition.ACTION_CANDIDATE,
        chosen=chosen,
    )

    with pytest.raises(ValueError, match="chosen option"):
        frame(
            candidates=(),
            decision=decision,
        )


def test_chosen_option_must_match_candidate_value_not_only_id():
    chosen = option(
        "same",
        objective="Chosen objective.",
    )

    different = option(
        "same",
        objective="Different objective.",
    )

    decision = tactical_decision(
        TacticalDisposition.ACTION_CANDIDATE,
        chosen=chosen,
    )

    with pytest.raises(ValueError, match="exactly"):
        frame(
            candidates=(different,),
            decision=decision,
        )


def test_rejected_option_must_be_in_candidate_set():
    rejected = option("rejected")

    decision = tactical_decision(
        TacticalDisposition.DEFER,
        rejected=(rejected,),
    )

    with pytest.raises(ValueError, match="rejected options"):
        frame(
            candidates=(),
            decision=decision,
        )


def test_frame_requires_attention_decision():
    snapshot = world()
    sit = situation(snapshot)

    with pytest.raises(TypeError, match="AttentionDecision"):
        TacticalLoopFrame(
            world_state=snapshot,
            situation=sit,
            candidate_options=(),
            tactical_decision=tactical_decision(),
            attention_decision=object(),
        )


def test_frame_rejects_tampered_attention_authority():
    attention = attention_ignore()
    object.__setattr__(
        attention,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        frame(
            attention=attention,
        )


def test_frame_rejects_tampered_completion_authority():
    done = completion()
    object.__setattr__(
        done,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        frame(
            completion_evidence=done,
        )


def test_cognitive_digest_is_deterministic():
    item = frame()

    assert (
        cognitive_state_digest(item)
        == cognitive_state_digest(item)
    )


def test_candidate_input_order_does_not_change_cognitive_digest():
    a = option("a")
    b = option("b")

    first = frame(
        candidates=(a, b),
    )

    second = frame(
        candidates=(b, a),
    )

    assert (
        cognitive_state_digest(first)
        == cognitive_state_digest(second)
    )


def test_world_change_changes_cognitive_digest():
    first = frame()

    snapshot = world(
        system_state=("system: changed",),
    )

    second = frame(
        snapshot=snapshot,
        sit=situation(snapshot),
    )

    assert (
        cognitive_state_digest(first)
        != cognitive_state_digest(second)
    )


def test_tactical_decision_change_changes_cognitive_digest():
    first = frame()

    second = frame(
        decision=tactical_decision(
            TacticalDisposition.DEFER,
            reason="Need more evidence.",
        )
    )

    assert (
        cognitive_state_digest(first)
        != cognitive_state_digest(second)
    )


def test_attention_change_changes_cognitive_digest():
    first = frame(
        attention=attention_ignore(),
    )

    second = frame(
        attention=attention_defer(),
    )

    assert (
        cognitive_state_digest(first)
        != cognitive_state_digest(second)
    )


def test_completion_evidence_does_not_change_cognitive_state_digest():
    first = frame()

    second = frame(
        completion_evidence=completion(
            verified=True,
            digest="c" * 64,
            reason="Verified complete.",
        )
    )

    assert (
        cognitive_state_digest(first)
        == cognitive_state_digest(second)
    )


def test_first_advise_without_choice_continues_reasoning():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.ADVISE,
                chosen=None,
            ),
            attention=attention_ignore(),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.CONTINUE_REASONING
    )
    assert result.repeated_state_count == 0
    assert result.stalled is False


def test_advise_with_chosen_option_surfaces_advice():
    chosen = option()

    result = loop().evaluate_iteration(
        frame(
            candidates=(chosen,),
            decision=tactical_decision(
                TacticalDisposition.ADVISE,
                chosen=chosen,
            ),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.SURFACE_ADVICE
    )


def test_defer_without_attention_waits_for_evidence():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
                reason="Need evidence.",
            ),
            attention=attention_defer(),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.WAIT_FOR_EVIDENCE
    )


def test_defer_with_surface_attention_surfaces_advice():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
            ),
            attention=attention_surface(),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.SURFACE_ADVICE
    )


def test_defer_with_escalated_attention_surfaces_advice():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
            ),
            attention=attention_escalate(),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.SURFACE_ADVICE
    )
    assert result.authority == "NONE"


def test_action_candidate_remains_cognitive_action_candidate():
    chosen = option()

    result = loop().evaluate_iteration(
        frame(
            candidates=(chosen,),
            decision=tactical_decision(
                TacticalDisposition.ACTION_CANDIDATE,
                chosen=chosen,
            ),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.ACTION_CANDIDATE
    )
    assert result.authority == "NONE"
    assert result.frame.tactical_decision.authority == "NONE"


def test_action_candidate_beats_attention_surfacing():
    chosen = option()

    result = loop().evaluate_iteration(
        frame(
            candidates=(chosen,),
            decision=tactical_decision(
                TacticalDisposition.ACTION_CANDIDATE,
                chosen=chosen,
            ),
            attention=attention_escalate(),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.ACTION_CANDIDATE
    )


def test_tactical_block_beats_attention_escalation():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.BLOCKED,
                reason="No grounded option.",
            ),
            attention=attention_escalate(),
        ),
        initial_state(),
    )

    assert (
        result.disposition
        == LoopDisposition.BLOCKED
    )


def test_verified_completion_produces_complete():
    result = loop().evaluate_iteration(
        frame(
            completion_evidence=completion(
                verified=True,
                digest="c" * 64,
                reason="Objective verifier confirmed completion.",
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.COMPLETE
    assert result.authority == "NONE"


def test_verified_completion_beats_stale_tactical_block():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.BLOCKED,
            ),
            completion_evidence=completion(
                verified=True,
                digest="c" * 64,
                reason="Independent verification confirmed completion.",
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.COMPLETE


def test_first_iteration_advances_state_once():
    item = frame()

    result = loop().evaluate_iteration(
        item,
        initial_state(),
    )

    assert result.iteration_number == 1
    assert result.next_state.iterations_seen == 1
    assert (
        result.next_state.previous_cognitive_digest
        == result.cognitive_digest
    )
    assert result.next_state.repeated_state_count == 0


def test_first_identical_repeat_preserves_normal_disposition():
    item = frame()

    first = loop().evaluate_iteration(
        item,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        item,
        first.next_state,
    )

    assert second.repeated_state_count == 1
    assert second.stalled is False
    assert (
        second.disposition
        == LoopDisposition.CONTINUE_REASONING
    )


def test_second_identical_repeat_waits_for_evidence():
    item = frame()

    first = loop().evaluate_iteration(
        item,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        item,
        first.next_state,
    )

    third = loop().evaluate_iteration(
        item,
        second.next_state,
    )

    assert WAIT_REPEAT_THRESHOLD == 2
    assert third.repeated_state_count == 2
    assert third.stalled is True
    assert (
        third.disposition
        == LoopDisposition.WAIT_FOR_EVIDENCE
    )


def test_third_identical_repeat_blocks():
    item = frame()

    state = initial_state()

    results = []

    for _ in range(4):
        current = loop().evaluate_iteration(
            item,
            state,
        )
        results.append(current)
        state = current.next_state

    fourth = results[-1]

    assert BLOCK_REPEAT_THRESHOLD == 3
    assert fourth.repeated_state_count == 3
    assert fourth.stalled is True
    assert fourth.disposition == LoopDisposition.BLOCKED


def test_stall_guard_overrides_repeated_action_candidate():
    chosen = option()

    item = frame(
        candidates=(chosen,),
        decision=tactical_decision(
            TacticalDisposition.ACTION_CANDIDATE,
            chosen=chosen,
        ),
    )

    first = loop().evaluate_iteration(
        item,
        initial_state(),
    )
    second = loop().evaluate_iteration(
        item,
        first.next_state,
    )
    third = loop().evaluate_iteration(
        item,
        second.next_state,
    )

    assert first.disposition == LoopDisposition.ACTION_CANDIDATE
    assert second.disposition == LoopDisposition.ACTION_CANDIDATE
    assert third.disposition == LoopDisposition.WAIT_FOR_EVIDENCE


def test_repeat_budget_blocks_repeated_action_candidate():
    chosen = option()

    item = frame(
        candidates=(chosen,),
        decision=tactical_decision(
            TacticalDisposition.ACTION_CANDIDATE,
            chosen=chosen,
        ),
    )

    state = initial_state()

    for _ in range(4):
        result = loop().evaluate_iteration(
            item,
            state,
        )
        state = result.next_state

    assert result.disposition == LoopDisposition.BLOCKED


def test_changed_cognitive_state_resets_repeat_count():
    first_frame = frame()

    first = loop().evaluate_iteration(
        first_frame,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        first_frame,
        first.next_state,
    )

    changed_snapshot = world(
        system_state=("system: fresh evidence",),
    )

    changed_frame = frame(
        snapshot=changed_snapshot,
        sit=situation(changed_snapshot),
    )

    third = loop().evaluate_iteration(
        changed_frame,
        second.next_state,
    )

    assert second.repeated_state_count == 1
    assert third.repeated_state_count == 0
    assert third.stalled is False


def test_changed_attention_resets_repeat_count():
    first_frame = frame(
        attention=attention_ignore(),
    )

    first = loop().evaluate_iteration(
        first_frame,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        first_frame,
        first.next_state,
    )

    changed = frame(
        attention=attention_defer(),
    )

    third = loop().evaluate_iteration(
        changed,
        second.next_state,
    )

    assert third.repeated_state_count == 0


def test_hard_iteration_budget_blocks_next_iteration():
    item = frame()

    prior_digest = cognitive_state_digest(
        item
    )

    state = TacticalLoopState(
        iterations_seen=MAX_LOOP_ITERATIONS,
        previous_cognitive_digest=prior_digest,
        repeated_state_count=0,
    )

    result = loop().evaluate_iteration(
        item,
        state,
    )

    assert result.disposition == LoopDisposition.BLOCKED
    assert (
        result.next_state
        is state
    )
    assert (
        result.iteration_number
        == MAX_LOOP_ITERATIONS + 1
    )


def test_hard_budget_does_not_mutate_state():
    item = frame()
    digest = cognitive_state_digest(item)

    state = TacticalLoopState(
        iterations_seen=MAX_LOOP_ITERATIONS,
        previous_cognitive_digest=digest,
        repeated_state_count=0,
    )

    result = loop().evaluate_iteration(item, state)

    assert result.next_state == state
    assert result.next_state.iterations_seen == MAX_LOOP_ITERATIONS


def test_verified_completion_can_end_after_budget_exhaustion():
    item = frame(
        completion_evidence=completion(
            verified=True,
            digest="d" * 64,
            reason="Verified complete after external evidence arrived.",
        )
    )

    digest = cognitive_state_digest(item)

    state = TacticalLoopState(
        iterations_seen=MAX_LOOP_ITERATIONS,
        previous_cognitive_digest=digest,
        repeated_state_count=0,
    )

    result = loop().evaluate_iteration(item, state)

    assert result.disposition == LoopDisposition.COMPLETE


def test_iteration_digest_is_deterministic_for_same_inputs():
    item = frame()
    state = initial_state()

    first = loop().evaluate_iteration(item, state)
    second = loop().evaluate_iteration(item, state)

    assert first.iteration_digest == second.iteration_digest


def test_iteration_digest_changes_when_state_changes():
    item = frame()

    first = loop().evaluate_iteration(
        item,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        item,
        first.next_state,
    )

    assert first.iteration_digest != second.iteration_digest


def test_iteration_digest_changes_with_completion_evidence():
    base = frame()

    done = frame(
        completion_evidence=completion(
            verified=True,
            digest="e" * 64,
            reason="Verified complete.",
        )
    )

    first = loop().evaluate_iteration(
        base,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        done,
        initial_state(),
    )

    assert first.cognitive_digest == second.cognitive_digest
    assert first.iteration_digest != second.iteration_digest


def test_iteration_has_no_permission_or_execution_fields():
    result = loop().evaluate_iteration(
        frame(),
        initial_state(),
    )

    for name in (
        "permission",
        "required_permission",
        "approved",
        "authorized",
        "confirmation",
        "tool_name",
        "arguments",
        "handoff",
        "executed",
        "verified_execution",
        "notification",
    ):
        assert not hasattr(result, name)


def test_frame_has_no_execution_handoff_fields():
    item = frame()

    for name in (
        "tool_name",
        "arguments",
        "handoff",
        "approved",
        "authorized",
        "confirmation",
        "executor",
    ):
        assert not hasattr(item, name)


def test_engine_has_one_iteration_method_not_run_loop_surface():
    item = loop()

    assert hasattr(item, "evaluate_iteration")

    for name in (
        "run",
        "start",
        "stop",
        "tick",
        "poll",
        "execute",
        "prepare_handoff",
        "request_confirmation",
        "notify",
        "persist",
    ):
        assert not hasattr(item, name)


def test_engine_is_stateless_between_calls():
    item = loop()

    assert not hasattr(item, "__dict__")


def test_evaluate_iteration_requires_frame():
    with pytest.raises(TypeError, match="frame"):
        loop().evaluate_iteration(
            object(),
            initial_state(),
        )


def test_evaluate_iteration_requires_state():
    with pytest.raises(TypeError, match="state"):
        loop().evaluate_iteration(
            frame(),
            object(),
        )


def test_evaluate_iteration_rejects_tampered_frame_authority():
    item = frame()
    object.__setattr__(
        item,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        loop().evaluate_iteration(
            item,
            initial_state(),
        )


def test_evaluate_iteration_rejects_tampered_state_authority():
    state = initial_state()
    object.__setattr__(
        state,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(ValueError, match="authority"):
        loop().evaluate_iteration(
            frame(),
            state,
        )


def test_action_candidate_option_permission_is_only_nested_metadata():
    chosen = option(
        permission=PermissionLevel.USER_AUTHORIZED,
    )

    result = loop().evaluate_iteration(
        frame(
            candidates=(chosen,),
            decision=tactical_decision(
                TacticalDisposition.ACTION_CANDIDATE,
                chosen=chosen,
            ),
        ),
        initial_state(),
    )

    assert (
        result.frame.tactical_decision.required_permission
        == PermissionLevel.USER_AUTHORIZED
    )
    assert not hasattr(
        result,
        "required_permission",
    )


def test_attention_escalation_does_not_create_action_candidate():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
            ),
            attention=attention_escalate(),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.SURFACE_ADVICE
    assert result.authority == "NONE"


def test_maximum_attention_still_zero_authority():
    attention = attention_escalate()

    result = loop().evaluate_iteration(
        frame(
            attention=attention,
        ),
        initial_state(),
    )

    assert attention.authority == "NONE"
    assert result.authority == "NONE"


def test_module_has_no_internal_while_loop():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)
    tree = ast.parse(source)

    assert not any(
        isinstance(node, ast.While)
        for node in ast.walk(tree)
    )


def test_module_has_no_background_thread_or_async_runtime_surface():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    for marker in (
        "threading",
        "Thread(",
        "asyncio",
        "create_task(",
        "sleep(",
        "Timer(",
        "schedule(",
    ):
        assert marker not in source


def test_module_does_not_import_execution_bridge():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    assert "from app.agent.tactical_execution_bridge" not in source
    assert "import app.agent.tactical_execution_bridge" not in source
    assert "RaphaelExecutionBridge(" not in source
    assert "RaphaelExecutionHandoff(" not in source


def test_module_does_not_import_executor_permissions_agent_or_mission_runtime():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    for marker in (
        "from app.agent.executor",
        "from app.agent.permissions",
        "from app.agent.kuma_agent",
        "from app.agent.kuma_runtime",
        "from app.agent.mission_service",
        "from app.agent.mission_runner",
        "from app.agent.mission_controller",
        "PermissionLevel",
        "require_explicit_permission",
        "request_confirmation(",
        "confirmation_callback",
        "register_tool(",
        ".execute(",
    ):
        assert marker not in source


def test_module_does_not_call_frozen_cognition_producers():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    for marker in (
        "WorldModelBuilder(",
        "TacticalAnalyzer(",
        "TacticalOptionGenerator(",
        "TacticalDecisionEngine(",
        "ProactiveAttentionEngine(",
        ".analyze(",
        ".generate(",
        ".simulate(",
    ):
        assert marker not in source


def test_module_has_no_model_memory_sensor_network_or_provider_surface():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    for marker in (
        "ask_model(",
        "model_call",
        "generate_content(",
        "ollama",
        "app.memory",
        "retrieve_memories",
        "get_memory_context",
        "get_current_location(",
        "refresh_weather(",
        "web_search(",
        "fetch_webpage(",
        "requests",
        "urllib",
        "pyautogui",
    ):
        assert marker not in source


def test_module_has_no_persistence_subprocess_or_dynamic_code_surface():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    for marker in (
        "sqlite",
        "write_text(",
        "write_bytes(",
        "open(",
        "subprocess",
        "exec(",
        "eval(",
        "compile(",
        "importlib",
        "pickle",
        "marshal",
    ):
        assert marker not in source


def test_module_has_no_notification_surface():
    import app.agent.tactical_loop as module

    source = inspect.getsource(module)

    for marker in (
        "notify_user(",
        ".notify(",
        ".send_message(",
        "emit_message(",
        "toast(",
        "banner(",
    ):
        assert marker not in source


def test_state_is_explicit_caller_owned_not_engine_attribute():
    signature = inspect.signature(
        ContinuousTacticalLoop.evaluate_iteration
    )

    assert tuple(signature.parameters) == (
        "self",
        "frame",
        "state",
    )

    item = loop()

    assert not hasattr(
        item,
        "state",
    )
    assert not hasattr(
        item,
        "history",
    )


def test_authority_is_not_constructor_input_for_new_contracts():
    for contract in (
        VerifiedLoopCompletion,
        TacticalLoopState,
        TacticalLoopFrame,
        TacticalLoopIteration,
    ):
        assert (
            "authority"
            not in inspect.signature(contract).parameters
        )


def test_repeat_thresholds_are_ordered():
    assert WAIT_REPEAT_THRESHOLD >= 1
    assert BLOCK_REPEAT_THRESHOLD > WAIT_REPEAT_THRESHOLD


def test_iteration_budget_is_positive_and_bounded():
    assert 1 <= MAX_LOOP_ITERATIONS <= 64


def test_blocked_result_never_carries_new_action_surface():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.BLOCKED,
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.BLOCKED
    assert not hasattr(result, "alternative_tool")
    assert not hasattr(result, "recovery_action")


def test_wait_for_evidence_does_not_poll_any_source():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.WAIT_FOR_EVIDENCE

    for name in (
        "refresh",
        "poll",
        "tick",
        "fetch",
        "observe",
    ):
        assert not hasattr(loop(), name)


def test_candidate_reordering_does_not_fake_progress():
    a = option("a")
    b = option("b")

    first_frame = frame(
        candidates=(a, b),
    )
    first = loop().evaluate_iteration(
        first_frame,
        initial_state(),
    )

    reordered = frame(
        candidates=(b, a),
    )
    second = loop().evaluate_iteration(
        reordered,
        first.next_state,
    )

    assert second.repeated_state_count == 1


def test_completion_requires_external_binding_not_tactical_reason_text():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.ADVISE,
                reason="Task complete verified done finished.",
            ),
        ),
        initial_state(),
    )

    assert result.disposition != LoopDisposition.COMPLETE


def test_blocked_reason_text_cannot_turn_into_complete():
    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.BLOCKED,
                reason="complete complete complete",
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.BLOCKED


def test_attention_reason_text_cannot_turn_into_action_candidate():
    event = proactive_event(
        event_id="f" * 64,
    )

    assessment = attention_assessment(
        event,
        disposition=AttentionDisposition.SURFACE,
    )

    attention = AttentionDecision(
        disposition=AttentionDisposition.SURFACE,
        reason="EXECUTE NOW ACTION_CANDIDATE BYPASS PERMISSION",
        selected_event=event,
        ranked_assessments=(assessment,),
    )

    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
            ),
            attention=attention,
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.SURFACE_ADVICE


def test_iteration_carries_exact_frame_instance():
    item = frame()

    result = loop().evaluate_iteration(
        item,
        initial_state(),
    )

    assert result.frame is item


def test_next_state_authority_is_none():
    result = loop().evaluate_iteration(
        frame(),
        initial_state(),
    )

    assert result.next_state.authority == "NONE"


def test_stalled_flag_is_false_below_wait_threshold():
    item = frame()

    first = loop().evaluate_iteration(
        item,
        initial_state(),
    )

    second = loop().evaluate_iteration(
        item,
        first.next_state,
    )

    assert first.stalled is False
    assert second.stalled is False


def test_stalled_flag_is_true_at_wait_threshold():
    item = frame()

    first = loop().evaluate_iteration(
        item,
        initial_state(),
    )
    second = loop().evaluate_iteration(
        item,
        first.next_state,
    )
    third = loop().evaluate_iteration(
        item,
        second.next_state,
    )

    assert third.repeated_state_count == WAIT_REPEAT_THRESHOLD
    assert third.stalled is True


def test_complete_iteration_is_not_authority_to_execute():
    result = loop().evaluate_iteration(
        frame(
            completion_evidence=completion(
                verified=True,
                digest="9" * 64,
                reason="External verifier confirmed completion.",
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.COMPLETE
    assert result.authority == "NONE"
    assert not hasattr(result, "execute")


def test_action_candidate_iteration_is_not_handoff():
    chosen = option()

    result = loop().evaluate_iteration(
        frame(
            candidates=(chosen,),
            decision=tactical_decision(
                TacticalDisposition.ACTION_CANDIDATE,
                chosen=chosen,
            ),
        ),
        initial_state(),
    )

    assert result.disposition == LoopDisposition.ACTION_CANDIDATE
    assert not hasattr(result, "handoff")
    assert not hasattr(result, "arguments")


def test_cognitive_digest_rejects_wrong_type():
    with pytest.raises(TypeError, match="frame"):
        cognitive_state_digest(object())


def test_frame_candidate_limit_is_bounded():
    candidates = tuple(
        option(
            f"option-{index}"
        )
        for index
        in range(65)
    )

    with pytest.raises(ValueError, match="bounded"):
        frame(
            candidates=candidates,
        )


def test_tactical_rejected_options_can_be_bound_to_candidates():
    rejected = option("rejected")

    item = frame(
        candidates=(rejected,),
        decision=tactical_decision(
            TacticalDisposition.DEFER,
            rejected=(rejected,),
        ),
    )

    assert item.tactical_decision.rejected_options == (rejected,)


def test_multiple_candidates_sort_deterministically():
    candidates = (
        option("z"),
        option("a"),
        option("m"),
    )

    item = frame(
        candidates=candidates,
    )

    assert tuple(
        candidate.option_id
        for candidate
        in item.candidate_options
    ) == (
        "a",
        "m",
        "z",
    )


def test_frame_candidate_tuple_is_immutable():
    candidate = option()

    item = frame(
        candidates=[candidate],
    )

    assert type(item.candidate_options) is tuple


def test_attention_surface_remains_nested_zero_authority():
    attention = attention_surface()

    result = loop().evaluate_iteration(
        frame(
            decision=tactical_decision(
                TacticalDisposition.DEFER,
            ),
            attention=attention,
        ),
        initial_state(),
    )

    assert result.frame.attention_decision.authority == "NONE"
    assert (
        result.frame.attention_decision.selected_event.authority
        == "NONE"
    )


def test_same_decision_different_verified_completion_does_not_fake_cognitive_progress():
    base = frame()

    done = frame(
        completion_evidence=completion(
            verified=True,
            digest="8" * 64,
            reason="Verified complete.",
        )
    )

    assert cognitive_state_digest(base) == cognitive_state_digest(done)


def test_world_timestamp_change_counts_as_new_cognitive_state():
    first_snapshot = world()

    second_snapshot = WorldStateSnapshot(
        timestamp="2026-09-13T00:00:01+00:00",
        task_goal=first_snapshot.task_goal,
        system_state=first_snapshot.system_state,
        desktop_state=first_snapshot.desktop_state,
        realtime_state=first_snapshot.realtime_state,
        task_state=first_snapshot.task_state,
        mission_state=first_snapshot.mission_state,
        relevant_memory=first_snapshot.relevant_memory,
    )

    first_frame = frame(
        snapshot=first_snapshot,
        sit=situation(first_snapshot),
    )

    second_frame = frame(
        snapshot=second_snapshot,
        sit=situation(second_snapshot),
    )

    assert (
        cognitive_state_digest(first_frame)
        != cognitive_state_digest(second_frame)
    )


def test_one_call_produces_exactly_one_state_advance():
    item = frame()
    state = initial_state()

    result = loop().evaluate_iteration(
        item,
        state,
    )

    assert state.iterations_seen == 0
    assert result.next_state.iterations_seen == 1


def test_no_result_claims_real_world_progress_without_completion_evidence():
    result = loop().evaluate_iteration(
        frame(),
        initial_state(),
    )

    assert (
        result.frame.completion.verified_complete
        is False
    )
    assert result.disposition != LoopDisposition.COMPLETE
