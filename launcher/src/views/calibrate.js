/**
 * Calibrate view — four-corner capture flow.
 *
 * Walks the operator through TL → TR → BR → BL. For each corner the
 * operator touches the projected target; pressing Capture records the
 * current raw sensor-space position via /api/calibration/capture. Once
 * all four corners are captured the operator names the preset and saves
 * it, which writes the preset and the active-pointer file the
 * lidar-service watcher polls.
 */

import { api } from '../api.js';

const CORNERS = [
  { id: 'tl', label: 'Top-Left', x: '0%', y: '0%' },
  { id: 'tr', label: 'Top-Right', x: '100%', y: '0%' },
  { id: 'br', label: 'Bottom-Right', x: '100%', y: '100%' },
  { id: 'bl', label: 'Bottom-Left', x: '0%', y: '100%' },
];

export function renderCalibrate(container, _context) {
  container.innerHTML = `
    <h1 class="view-title">Calibrate</h1>
    <p class="view-help">
      Touch the highlighted target on the projection surface, then press
      <strong>Capture</strong>. Repeat for all four corners and save the
      preset.
    </p>
    <section class="calibrate-stage" id="calibrate-stage">
      ${CORNERS.map(
        (c) => `
          <div class="corner" data-corner="${c.id}" style="left:${c.x};top:${c.y};">
            <div class="corner-marker"></div>
            <div class="corner-label">${c.label}</div>
            <div class="corner-value" data-role="value">—</div>
          </div>
        `,
      ).join('')}
    </section>
    <section class="panel calibrate-controls">
      <div class="row">
        <span class="cur-corner">Current corner:
          <strong id="cur-corner-name">${CORNERS[0].label}</strong>
        </span>
        <button id="btn-capture" type="button">Capture corner</button>
        <button id="btn-reset" type="button" class="ghost">Reset session</button>
      </div>
      <div class="row save-row">
        <label for="preset-name">Preset name</label>
        <input id="preset-name" type="text" placeholder="rig-a" autocomplete="off" />
        <button id="btn-save" type="button" disabled>Save &amp; activate</button>
      </div>
      <div class="row">
        <span id="cal-message" class="muted"></span>
      </div>
    </section>
  `;
  attachCalibrateStyles();

  const state = {
    index: 0,
    captured: {},
  };

  const message = container.querySelector('#cal-message');
  const captureBtn = container.querySelector('#btn-capture');
  const resetBtn = container.querySelector('#btn-reset');
  const saveBtn = container.querySelector('#btn-save');
  const nameInput = container.querySelector('#preset-name');
  const curCornerName = container.querySelector('#cur-corner-name');
  const cornerEls = new Map(
    Array.from(container.querySelectorAll('.corner')).map((el) => [
      el.dataset.corner,
      el,
    ]),
  );

  const setMessage = (text, tone = 'muted') => {
    message.textContent = text;
    message.dataset.tone = tone;
  };

  const refreshFromSession = (captured) => {
    state.captured = captured || {};
    for (const corner of CORNERS) {
      const el = cornerEls.get(corner.id);
      const point = state.captured[corner.id];
      el.classList.toggle('captured', Array.isArray(point));
      const valueEl = el.querySelector('[data-role="value"]');
      valueEl.textContent = Array.isArray(point)
        ? `${point[0].toFixed(0)}, ${point[1].toFixed(0)} mm`
        : '—';
    }
    state.index = CORNERS.findIndex((c) => !(c.id in state.captured));
    if (state.index < 0) {
      state.index = CORNERS.length - 1;
      curCornerName.textContent = 'All corners captured';
      captureBtn.disabled = true;
      saveBtn.disabled = !nameInput.value.trim();
    } else {
      curCornerName.textContent = CORNERS[state.index].label;
      captureBtn.disabled = false;
      saveBtn.disabled = true;
    }
    for (const corner of CORNERS) {
      cornerEls.get(corner.id).classList.toggle(
        'active',
        corner.id === CORNERS[state.index]?.id,
      );
    }
  };

  api
    .getCapture()
    .then((data) => refreshFromSession(data.captured))
    .catch(() => refreshFromSession({}));

  captureBtn.addEventListener('click', async () => {
    if (state.index < 0 || state.index >= CORNERS.length) {
      return;
    }
    const corner = CORNERS[state.index];
    captureBtn.disabled = true;
    setMessage(`Capturing ${corner.label}…`);
    try {
      const data = await api.captureCorner(corner.id);
      refreshFromSession(data.captured);
      const next = CORNERS[state.index];
      if (next) {
        setMessage(`Captured ${corner.label}. Move to ${next.label}.`, 'ok');
      } else {
        setMessage('All corners captured. Name the preset and save.', 'ok');
      }
    } catch (err) {
      captureBtn.disabled = false;
      setMessage(
        `Capture failed: ${err.message}. Make sure a touch is active.`,
        'bad',
      );
    }
  });

  resetBtn.addEventListener('click', async () => {
    try {
      await api.resetCapture();
    } catch (err) {
      setMessage(`Reset failed: ${err.message}`, 'bad');
      return;
    }
    refreshFromSession({});
    setMessage('Session reset.', 'muted');
  });

  nameInput.addEventListener('input', () => {
    const ready = CORNERS.every((c) => c.id in state.captured);
    saveBtn.disabled = !ready || !nameInput.value.trim();
  });

  saveBtn.addEventListener('click', async () => {
    const name = nameInput.value.trim();
    if (!name) return;
    saveBtn.disabled = true;
    setMessage(`Saving preset “${name}”…`);
    const preset = {
      name,
      source_corners: CORNERS.map((c) => state.captured[c.id]),
      dest_corners: [
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ],
    };
    try {
      await api.savePreset(preset);
      await api.setActive(name);
      setMessage(`Preset “${name}” saved and activated.`, 'ok');
    } catch (err) {
      saveBtn.disabled = false;
      setMessage(`Save failed: ${err.message}`, 'bad');
    }
  });

  return () => {
    // Nothing to tear down — the API calls and DOM state stop with the view.
  };
}

let stylesAttached = false;
function attachCalibrateStyles() {
  if (stylesAttached) return;
  stylesAttached = true;
  const style = document.createElement('style');
  style.textContent = `
    .calibrate-stage {
      position: relative;
      height: 360px;
      margin-bottom: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      overflow: hidden;
    }
    .corner {
      position: absolute;
      transform: translate(-50%, -50%);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 8px;
    }
    .corner-marker {
      width: 22px;
      height: 22px;
      border-radius: 50%;
      background: var(--panel-2);
      border: 2px solid var(--muted);
    }
    .corner.active .corner-marker {
      background: var(--accent);
      border-color: var(--accent);
      box-shadow: 0 0 0 8px rgba(61, 167, 255, 0.18);
    }
    .corner.captured .corner-marker {
      background: var(--ok);
      border-color: var(--ok);
    }
    .corner-label {
      font-size: 12px;
      color: var(--muted);
    }
    .corner-value {
      font-size: 11px;
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, monospace;
    }
    .calibrate-controls .row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .calibrate-controls .row:last-child {
      margin-bottom: 0;
    }
    .cur-corner {
      color: var(--muted);
    }
    .save-row label {
      color: var(--muted);
      font-size: 13px;
    }
    .save-row input {
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 12px;
      color: var(--text);
      font-family: inherit;
      flex: 1;
      max-width: 260px;
    }
    #cal-message[data-tone='ok'] { color: var(--ok); }
    #cal-message[data-tone='bad'] { color: var(--bad); }
    #cal-message[data-tone='muted'] { color: var(--muted); }
  `;
  document.head.appendChild(style);
}
