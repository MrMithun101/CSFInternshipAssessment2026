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

  // Build the visible set: always include first, last, and a window around current.
  const visible = new Set([1, totalPages]);
  const left  = Math.max(2, currentPage - delta);
  const right = Math.min(totalPages - 1, currentPage + delta);
  for (let i = left; i <= right; i++) visible.add(i);

  // Convert sorted set to array, inserting '...' only when a gap hides more
  // than one page. A gap of exactly 1 hidden page is filled directly (showing
  // the actual page number is cleaner than "..." hiding a single digit).
  const sorted = [...visible].sort((a, b) => a - b);
  const result = [];
  for (let i = 0; i < sorted.length; i++) {
    result.push(sorted[i]);
    if (i < sorted.length - 1) {
      const gap = sorted[i + 1] - sorted[i];
      if (gap === 2) result.push(sorted[i] + 1);   // show the single hidden page
      else if (gap > 2) result.push('...');
    }
  }
  return result;
}

// Support both browser (global) and Node.js (module.exports) environments.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { getPaginationRange };
}
