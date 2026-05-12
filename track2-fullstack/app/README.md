# FarmTracker

A livestock record management application for tracking animals, paddock assignments, and health events.

## Requirements

- Node.js 22.5+ (uses built-in `node:sqlite`)

## Setup

```bash
cd track2-fullstack/app/backend
npm install
node seed.js
npm start        # production
npm run dev      # watch mode — auto-restarts on file changes
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Running tests

The test suite starts its own isolated server and temporary SQLite database — no seed or running server needed:

```bash
cd track2-fullstack/app/backend
npm test
```

## Project structure

```
track2-fullstack/
├── AUDIT.md               # Pre-change code review — bugs found and prioritised
├── RETRO.md               # Trade-offs and post-implementation retrospective
├── ARCH_PROPOSAL.md       # Concrete proposal for JWT auth + multi-tenancy
└── app/
    ├── README.md          # This file
    ├── backend/
    │   ├── server.js          # Express app entry point
    │   ├── db.js              # Database connection and schema
    │   ├── routes/
    │   │   ├── animals.js     # Animal + health event + weight endpoints
    │   │   └── paddocks.js    # Paddock endpoints
    │   ├── test/
    │   │   └── api.test.js    # Integration tests (18 tests)
    │   ├── seed.js            # Seed script (run once after install)
    │   └── package.json
    └── frontend/
        ├── index.html         # Paddocks overview
        ├── animals.html       # Paginated animal list
        ├── animal-detail.html # Animal detail, health events, weight history
        ├── app.js             # Shared fetch utilities
        └── styles.css
```

## API reference

| Method | Path | Description |
|--------|------|-------------|
| GET | /api/paddocks | List all paddocks |
| POST | /api/paddocks | Create a paddock |
| GET | /api/paddocks/:id | Get a paddock |
| GET | /api/animals | List animals (`page`, `limit` query params) |
| POST | /api/animals | Create an animal |
| GET | /api/animals/:id | Get an animal |
| PUT | /api/animals/:id | Update an animal |
| DELETE | /api/animals/:id | Delete an animal |
| GET | /api/animals/:id/health-events | List health events |
| POST | /api/animals/:id/health-events | Log a health event |
| GET | /api/animals/:id/weights | List weight records (ordered by date DESC) |
| POST | /api/animals/:id/weights | Log a weight record |

### Pagination

`GET /api/animals` accepts `page` (0-indexed, default 0) and `limit` (default 10) query parameters. The offset is calculated as `page * limit`, so page 0 returns rows 0–9, page 1 returns rows 10–19, and so on.

### Weight record shape

```json
{
  "id": 1,
  "animal_id": 3,
  "weight_kg": 44.8,
  "date": "2024-12-01",
  "notes": "Post-shearing weigh-in"
}
```

`notes` is nullable. `weight_kg` must be a positive number. `date` is required (ISO 8601 string, e.g. `"2024-12-01"`).

## Known limitations

- **No authentication.** All endpoints are public. See `ARCH_PROPOSAL.md` for the proposed JWT + farm-scoped multi-tenancy design.
- **`animal_count` is a cached counter.** Concurrent writes have a narrow race window where two requests could both pass the capacity check before either increments the count. Under SQLite's single-writer WAL mode this window is very small, but a `CHECK` constraint or serialised transaction would fully close it. Documented in `RETRO.md`.
- **Weight and health event history is unpaginated.** All records are returned in a single response. For long-lived animals this could grow, but agricultural data accumulates slowly and the current approach keeps the API simple.
- **Hard deletes only.** Deleting an animal permanently removes its record. In a full traceability system, records would be soft-deleted or archived to preserve the animal's history for compliance purposes.
