const { after, before, test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'farmtracker-test-'));
process.env.FARMTRACKER_DB_PATH = path.join(tempDir, 'farmtracker.db');

const app = require('../server');
const { db } = require('../db');

let server;
let baseUrl;

before(async () => {
  seedTestData();
  server = await new Promise(resolve => {
    const instance = app.listen(0, '127.0.0.1', () => resolve(instance));
  });
  baseUrl = `http://127.0.0.1:${server.address().port}/api`;
});

after(async () => {
  if (server) {
    await new Promise(resolve => server.close(resolve));
  }
  db.close();
  fs.rmSync(tempDir, { recursive: true, force: true });
});

function seedTestData() {
  db.exec('DELETE FROM weights; DELETE FROM health_events; DELETE FROM animals; DELETE FROM paddocks;');

  // No animal_count column — occupancy is always derived via COUNT(*).
  const northId = db.prepare(
    'INSERT INTO paddocks (name, capacity) VALUES (?, ?)'
  ).run('North Paddock', 50).lastInsertRowid;

  const southId = db.prepare(
    'INSERT INTO paddocks (name, capacity) VALUES (?, ?)'
  ).run('South Paddock', 30).lastInsertRowid;

  const insertAnimal = db.prepare(
    'INSERT INTO animals (name, tag_number, breed, date_of_birth, paddock_id) VALUES (?, ?, ?, ?, ?)'
  );

  const bellaId = insertAnimal.run('Bella', 'TAG-001', 'Merino', '2021-03-14', northId).lastInsertRowid;
  const daisyId = insertAnimal.run('Daisy', 'TAG-002', 'Dorper', '2020-07-22', southId).lastInsertRowid;

  // Two weight records for Bella so trend can be computed (44.8 - 40.0 = +4.8).
  db.prepare('INSERT INTO weights (animal_id, weight_kg, date) VALUES (?, ?, ?)').run(bellaId, 40.0, '2024-10-01');
  db.prepare('INSERT INTO weights (animal_id, weight_kg, date) VALUES (?, ?, ?)').run(bellaId, 44.8, '2024-12-01');

  db.prepare(
    'INSERT INTO health_events (animal_id, event_type, notes, date, vet_name) VALUES (?, ?, ?, ?, ?)'
  ).run(bellaId, 'vaccination', 'Routine vaccination', '2024-01-15', 'Dr. Walsh');
}

// ─── Helpers ────────────────────────────────────────────────────────────────

async function get(path) {
  const res = await fetch(baseUrl + path);
  return { status: res.status, body: await res.json() };
}

async function post(path, body) {
  const res = await fetch(baseUrl + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return { status: res.status, body: await res.json() };
}

async function put(path, body) {
  const res = await fetch(baseUrl + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return { status: res.status, body: await res.json() };
}

async function del(path) {
  const res = await fetch(baseUrl + path, { method: 'DELETE' });
  return { status: res.status, body: await res.json() };
}

// Unwraps the pagination envelope for GET /api/animals?page=... requests.
// Tag-search requests (GET /api/animals?tag=...) still return a bare array and
// should continue to use get() directly.
async function animalsPage(path) {
  const { status, body } = await get(path);
  return { status, body: body.animals, meta: body };
}

// ─── Paddocks ────────────────────────────────────────────────────────────────

test('GET /api/paddocks returns an array', async () => {
  const { status, body } = await get('/paddocks');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
});

test('GET /api/paddocks includes derived animal_count', async () => {
  const { body } = await get('/paddocks');
  assert.ok('animal_count' in body[0]);
  assert.equal(typeof body[0].animal_count, 'number');
});

test('GET /api/paddocks/:id returns a single paddock', async () => {
  const { body: paddocks } = await get('/paddocks');
  const id = paddocks[0].id;
  const { status, body } = await get(`/paddocks/${id}`);
  assert.equal(status, 200);
  assert.equal(body.id, id);
  assert.ok('animal_count' in body);
});

test('GET /api/paddocks/:id returns 404 for unknown paddock', async () => {
  const { status } = await get('/paddocks/999999');
  assert.equal(status, 404);
});

test('POST /api/paddocks creates paddock and returns 201', async () => {
  const { status, body } = await post('/paddocks', { name: 'Test Paddock 201', capacity: 20 });
  assert.equal(status, 201);
  assert.equal(body.name, 'Test Paddock 201');
  assert.equal(body.capacity, 20);
  assert.equal(body.animal_count, 0);
});

test('POST /api/paddocks returns 422 for negative capacity', async () => {
  const { status, body } = await post('/paddocks', { name: 'Bad Pen', capacity: -1 });
  assert.equal(status, 422);
  assert.ok(body.error);
});

test('POST /api/paddocks returns 422 for zero capacity', async () => {
  const { status, body } = await post('/paddocks', { name: 'Zero Pen', capacity: 0 });
  assert.equal(status, 422);
  assert.ok(body.error);
});

// ─── Animals list — pagination envelope ──────────────────────────────────────

test('GET /api/animals returns pagination envelope', async () => {
  const { status, body } = await get('/animals?page=0&limit=5');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body.animals));
  assert.equal(typeof body.total, 'number');
  assert.equal(typeof body.totalPages, 'number');
  assert.equal(body.page, 0);
  assert.equal(body.limit, 5);
});

