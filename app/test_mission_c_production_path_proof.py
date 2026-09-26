from __future__ import annotations

from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import sqlite3

import pytest

import app.agent.gui_runtime as gui_runtime
import app.agent.kuma_agent as kuma_agent_module
import app.agent.kuma_runtime as kuma_runtime
import app.memory.memory as memory_module
import app.agent.mission_cognitive_observation as mission_cognitive_module

from app.agent.goal_decision import (
    GoalDecision,
    GoalStatus,
)
from app.runtime_v2_live_owner import (
    KumaRuntimeV2LiveOwner as RealRuntimeOwner,
)
from app.realtime.runtime import (
    RealtimeRuntime,
)


ADVISORY_MARKER = (
    "KUMA CURRENT-TURN COGNITIVE ADVISORY"
)

SAFE_USER_MESSAGE = (
    "Inspect my system and then summarize the result."
)

SAFE_FINAL_RESPONSE = (
    "MISSION-C-FINAL-RESPONSE"
)

TOOL_RESULT = (
    "MISSION-C-PROOF-SYSTEM-RESULT"
)


class CountingRealtime(
    RealtimeRuntime
):
    """
    Deterministic sensor boundary that preserves the real RealtimeRuntime
    nominal type required by frozen Integration-V2.

    The inherited production runtime is constructed normally. Only the two
    explicit acquisition methods used by the production turn preflight are
    overridden so Mission-C can count calls without refreshing external
    realtime providers.

    TEST OBSERVATION != PRODUCTION AUTHORITY
    """

    def __init__(
        self,
    ):
        super().__init__()

        self.tick_calls = 0
        self.pending_calls = 0

    def tick(
        self,
        *args,
        **kwargs,
    ):
        self.tick_calls += 1
        return None

    def pending_signals(
        self,
        *args,
        **kwargs,
    ):
        self.pending_calls += 1
        return ()


def _message_snapshot(
    messages,
):
    result = []

    for message in messages:
        if isinstance(
            message,
            dict,
        ):
            role = message.get(
                "role"
            )
            content = message.get(
                "content"
            )
        else:
            role = getattr(
                message,
                "role",
                None,
            )
            content = getattr(
                message,
                "content",
                None,
            )

        result.append(
            (
                role,
                str(
                    content
                    or ""
                ),
            )
        )

    return tuple(
        result
    )


def _contains_advisory(
    messages,
):
    return any(
        ADVISORY_MARKER
        in content
        for _role, content
        in _message_snapshot(
            messages
        )
    )


