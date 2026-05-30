/**
 * Status view — surfaces /api/status as labelled rows, polled at 1Hz.
 */

import { api } from '../api.js';

const POLL_MS = 1000;

export function renderStatus(container, _context) {
  container.innerHTML = `
    <h1 class="view-title">Status</h1>
    <p class="view-help">LiDAR connection, baseline, and active calibration.</p>
    <section class="panel status-rows" id="status-rows">
      <div class="muted">Polling…</div>
    </section>
  `;
  attachStatusStyles();
  const rows = container.querySelector('#status-rows');
  let stopped = false;
  let timer = null;

  const tick = async () => {
    try {
      const data = await api.status();
      renderRows(rows, data);
    } catch (err) {
      rows.innerHTML = `<div class="bad">/api/status failed: ${err.message}</div>`;
    }
    if (!stopped) {
      timer = window.setTimeout(tick, POLL_MS);
    }
  };
  tick();

  return () => {
    stopped = true;
    if (timer !== null) {
      clearTimeout(timer);
    }
  };
}

function renderRows(container, data) {
  const lidar = data?.lidar || {};
  const rows = [
    ['Lidar state', lidar.state || 'unknown', stateClass(lidar.state)],
    ['Has baseline', lidar.has_baseline ? 'yes' : 'no'],
    ['Last sequence', lidar.last_seq ?? 0],
    ['Last scan seen', formatTs(lidar.last_seen_ts)],
    ['Status file updated', formatTs(lidar.status_updated_at)],
    ['Active preset', lidar.active_preset || '— none —'],
    ['Stream connected', lidar.stream_connected ? 'yes' : 'no'],
    ['Stream last frame', formatTs(lidar.stream_last_frame_ts)],
  ];
  container.innerHTML = rows
    .map(
      ([label, value, klass]) => `
      <div class="status-row">
        <span class="status-label">${label}</span>
        <span class="status-value ${klass || ''}">${escapeHtml(value)}</span>
      </div>
    `,
    )
    .join('');
}

function stateClass(state) {
  switch (state) {
    case 'streaming':
      return 'ok';
    case 'stale':
    case 'connecting':
      return 'warn';
    case 'failed':
    case 'disconnected':
      return 'bad';
    default:
      return '';
  }
}

function formatTs(ts) {
  if (!ts || ts === 0) return '—';
  const date = new Date(ts * 1000);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleTimeString();
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

let stylesAttached = false;
function attachStatusStyles() {
  if (stylesAttached) return;
  stylesAttached = true;
  const style = document.createElement('style');
  style.textContent = `
    .status-rows {
      display: grid;
      grid-template-columns: max-content 1fr;
      column-gap: 32px;
      row-gap: 8px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 14px;
    }
    .status-label { color: var(--muted); }
    .status-value.ok { color: var(--ok); }
    .status-value.warn { color: var(--warn); }
    .status-value.bad { color: var(--bad); }
    .bad { color: var(--bad); }
  `;
  document.head.appendChild(style);
}
