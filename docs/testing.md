# KUMA test modes

## Default: deterministic offline tests

From the repository root:

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Pytest discovers `app` and `tests`. The default run explicitly skips 17 native
macOS containment tests and one real-model test. These skips mean those
integrations were not exercised; they are not evidence that containment or
model integration passed.

The remaining tests run with network connection/DNS guards and guards on
loaded model constructors and desktop-input APIs. Unexpected external calls
fail the test rather than returning a fabricated successful result. These are
test isolation helpers, not a sandbox for arbitrary test code or child
processes. Mocked agent-loop tests explicitly inject empty memory context and
conversation seams. Other tests that use KUMA's conversation database get a
fresh database path under their temporary test directory.

No production containment policy, authority check, permission logic, or desktop
collector behavior changes for the test modes. Native subprocess tests,
including bounded desktop worker tests, remain where their own dependencies
are deterministic. Repair contract/validation rejection tests and mocked
fail-closed cleanup checks stay in the default suite.

## Explicit native containment checks

Run in a normal macOS terminal with the existing required facilities:

```sh
.venv/bin/python -B -m pytest -q -m native_sandbox --run-native-sandbox
```

The option enables the marked tests. If `sandbox-exec`, trusted Python, process
inspection, or the required native behavior is unavailable, the tests fail;
there is no automatic downgrade to a mock or a passing result. No test grants
permissions or changes the production sandbox policy.

These tests intentionally launch candidates inside the production containment
boundary, exercising blocked reads/writes, network/process restrictions,
time/memory/output limits, scratch access, and candidate-test execution. The
normal sandbox and test fixtures remain responsible for those operations.

## Explicit real-model check

With the configured local model already available:

```sh
.venv/bin/python -B -m pytest -q -m live_model --run-live-model
```

This permits model/network use only in tests marked `live_model`. It does not
authorize real desktop input or screenshots. The current live agent test uses
a fixed system-information tool and mocked memory so it exercises the model
and agent integration without inspecting or controlling the user's desktop.
The model is currently `qwen3:8b`; the tests do not install or pull it.

## Manual demos

The four historical files below are demonstrations, not unit tests. Their
runtime imports and actions now live inside `main()`. Importing them during
pytest collection is inert. They run only when explicitly invoked, for example:

```sh
.venv/bin/python -B -m app.agent.test_ollama_speed
.venv/bin/python -B -m app.brain.test_ollama
.venv/bin/python -B -m app.brain.test_real_agent
.venv/bin/python -B -m app.brain.test_local_agent
```

These standalone demos retain their original model/tool behavior and are
outside pytest's isolation fixtures. They are not required for offline
acceptance and were not run during this cleanup.

## Restored coverage

All nine `TestGoalPlan` methods are now collected. Previously three functions
were outside the class and requested an undefined `self` fixture; three more
were nested inside other tests and never collected. Their assertions are
preserved.

Test-policy regressions verify independent opt-ins, accidental network-call
failure, and inert demo imports. Additional deterministic tests exercise
unavailable process-memory evidence, unsupported host denial, native-worker
kill/reap/stream cleanup on inspection failure, and rejection of unavailable
contained execution. They complement, rather than replace, the real native
containment tests.