test('GET /api/animals totalPages is at least 1', async () => {
  const { body } = await get('/animals?page=0&limit=5');
  assert.ok(body.totalPages >= 1);
});

test('GET /api/animals returns animals with latest_health_event field', async () => {
  const { status, body } = await animalsPage('/animals?page=0&limit=5');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
  assert.ok(body.length > 0);
  assert.ok('latest_health_event' in body[0]);
});

test('GET /api/animals returns animals with latest_weight field', async () => {
  const { status, body } = await animalsPage('/animals?page=0&limit=5');
  assert.equal(status, 200);
  assert.ok('latest_weight' in body[0]);
});

test('GET /api/animals latest_weight includes trend when two weights exist', async () => {
  const { body } = await animalsPage('/animals?page=0&limit=10');
  const bella = body.find(a => a.tag_number === 'TAG-001');
  assert.ok(bella, 'Bella not found in animal list');
  assert.ok(bella.latest_weight !== null, 'Bella should have a latest_weight');
  assert.equal(bella.latest_weight.weight_kg, 44.8);
  assert.equal(bella.latest_weight.trend, 4.8); // 44.8 - 40.0
});

test('GET /api/animals latest_weight trend is null when only one weight exists', async () => {
  // Add a single weight for Daisy and confirm trend is null.
  const { body: animals } = await animalsPage('/animals?page=0&limit=10');
  const daisy = animals.find(a => a.tag_number === 'TAG-002');
  await post(`/animals/${daisy.id}/weights`, { weight_kg: 50.0, date: '2025-01-01' });

  const { body: refreshed } = await animalsPage('/animals?page=0&limit=10');
  const daisyRefreshed = refreshed.find(a => a.tag_number === 'TAG-002');
  assert.equal(daisyRefreshed.latest_weight.weight_kg, 50.0);
  assert.equal(daisyRefreshed.latest_weight.trend, null);
});

test('GET /api/animals latest_weight is null when no weights logged', async () => {
  // Fresh animal with no weights.
  const { body: animal } = await post('/animals', { name: 'NoWeight', tag_number: 'TAG-NW-001' });
  const { body: list } = await animalsPage('/animals?page=0&limit=100');
  const found = list.find(a => a.id === animal.id);
  assert.ok(found);
  assert.equal(found.latest_weight, null);
});

// ─── Animal CRUD ─────────────────────────────────────────────────────────────

test('GET /api/animals/:id returns a single animal', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status, body } = await get(`/animals/${id}`);
  assert.equal(status, 200);
  assert.equal(body.id, id);
});

test('GET /api/animals/:id returns 404 for unknown id', async () => {
  const { status } = await get('/animals/999999');
  assert.equal(status, 404);
});

