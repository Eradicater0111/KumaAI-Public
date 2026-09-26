"""Exercise test selection and import safety in fresh interpreters."""
from pathlib import Path
import subprocess
import sys

import pytest

pytest_plugins = ['pytester']
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('option', [None, '--run-native-sandbox', '--run-live-model'])
def test_external_checks_require_their_own_opt_in(pytester, option):
    pytester.makeconftest((ROOT / 'conftest.py').read_text())
    pytester.makeini('''[pytest]
markers =
    native_sandbox: native containment
    live_model: real model
''')
    pytester.makepyfile('''
import socket
import pytest

@pytest.mark.native_sandbox
def test_native():
    pytest.fail('Selected native check fails; never silently skip an unavailable check.')

@pytest.mark.live_model
def test_model():
    pytest.fail('Selected model check fails; never turn a failed check into a pass.')

def test_local():
    assert 2 + 2 == 4

def test_accidental_network_is_blocked():
    with socket.socket() as connection:
        with pytest.raises(pytest.fail.Exception, match='Unmocked external effect'):
            connection.connect(('127.0.0.1', 9))
''')
    result = pytester.runpytest_subprocess('-q', '-p', 'no:cacheprovider',
                                         *([option] if option else []), timeout=15)
    result.assert_outcomes(passed=2, skipped=2 if option is None else 1,
                           failed=0 if option is None else 1)


def test_manual_demos_do_not_import_runtime_or_call_models_on_import():
    script = r'''
import runpy
import sys
class RejectRuntime:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('app.', 'ollama', 'sentence_transformers')):
            raise AssertionError('Demo imported live runtime during collection')
sys.meta_path.insert(0, RejectRuntime())
for path in sys.argv[1:]:
    runpy.run_path(path, run_name='collection_probe')
'''
    demos = ['app/agent/test_ollama_speed.py', 'app/brain/test_local_agent.py',
             'app/brain/test_ollama.py', 'app/brain/test_real_agent.py']
    result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
                             *(str(ROOT / path) for path in demos)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == result.stderr == ''
