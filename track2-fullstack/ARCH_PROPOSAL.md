# Architectural Proposal: JWT-Based Authentication with Farm-Scoped Data

## Problem

Every API endpoint is currently public. Any user can read or modify any farm's paddocks, animals, health events, and weights. Adding multi-tenancy requires (a) identity, (b) ownership, and (c) enforcement on every query.

---

## Schema Changes

```sql
CREATE TABLE farms (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL UNIQUE,
  created_at TEXT    NOT NULL DEFAULT (date('now'))
);

CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  farm_id       INTEGER NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
  email         TEXT    NOT NULL UNIQUE,
  password_hash TEXT    NOT NULL
);

-- Add farm_id to paddocks (animals cascade through paddock_id already)
ALTER TABLE paddocks ADD COLUMN farm_id INTEGER NOT NULL REFERENCES farms(id);
```

`farm_id` on `paddocks` is sufficient: animals reference `paddock_id`, health events and weights reference `animal_id`, so ownership flows through the hierarchy without adding the foreign key to every table.

---

## New Endpoints

### `POST /api/auth/register`

```
Body: { name, email, password }
1. Insert into farms (name)
2. Hash password: bcrypt.hash(password, 12)
3. Insert into users (farm_id, email, password_hash)
4. Return 201 { token: sign({ userId, farmId }, JWT_SECRET, { expiresIn: '7d' }) }
```

### `POST /api/auth/login`

```
Body: { email, password }
1. SELECT user WHERE email = ?
2. bcrypt.compare(password, user.password_hash) — 401 on mismatch
3. Return 200 { token: sign({ userId, farmId }, JWT_SECRET, { expiresIn: '7d' }) }
```

---

## `requireAuth` Middleware

```js
// backend/middleware/auth.js
const jwt = require('jsonwebtoken');

function requireAuth(req, res, next) {
  const header = req.headers.authorization ?? '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: 'Authentication required' });
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  } catch {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
}

module.exports = requireAuth;
```

Wire it in `server.js`:

```js
const requireAuth = require('./middleware/auth');
app.use('/api/paddocks', requireAuth, paddocksRouter);
app.use('/api/animals', requireAuth, animalsRouter);
```

---

## Scoping Existing Queries

Every query that reads or writes paddocks must gain a `farm_id` filter. Examples:

```js
// GET /api/paddocks
db.prepare('SELECT * FROM paddocks WHERE farm_id = ?').all(req.user.farmId);

// POST /api/paddocks
db.prepare('INSERT INTO paddocks (name, capacity, farm_id) VALUES (?, ?, ?)').run(name, capacity, req.user.farmId);

// GET /api/animals  (join path: animals → paddocks → farm_id)
`... FROM animals a
 LEFT JOIN paddocks p ON p.id = a.paddock_id AND p.farm_id = ?`
// bind req.user.farmId as the first parameter
```

Animals, health events, and weights have no direct `farm_id` column. Ownership is verified by confirming the paddock (or parent animal's paddock) belongs to `req.user.farmId` before any mutation. For `GET /api/animals/:id`, join through paddocks and add `WHERE p.farm_id = ?`.

---

## Frontend Changes

1. **`login.html`** — form that POSTs to `/api/auth/login`, stores the returned JWT in `localStorage`.
2. **`app.js`** — add `Authorization: Bearer <token>` header to every `api.get`, `api.post`, `api.put`, `api.delete` call.
3. **401 redirect** — in the `api` helper, if the response is 401, clear `localStorage` and `window.location.href = '/login.html'`.

---

## Dependencies

```json
"bcrypt": "^5.1.0",
"jsonwebtoken": "^9.0.0"
```

`JWT_SECRET` must be set as an environment variable (minimum 32 random bytes). Never hard-code it.

---

## Migration Strategy

Use a `REQUIRE_AUTH` feature flag so existing single-farm deployments are not broken immediately:

```js
// server.js
if (process.env.REQUIRE_AUTH === 'true') {
  app.use('/api/paddocks', requireAuth, paddocksRouter);
  app.use('/api/animals', requireAuth, animalsRouter);
} else {
  app.use('/api/paddocks', paddocksRouter);
  app.use('/api/animals', animalsRouter);
}
```

Migration steps:
1. Deploy with `REQUIRE_AUTH=false` (default).
2. Run `node scripts/migrate-add-auth.js` — creates `farms` and `users` tables, backfills a single default farm, sets `farm_id` on all existing paddocks.
3. Create a user account via `POST /api/auth/register`.
4. Smoke-test the protected routes with the new token.
5. Set `REQUIRE_AUTH=true` and restart.

This lets any deployment opt in at its own pace without a hard cutover.
