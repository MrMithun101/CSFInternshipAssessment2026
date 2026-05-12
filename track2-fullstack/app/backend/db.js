const { DatabaseSync } = require('node:sqlite');
const path = require('path');

const dbPath = process.env.FARMTRACKER_DB_PATH || path.join(__dirname, 'farmtracker.db');
const db = new DatabaseSync(dbPath);

db.exec('PRAGMA journal_mode = WAL');
db.exec('PRAGMA foreign_keys = ON');

function initDb() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS paddocks (
      id           INTEGER PRIMARY KEY AUTOINCREMENT,
      name         TEXT    NOT NULL UNIQUE,
      capacity     INTEGER NOT NULL,
      animal_count INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS animals (
      id            INTEGER PRIMARY KEY AUTOINCREMENT,
      name          TEXT    NOT NULL,
      tag_number    TEXT    NOT NULL UNIQUE,
      breed         TEXT,
      date_of_birth TEXT,
      paddock_id    INTEGER REFERENCES paddocks(id)
    );

    CREATE TABLE IF NOT EXISTS health_events (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      animal_id  INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
      event_type TEXT    NOT NULL,
      notes      TEXT,
      date       TEXT    NOT NULL,
      vet_name   TEXT
    );

    CREATE TABLE IF NOT EXISTS weights (
      id         INTEGER PRIMARY KEY AUTOINCREMENT,
      animal_id  INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
      weight_kg  REAL    NOT NULL,
      date       TEXT    NOT NULL,
      notes      TEXT
    );
  `);
}

module.exports = { db, initDb };
