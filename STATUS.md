# KUMA development checkpoint

Updated: 2026-09-05

## Validated checkpoint

Phase 7.4A1 adds an isolated, read-only desktop observation contract, injectable
collector, macOS provider, bounded worker, and explicitly invoked diagnostic.
Native number wrappers are normalized only at the macOS boundary. The layer
has no connection to MissionService or execution authority.

This checkpoint also includes the previously uncommitted Phase 7.3D verifier
result-contract hardening and the offline-test cleanup. Semantic target
verification is bound to the human goal, observation, image digest, and exact
integer coordinates before its evidence can support click authority.

## Validation

The user ran all three test groups from the normal local KUMA terminal and
provided their results on 2026-09-05:

- Offline suite: 669 passed, 18 intentional integration skips, 62 subtests passed.
- Native macOS containment: 17 passed, 670 deselected.
- Live-model integration: 1 passed, 686 deselected.

These are 687 passing tests across three separate runs, not one combined run.
The Google SDK emits one existing Python deprecation warning. The agent's
isolated validation copy also passed the offline suite and 244 focused desktop
and GUI tests; native containment remained unavailable inside that restricted
execution environment, so the positive native result comes from the user's run.

Live read-only diagnostics supplied by the user verified VS Code and Finder,
with each native window owner PID matching the corresponding active app PID,
fresh observation IDs, and explicit bounds. Unknown focus was reported as
`partial` with `focus_unavailable`; titles remained redacted. App changes during
a collection are covered by mocked tests; the live check switched apps between
collections. This is not an atomic snapshot or execution authorization.

## Test commands

```sh
.venv/bin/python -B -m pytest -q -p no:cacheprovider
.venv/bin/python -B -m pytest -q -m native_sandbox --run-native-sandbox
.venv/bin/python -B -m pytest -q -m live_model --run-live-model
```

See `docs/testing.md` for explicit opt-ins and `docs/phase-7.4A1.md` for the
observation boundary, limits, and diagnostic. Live tests and demos are not
required for routine offline runs.

## Current work after checkpoint 75486c6

The user approved Phase 7.4A2: a bounded, in-memory DesktopContextStore with
capture-time expiry and an injectable clock. It is now implemented in
`app/desktop/store.py`, with 28 tests and scope documented in
`docs/phase-7.4A2.md`. It neither invokes collection nor grants execution
authority. A newer unavailable observation does not fall back to older available
data. There are no timers, persistence, or native API calls.

Validation after adding the store, confirmed by both agent and user runs:

- Desktop tests: 131 passed (103 existing + 28 store tests).
- Full offline suite: 697 passed, 18 intentional integration skips,
  62 subtests passed; one existing Google SDK warning.
- Compilation and whitespace checks passed.

The native and live-model integrations were not rerun for this isolated store
change; the previous user-confirmed results remain recorded above. Phase 7.4A2
is the validated store checkpoint. Screen binding and pre-action revalidation
remain separate future tickets.

## Current work after checkpoint f739f1d

The user approved Phase 7.4A3 as a metadata-only link between an existing screen
observation and desktop context. It is implemented in
`app/desktop/screen_binding.py`, documented in `docs/phase-7.4A3.md`, and covered
by 57 synthetic tests. Two distinct desktop samples must bracket the screen's
capture timestamp, agree on PID and bundle ID, and satisfy bounded age/gap
limits. Partial source status and diagnostics remain explicit.

The link contains IDs, timestamps, and application identity only, plus source
integrity metadata. It does not capture screens, call collectors or stores,
consume screen claims, inspect pixels/analysis, or authorize execution. Existing
production modules remain unchanged. Caller provenance and actual sequential
sampling are required; recorded timestamp order cannot prove an atomic capture.

Validation confirmed by the agent and the user’s local terminal:

- Desktop plus existing screen-observation tests: 199 passed, 11 subtests.
- Existing GUI regressions: 141 passed, 9 subtests.
- Full offline suite: 754 passed, 18 intentional skips, 62 subtests.
- Compilation and whitespace checks passed; one existing Google SDK warning.

No live capture or native/model integration was run for this metadata-only
phase. Phase 7.4A3 is the validated metadata-binding checkpoint. Read-only
capture orchestration is the next approved phase; geometry/pixel validation,
store-claim enforcement, and pre-action revalidation remain separate work.