test('POST /api/animals creates animal and returns 201', async () => {
  const { status, body } = await post('/animals', {
    name: 'Test Sheep',
    tag_number: 'TAG-999',
    breed: 'Merino',
  });
  assert.equal(status, 201);
  assert.equal(body.name, 'Test Sheep');
  assert.ok(body.id);
});

test('POST /api/animals returns 409 for duplicate tag_number', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status, body } = await post('/animals', {
    name: 'Duplicate',
    tag_number: animals[0].tag_number,
  });
  assert.equal(status, 409);
  assert.ok(body.error);
});

test('PUT /api/animals/:id returns 404 for unknown animal', async () => {
  const { status } = await put('/animals/999999', { name: 'Ghost' });
  assert.equal(status, 404);
});

test('PUT /api/animals/:id returns 409 for duplicate tag_number', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=2');
  const [a, b] = animals;
  const { status } = await put(`/animals/${a.id}`, { tag_number: b.tag_number });
  assert.equal(status, 409);
});

test('DELETE /api/animals/:id removes the animal', async () => {
  const { body: animal } = await post('/animals', { name: 'Delete Me', tag_number: 'TAG-DEL-X01' });
  const { status } = await del(`/animals/${animal.id}`);
  assert.equal(status, 200);
  const { status: s2 } = await get(`/animals/${animal.id}`);
  assert.equal(s2, 404);
});

test('DELETE /api/animals/:id returns 404 for unknown animal', async () => {
  const { status } = await del('/animals/999999');
  assert.equal(status, 404);
});

// ─── Paddock capacity & count ─────────────────────────────────────────────────

test('POST /api/animals returns 422 when paddock is at capacity', async () => {
  const { body: paddock } = await post('/paddocks', { name: 'Tiny Pen', capacity: 1 });
  await post('/animals', { name: 'First', tag_number: 'TAG-CAP-001', paddock_id: paddock.id });
  const { status, body } = await post('/animals', {
    name: 'Second',
    tag_number: 'TAG-CAP-002',
    paddock_id: paddock.id,
  });
  assert.equal(status, 422);
  assert.ok(body.error);
});

test('GET /api/paddocks animal_count is accurate after animal creation', async () => {
  const { body: paddocks } = await get('/paddocks');
  const paddock = paddocks[0];
  const countBefore = paddock.animal_count;
  await post('/animals', { name: 'Counter Test', tag_number: 'TAG-CNT-001', paddock_id: paddock.id });
  const { body: updated } = await get(`/paddocks/${paddock.id}`);
  assert.equal(updated.animal_count, countBefore + 1);
});

test('DELETE /api/animals/:id paddock animal_count decrements automatically', async () => {
  const { body: paddocks } = await get('/paddocks');
  const paddock = paddocks[0];
  const { body: animal } = await post('/animals', {
    name: 'Delete Me',
    tag_number: 'TAG-DEL-001',
    paddock_id: paddock.id,
  });
  const { body: before } = await get(`/paddocks/${paddock.id}`);
  await del(`/animals/${animal.id}`);
  const { body: after } = await get(`/paddocks/${paddock.id}`);
  assert.equal(after.animal_count, before.animal_count - 1);
});

test('PUT /api/animals/:id reassigning paddock updates both animal_counts', async () => {
  const { body: paddocks } = await get('/paddocks');
  const fromPaddock = paddocks[0];
  const toPaddock = paddocks[1];

  const { body: animal } = await post('/animals', {
    name: 'Reassign Me',
    tag_number: 'TAG-MOVE-001',
    paddock_id: fromPaddock.id,
  });

  const { body: from0 } = await get(`/paddocks/${fromPaddock.id}`);
  const { body: to0 } = await get(`/paddocks/${toPaddock.id}`);

  const { status } = await put(`/animals/${animal.id}`, { paddock_id: toPaddock.id });
  assert.equal(status, 200);

  const { body: from1 } = await get(`/paddocks/${fromPaddock.id}`);
  const { body: to1 } = await get(`/paddocks/${toPaddock.id}`);

  assert.equal(from1.animal_count, from0.animal_count - 1, 'source paddock should decrease');
  assert.equal(to1.animal_count, to0.animal_count + 1, 'destination paddock should increase');
});

