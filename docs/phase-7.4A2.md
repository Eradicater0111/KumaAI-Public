# Phase 7.4A2 — In-memory desktop observation store

Scope approved after the validated 7.4A1 checkpoint commit `75486c6`.

`app.desktop.store.DesktopContextStore` retains already-collected immutable
observations in process memory. It does not invoke the collector, read desktop
APIs, write files, log titles, contact models, or participate in execution
permissions. There is no global store instance or MissionService integration.

## API

```python
from app.desktop.store import DesktopContextStore

store = DesktopContextStore(capacity=32, ttl_seconds=5.0)
accepted = store.put(observation)  # an existing DesktopContextObservation
current = store.latest()         # observation or None
by_id = store.get(observation.observation_id)
store.clear()
```

A caller may inject a callable `clock` returning monotonic seconds in the same
clock domain as `captured_at_monotonic`. Tests use controlled clocks and do not
sleep for expiration. Default capacity is 32 (allowed 1–256); default lifetime
is 5 seconds (allowed 0.05–60). Booleans are not accepted as numeric options.

Expiry is measured from the observation's capture time, not insertion time.
A record expires at `now - captured_at_monotonic >= ttl_seconds`. Reads never
refresh that deadline or reorder the capacity queue. Cleanup is lazy during
reads and writes; no timer or background thread runs. At most `capacity`
observations remain resident, including expired ones awaiting cleanup.

`put()` requires the exact immutable observation type. It returns False for
expired observations, duplicate resident IDs, or capture times no newer than
the last accepted capture. Equal-time samples are conservatively refused.
Future capture timestamps raise ValueError; wrong input types raise TypeError.
A rejected insertion leaves the most recent valid retained context unchanged,
subject to its original expiry. Capacity overflow evicts the oldest record.
Eviction and expiry preserve the capture-time ordering high-water mark.

Available, partial, and unavailable observations are stored without changing
status or diagnostics. A newer unavailable observation becomes the latest
result; the store never substitutes an earlier available observation. `get()`
can explicitly retrieve an older resident record while it remains unexpired.

A failing, invalid, or backward-moving clock clears retained data and raises a
sanitized ValueError. The last valid clock reading remains a high-water mark;
collection cannot resume against an earlier clock value. `clear()` drops the
records and capture ordering but does not reset that clock high-water mark.

All public operations are serialized by a lock. The injected clock should be
fast and must not re-enter the same store. No native work is performed under
the lock.

## Boundary

A retained observation is historical metadata, not proof that the desktop is
still in that state. TTL is a storage freshness limit, not a validity guarantee
for clicking, typing, app ownership at action time, or execution authority.
There is no screen binding, target attestation, automatic recollection,
pre-action validation, or durable replay protection in this phase. IDs are
checked only while resident; clear/clock invalidation reset capture ordering.
Those future responsibilities remain separate tickets.

## Validation

The store has 28 deterministic tests, including capture-time expiry and its
exact boundary, no lifetime extension on reads, oldest-record eviction,
rejected old/duplicate/future inputs, unavailable-latest behavior, immutable
identity, invalid options, clock rollback/failure, clear, and concurrent writes.
An audited fresh interpreter verifies that imports and store operations neither
write files nor invoke network/process/model/desktop/authority APIs. An
instruction-like title stays inert observation data.

Run:

```sh
.venv/bin/python -B -m pytest app/desktop -q -p no:cacheprovider
.venv/bin/python -B -m pytest -q -p no:cacheprovider
```
