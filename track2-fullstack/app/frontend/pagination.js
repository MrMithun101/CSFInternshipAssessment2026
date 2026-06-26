/**
 * getPaginationRange(currentPage, totalPages, delta)
 *
 * Returns an array of page numbers (1-indexed) and '...' strings
 * representing the ellipsis-style pagination range to display.
 *
 * Examples (delta = 2):
 *   page 1  of 100 → [1, 2, 3, 4, 5, '...', 100]
 *   page 50 of 100 → [1, '...', 48, 49, 50, 51, 52, '...', 100]
 *   page 99 of 100 → [1, '...', 96, 97, 98, 99, 100]
 *
 * @param {number} currentPage  1-indexed current page
 * @param {number} totalPages   total number of pages
 * @param {number} [delta=2]    pages shown on each side of the current page
 * @returns {Array<number|'...'>}
 */
function getPaginationRange(currentPage, totalPages, delta = 2) {
  if (totalPages <= 1) return [1];

  const range = [];
  // Build the window around the current page [left..right], clamped to valid bounds.
  const left  = Math.max(2, currentPage - delta);
  const right = Math.min(totalPages - 1, currentPage + delta);

  range.push(1);

  if (left > 2) range.push('...');

  for (let i = left; i <= right; i++) range.push(i);

  if (right < totalPages - 1) range.push('...');

  range.push(totalPages);

  return range;
}

// Support both browser (global) and Node.js (module.exports) environments.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { getPaginationRange };
}