// ─── Health events ────────────────────────────────────────────────────────────

test('POST /api/animals/:id/health-events creates an event', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status, body } = await post(`/animals/${id}/health-events`, {
    event_type: 'checkup',
    date: '2025-01-10',
    vet_name: 'Dr. Test',
  });
  assert.equal(status, 201);
  assert.equal(body.event_type, 'checkup');
  assert.equal(body.animal_id, id);
});

test('POST /api/animals/:id/health-events returns 400 when event_type is missing', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/health-events`, { date: '2025-01-01' });
  assert.equal(status, 400);
});

test('POST /api/animals/:id/health-events returns 400 when date is missing', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/health-events`, { event_type: 'checkup' });
  assert.equal(status, 400);
});

test('POST /api/animals/:id/health-events returns 404 for unknown animal', async () => {
  const { status } = await post('/animals/999999/health-events', {
    event_type: 'checkup',
    date: '2025-01-01',
  });
  assert.equal(status, 404);
});

// ─── Weights ──────────────────────────────────────────────────────────────────

test('POST /api/animals/:id/weights creates a weight record (201)', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status, body } = await post(`/animals/${id}/weights`, {
    weight_kg: 45.5,
    date: '2025-03-01',
    notes: 'Spring weigh-in',
  });
  assert.equal(status, 201);
  assert.equal(body.animal_id, id);
  assert.equal(body.weight_kg, 45.5);
  assert.equal(body.date, '2025-03-01');
  assert.equal(body.notes, 'Spring weigh-in');
});

test('GET /api/animals/:id/weights returns weights ordered by date descending', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const id = animals[0].id;
  await post(`/animals/${id}/weights`, { weight_kg: 40.0, date: '2025-01-01' });
  await post(`/animals/${id}/weights`, { weight_kg: 42.0, date: '2025-03-01' });
  await post(`/animals/${id}/weights`, { weight_kg: 41.0, date: '2025-02-01' });
  const { status, body } = await get(`/animals/${id}/weights`);
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
  assert.ok(body.length >= 3);
  for (let i = 1; i < body.length; i++) {
    assert.ok(body[i - 1].date >= body[i].date, 'weights not in descending date order');
  }
});

test('GET /api/animals/:id/weights returns empty array for animal with no weights', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=2');
  // Daisy (TAG-002) has only one weight from the latest_weight trend test — still fine to check for array
  const { status, body } = await get(`/animals/${animals[1].id}/weights`);
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is missing', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, { date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is zero', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, { weight_kg: 0, date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is negative', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, { weight_kg: -5, date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is NaN', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, { weight_kg: NaN, date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is a string', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, { weight_kg: '45', date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when date is missing', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, { weight_kg: 50 });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights accepts record with no notes', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status, body } = await post(`/animals/${animals[0].id}/weights`, {
    weight_kg: 38.0,
    date: '2025-04-01',
  });
  assert.equal(status, 201);
  assert.equal(body.notes, null);
});

test('POST /api/animals/:id/weights returns 404 for unknown animal', async () => {
  const { status } = await post('/animals/999999/weights', { weight_kg: 50, date: '2025-03-01' });
  assert.equal(status, 404);
});

test('GET /api/animals/:id/weights returns 404 for unknown animal', async () => {
  const { status } = await get('/animals/999999/weights');
  assert.equal(status, 404);
});

// ─── Tag search ───────────────────────────────────────────────────────────────

test('GET /api/animals?tag= returns matching animals', async () => {
  const { status, body } = await get('/animals?tag=TAG-001');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
  assert.ok(body.length > 0);
  assert.ok(body.every(a => a.tag_number.toLowerCase().includes('tag-001')));
});

test('GET /api/animals?tag= returns empty array for no match', async () => {
  const { status, body } = await get('/animals?tag=DOES-NOT-EXIST-XYZ');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
  assert.equal(body.length, 0);
});

