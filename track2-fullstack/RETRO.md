# Retrospective

## Trade-offs Made

**`animal_count` as a cached counter vs. a derived count.**
Keeping `animal_count` on the `paddocks` row makes the paddock list fast — one query, no joins, no subquery aggregation. The trade-off is that every mutation path (create, reassign, delete) must remember to update the counter. The bug found in this audit (missing decrement on reassignment) is a direct consequence of that maintenance burden. A derived count via `SELECT COUNT(*) FROM animals WHERE paddock_id = ?` would always be accurate but adds per-row overhead to every paddocks list render. At current scale the derived approach would be fine; the cached counter only pays off at thousands of paddocks.

In a production traceability context, a periodic reconciliation job would be a sensible safeguard against any future drift:
```sql
UPDATE paddocks SET animal_count = (
  SELECT COUNT(*) FROM animals WHERE paddock_id = paddocks.id
);
```

**Capacity enforcement at the application layer.**
The check `if paddock.animal_count >= paddock.capacity` is correct under serialised SQLite writes (WAL mode processes one writer at a time). Under concurrent HTTP requests, two requests could both read the same `animal_count`, both pass the check, and both increment — leaving the paddock one over capacity. SQLite's serialisation makes this a narrow race window, but it is not zero. The correct fix is a CHECK constraint on the table or a serialised transaction with a re-read inside. Left as a known limitation given the single-process deployment target.

**No pagination on weight history.**
Weight endpoints return all records for an animal. For a long-lived flock this could grow large, but farming data accumulates slowly and the table is append-only. Adding `LIMIT`/`OFFSET` to the weight endpoints is straightforward if needed.

## What I Would Do Differently

- **Implement auth from the start.** Adding `farm_id` to an existing schema requires a migration; baking it in from day one is cheaper. The proposal in `ARCH_PROPOSAL.md` requires a backfill step that would not be needed if the schema had included `farm_id` originally.
- **Write regression tests for bug fixes at the same time as the fix.** Capacity enforcement and paddock-count drift are the highest-risk mutation paths — tests for those should have been committed alongside the fix, not as a separate pass.

## What I Left Alone

**Plain HTML/JS frontend — no framework added.** The task explicitly forbids React, TypeScript, and a build step, and at this scale no framework is needed. The DOM-rendering rewrite removed the XSS risk without adding any dependency. Introducing a bundler would make reviewer setup harder with no benefit to correctness.

**`server.js` and `routes/paddocks.js` — untouched.** Neither file contained bugs relevant to the assessment, and the brief asked to avoid modifying them unless necessary.
