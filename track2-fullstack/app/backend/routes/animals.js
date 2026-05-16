const express = require('express');
const router = express.Router();
const { db } = require('../db');

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Fetch a paddock with its live animal count (derived via COUNT(*)).
function getPaddockWithCount(id) {
  return db.prepare(`
    SELECT p.id, p.name, p.capacity, COUNT(a.id) AS animal_count
    FROM paddocks p
    LEFT JOIN animals a ON a.paddock_id = p.id
    WHERE p.id = ?
    GROUP BY p.id
  `).get(id);
}

// Validate that a date string is a real calendar date in YYYY-MM-DD format.
function isValidDate(d) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return false;
  const dt = new Date(d);
  return !isNaN(dt.getTime());
}

// ─── Animal list ──────────────────────────────────────────────────────────────

router.get('/', (req, res) => {
  const page  = Math.max(0, parseInt(req.query.page)  || 0);
  const limit = Math.max(1, parseInt(req.query.limit) || 10);
  const tag   = req.query.tag ? req.query.tag.trim() : null;

  // Single query: animals + paddock name + latest health event + latest two
  // weights (for trend) + at-risk signals. All data in one round-trip.
  const whereClause  = tag ? 'WHERE LOWER(a.tag_number) LIKE LOWER(?)' : '';
  const limitClause  = tag ? '' : 'LIMIT ? OFFSET ?';
  const queryParams  = tag
    ? [`%${tag}%`]
    : [limit, page * limit];

  const rows = db.prepare(`
    SELECT
      a.*,
      p.name AS paddock_name,
      he.id         AS he_id,
      he.event_type AS he_event_type,
      he.notes      AS he_notes,
      he.date       AS he_date,
      he.vet_name   AS he_vet_name,
      lw.weight_kg  AS lw_weight_kg,
      lw.date       AS lw_date,
      pw.weight_kg  AS pw_weight_kg
    FROM animals a
    LEFT JOIN paddocks p ON p.id = a.paddock_id
    LEFT JOIN health_events he ON he.id = (
      SELECT id FROM health_events
      WHERE animal_id = a.id
      ORDER BY date DESC
      LIMIT 1
    )
    LEFT JOIN weights lw ON lw.id = (
      SELECT id FROM weights
      WHERE animal_id = a.id
      ORDER BY date DESC, id DESC
      LIMIT 1
    )
    LEFT JOIN weights pw ON pw.id = (
      SELECT id FROM weights
      WHERE animal_id = a.id
      ORDER BY date DESC, id DESC
      LIMIT 1 OFFSET 1
    )
    ${whereClause}
    ${limitClause}
  `).all(...queryParams);

  const result = rows.map(row => {
    const {
      he_id, he_event_type, he_notes, he_date, he_vet_name,
      lw_weight_kg, lw_date, pw_weight_kg,
      ...animal
    } = row;

    const latest_health_event = he_id
      ? { id: he_id, animal_id: animal.id, event_type: he_event_type, notes: he_notes, date: he_date, vet_name: he_vet_name }
      : null;

    // Weight trend: kg gained (+) or lost (-) since the previous measurement.
    // Rounded to one decimal. null when fewer than two records exist.
    const weight_trend = (lw_weight_kg != null && pw_weight_kg != null)
      ? Math.round((lw_weight_kg - pw_weight_kg) * 10) / 10
      : null;

    const latest_weight = lw_weight_kg != null
      ? { weight_kg: lw_weight_kg, date: lw_date, trend: weight_trend }
      : null;

    // At-risk flag: aggregate early-warning signals that a farmer should act on.
    //   • Losing weight  — a negative weight trend is the earliest detectable
    //                      sign of illness or poor nutrition in livestock.
    //   • Under treatment — the most recent health event was a treatment,
    //                       meaning the animal has an active medical concern.
    const risk_reasons = [];
    if (weight_trend !== null && weight_trend < 0) risk_reasons.push('losing weight');
    if (he_event_type === 'treatment') risk_reasons.push('under treatment');
    const at_risk = risk_reasons.length > 0;

    return { ...animal, latest_health_event, latest_weight, at_risk, risk_reasons };
  });

  res.json(result);
});

// ─── Animal CRUD ──────────────────────────────────────────────────────────────

router.post('/', (req, res) => {
  const { name, tag_number, breed, date_of_birth, paddock_id } = req.body;

  if (!name || !tag_number) {
    return res.status(400).json({ error: 'name and tag_number are required' });
  }

  // Wrap the capacity check + insert in a transaction so that:
  //   (a) a failed insert never leaves any state partially modified, and
  //   (b) two concurrent creates cannot both pass the capacity check before
  //       either is committed (SQLite serialises write transactions).
  db.exec('BEGIN');
  try {
    if (paddock_id) {
      const paddock = getPaddockWithCount(paddock_id);
      if (!paddock) {
        db.exec('ROLLBACK');
        return res.status(400).json({ error: 'Paddock not found' });
      }
      if (paddock.animal_count >= paddock.capacity) {
        db.exec('ROLLBACK');
        return res.status(422).json({ error: 'Paddock is at full capacity' });
      }
    }

    const result = db.prepare(
      'INSERT INTO animals (name, tag_number, breed, date_of_birth, paddock_id) VALUES (?, ?, ?, ?, ?)'
    ).run(name, tag_number, breed ?? null, date_of_birth ?? null, paddock_id ?? null);

    db.exec('COMMIT');
    const animal = db.prepare('SELECT * FROM animals WHERE id = ?').get(result.lastInsertRowid);
    return res.status(201).json(animal);
  } catch (err) {
    db.exec('ROLLBACK');
    if (err.errcode === 2067) {
      return res.status(409).json({ error: 'tag_number already exists' });
    }
    throw err;
  }
});