test('GET /api/animals?tag= result includes latest_weight and at_risk fields', async () => {
  const { body } = await get('/animals?tag=TAG-001');
  assert.ok(body.length > 0);
  assert.ok('latest_weight' in body[0]);
  assert.ok('at_risk' in body[0]);
  assert.ok('risk_reasons' in body[0]);
});

// ─── At-risk flag ─────────────────────────────────────────────────────────────

test('GET /api/animals returns at_risk field', async () => {
  const { body } = await animalsPage('/animals?page=0&limit=10');
  assert.ok(body.length > 0);
  assert.ok('at_risk' in body[0]);
  assert.ok('risk_reasons' in body[0]);
});

test('GET /api/animals at_risk is true when weight trend is negative', async () => {
  // Create a fresh animal and log two weights where second < first.
  const { body: animal } = await post('/animals', { name: 'Shrinking', tag_number: 'TAG-RISK-001' });
  await post(`/animals/${animal.id}/weights`, { weight_kg: 50.0, date: '2025-01-01' });
  await post(`/animals/${animal.id}/weights`, { weight_kg: 47.0, date: '2025-02-01' });

  const { body: list } = await animalsPage('/animals?page=0&limit=100');
  const found = list.find(a => a.id === animal.id);
  assert.ok(found);
  assert.equal(found.at_risk, true);
  assert.ok(found.risk_reasons.includes('losing weight'));
});

test('GET /api/animals at_risk is false when weight trend is positive', async () => {
  const { body: animal } = await post('/animals', { name: 'Growing', tag_number: 'TAG-RISK-002' });
  await post(`/animals/${animal.id}/weights`, { weight_kg: 45.0, date: '2025-01-01' });
  await post(`/animals/${animal.id}/weights`, { weight_kg: 48.0, date: '2025-02-01' });

  const { body: list } = await animalsPage('/animals?page=0&limit=100');
  const found = list.find(a => a.id === animal.id);
  assert.ok(found);
  assert.equal(found.at_risk, false);
});

// ─── Paddock PUT ──────────────────────────────────────────────────────────────

test('PUT /api/paddocks/:id updates name and capacity', async () => {
  const { body: paddock } = await post('/paddocks', { name: 'Old Name', capacity: 10 });
  const { status, body } = await put(`/paddocks/${paddock.id}`, { name: 'New Name', capacity: 20 });
  assert.equal(status, 200);
  assert.equal(body.name, 'New Name');
  assert.equal(body.capacity, 20);
});

test('PUT /api/paddocks/:id returns 404 for unknown paddock', async () => {
  const { status } = await put('/paddocks/999999', { name: 'Ghost' });
  assert.equal(status, 404);
});

test('PUT /api/paddocks/:id returns 422 when capacity is below current occupancy', async () => {
  const { body: paddock } = await post('/paddocks', { name: 'Full Pen', capacity: 5 });
  await post('/animals', { name: 'A1', tag_number: 'TAG-CAP-OCC-1', paddock_id: paddock.id });
  await post('/animals', { name: 'A2', tag_number: 'TAG-CAP-OCC-2', paddock_id: paddock.id });
  const { status, body } = await put(`/paddocks/${paddock.id}`, { capacity: 1 });
  assert.equal(status, 422);
  assert.ok(body.error);
});

test('PUT /api/paddocks/:id returns 422 for invalid capacity', async () => {
  const { body: paddock } = await post('/paddocks', { name: 'Resize Test', capacity: 10 });
  const { status } = await put(`/paddocks/${paddock.id}`, { capacity: -5 });
  assert.equal(status, 422);
});

// ─── Date validation ──────────────────────────────────────────────────────────

test('POST /api/animals/:id/weights returns 422 for invalid date format', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/weights`, {
    weight_kg: 45,
    date: 'not-a-date',
  });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/health-events returns 400 for invalid date format', async () => {
  const { body: animals } = await animalsPage('/animals?page=0&limit=1');
  const { status } = await post(`/animals/${animals[0].id}/health-events`, {
    event_type: 'checkup',
    date: '16/05/2026',
  });
  assert.equal(status, 400);
});
