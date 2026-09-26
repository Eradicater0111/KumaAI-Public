"""Native numeric bridges are normalized only at the macOS adapter boundary."""
from unittest.mock import Mock

import pytest

from app.desktop.collector import assemble_snapshot
from app.desktop.contracts import ApplicationIdentity, WindowBounds, COORDINATE_SPACE
from app.desktop.test_desktop_context import APP, native_provider


class BridgedInt(int):
    pass


class BridgedFloat(float):
    pass


def native_row(integer=BridgedInt, real=BridgedFloat, **changes):
    return dict(pid=integer(123), id=integer(42), title='Example', bounds={
        'X': real(-20.5), 'Y': integer(10), 'Width': real(100), 'Height': integer(50),
    }, **changes)


def collect_native(rows):
    p = native_provider(rows)
    p.frontmost_application = Mock(return_value=APP)
    p.quartz.CGPreflightScreenCaptureAccess.return_value = True
    return assemble_snapshot(p, clock=lambda: 100.0)


def assert_window(result):
    assert len(result.windows) == 1
    window = result.windows[0]
    assert type(window.owner_pid) is int and window.owner_pid == 123
    assert type(window.native_window_id) is int and window.native_window_id == 42
    assert window.bounds == WindowBounds(-20.5, 10, 100, 50, COORDINATE_SPACE)
    assert all(type(v) in (int, float) for v in (
        window.bounds.x, window.bounds.y, window.bounds.width, window.bounds.height))
    assert result.diagnostics == ('focus_unavailable',)


def test_numeric_subclasses_produce_a_window_through_full_assembly():
    assert_window(collect_native([native_row()]))


def test_real_foundation_numbers_without_desktop_access():
    foundation = pytest.importorskip('Foundation')
    integer = foundation.NSNumber.numberWithInt_
    real = foundation.NSNumber.numberWithDouble_
    assert_window(collect_native([native_row(integer, real)]))


@pytest.mark.parametrize('value', [True, '123', 123.0, 123.5, None, 0, -1])
def test_invalid_owner_is_failed_enumeration_not_a_successful_empty_list(value):
    row = native_row()
    row['pid'] = value
    result = collect_native([row])
    assert result.status == 'partial'
    assert not result.enumeration_succeeded
    assert result.diagnostics == ('window_enumeration_unavailable',)


def test_foreign_bridged_pid_still_cannot_associate_by_title():
    row = native_row()
    row['pid'] = BridgedInt(456)
    result = collect_native([row])
    assert result.windows == () and result.enumeration_succeeded


@pytest.mark.parametrize('value', [True, '42', 42.0, 42.5, 0, -1])
def test_invalid_native_id_is_unknown_without_coercion(value):
    row = native_row()
    row['id'] = value
    result = collect_native([row])
    assert len(result.windows) == 1
    assert result.windows[0].native_window_id is None
    assert 'window_metadata_missing' in result.diagnostics


@pytest.mark.parametrize('value', [True, '100', float('nan'), float('inf'),
                                  BridgedFloat('-inf'), 0, -1])
def test_invalid_native_bounds_remain_unknown(value):
    row = native_row()
    row['bounds']['Width'] = value
    result = collect_native([row])
    assert len(result.windows) == 1
    assert result.windows[0].bounds is None
    assert 'malformed_window_record' in result.diagnostics


def test_portable_contract_still_rejects_numeric_subclasses():
    with pytest.raises(ValueError):
        ApplicationIdentity(BridgedInt(123))
    with pytest.raises(ValueError):
        WindowBounds(BridgedFloat(0), 0, 1, 1, COORDINATE_SPACE)
