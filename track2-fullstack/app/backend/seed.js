const { db, initDb } = require('./db');

initDb();

db.exec('DELETE FROM weights; DELETE FROM health_events; DELETE FROM animals; DELETE FROM paddocks;');

const insertPaddock = db.prepare('INSERT INTO paddocks (name, capacity) VALUES (?, ?)');
const northId = insertPaddock.run('North Paddock', 50).lastInsertRowid;
const southId = insertPaddock.run('South Paddock', 30).lastInsertRowid;
const eastId  = insertPaddock.run('East Paddock',  40).lastInsertRowid;
insertPaddock.run('Holding Pen', 10);

const insertAnimal = db.prepare(
  'INSERT INTO animals (name, tag_number, breed, date_of_birth, paddock_id) VALUES (?, ?, ?, ?, ?)'
);

const animalsData = [
  ['Bella', 'TAG-001', 'Merino',  '2021-03-14', northId],
  ['Daisy', 'TAG-002', 'Dorper',  '2020-07-22', northId],
  ['Molly', 'TAG-003', 'Merino',  '2022-01-05', southId],
  ['Rosie', 'TAG-004', 'Suffolk', '2021-09-18', southId],
  ['Lucy',  'TAG-005', 'Merino',  '2020-11-30', eastId],
  ['Penny', 'TAG-006', 'Dorper',  '2022-04-12', eastId],
  ['Nora',  'TAG-007', 'Suffolk', '2021-06-08', northId],
  ['Hazel', 'TAG-008', 'Merino',  '2020-02-27', southId],
  ['Ivy',   'TAG-009', 'Dorper',  '2022-08-15', eastId],
  ['June',  'TAG-010', 'Merino',  '2021-12-03', northId],
  ['Fern',  'TAG-011', 'Suffolk', '2020-05-19', southId],
  ['Gwen',  'TAG-012', 'Merino',  '2022-02-07', eastId],
];

// No animal_count column to maintain — occupancy is derived via COUNT(*).
const animalIds = animalsData.map(([name, tag, breed, dob, paddockId]) =>
  insertAnimal.run(name, tag, breed, dob, paddockId).lastInsertRowid
);

const insertEvent = db.prepare(
  'INSERT INTO health_events (animal_id, event_type, notes, date, vet_name) VALUES (?, ?, ?, ?, ?)'
);

const types = ['vaccination', 'checkup', 'treatment'];
const vets  = ['Dr. McGregor', 'Dr. Walsh'];

animalIds.slice(0, 6).forEach((animalId, i) => {
  insertEvent.run(
    animalId,
    types[i % 3],
    `Routine ${types[i % 3]}`,
    `2024-${String((i % 9) + 1).padStart(2, '0')}-15`,
    vets[i % 2]
  );
});

const insertWeight = db.prepare(
  'INSERT INTO weights (animal_id, weight_kg, date, notes) VALUES (?, ?, ?, ?)'
);

// Animal 0 = Bella, Animal 1 = Daisy, Animal 2 = Molly
insertWeight.run(animalIds[0], 38.5, '2024-09-01', 'Pre-shearing');
insertWeight.run(animalIds[0], 41.2, '2024-10-15', null);
insertWeight.run(animalIds[0], 44.8, '2024-12-01', 'Post-shearing weigh-in');
insertWeight.run(animalIds[1], 52.1, '2024-10-01', null);
insertWeight.run(animalIds[1], 53.4, '2024-11-20', 'Healthy, on track');
insertWeight.run(animalIds[2], 29.3, '2024-11-05', 'Monitoring weight');

console.log('Database seeded successfully.');
