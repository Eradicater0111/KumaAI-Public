"""Deterministic denial/cleanup checks; never launch a native candidate."""
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.agent import repair_execution_sandbox as native
from app.agent.repair_workspace import RepairWorkspaceError


@pytest.mark.parametrize('response', [
    PermissionError('process inspection denied'),
    subprocess.TimeoutExpired('ps', 1),
    SimpleNamespace(returncode=1, stdout=''),
    SimpleNamespace(returncode=0, stdout=''),
    SimpleNamespace(returncode=0, stdout='not-a-number'),
    SimpleNamespace(returncode=0, stdout='-1'),
])
def test_unusable_process_memory_evidence_is_rejected(monkeypatch, response):
    runner = native.RepairExecutionSandbox()
    process = SimpleNamespace(pid=123, poll=Mock(return_value=None))
    read = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
    monkeypatch.setattr(native.subprocess, 'run', read)
    with pytest.raises(RepairWorkspaceError):
        runner._resident_memory_bytes(process)
    read.assert_called_once()
    assert read.call_args.kwargs['shell'] is False


def test_unsupported_host_cannot_launch_a_candidate(monkeypatch, tmp_path):
    runner = native.RepairExecutionSandbox()
    monkeypatch.setattr(native.sys, 'platform', 'unsupported')
    launch = Mock()
    monkeypatch.setattr(native.subprocess, 'Popen', launch)
    with pytest.raises(RepairWorkspaceError, match='fails closed'):
        runner._run_contained_python(candidate_root=tmp_path, harness_body='pass', payload_args=())
    launch.assert_not_called()


def test_inspection_failure_kills_reaps_and_closes_native_worker(monkeypatch, tmp_path):
    runner = native.RepairExecutionSandbox()
    monkeypatch.setattr(runner, '_host_support', lambda: (
        tmp_path / 'sandbox-exec', tmp_path / 'python', tmp_path, ()))
    monkeypatch.setattr(runner, '_build_profile', Mock(return_value='(deny default)'))
    process = SimpleNamespace(stdout=Mock(), stderr=Mock(), wait=Mock())
    launch = Mock(return_value=process)
    monkeypatch.setattr(native.subprocess, 'Popen', launch)
    monkeypatch.setattr(runner, '_collect_output', Mock(
        side_effect=RepairWorkspaceError('memory inspection unavailable')))
    kill = Mock()
    monkeypatch.setattr(runner, '_kill_group', kill)
    with pytest.raises(RepairWorkspaceError, match='memory inspection unavailable'):
        runner._run_contained_python(candidate_root=tmp_path, harness_body='pass', payload_args=())
    launch.assert_called_once()
    assert launch.call_args.args[0][0] == str(tmp_path / 'sandbox-exec')
    assert launch.call_args.kwargs['shell'] is False
    kill.assert_called_once_with(process)
    process.wait.assert_called_once_with(timeout=2)
    process.stdout.close.assert_called_once()
    process.stderr.close.assert_called_once()
