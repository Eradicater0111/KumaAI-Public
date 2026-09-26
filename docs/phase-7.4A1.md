# Phase 7.4A1 — Read-only Trusted Desktop Context

This implementation adds native desktop metadata observations and a local
diagnostic. It does not connect them to the agent, MissionService, models,
memory, ScreenObservation, click attestations, permissions, or action tools.
The pre-existing uncommitted Phase 7.3D hardening changes are preserved.

## Layers

| Module under `app/desktop` | Responsibility |
| --- | --- |
| `contracts.py` | Frozen application/window/observation records and validation |
| `macos.py` | Lazy AppKit/Quartz metadata reads, native PID ownership filtering |
| `collector.py` | Injected-provider collection, normalization, consistency checks |
| `_worker.py` | Fixed-purpose native worker and private JSON IPC |
| `runtime.py` | Deadline, single-worker limit, bounded output, kill/reap, IPC checks |
| `diagnostic.py` | Explicit local JSON presentation, titles redacted by default |

The optional macOS dependencies are pinned separately in
`requirements-desktop.txt`. They were already installed in this checkout.
On a new environment, install that file alongside the project's dependencies.

## Native scope and evidence

The collector reads the frontmost application, its on-screen windows excluding
desktop elements, and then the frontmost application again. Windows are joined
by native owner PID, never by application name. PID and bundle identity must
agree across the two application reads. If they differ or the second read is
unavailable, all combined context is discarded.

Identified window records are sampled again before the final app read. A
vanished, duplicated, retitled, or moved window is discarded with a diagnostic.
Records lacking a native ID remain explicitly partial and cannot be identity-
revalidated. No synthetic window ID is created.

This scope is not all windows on all Spaces: hidden/minimized/off-screen
windows may be absent. No layer-zero-only assumption hides dialogs. The
adapter scans at most 4096 returned native records and returns at most the
requested window limit (default 32, maximum 64). Truncation is explicit. The
native enumeration itself can allocate its full OS list inside the disposable
worker; these limits bound KUMA processing/output, not that native allocation.

Bounds retain the native coordinate space, named
`quartz_global_screen_space_top_left_main_display`. Its origin is the upper-left
of the main display; negative origins are allowed. These are not vision-image
coordinates, and no conversion to action coordinates is provided.

Quartz stacking order is not proof of keyboard focus. Window focus is `null`
and reported as unavailable. Titles, app names, and bundle identifiers are
optional metadata; they never become instructions. Native IDs identify session
objects, not durable identities or an authorization to act.

## Collection integrity

- `available`: stable native app identity, successful enumeration, and no
  missing requested window evidence or collection diagnostics. With this
  adapter, a successful empty enumeration can be available.
- `partial`: app identity remains coherent, but window metadata, focus,
  permissions, revalidation, or collection completeness is missing.
- `unavailable`: no coherent application context, inconsistent app samples,
  unsupported platform, worker failure, malformed IPC, or timeout.

`enumeration_succeeded` distinguishes a successful empty enumeration from an
enumeration that was unavailable. It refers to the initial native enumeration;
later window-revalidation failures have their own diagnostics. Status describes
evidence collection, never execution authority.

Screen capture access is checked with the non-requesting preflight API.
Without confirmed access, app identity may be retained, but window enumeration
is deliberately withheld. No permission dialog is requested or settings changed.
No Accessibility UI traversal, screenshots, or native input APIs are used.

## Time, process, and privacy limits

The production entry point is `collect_desktop_context()`. Native imports and
reads run in a separate interpreter started with `-I -B` and a fixed script path.
Do not call `assemble_snapshot()` directly for live collection; its injected
provider is intentionally synchronous, and the process wrapper supplies the
hard deadline for native calls.