def _snapshot_memories_table():
    """
    Snapshot logical durable memory rows only.

    Creating the SQLite container or an empty `memories` table is storage
    initialization, not durable-memory persistence. Mission-C therefore
    normalizes database-absent, table-absent, and empty-table states to the
    same logical empty durable-memory snapshot.

    Any actual durable row remains observable and must compare exactly.
    """

    db_path = Path(
        memory_module.DB_PATH
    )

    if not db_path.exists():
        return ()

    connection = sqlite3.connect(
        "file:"
        + str(
            db_path.resolve()
        )
        + "?mode=ro",
        uri=True,
    )

    try:
        table = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'memories'
            """
        ).fetchone()

        if table is None:
            return ()

        return tuple(
            connection.execute(
                "SELECT * FROM memories ORDER BY rowid"
            ).fetchall()
        )

    finally:
        connection.close()


def _event_kinds(
    events,
):
    return tuple(
        getattr(
            event,
            "event_kind",
            None,
        )
        for event in events
    )


def _assert_one_runtime_turn(
    events,
):
    kinds = _event_kinds(
        events
    )

    assert (
        kinds.count(
            "turn.started"
        )
        == 1
    )

    assert (
        kinds.count(
            "turn.ended"
        )
        == 1
    )

    for event in events:
        authority = getattr(
            event,
            "authority",
            "NONE",
        )

        assert (
            authority
            == "NONE"
        )


def _assert_trace_privacy(
    events,
    *,
    user_message,
    response,
    advisory_text="",
):
    rendered = repr(
        tuple(
            events
        )
    )

    assert (
        user_message
        not in rendered
    )

    assert (
        response
        not in rendered
    )

    assert (
        ADVISORY_MARKER
        not in rendered
    )

    if advisory_text:
        assert (
            advisory_text
            not in rendered
        )


def _install_no_persistence_conversation_seam(
    monkeypatch,
):
    saved = []

    def fake_save_message(
        role,
        content,
    ):
        saved.append(
            (
                str(
                    role
                ),
                str(
                    content
                    or ""
                ),
            )
        )

    monkeypatch.setattr(
        kuma_agent_module,
        "save_message",
        fake_save_message,
    )

    monkeypatch.setattr(
        kuma_agent_module,
        "get_recent_messages",
        lambda *args, **kwargs: [],
    )

    return saved


def _install_mission_service_tripwires(
    monkeypatch,
    kuma,
):
    calls = []

    def forbidden(
        *args,
        **kwargs,
    ):
        calls.append(
            (
                args,
                kwargs,
            )
        )

        raise AssertionError(
            "MissionService must not be invoked by Mission-A/B cognition."
        )

    for name in (
        "execute_mission_step",
        "execute_mission",
        "resume_mission",
    ):
        if hasattr(
            kuma.mission_service,
            name,
        ):
            monkeypatch.setattr(
                kuma.mission_service,
                name,
                forbidden,
            )

    return calls


def _install_permission_spy(
    monkeypatch,
):
    original = (
        kuma_agent_module
        .get_permission_level
    )

    calls = []

    def wrapped(
        *args,
        **kwargs,
    ):
        result = original(
            *args,
            **kwargs,
        )

        calls.append(
            (
                args,
                kwargs,
                result,
            )
        )

        return result

    monkeypatch.setattr(
        kuma_agent_module,
        "get_permission_level",
        wrapped,
    )

    return calls


def _install_projection_spy(
    monkeypatch,
):
    original = (
        mission_cognitive_module
        .project_mission_cognitive_observation
    )

    projections = []

    def wrapped(
        *,
        integrated_observation,
    ):
        result = original(
            integrated_observation=(
                integrated_observation
            ),
        )

        projections.append(
            result
        )

        return result

    monkeypatch.setattr(
        mission_cognitive_module,
        "project_mission_cognitive_observation",
        wrapped,
    )

    return projections


def _prepare_safe_real_agent(
    monkeypatch,
    *,
    production_factory,
):
    """
    Construct the real production KumaAgent and replace only deterministic
    external boundaries.

    The real run(), grounding, build_action, permission, ActionExecutor,
    verification, TaskState, Integration-1F, Mission-A and Mission-B paths
    remain live.
    """

    saved_messages = (
        _install_no_persistence_conversation_seam(
            monkeypatch
        )
    )

    permission_calls = (
        _install_permission_spy(
            monkeypatch
        )
    )

    projections = (
        _install_projection_spy(
            monkeypatch
        )
    )

    kuma = production_factory()

    realtime = CountingRealtime()
    kuma.realtime_runtime = realtime

    mission_service_calls = (
        _install_mission_service_tripwires(
            monkeypatch,
            kuma,
        )
    )

    tool_calls = []

    def proof_inspect_system():
        tool_calls.append(
            (
                "inspect_system",
                {},
            )
        )

        return TOOL_RESULT

    kuma.register_tool(
        "inspect_system",
        proof_inspect_system,
    )

    build_actions = []
    original_build_action = (
        kuma.build_action
    )

    def build_action_spy(
        tool_name,
        arguments,
    ):
        build_actions.append(
            (
                str(
                    tool_name
                ),
                dict(
                    arguments
                    or {}
                ),
            )
        )

        return original_build_action(
            tool_name,
            arguments,
        )

    kuma.build_action = (
        build_action_spy
    )

    executor_calls = []
    original_execute = (
        kuma.executor.execute
    )

    def executor_spy(
        *args,
        **kwargs,
    ):
        executor_calls.append(
            (
                args,
                kwargs,
            )
        )

        return original_execute(
            *args,
            **kwargs,
        )

    kuma.executor.execute = (
        executor_spy
    )

    model_inputs = []
    model_calls = {
        "count": 0,
    }

    def deterministic_ask_model(
        messages,
    ):
        model_inputs.append(
            _message_snapshot(
                messages
            )
        )

        model_calls[
            "count"
        ] += 1

        if (
            model_calls[
                "count"
            ]
            == 1
        ):
            return (
                kuma
                ._synthetic_model_response(
                    tool_name="inspect_system",
                    arguments={},
                )
            )

        if (
            model_calls[
                "count"
            ]
            == 2
        ):
            return (
                kuma
                ._synthetic_model_response(
                    content=(
                        SAFE_FINAL_RESPONSE
                    ),
                )
            )

        raise AssertionError(
            "Mission-C safe proof received an unexpected extra model call."
        )

    kuma.ask_model = (
        deterministic_ask_model
    )

    goal_decisions = []

    def deterministic_goal_decision(
        messages,
    ):
        decision = GoalDecision(
            status=(
                GoalStatus.CONTINUE
            ),
            remaining_objective=(
                "Summarize the verified inspection result for the user."
            ),
            next_action="",
            reason=(
                "The safe inspection completed, but the explicit user request "
                "requires a final natural-language summary."
            ),
        )

        goal_decisions.append(
            decision
        )

        return (
            decision,
            None,
        )

    kuma.ask_goal_decision = (
        deterministic_goal_decision
    )

    run_calls = []
    original_run = (
        kuma.run
    )

    def counted_run(
        user_message,
        *,
        prepared_realtime_turn=None,
    ):
        run_calls.append(
            (
                str(
                    user_message
                ),
                prepared_realtime_turn,
            )
        )

        return original_run(
            user_message,
            prepared_realtime_turn=(
                prepared_realtime_turn
            ),
        )

    kuma.run = (
        counted_run
    )

    return SimpleNamespace(
        kuma=kuma,
        realtime=realtime,
        saved_messages=saved_messages,
        permission_calls=permission_calls,
        projections=projections,
        mission_service_calls=mission_service_calls,
        tool_calls=tool_calls,
        build_actions=build_actions,
        executor_calls=executor_calls,
        model_inputs=model_inputs,
        model_calls=model_calls,
        goal_decisions=goal_decisions,
        run_calls=run_calls,
    )


def _assert_safe_turn_contract(
    proof,
    *,
    result,
):
    assert (
        result
        == SAFE_FINAL_RESPONSE
    )

    assert len(
        proof.run_calls
    ) == 1

    assert (
        proof.run_calls[
            0
        ][
            0
        ]
        == SAFE_USER_MESSAGE
    )

    assert (
        proof.run_calls[
            0
        ][
            1
        ]
        is not None
    )

    assert (
        proof.realtime.tick_calls
        == 1
    )

    assert (
        proof.realtime.pending_calls
        == 1
    )

    assert (
        proof.model_calls[
            "count"
        ]
        == 2
    )

    assert len(
        proof.model_inputs
    ) == 2

    assert not any(
        ADVISORY_MARKER
        in content
        for _role, content
        in proof.model_inputs[
            0
        ]
    )

    second_advisories = [
        content
        for role, content
        in proof.model_inputs[
            1
        ]
        if (
            role
            == "system"
            and ADVISORY_MARKER
            in content
        )
    ]

    assert len(
        second_advisories
    ) == 1

    advisory_text = (
        second_advisories[
            0
        ]
    )

    assert (
        "AUTHORITY:NONE"
        in advisory_text
    )

    assert len(
        proof.projections
    ) == 1

    projection = (
        proof.projections[
            0
        ]
    )

    assert (
        projection.authority
        == "NONE"
    )

    assert (
        projection.to_reasoning_context()
        == advisory_text
    )

    assert (
        proof.build_actions
        == [
            (
                "inspect_system",
                {},
            )
        ]
    )

    assert (
        proof.tool_calls
        == [
            (
                "inspect_system",
                {},
            )
        ]
    )

    assert len(
        proof.executor_calls
    ) == 1

    assert (
        proof.mission_service_calls
        == []
    )

    assert (
        len(
            proof.permission_calls
        )
        >= 1
    )

    permission_names = {
        getattr(
            call[
                2
            ],
            "name",
            str(
                call[
                    2
                ]
            ),
        )
        for call
        in proof.permission_calls
    }

    assert (
        "SAFE"
        in permission_names
        or any(
            "safe"
            in str(
                value
            ).casefold()
            for value
            in permission_names
        )
    )

    assert len(
        proof.goal_decisions
    ) == 1

    assert (
        proof.goal_decisions[
            0
        ].status
        is GoalStatus.CONTINUE
    )

    assert not any(
        ADVISORY_MARKER
        in str(
            content
        )
        for _role, content
        in proof.saved_messages
    )

    assert not any(
        ADVISORY_MARKER
        in str(
            getattr(
                message,
                "content",
                (
                    message.get(
                        "content",
                        "",
                    )
                    if isinstance(
                        message,
                        dict,
                    )
                    else ""
                ),
            )
        )
        for message
        in proof.kuma.messages
    )

    assert not any(
        "mission_cognitive_advisory"
        in name
        for name
        in vars(
            proof.kuma
        )
    )

    return advisory_text


def test_mission_c_gui_real_production_chain_carries_one_shot_advisory(
    monkeypatch,
):
    production_factory = (
        kuma_runtime.create_kuma
    )

    memories_before = (
        _snapshot_memories_table()
    )

    proof = (
        _prepare_safe_real_agent(
            monkeypatch,
            production_factory=(
                production_factory
            ),
        )
    )

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: proof.kuma,
    )

    runtime = (
        gui_runtime.KumaGUIRuntime()
    )

    try:
        result = runtime.run(
            SAFE_USER_MESSAGE
        )

        advisory_text = (
            _assert_safe_turn_contract(
                proof,
                result=result,
            )
        )

        events = (
            runtime
            .runtime_trace_events()
        )

        _assert_one_runtime_turn(
            events
        )

        _assert_trace_privacy(
            events,
            user_message=(
                SAFE_USER_MESSAGE
            ),
            response=(
                SAFE_FINAL_RESPONSE
            ),
            advisory_text=(
                advisory_text
            ),
        )

        memories_after = (
            _snapshot_memories_table()
        )

        assert (
            memories_after
            == memories_before
        )

        # -------------------------------------------------
        # NEXT EXPLICIT USER TURN MUST START CLEAN
        # -------------------------------------------------

        next_turn_inputs = []

        def next_turn_model(
            messages,
        ):
            next_turn_inputs.append(
                _message_snapshot(
                    messages
                )
            )

            return (
                proof.kuma
                ._synthetic_model_response(
                    content="SECOND-TURN-CLEAN",
                )
            )

        proof.kuma.ask_model = (
            next_turn_model
        )

        second = runtime.run(
            "Hello KUMA."
        )

        assert (
            second
            == "SECOND-TURN-CLEAN"
        )

        assert len(
            next_turn_inputs
        ) == 1

        assert not any(
            ADVISORY_MARKER
            in content
            for _role, content
            in next_turn_inputs[
                0
            ]
        )

        assert (
            proof.realtime.tick_calls
            == 2
        )

        assert (
            proof.realtime.pending_calls
            == 2
        )

        assert len(
            proof.run_calls
        ) == 2

        all_events = (
            runtime
            .runtime_trace_events()
        )

        kinds = Counter(
            _event_kinds(
                all_events
            )
        )

        assert (
            kinds[
                "turn.started"
            ]
            == 2
        )

        assert (
            kinds[
                "turn.ended"
            ]
            == 2
        )

        assert (
            _snapshot_memories_table()
            == memories_before
        )

    finally:
        closer = getattr(
            runtime,
            "close",
            None,
        )

        if callable(
            closer
        ):
            closer()
        else:
            runtime._runtime_v2_owner.close()


def test_mission_c_cli_real_production_chain_carries_one_shot_advisory(
    monkeypatch,
    capsys,
):
    production_factory = (
        kuma_runtime.create_kuma
    )

    memories_before = (
        _snapshot_memories_table()
    )

    proof = (
        _prepare_safe_real_agent(
            monkeypatch,
            production_factory=(
                production_factory
            ),
        )
    )

    captured_runtime_owners = []

    class CapturingRuntimeOwner(
        RealRuntimeOwner
    ):
        def __init__(
            self,
            *args,
            **kwargs,
        ):
            super().__init__(
                *args,
                **kwargs,
            )

            captured_runtime_owners.append(
                self
            )

    monkeypatch.setattr(
        kuma_runtime,
        "create_kuma",
        lambda: proof.kuma,
    )

    monkeypatch.setattr(
        kuma_runtime,
        "KumaRuntimeV2LiveOwner",
        CapturingRuntimeOwner,
    )

    monkeypatch.setattr(
        kuma_runtime,
        "release_owned_mouse_button_for_shutdown",
        lambda: SimpleNamespace(
            success=True,
            result="already CLEAR",
            error=None,
        ),
    )

    inputs = iter(
        (
            SAFE_USER_MESSAGE,
            "exit",
        )
    )

    monkeypatch.setattr(
        "builtins.input",
        lambda _prompt: next(
            inputs
        ),
    )

    kuma_runtime.main()

    output = (
        capsys
        .readouterr()
        .out
    )

    assert (
        SAFE_FINAL_RESPONSE
        in output
    )

    advisory_text = (
        _assert_safe_turn_contract(
            proof,
            result=(
                SAFE_FINAL_RESPONSE
            ),
        )
    )

    assert len(
        captured_runtime_owners
    ) == 1

    events = (
        captured_runtime_owners[
            0
        ].events()
    )

    _assert_one_runtime_turn(
        events
    )

    _assert_trace_privacy(
        events,
        user_message=(
            SAFE_USER_MESSAGE
        ),
        response=(
            SAFE_FINAL_RESPONSE
        ),
        advisory_text=(
            advisory_text
        ),
    )

    assert (
        _snapshot_memories_table()
        == memories_before
    )


def test_mission_c_gui_confirmation_still_blocks_dangerous_execution(
    monkeypatch,
):
    production_factory = (
        kuma_runtime.create_kuma
    )

    saved_messages = (
        _install_no_persistence_conversation_seam(
            monkeypatch
        )
    )

    permission_calls = (
        _install_permission_spy(
            monkeypatch
        )
    )

    projections = (
        _install_projection_spy(
            monkeypatch
        )
    )

    kuma = production_factory()

    realtime = CountingRealtime()
    kuma.realtime_runtime = realtime

    mission_service_calls = (
        _install_mission_service_tripwires(
            monkeypatch,
            kuma,
        )
    )

    executed = []

    def must_not_execute(
        command,
    ):
        executed.append(
            command
        )

        raise AssertionError(
            "Denied dangerous command reached the registered tool."
        )

    kuma.register_tool(
        "execute_command",
        must_not_execute,
    )

    model_inputs = []

    def dangerous_model(
        messages,
    ):
        model_inputs.append(
            _message_snapshot(
                messages
            )
        )

        if len(
            model_inputs
        ) > 1:
            raise AssertionError(
                "Denied dangerous action must not create another normal model step."
            )

        return (
            kuma
            ._synthetic_model_response(
                tool_name=(
                    "execute_command"
                ),
                arguments={
                    "command": (
                        "echo SHOULD-NOT-RUN"
                    ),
                },
            )
        )

    kuma.ask_model = (
        dangerous_model
    )

    run_calls = []
    original_run = (
        kuma.run
    )

    def counted_run(
        user_message,
        *,
        prepared_realtime_turn=None,
    ):
        run_calls.append(
            (
                user_message,
                prepared_realtime_turn,
            )
        )

        return original_run(
            user_message,
            prepared_realtime_turn=(
                prepared_realtime_turn
            ),
        )

    kuma.run = (
        counted_run
    )

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: kuma,
    )

    runtime = (
        gui_runtime.KumaGUIRuntime()
    )

    confirmations = []

    def deny(
        *args,
        **kwargs,
    ):
        confirmations.append(
            (
                args,
                kwargs,
            )
        )

        return False

    runtime.kuma.confirmation_callback = (
        deny
    )

    memories_before = (
        _snapshot_memories_table()
    )

    user_message = (
        "Run command echo SHOULD-NOT-RUN"
    )

    try:
        result = runtime.run(
            user_message
        )

        assert len(
            run_calls
        ) == 1

        assert (
            realtime.tick_calls
            == 1
        )

        assert (
            realtime.pending_calls
            == 1
        )

        assert len(
            model_inputs
        ) == 1

        assert len(
            confirmations
        ) == 1

        assert executed == []

        assert mission_service_calls == []

        assert len(
            permission_calls
        ) >= 1

        permission_names = {
            getattr(
                call[
                    2
                ],
                "name",
                str(
                    call[
                        2
                    ]
                ),
            )
            for call
            in permission_calls
        }

        assert (
            "DANGEROUS"
            in permission_names
            or any(
                "danger"
                in str(
                    value
                ).casefold()
                for value
                in permission_names
            )
        )

        assert (
            "denied"
            in str(
                result
            ).casefold()
            or "not executed"
            in str(
                result
            ).casefold()
        )

        # Cognition may observe the proposed action, but denial remains final.
        for projection in projections:
            assert (
                projection.authority
                == "NONE"
            )

        assert not any(
            ADVISORY_MARKER
            in str(
                content
            )
            for _role, content
            in saved_messages
        )

        events = (
            runtime
            .runtime_trace_events()
        )

        _assert_one_runtime_turn(
            events
        )

        _assert_trace_privacy(
            events,
            user_message=(
                user_message
            ),
            response=str(
                result
            ),
        )

        assert (
            _snapshot_memories_table()
            == memories_before
        )

    finally:
        closer = getattr(
            runtime,
            "close",
            None,
        )

        if callable(
            closer
        ):
            closer()
        else:
            runtime._runtime_v2_owner.close()


def test_mission_c_projection_failure_is_fail_soft_in_real_gui_chain(
    monkeypatch,
):
    production_factory = (
        kuma_runtime.create_kuma
    )

    proof = (
        _prepare_safe_real_agent(
            monkeypatch,
            production_factory=(
                production_factory
            ),
        )
    )

    def explode_projection(
        *,
        integrated_observation,
    ):
        raise RuntimeError(
            "MISSION-C synthetic projection failure"
        )

    monkeypatch.setattr(
        mission_cognitive_module,
        "project_mission_cognitive_observation",
        explode_projection,
    )

    # The helper above already installed a spy wrapper. Replace it deliberately
    # with failure after construction so the live run exercises Mission-B's
    # fail-soft capture boundary.
    proof.projections.clear()

    monkeypatch.setattr(
        gui_runtime,
        "create_kuma",
        lambda: proof.kuma,
    )

    runtime = (
        gui_runtime.KumaGUIRuntime()
    )

    try:
        result = runtime.run(
            SAFE_USER_MESSAGE
        )

        assert (
            result
            == SAFE_FINAL_RESPONSE
        )

        assert (
            proof.model_calls[
                "count"
            ]
            == 2
        )

        assert len(
            proof.model_inputs
        ) == 2

        assert not any(
            ADVISORY_MARKER
            in content
            for messages
            in proof.model_inputs
            for _role, content
            in messages
        )

        assert (
            proof.tool_calls
            == [
                (
                    "inspect_system",
                    {},
                )
            ]
        )

        assert (
            proof.realtime.tick_calls
            == 1
        )

        assert (
            proof.realtime.pending_calls
            == 1
        )

        _assert_one_runtime_turn(
            runtime
            .runtime_trace_events()
        )

    finally:
        closer = getattr(
            runtime,
            "close",
            None,
        )

        if callable(
            closer
        ):
            closer()
        else:
            runtime._runtime_v2_owner.close()
