/**
 * Test view — live touch visualisation.
 *
 * Subscribes to the shared TouchClient and draws each active touch as a
 * coloured circle, colouring by touch id. Mouse pointer events drive the
 * same path when the bridge is offline, so an operator can see the view
 * react without a sensor.
 */

const COLOURS = [
  '#3da7ff',
  '#4ade80',
  '#facc15',
  '#f87171',
  '#a78bfa',
  '#fb7185',
  '#34d399',
  '#fbbf24',
];

export function renderTest(container, context) {
  container.innerHTML = `
    <h1 class="view-title">Test</h1>
    <p class="view-help">
      Each circle is one active touch. Touches keep their colour across
      frames so you can see tracking stay locked on.
    </p>
    <section class="panel test-stage-wrap">
      <div class="test-stage" id="test-stage" aria-hidden="true"></div>
      <div class="test-readout">
        <div><span class="muted">touches:</span> <strong id="test-count">0</strong></div>
        <div><span class="muted">seq:</span> <strong id="test-seq">—</strong></div>
        <div><span class="muted">source:</span> <strong id="test-source">—</strong></div>
      </div>
    </section>
  `;
  attachTestStyles();

  const stage = container.querySelector('#test-stage');
  const countEl = container.querySelector('#test-count');
  const seqEl = container.querySelector('#test-seq');
  const sourceEl = container.querySelector('#test-source');
  const dots = new Map(); // id -> element

  const handle = (frame) => {
    if (!frame || !Array.isArray(frame.touches)) return;
    if ('connected' in frame) {
      sourceEl.textContent = frame.connected ? 'live (bridge)' : 'mouse fallback';
      return;
    }
    sourceEl.textContent = context.touch?.connected
      ? 'live (bridge)'
      : 'mouse fallback';
    seqEl.textContent = String(frame.seq);
    countEl.textContent = String(frame.count);
    const seen = new Set();
    for (const touch of frame.touches) {
      seen.add(touch.id);
      let dot = dots.get(touch.id);
      if (dot === undefined) {
        dot = document.createElement('div');
        dot.className = 'touch-dot';
        dot.style.background = COLOURS[touch.id % COLOURS.length];
        dot.dataset.id = String(touch.id);
        const label = document.createElement('span');
        label.textContent = String(touch.id);
        dot.appendChild(label);
        stage.appendChild(dot);
        dots.set(touch.id, dot);
      }
      dot.style.left = `${(touch.x * 100).toFixed(2)}%`;
      dot.style.top = `${(touch.y * 100).toFixed(2)}%`;
    }
    for (const [id, dot] of dots) {
      if (!seen.has(id)) {
        dot.remove();
        dots.delete(id);
      }
    }
  };

  const unsubscribe = context.touch?.subscribe(handle);

  return () => {
    unsubscribe?.();
    for (const dot of dots.values()) {
      dot.remove();
    }
    dots.clear();
  };
}

let stylesAttached = false;
function attachTestStyles() {
  if (stylesAttached) return;
  stylesAttached = true;
  const style = document.createElement('style');
  style.textContent = `
    .test-stage-wrap {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .test-stage {
      position: relative;
      height: 420px;
      background: var(--panel-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    .touch-dot {
      position: absolute;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      transform: translate(-50%, -50%);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #06121f;
      font-weight: 800;
      font-size: 12px;
      box-shadow: 0 0 0 6px rgba(61, 167, 255, 0.16);
      transition:
        left 60ms linear,
        top 60ms linear;
    }
    .test-readout {
      display: flex;
      gap: 32px;
      font-family: ui-monospace, SFMono-Regular, monospace;
      font-size: 13px;
    }
    .test-readout .muted { color: var(--muted); }
  `;
  document.head.appendChild(style);
}
