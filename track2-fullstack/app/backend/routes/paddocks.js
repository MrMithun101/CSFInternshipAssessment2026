const express = require('express');
const router = express.Router();
const { db } = require('../db');

// Derive animal_count via COUNT(*) so the value is always accurate by
// definition — no stored counter to drift.
const PADDOCK_WITH_COUNT = `
  SELECT p.id, p.name, p.capacity, COUNT(a.id) AS animal_count
  FROM paddocks p
  LEFT JOIN animals a ON a.paddock_id = p.id
`;

router.get('/', (req, res) => {
  const paddocks = db.prepare(`${PADDOCK_WITH_COUNT} GROUP BY p.id ORDER BY p.id`).all();
  res.json(paddocks);
});

router.post('/', (req, res) => {
  const { name, capacity } = req.body;
  if (!name || capacity == null) {
    return res.status(400).json({ error: 'name and capacity are required' });
  }
  if (typeof capacity !== 'number' || !Number.isInteger(capacity) || capacity < 1) {
    return res.status(422).json({ error: 'capacity must be a positive integer' });
  }
  const result = db.prepare(
    'INSERT INTO paddocks (name, capacity) VALUES (?, ?)'
  ).run(name, capacity);
  const paddock = db.prepare(`${PADDOCK_WITH_COUNT} WHERE p.id = ? GROUP BY p.id`).get(result.lastInsertRowid);
  res.status(201).json(paddock);
});

router.get('/:id', (req, res) => {
  const paddock = db.prepare(`${PADDOCK_WITH_COUNT} WHERE p.id = ? GROUP BY p.id`).get(req.params.id);
  if (!paddock) return res.status(404).json({ error: 'Paddock not found' });
  res.json(paddock);
});

router.put('/:id', (req, res) => {
  const paddock = db.prepare(`${PADDOCK_WITH_COUNT} WHERE p.id = ? GROUP BY p.id`).get(req.params.id);
  if (!paddock) return res.status(404).json({ error: 'Paddock not found' });

  const name     = req.body.name     ?? paddock.name;
  const capacity = 'capacity' in req.body ? req.body.capacity : paddock.capacity;

  if (typeof capacity !== 'number' || !Number.isInteger(capacity) || capacity < 1) {
    return res.status(422).json({ error: 'capacity must be a positive integer' });
  }
  if (capacity < paddock.animal_count) {
    return res.status(422).json({
      error: `capacity cannot be less than current occupancy (${paddock.animal_count} animals)`
    });
  }

  db.prepare('UPDATE paddocks SET name = ?, capacity = ? WHERE id = ?').run(name, capacity, req.params.id);
  const updated = db.prepare(`${PADDOCK_WITH_COUNT} WHERE p.id = ? GROUP BY p.id`).get(req.params.id);
  res.json(updated);
});

module.exports = router;
