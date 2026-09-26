from dataclasses import (
    replace,
)
from pathlib import Path
from unittest.mock import (
    Mock,
)

import pytest

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_provenance import (
    FocusDesktopProvenanceStore,
)
from app.ui_observation.focus_store import (
    FocusedUIObservationStore,
)
from app.ui_observation.focus_target_correlation import (
    AMBIGUOUS_CODE,
    CORRELATION_STATUS_AMBIGUOUS,
    CORRELATION_STATUS_MATCHED,
    CORRELATION_STATUS_MISMATCHED,
    CORRELATION_STATUS_UNKNOWN,
    FocusTargetCorrelationResult,
    FocusTargetSemanticCandidate,
)
from app.ui_observation.focus_target_producer import (
    PRODUCTION_STATUS_MATCHED,
    PRODUCTION_STATUS_UNKNOWN,
    FocusTargetProvenanceProducer,
    FocusTargetProvenanceProduction,
)
from app.ui_observation.focus_target_provenance import (
    FocusTargetProvenanceStore,
)
from app.ui_observation.target_revalidation import (
    StructuredUITargetRevalidationResult,
)
from app.ui_observation.test_focus_target_provenance import (
    sources,
)


class Clock:
    def __init__(
        self,
        *values,
    ):
        self.values = list(
            values
        )

    def __call__(
        self,
    ):
        if len(
            self.values
        ) > 1:
            return self.values.pop(
                0
            )

        return self.values[
            0
        ]


def correlation_for(
    semantic,
    *,
    captured,
    status=CORRELATION_STATUS_MATCHED,
):
    target = (
        semantic.revalidation
    )

    selector = replace(
        target.selector
    )

    application = (
        ApplicationIdentity(
            target.application_pid,
            target.application_bundle_id,
        )
    )

    candidate = (
        FocusTargetSemanticCandidate(
            path=(
                0,
            ),
            owner_pid=(
                application.pid
            ),
            role=(
                selector.role
            ),
            subrole=(
                selector.subrole
            ),
            title=(
                selector.text
            ),
            description=None,
            enabled=(
                True
                if selector.require_enabled
                else None
            ),
            position_x=(
                10.0
                if selector.require_positive_area
                else None
            ),
            position_y=(
                20.0
                if selector.require_positive_area
                else None
            ),
            width=(
                100.0
                if selector.require_positive_area
                else None
            ),
            height=(
                30.0
                if selector.require_positive_area
                else None
            ),
        )
    )

    if (
        status
        == CORRELATION_STATUS_MATCHED
    ):
        return FocusTargetCorrelationResult(
            captured_at_monotonic=(
                captured
            ),
            status=status,
            expected_application=(
                application
            ),
            selector=selector,
            candidate_count=1,
            candidate=candidate,
            diagnostics=(),
        )

    if (
        status
        == CORRELATION_STATUS_MISMATCHED
    ):
        return FocusTargetCorrelationResult(
            captured_at_monotonic=(
                captured
            ),
            status=status,
            expected_application=(
                application
            ),
            selector=selector,
            candidate_count=1,
            candidate=candidate,
            diagnostics=(
                "focused_target_mismatch",
            ),
        )

    if (
        status
        == CORRELATION_STATUS_AMBIGUOUS
    ):
        return FocusTargetCorrelationResult(
            captured_at_monotonic=(
                captured
            ),
            status=status,
            expected_application=(
                application
            ),
            selector=selector,
            candidate_count=2,
            candidate=None,
            diagnostics=(
                AMBIGUOUS_CODE,
            ),
        )

    return FocusTargetCorrelationResult(
        captured_at_monotonic=(
            captured
        ),
        status=(
            CORRELATION_STATUS_UNKNOWN
        ),
        expected_application=(
            application
        ),
        selector=selector,
        candidate_count=0,
        candidate=None,
        diagnostics=(
            "focused_element_unavailable",
        ),
    )


def fixture():
    (
        semantic,
        focus,
        _correlation,
        issued,
    ) = sources()

    captured = (
        max(
            semantic
            .revalidation
            .revalidated_at_monotonic,
            focus
            .binding
            .bound_at_monotonic,
        )
        + 0.01
    )

    issued = max(
        issued,
        captured
        + 0.01,
    )

    active_focus = {
        "value": focus,
    }

    focus_store = (
        FocusDesktopProvenanceStore(
            focus_store=(
                FocusedUIObservationStore(
                    ttl_seconds=60.0,
                    clock=lambda: issued,
                )
            ),
            clock=lambda: issued,
        )
    )

    provenance_store = (
        FocusTargetProvenanceStore(
            focus_lookup=(
                lambda observation_id:
                (
                    active_focus[
                        "value"
                    ]
                    if (
                        active_focus[
                            "value"
                        ]
                        is not None
                        and active_focus[
                            "value"
                        ]
                        .focus_observation_id
                        == observation_id
                    )
                    else None
                )
            ),
            clock=lambda: issued,
        )
    )

    correlation = correlation_for(
        semantic,
        captured=captured,
    )

    runtime = Mock(
        return_value=correlation
    )

    producer = (
        FocusTargetProvenanceProducer(
            focus_store=focus_store,
            provenance_store=(
                provenance_store
            ),
            correlation_runtime=runtime,
            clock=Clock(
                captured,
                issued,
            ),
        )
    )

    return {
        "semantic": semantic,
        "focus": focus,
        "captured": captured,
        "issued": issued,
        "active_focus": active_focus,
        "focus_store": focus_store,
        "provenance_store": provenance_store,
        "correlation": correlation,
        "runtime": runtime,
        "producer": producer,
    }


