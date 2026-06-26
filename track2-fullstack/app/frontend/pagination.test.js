const { test } = require('node:test');
const assert = require('node:assert/strict');
const { getPaginationRange } = require('./pagination');

// ─── Edge cases ───────────────────────────────────────────────────────────────

test('totalPages = 1 returns [1]', () => {
  assert.deepEqual(getPaginationRange(1, 1), [1]);
});

test('totalPages = 0 returns [1]', () => {
  assert.deepEqual(getPaginationRange(1, 0), [1]);
});

// ─── Small page counts (no ellipsis expected) ─────────────────────────────────

test('5 total pages, page 1 — no ellipsis', () => {
  assert.deepEqual(getPaginationRange(1, 5), [1, 2, 3, 4, 5]);
});

test('5 total pages, page 3 — no ellipsis', () => {
  assert.deepEqual(getPaginationRange(3, 5), [1, 2, 3, 4, 5]);
});

test('5 total pages, page 5 — no ellipsis', () => {
  assert.deepEqual(getPaginationRange(5, 5), [1, 2, 3, 4, 5]);
});

// ─── First page of a large set ───────────────────────────────────────────────

test('page 1 of 100 — ellipsis at end', () => {
  assert.deepEqual(getPaginationRange(1, 100), [1, 2, 3, '...', 100]);
});

// ─── Near the start ───────────────────────────────────────────────────────────

test('page 3 of 100 — ellipsis at end only', () => {
  assert.deepEqual(getPaginationRange(3, 100), [1, 2, 3, 4, 5, '...', 100]);
});

// ─── Middle of a large set ───────────────────────────────────────────────────

test('page 50 of 100 — ellipsis on both sides', () => {
  assert.deepEqual(getPaginationRange(50, 100), [1, '...', 48, 49, 50, 51, 52, '...', 100]);
});

// ─── Near the end ─────────────────────────────────────────────────────────────

test('page 98 of 100 — ellipsis at start only', () => {
  assert.deepEqual(getPaginationRange(98, 100), [1, '...', 96, 97, 98, 99, 100]);
});

test('page 100 of 100 — last page', () => {
  assert.deepEqual(getPaginationRange(100, 100), [1, '...', 98, 99, 100]);
});

// ─── Custom delta ─────────────────────────────────────────────────────────────

test('delta = 1 narrows the window', () => {
  assert.deepEqual(getPaginationRange(50, 100, 1), [1, '...', 49, 50, 51, '...', 100]);
});

test('delta = 0 shows only current page in the middle', () => {
  assert.deepEqual(getPaginationRange(50, 100, 0), [1, '...', 50, '...', 100]);
});

// ─── Always includes first and last page ─────────────────────────────────────

test('first page is always 1', () => {
  const range = getPaginationRange(50, 100);
  assert.equal(range[0], 1);
});

test('last page is always totalPages', () => {
  const range = getPaginationRange(50, 100);
  assert.equal(range[range.length - 1], 100);
});

test('current page is always in the range', () => {
  const range = getPaginationRange(50, 100);
  assert.ok(range.includes(50));
});
