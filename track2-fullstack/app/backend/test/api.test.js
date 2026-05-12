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

  const northId = db.prepare(
    'INSERT INTO paddocks (name, capacity, animal_count) VALUES (?, ?, 0)'
  ).run('North Paddock', 50).lastInsertRowid;

  const southId = db.prepare(
    'INSERT INTO paddocks (name, capacity, animal_count) VALUES (?, ?, 0)'
  ).run('South Paddock', 30).lastInsertRowid;

  const insertAnimal = db.prepare(
    'INSERT INTO animals (name, tag_number, breed, date_of_birth, paddock_id) VALUES (?, ?, ?, ?, ?)'
  );

  const bellaId = insertAnimal.run('Bella', 'TAG-001', 'Merino', '2021-03-14', northId).lastInsertRowid;
  insertAnimal.run('Daisy', 'TAG-002', 'Dorper', '2020-07-22', southId);

  db.prepare('UPDATE paddocks SET animal_count = animal_count + 1 WHERE id = ?').run(northId);
  db.prepare('UPDATE paddocks SET animal_count = animal_count + 1 WHERE id = ?').run(southId);

  db.prepare(
    'INSERT INTO health_events (animal_id, event_type, notes, date, vet_name) VALUES (?, ?, ?, ?, ?)'
  ).run(bellaId, 'vaccination', 'Routine vaccination', '2024-01-15', 'Dr. Walsh');
}

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

async function del(path) {
  const res = await fetch(baseUrl + path, { method: 'DELETE' });
  return { status: res.status, body: await res.json() };
}

test('GET /api/paddocks returns an array', async () => {
  const { status, body } = await get('/paddocks');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
});

test('GET /api/animals returns animals with latest_health_event field', async () => {
  const { status, body } = await get('/animals?page=0&limit=5');
  assert.equal(status, 200);
  assert.ok(Array.isArray(body));
  assert.ok(body.length > 0);
  assert.ok('latest_health_event' in body[0]);
});

test('GET /api/animals/:id returns a single animal', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status, body } = await get(`/animals/${id}`);
  assert.equal(status, 200);
  assert.equal(body.id, id);
});

test('GET /api/animals/:id returns 404 for unknown id', async () => {
  const { status } = await get('/animals/999999');
  assert.equal(status, 404);
});

test('POST /api/animals/:id/health-events creates an event', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
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

test('POST /api/animals/:id/weights creates a weight record (201)', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
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
  const { body: animals } = await get('/animals?page=0&limit=1');
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

test('POST /api/animals/:id/weights returns 422 when weight_kg is missing', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status } = await post(`/animals/${id}/weights`, { date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is zero', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status } = await post(`/animals/${id}/weights`, { weight_kg: 0, date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is negative', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status } = await post(`/animals/${id}/weights`, { weight_kg: -5, date: '2025-03-01' });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 404 for unknown animal', async () => {
  const { status } = await post('/animals/999999/weights', { weight_kg: 50, date: '2025-03-01' });
  assert.equal(status, 404);
});

test('GET /api/animals/:id/weights returns 404 for unknown animal', async () => {
  const { status } = await get('/animals/999999/weights');
  assert.equal(status, 404);
});

test('POST /api/animals/:id/weights accepts record with no notes', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status, body } = await post(`/animals/${id}/weights`, {
    weight_kg: 38.0,
    date: '2025-04-01',
  });
  assert.equal(status, 201);
  assert.equal(body.notes, null);
});

test('POST /api/animals/:id/weights returns 422 when date is missing', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status } = await post(`/animals/${id}/weights`, { weight_kg: 50 });
  assert.equal(status, 422);
});

test('POST /api/animals/:id/weights returns 422 when weight_kg is NaN', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const id = animals[0].id;
  const { status } = await post(`/animals/${id}/weights`, { weight_kg: NaN, date: '2025-03-01' });
  assert.equal(status, 422);
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

test('DELETE /api/animals/:id decrements paddock animal_count', async () => {
  const { body: paddocks } = await get('/paddocks');
  const paddock = paddocks[0];

  const { body: animal } = await post('/animals', {
    name: 'Delete Me',
    tag_number: 'TAG-DEL-001',
    paddock_id: paddock.id,
  });
  assert.equal(animal.paddock_id, paddock.id);

  const { status } = await del(`/animals/${animal.id}`);
  assert.equal(status, 200);

  const { body: after } = await get(`/paddocks/${paddock.id}`);
  assert.equal(after.animal_count, paddock.animal_count);
});

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

test('POST /api/animals returns 409 for duplicate tag_number', async () => {
  const { body: animals } = await get('/animals?page=0&limit=1');
  const { status, body } = await post('/animals', {
    name: 'Duplicate',
    tag_number: animals[0].tag_number,
  });
  assert.equal(status, 409);
  assert.ok(body.error);
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

  const res = await fetch(baseUrl + `/animals/${animal.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paddock_id: toPaddock.id }),
  });
  assert.equal(res.status, 200);

  const updated = await res.json();
  assert.equal(updated.paddock_id, toPaddock.id);
  assert.equal(updated.paddock_name, toPaddock.name);

  const { body: from } = await get(`/paddocks/${fromPaddock.id}`);
  const { body: to } = await get(`/paddocks/${toPaddock.id}`);
  assert.equal(from.animal_count, fromPaddock.animal_count, 'old paddock count should be restored');
  assert.equal(to.animal_count, toPaddock.animal_count + 1, 'new paddock count should increment');
});

test('PUT /api/animals/:id returns 409 for duplicate tag_number', async () => {
  const { body: animals } = await get('/animals?page=0&limit=2');
  const [a, b] = animals;
  const res = await fetch(baseUrl + `/animals/${a.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tag_number: b.tag_number }),
  });
  assert.equal(res.status, 409);
});