The default deadline is 3 seconds; callers may select 0.05–10 seconds. Only one
production collection can be active per process; other requests return busy.
Output is capped at 1 MiB, sufficient for 64 maximum-length titles even with
JSON escaping of astral Unicode characters. Bytecode cache writes are disabled
in the worker. A failed, oversized, or timed-out worker is killed
and reaped before return. There are no background futures or late-result queues.
OS process startup/reaping may add scheduling latency; this is not real-time
scheduling or a sandbox for arbitrary/untrusted worker code.

Titles are at most 1024 characters and omitted from normal object repr and
diagnostic output. Full evidence can exist transiently in private subprocess
IPC and in the returned observation. Nothing saves it to memory, files, model
requests, or routine application logs. Errors expose fixed diagnostic codes,
not raw exception messages or native stderr.

## Local diagnostic

From the repository root:

```sh
.venv/bin/python -B -m app.desktop.diagnostic
.venv/bin/python -B -m app.desktop.diagnostic --timeout 5 --max-windows 16
```

Only explicitly add `--include-titles` when window titles should appear in
stdout. Default output still includes local app identity and geometry.
Exit codes: available `0`, partial `2`, unavailable `3`; invalid CLI arguments
use argparse's `2`. Inspect JSON status to distinguish partial from CLI errors.

## Validation and acceptance

Deterministic desktop tests cover immutable contracts, native ownership,
missing permissions, malformed/duplicate/vanished windows, app changes, bounds,
metadata limits, redaction, diagnostic output, timeout termination, process
reaping, invalid IPC, unsupported platforms, and concurrent requests.

```sh
.venv/bin/python -m pytest app/desktop -q
```

The user completed positive live acceptance from a normal local terminal:
VS Code and Finder each produced a matching native owner PID, window ID, and
explicit bounds after switching apps between collections. Both reported
`partial` with `focus_unavailable`, as expected; titles stayed redacted.
The restricted agent environment separately exercised graceful unavailability.

The user also supplied passing results for 669 offline tests (plus 62 subtests),
17 native containment tests, and one live-model test in separate runs. Desktop
coverage comprises 103 tests. See `STATUS.md` and `docs/testing.md` for scope.

Sampling is not an atomic snapshot. Before/after checks cannot detect every
ABA switch, process-ID reuse, or a change after the final sample. Future
DesktopContextStore, screen binding, and pre-action revalidation remain separate
tickets. A1 evidence must not be reused as action authority.

## API references

- [NSWorkspace.frontmostApplication](https://developer.apple.com/documentation/appkit/nsworkspace/frontmostapplication)
- [CGWindowListCopyWindowInfo](https://developer.apple.com/documentation/coregraphics/cgwindowlistcopywindowinfo(_:_:))
- [Window owner PID](https://developer.apple.com/documentation/coregraphics/kcgwindowownerpid)
- [Window bounds](https://developer.apple.com/documentation/coregraphics/kcgwindowbounds)
- [CGPreflightScreenCaptureAccess](https://developer.apple.com/documentation/coregraphics/cgpreflightscreencaptureaccess())

The installed Apple SDK's `CoreGraphics.framework/Headers/CGWindow.h` was also
checked for native ownership, window scope, origin conventions, and the
non-prompting permission-preflight contract.

## Follow-up review in this session

The existing draft was found alongside uncommitted Phase 7.3D hardening at
HEAD `1f08aa4`. This review preserves those changes. It disables worker
bytecode writes, raises the bounded IPC allowance to cover valid Unicode
observations at the maximum window count, and adds regressions for both.
Additional mocked checks cover permission-preflight exceptions, native API
initialization failures, app disappearance, known focus contract values, late
worker results, and malformed native enumeration. An audited fresh interpreter
checks that mocked observation imports/collection perform no writes, network
requests, process launches, or imports of model, memory, GUI-input, or authority
modules. Production collection's sole subprocess is the fixed metadata worker.

The user applied the prepared patches to the original checkout and completed
the live checks described above. The native numeric fix accepts PyObjC integer
and float subclasses at the macOS adapter boundary and converts them to plain
Python values. The portable contract remains strict. Regression coverage uses
both deterministic subclasses and synthetic Foundation NSNumber objects.
