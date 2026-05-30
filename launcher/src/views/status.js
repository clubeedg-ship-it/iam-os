/**
 * Status view — placeholder.
 *
 * The real /api/status read-out lands in the next commit.
 */
export function renderStatus(container, _context) {
  container.innerHTML = `
    <h1 class="view-title">Status</h1>
    <p class="view-help">LiDAR connection and tracking health.</p>
    <section class="panel">Coming in the next commit.</section>
  `;
}
