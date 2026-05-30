/**
 * Games view — catalogue + launch.
 *
 * Reads /api/games and renders each entry as a card; clicking launch
 * navigates the browser to the game URL under /games/{id}/{entry}. The
 * web-server serves the games tree as static files so the active page
 * becomes the game.
 */

import { api } from '../api.js';

export function renderGames(container, _context) {
  container.innerHTML = `
    <h1 class="view-title">Games</h1>
    <p class="view-help">Pick a game to hand the screen over to it.</p>
    <section class="panel games-list" id="games-list">
      <div class="muted">Loading…</div>
    </section>
  `;
  attachGamesStyles();
  const list = container.querySelector('#games-list');

  api
    .listGames()
    .then((data) => renderList(list, data?.games || []))
    .catch((err) => {
      list.innerHTML = `<div class="bad">Failed to load games: ${err.message}</div>`;
    });

  return () => {};
}

function renderList(container, games) {
  if (games.length === 0) {
    container.innerHTML = `
      <div class="muted">
        No games installed yet. Drop a game under <code>games/</code> and
        list it in <code>games/manifest.json</code> (Phase 5 wires this up).
      </div>
    `;
    return;
  }
  container.innerHTML = '';
  for (const game of games) {
    if (!game?.id) continue;
    const entry = typeof game.entry === 'string' ? game.entry : 'index.html';
    const card = document.createElement('article');
    card.className = 'game-card';
    card.innerHTML = `
      <div class="game-card-body">
        <h2>${escapeHtml(game.name || game.id)}</h2>
        <p class="muted">v${escapeHtml(game.version || '?')}</p>
      </div>
      <button type="button">Launch</button>
    `;
    card.querySelector('button').addEventListener('click', () => {
      window.location.href = `/games/${encodeURIComponent(game.id)}/${entry}`;
    });
    container.appendChild(card);
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

let stylesAttached = false;
function attachGamesStyles() {
  if (stylesAttached) return;
  stylesAttached = true;
  const style = document.createElement('style');
  style.textContent = `
    .games-list {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 16px;
    }
    .game-card {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 16px;
    }
    .game-card h2 {
      margin: 0 0 4px;
      font-size: 18px;
    }
    .game-card .muted {
      font-size: 12px;
      color: var(--muted);
    }
    .bad { color: var(--bad); }
  `;
  document.head.appendChild(style);
}
