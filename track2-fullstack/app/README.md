# FarmTracker

A livestock record management application for tracking animals, paddock assignments, and health events.

## Requirements

- Node.js 22.5+ (uses built-in `node:sqlite`)

## Setup

```bash
cd backend
npm install
node seed.js
npm start
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Running tests

The test suite starts its own server and temporary SQLite database:

```bash
cd backend
npm test
```

## Project structure

```
app/
├── backend/
│   ├── server.js          # Express app entry point
│   ├── db.js              # Database connection and schema
│   ├── routes/
│   │   ├── animals.js     # Animal endpoints
│   │   └── paddocks.js    # Paddock endpoints
│   ├── test/
│   │   └── api.test.js    # Integration tests
│   ├── seed.js            # Seed script (run once after install)
│   └── package.json
└── frontend/
    ├── index.html         # Paddocks overview
    ├── animals.html       # Animal list
    ├── animal-detail.html # Animal detail and health events
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
