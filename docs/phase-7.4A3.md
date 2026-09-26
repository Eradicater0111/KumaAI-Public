# Phase 7.4A3 — Metadata-only desktop/screen association

Scope approved after the store checkpoint `f739f1d`.

`app.desktop.screen_binding.bind_desktop_to_screen()` associates one existing
`ScreenObservation` with two existing `DesktopContextObservation` values.
It does not capture a screen, collect desktop context, invoke either store,
consume a screen observation, or connect to MissionService or execution.

## Why two desktop samples

The existing screen-observation contract supplies a capture timestamp and ID,
but no active-app identity. App ownership cannot be inferred from its analysis
text. A link therefore requires before/after desktop samples that agree on
positive PID and a complete, exact bundle ID. App presentation names, titles,
window stacking, and model analysis are never used as identity.

The trusted caller must supply samples taken in this order: complete a desktop
observation, capture the screen, then complete another desktop observation.
This phase adds no orchestration to perform that sequence. It checks recorded
capture timestamps, not completion timestamps or an atomic capture interval.
A1 desktop timestamps identify sampling starts; timestamp order alone cannot
prove that a caller completed those operations in sequence.

## Contract and policy

The pure binding function accepts an exact `ScreenObservation` and two exact
immutable desktop observations, plus an injectable monotonic `clock`.

A successful result requires:

- A canonical screen ID and finite, nonnegative capture timestamp.
- Two distinct desktop observation IDs and strictly increasing desktop times.
- Available or partial desktop sources with matching PID and nonempty bundle ID.
- `before.capture <= screen.capture <= after.capture <= now`.
- A desktop bracket no wider than the configured capture-gap limit.
- Unexpired evidence, with expiry measured from the oldest (before) timestamp.

Defaults are maximum age 5 seconds and capture gap 1 second. Age may be set
from 0.05 to 60 seconds; capture gap must be positive and no greater than both
5 seconds and the chosen age. Evidence expires at the exact expiry boundary.
Constructed bindings also enforce the hard 60-second/5-second bounds.

The frozen `DesktopScreenBinding` records the three observation IDs, three
capture times, application PID/bundle ID, binding/expiry times, and both desktop
source statuses and diagnostic codes. It carries no screen analysis, window
titles, windows, geometry, image data, image hash, or action coordinates.

The frozen `DesktopScreenBindingResult` has an optional binding, bounded
structured diagnostics, and a `linked` property. Partial source status stays
partial in the link and adds `desktop_context_partial`; it is not promoted to
available evidence. Rejections return no binding and a fixed diagnostic code.
Invalid caller options raise ValueError/TypeError; clock failures expose no raw
exception message.

`binding.is_fresh(now)` checks only the recorded lifetime and rejects times
before binding creation. It neither refreshes the link nor checks the current
desktop. The binder itself is stateless and cannot detect arbitrary clock
rollback between independent invocations; all supplied times must share a
trusted monotonic clock domain.

## Usage

```python
from app.desktop.screen_binding import bind_desktop_to_screen

result = bind_desktop_to_screen(
    existing_screen_observation,
    desktop_observation_before,
    desktop_observation_after,
)
if result.linked:
    metadata_link = result.binding
```

This illustrates use with values already obtained by a trusted caller. It does
not add or authorize collection. No automatically populated singleton, timer,
storage, logging, or native dependency is introduced. The screen metadata
module is imported only for its existing observation type; its global store
is never read, replaced, or claimed by the binder.

## Limits

A link means supplied metadata passed temporal and identity consistency checks.
It is not an attestation of pixels, window inclusion in an image, foreground
continuity, current app identity, screen-store liveness, unclaimed single-use
state, or execution authority. It is not an authenticity check on arbitrary
Python objects. The caller remains responsible for provenance.

No screen geometry is validated or converted here; existing capture and action
contracts retain that responsibility. Bracketing cannot detect every ABA app
switch, PID reuse, change during an individual sample, or change after the
samples. A link can outlive a source store entry if configured differently;
its freshness must never bypass the original store's lifetime/claim checks.
Screen and desktop stores, click attestations, authority, and pre-action
revalidation remain unchanged. There is no live-capture acceptance claim for
this synthetic, metadata-only phase.

## Validation

57 deterministic binding tests cover valid and partial links, immutable
contracts, source diagnostic preservation, identity mismatches/missing identity,
invalid/duplicate references, capture order and gap limits, stale/future evidence,
exact expiry, invalid clocks/options, inert instruction-like analysis, and no
screen-store consumption. An audited fresh interpreter forbids writes,
network/process activity, capture/model/desktop/authority imports, and calls to
screen-store create/peek/claim during binding.

```sh
.venv/bin/python -B -m pytest app/desktop app/vision/test_observation.py -q -p no:cacheprovider
.venv/bin/python -B -m pytest -q -p no:cacheprovider
```