def activate_focus(
    values,
):
    focus = values[
        "focus"
    ]

    store = values[
        "focus_store"
    ]

    observation_store = (
        store._focus_store
    )

    assert observation_store.publish(
        focus.focus_observation
    )

    assert store.publish(
        focus
    )

    assert (
        store.get(
            focus.focus_observation_id
        )
        is focus
    )


def test_happy_path_runs_runtime_itself_and_publishes_exact_graph():
    values = fixture()

    activate_focus(
        values
    )

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert (
        result.status
        == PRODUCTION_STATUS_MATCHED
    )

    assert result.produced

    assert (
        result.correlation
        is values[
            "correlation"
        ]
    )

    provenance = (
        result.provenance
    )

    assert (
        provenance.semantic_result
        is values[
            "semantic"
        ]
    )

    assert (
        provenance.focus_provenance
        is values[
            "focus"
        ]
    )

    assert (
        provenance.correlation
        is values[
            "correlation"
        ]
    )

    assert (
        values[
            "provenance_store"
        ]
        .get(
            provenance
        )
        is provenance
    )

    runtime = values[
        "runtime"
    ]

    runtime.assert_called_once()

    args = (
        runtime.call_args.args
    )

    kwargs = (
        runtime.call_args.kwargs
    )

    assert (
        type(
            args[
                0
            ]
        )
        is ApplicationIdentity
    )

    assert (
        args[
            0
        ].pid
        == provenance.application_pid
    )

    assert (
        args[
            0
        ].bundle_id
        == provenance.application_bundle_id
    )

    assert (
        args[
            1
        ]
        is values[
            "semantic"
        ]
        .revalidation
        .selector
    )

    assert (
        kwargs[
            "timeout_seconds"
        ]
        == 3.0
    )


def test_caller_has_no_correlation_argument_surface():
    import inspect

    signature = (
        inspect.signature(
            FocusTargetProvenanceProducer
            .produce
        )
    )

    assert (
        "correlation"
        not in signature.parameters
    )

    assert (
        "candidate"
        not in signature.parameters
    )


def test_wrong_focus_id_never_falls_back_to_active_focus():
    values = fixture()

    activate_focus(
        values
    )

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            "wrong-focus-id",
        )
    )

    assert (
        result.status
        == PRODUCTION_STATUS_UNKNOWN
    )

    assert result.diagnostics == (
        "focus_provenance_unavailable",
    )

    values[
        "runtime"
    ].assert_not_called()

    assert len(
        values[
            "provenance_store"
        ]
    ) == 0


def test_equal_value_reconstructed_focus_is_not_recovered():
    values = fixture()

    activate_focus(
        values
    )

    clone = replace(
        values[
            "focus"
        ]
    )

    assert clone == values[
        "focus"
    ]

    assert clone is not values[
        "focus"
    ]

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            clone.focus_observation_id,
        )
    )

    assert result.produced

    assert (
        result.provenance.focus_provenance
        is values[
            "focus"
        ]
    )

    assert (
        result.provenance.focus_provenance
        is not clone
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        (
            CORRELATION_STATUS_UNKNOWN,
            "correlation_unknown",
        ),
        (
            CORRELATION_STATUS_AMBIGUOUS,
            "correlation_ambiguous",
        ),
        (
            CORRELATION_STATUS_MISMATCHED,
            "correlation_mismatch",
        ),
    ],
)
def test_nonmatched_runtime_evidence_is_never_promoted(
    status,
    expected,
):
    values = fixture()

    activate_focus(
        values
    )

    values[
        "runtime"
    ].return_value = (
        correlation_for(
            values[
                "semantic"
            ],
            captured=values[
                "captured"
            ],
            status=status,
        )
    )

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert (
        result.status
        == PRODUCTION_STATUS_UNKNOWN
    )

    assert result.diagnostics == (
        expected,
    )

    assert len(
        values[
            "provenance_store"
        ]
    ) == 0


def test_runtime_exception_is_sanitized_and_not_published():
    values = fixture()

    activate_focus(
        values
    )

    values[
        "runtime"
    ].side_effect = (
        RuntimeError(
            "SECRET"
        )
    )

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert result.diagnostics == (
        "correlation_unknown",
    )

    assert "SECRET" not in repr(
        result
    )

    assert len(
        values[
            "provenance_store"
        ]
    ) == 0


def test_invalid_runtime_shape_is_rejected():
    values = fixture()

    activate_focus(
        values
    )

    values[
        "runtime"
    ].return_value = object()

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert result.diagnostics == (
        "correlation_invalid",
    )

    assert len(
        values[
            "provenance_store"
        ]
    ) == 0


