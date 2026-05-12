# Pre-Change Code Review Audit

**Project:** FarmTracker (track2-fullstack)  
**Date:** 2026-05-12  
**Reviewer:** Mithun Selvananthan  
**Scope:** `app/backend/routes/animals.js`, `app/frontend/app.js`, `app/frontend/animals.html`, `app/frontend/animal-detail.html`

---

## Issues Found

### 1. Paddock `animal_count` Not Decremented on Reassignment (Critical)

**Location:** `routes/animals.js` — `PUT /:id`

When an animal is moved from one paddock to another, the code increments the new paddock's `animal_count` but never decrements the old paddock's count. Over time this causes silent data corruption: old paddocks accumulate phantom animals, their counts drift above reality, and capacity bars on the dashboard become meaningless. Because the bug is silent and affects a cached counter (not a derived count), it is difficult to detect without cross-referencing raw row counts.

---

### 2. Pagination Offset Wrong (High)

**Location:** `routes/animals.js` — `GET /`

The query uses `OFFSET page` instead of `OFFSET page * limit`. On page 0 this is correct by coincidence (`0 * 10 = 0`). On page 1 the offset is 1 instead of 10, so nine animals are skipped. On page 2 the offset is 2 instead of 20. Every page beyond the first returns overlapping or skipped records, making the paginated list unusable for flocks larger than the page size.

---

### 3. `POST /animals` Returns 200 Instead of 201 (Medium)

**Location:** `routes/animals.js` — `POST /`

The response uses `res.json(animal)` which defaults to HTTP 200. REST convention for a successful creation is 201 Created. The `POST /health-events` endpoint already returns 201, making the animal endpoint inconsistent. Any client or test that checks for 201 will incorrectly interpret a successful creation as a failure.

---

### 4. No Capacity Enforcement on Animal Create or Reassign (Medium)

**Location:** `routes/animals.js` — `POST /` and `PUT /:id`

Neither endpoint checks whether `paddock.animal_count >= paddock.capacity` before assigning an animal. A paddock configured for 10 animals can receive unlimited animals. The capacity field stored in the database has no effect at the application layer.

---

### 5. Frontend Throws Generic Error on Non-2xx (Low)

**Location:** `app/frontend/app.js` — `api.post` and `api.put`

The response body is never read before checking `res.ok`. When the backend returns a validation error like `{ "error": "paddock is at capacity" }`, the frontend discards the message and throws a generic `"POST /animals failed: 422"` string. Users see no actionable feedback.

---

### 6. XSS via `innerHTML` with Unsanitised API Data (Medium)

**Location:** `app/frontend/animals.html` and `app/frontend/animal-detail.html`

Animal names, tag numbers, breed, vet names, and event notes are interpolated directly into template literals assigned to `innerHTML`. A malicious value such as `<img src=x onerror=alert(1)>` stored in the database would execute as markup in any visitor's browser. The fix is to use `createElement`/`createTextNode` so values are always treated as text, never as HTML.

---

### 7. N+1 Query in `GET /animals` (Medium)

**Location:** `routes/animals.js` — `GET /`

The list endpoint fires one `SELECT` per animal to retrieve its latest health event. For a flock of 100 animals this is 101 database round trips. The same query can be rewritten as a single `LEFT JOIN` with a correlated subquery. This also provides an opportunity to join the paddock name, replacing raw `paddock_id` values in the UI with human-readable names.

---

## Prioritisation

| Priority | Issue | Reason |
|----------|-------|--------|
| 1 | Animal count not decremented (1) | Silent data corruption, hardest to detect after the fact |
| 2 | Pagination offset wrong (2) | Incorrect data returned to users on every page > 0 |
| 3 | Missing status 201 (3) | Correctness, breaks contract-testing clients |
| 4 | No capacity enforcement (4) | Business rule completely unenforced |
| 5 | XSS via innerHTML (6) | Security: stored XSS possible with any database write access |
| 6 | Generic error messages (5) | UX: fold in alongside the capacity fix so errors surface |
| 7 | N+1 + paddock name (7) | Performance + UX: fix together with paddock-name join |

---

## Architecture Gap Identified

There is no authentication layer. Every endpoint is publicly accessible with no concept of farm ownership. Any user can read or modify any farm's data. This gap is addressed in `ARCH_PROPOSAL.md`.