router.get('/:id', (req, res) => {
  const animal = db.prepare(`
    SELECT a.*, p.name AS paddock_name
    FROM animals a
    LEFT JOIN paddocks p ON p.id = a.paddock_id
    WHERE a.id = ?
  `).get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });
  res.json(animal);
});

router.put('/:id', (req, res) => {
  const animal = db.prepare('SELECT * FROM animals WHERE id = ?').get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });

  const updates = {
    name:          req.body.name          ?? animal.name,
    tag_number:    req.body.tag_number    ?? animal.tag_number,
    breed:         req.body.breed         ?? animal.breed,
    date_of_birth: req.body.date_of_birth ?? animal.date_of_birth,
    paddock_id:    'paddock_id' in req.body ? req.body.paddock_id : animal.paddock_id,
  };

  db.exec('BEGIN');
  try {
    if (updates.paddock_id !== animal.paddock_id && updates.paddock_id) {
      const paddock = getPaddockWithCount(updates.paddock_id);
      if (!paddock) {
        db.exec('ROLLBACK');
        return res.status(400).json({ error: 'Paddock not found' });
      }
      if (paddock.animal_count >= paddock.capacity) {
        db.exec('ROLLBACK');
        return res.status(422).json({ error: 'Paddock is at full capacity' });
      }
    }

    db.prepare(`
      UPDATE animals
      SET name = ?, tag_number = ?, breed = ?, date_of_birth = ?, paddock_id = ?
      WHERE id = ?
    `).run(updates.name, updates.tag_number, updates.breed, updates.date_of_birth, updates.paddock_id, req.params.id);

    db.exec('COMMIT');
  } catch (err) {
    db.exec('ROLLBACK');
    if (err.errcode === 2067) {
      return res.status(409).json({ error: 'tag_number already exists' });
    }
    throw err;
  }

  const updated = db.prepare(`
    SELECT a.*, p.name AS paddock_name
    FROM animals a
    LEFT JOIN paddocks p ON p.id = a.paddock_id
    WHERE a.id = ?
  `).get(req.params.id);
  res.json(updated);
});

router.delete('/:id', (req, res) => {
  const animal = db.prepare('SELECT * FROM animals WHERE id = ?').get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });
  // No paddock counter to update — the derived COUNT(*) adjusts automatically.
  db.prepare('DELETE FROM animals WHERE id = ?').run(req.params.id);
  res.json({ message: 'deleted' });
});

// ─── Health events ────────────────────────────────────────────────────────────

router.get('/:id/health-events', (req, res) => {
  const animal = db.prepare('SELECT id FROM animals WHERE id = ?').get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });

  const events = db.prepare(
    'SELECT * FROM health_events WHERE animal_id = ? ORDER BY date DESC'
  ).all(req.params.id);
  res.json(events);
});

router.post('/:id/health-events', (req, res) => {
  const animal = db.prepare('SELECT id FROM animals WHERE id = ?').get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });

  const { event_type, notes, date, vet_name } = req.body;
  if (!event_type || !date) {
    return res.status(400).json({ error: 'event_type and date are required' });
  }
  if (!isValidDate(date)) {
    return res.status(400).json({ error: 'date must be a valid date in YYYY-MM-DD format' });
  }

  const result = db.prepare(
    'INSERT INTO health_events (animal_id, event_type, notes, date, vet_name) VALUES (?, ?, ?, ?, ?)'
  ).run(req.params.id, event_type, notes ?? null, date, vet_name ?? null);

  const event = db.prepare('SELECT * FROM health_events WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(event);
});

// ─── Weights ──────────────────────────────────────────────────────────────────

router.get('/:id/weights', (req, res) => {
  const animal = db.prepare('SELECT id FROM animals WHERE id = ?').get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });

  const weights = db.prepare(
    'SELECT * FROM weights WHERE animal_id = ? ORDER BY date DESC, id DESC'
  ).all(req.params.id);
  res.json(weights);
});

router.post('/:id/weights', (req, res) => {
  const animal = db.prepare('SELECT id FROM animals WHERE id = ?').get(req.params.id);
  if (!animal) return res.status(404).json({ error: 'Animal not found' });

  const { weight_kg, date, notes } = req.body;
  if (weight_kg == null) return res.status(422).json({ error: 'weight_kg is required' });
  if (typeof weight_kg !== 'number' || !isFinite(weight_kg) || weight_kg <= 0) {
    return res.status(422).json({ error: 'weight_kg must be a positive number' });
  }
  if (!date) return res.status(422).json({ error: 'date is required' });
  if (!isValidDate(date)) {
    return res.status(422).json({ error: 'date must be a valid date in YYYY-MM-DD format' });
  }

  const result = db.prepare(
    'INSERT INTO weights (animal_id, weight_kg, date, notes) VALUES (?, ?, ?, ?)'
  ).run(req.params.id, weight_kg, date, notes ?? null);

  const record = db.prepare('SELECT * FROM weights WHERE id = ?').get(result.lastInsertRowid);
  res.status(201).json(record);
});

module.exports = router;