def test_invalid_semantic_result_fails_before_focus_or_runtime():
    values = fixture()

    result = (
        values[
            "producer"
        ]
        .produce(
            object(),
            "focus",
        )
    )

    assert result.diagnostics == (
        "invalid_semantic_result",
    )

    values[
        "runtime"
    ].assert_not_called()


def test_focus_application_mismatch_blocks_runtime():
    values = fixture()

    semantic = values[
        "semantic"
    ]

    original = values[
        "focus"
    ]

    foreign_application = (
        ApplicationIdentity(
            999,
            semantic
            .revalidation
            .application_bundle_id,
            "Other",
        )
    )

    foreign_binding = replace(
        original.binding,
        application_pid=(
            foreign_application.pid
        ),
        application_bundle_id=(
            foreign_application.bundle_id
        ),
    )

    foreign_observation = replace(
        original.focus_observation,
        active_application=(
            foreign_application
        ),
    )

    foreign_before = replace(
        original.desktop_before,
        active_application=(
            foreign_application
        ),
    )

    foreign_after = replace(
        original.desktop_after,
        active_application=(
            foreign_application
        ),
    )

    foreign_focus = type(
        original
    )(
        binding=foreign_binding,
        focus_observation=(
            foreign_observation
        ),
        desktop_before=(
            foreign_before
        ),
        desktop_after=(
            foreign_after
        ),
    )

    assert (
        foreign_focus.application_pid
        == 999
    )

    assert (
        foreign_focus.application_bundle_id
        == (
            semantic
            .revalidation
            .application_bundle_id
        )
    )

    values[
        "focus"
    ] = foreign_focus

    activate_focus(
        values
    )

    result = (
        values[
            "producer"
        ]
        .produce(
            semantic,
            foreign_focus
            .focus_observation_id,
        )
    )

    assert result.diagnostics == (
        "focus_application_mismatch",
    )

    values[
        "runtime"
    ].assert_not_called()

    assert len(
        values[
            "provenance_store"
        ]
    ) == 0

def test_failed_new_attempt_clears_previous_publication():
    values = fixture()

    activate_focus(
        values
    )

    first = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert first.produced

    assert len(
        values[
            "provenance_store"
        ]
    ) == 1

    values[
        "producer"
    ]._clock = Clock(
        values[
            "issued"
        ]
        + 0.01,
    )

    failed = (
        values[
            "producer"
        ]
        .produce(
            object(),
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert not failed.produced

    assert len(
        values[
            "provenance_store"
        ]
    ) == 0


def test_publication_failure_returns_no_provenance():
    values = fixture()

    activate_focus(
        values
    )

    values[
        "active_focus"
    ][
        "value"
    ] = None

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    assert result.diagnostics == (
        "publication_failed",
    )

    assert result.provenance is None


def test_production_lock_is_fail_closed():
    values = fixture()

    assert (
        values[
            "producer"
        ]
        ._lock
        .acquire(
            blocking=False
        )
    )

    try:
        result = (
            values[
                "producer"
            ]
            .produce(
                values[
                    "semantic"
                ],
                values[
                    "focus"
                ]
                .focus_observation_id,
            )
        )

        assert result.diagnostics == (
            "production_busy",
        )

    finally:
        values[
            "producer"
        ]._lock.release()


def test_result_contract_rejects_forged_combinations():
    with pytest.raises(
        ValueError
    ):
        FocusTargetProvenanceProduction(
            status=(
                PRODUCTION_STATUS_MATCHED
            ),
        )

    with pytest.raises(
        ValueError
    ):
        FocusTargetProvenanceProduction(
            status=(
                PRODUCTION_STATUS_UNKNOWN
            ),
            diagnostics=(
                "made_up",
            ),
        )


def test_production_has_no_authority_surface():
    values = fixture()

    activate_focus(
        values
    )

    result = (
        values[
            "producer"
        ]
        .produce(
            values[
                "semantic"
            ],
            values[
                "focus"
            ]
            .focus_observation_id,
        )
    )

    forbidden = (
        "authorized",
        "approved",
        "permission",
        "attestation",
        "keyboard_authority",
        "text_authority",
        "semantic_target_verified",
        "execute",
        "type_text",
    )

    for name in forbidden:
        assert not hasattr(
            result,
            name,
        )

        assert not hasattr(
            result.provenance,
            name,
        )


def test_module_has_no_native_or_execution_surface():
    path = Path(
        __file__
    ).with_name(
        "focus_target_producer.py"
    )

    text = path.read_text(
        encoding="utf-8"
    )

    forbidden = (
        "ApplicationServices",
        "AppKit",
        "CoreFoundation",
        "AXUIElementSetAttributeValue",
        "AXUIElementPerformAction",
        "pyautogui",
        "computer_tools",
        "mission_service",
    )

    for marker in forbidden:
        assert marker not in text


def test_caller_cannot_supply_application_identity():
    import inspect

    signature = (
        inspect.signature(
            FocusTargetProvenanceProducer
            .produce
        )
    )

    assert (
        "expected_application"
        not in signature.parameters
    )

    assert (
        "application"
        not in signature.parameters
    )
