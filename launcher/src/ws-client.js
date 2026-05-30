/**
 * Touch-contract WebSocket client.
 *
 * Connects to ws://localhost:8765 (touch-bridge) and emits each received
 * frame to subscribers. Reconnects automatically with a fixed backoff so
 * an operator does not need to refresh after a service restart. A mouse
 * fallback synthesises single-touch frames from pointer events so the
 * launcher can be developed without a sensor, matching the reference
 * game pattern (legacy/stapzone_training_v8_pro.html).
 */

const DEFAULT_URL = `ws://${window.location.hostname || 'localhost'}:8765`;
const RECONNECT_DELAY_MS = 1500;

export class TouchClient {
  constructor({ url = DEFAULT_URL, mouseFallback = true } = {}) {
    this.url = url;
    this.mouseFallback = mouseFallback;
    this._socket = null;
    this._subscribers = new Set();
    this._connected = false;
    this._closed = false;
    this._reconnectTimer = null;
    this._mouseSeq = 0;
    this._mouseTouchActive = false;
    this._mouseHandler = (event) => this._onMouseEvent(event);
  }

  get connected() {
    return this._connected;
  }

  subscribe(listener) {
    this._subscribers.add(listener);
    return () => this._subscribers.delete(listener);
  }

  start() {
    this._closed = false;
    this._connect();
    if (this.mouseFallback) {
      window.addEventListener('pointermove', this._mouseHandler);
      window.addEventListener('pointerdown', this._mouseHandler);
      window.addEventListener('pointerup', this._mouseHandler);
    }
  }

  stop() {
    this._closed = true;
    if (this._reconnectTimer !== null) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this._socket !== null) {
      this._socket.close();
      this._socket = null;
    }
    if (this.mouseFallback) {
      window.removeEventListener('pointermove', this._mouseHandler);
      window.removeEventListener('pointerdown', this._mouseHandler);
      window.removeEventListener('pointerup', this._mouseHandler);
    }
  }

  _connect() {
    try {
      this._socket = new WebSocket(this.url);
    } catch {
      this._scheduleReconnect();
      return;
    }
    this._socket.addEventListener('open', () => {
      this._connected = true;
      this._notifyStatus();
    });
    this._socket.addEventListener('message', (event) => {
      this._dispatchRawFrame(event.data);
    });
    this._socket.addEventListener('close', () => {
      this._connected = false;
      this._notifyStatus();
      this._scheduleReconnect();
    });
    this._socket.addEventListener('error', () => {
      // The close handler will run and reschedule a reconnect.
    });
  }

  _scheduleReconnect() {
    if (this._closed || this._reconnectTimer !== null) {
      return;
    }
    this._reconnectTimer = window.setTimeout(() => {
      this._reconnectTimer = null;
      this._connect();
    }, RECONNECT_DELAY_MS);
  }

  _dispatchRawFrame(raw) {
    let frame;
    try {
      frame = JSON.parse(raw);
    } catch {
      return;
    }
    this._emit(frame);
  }

  _emit(frame) {
    for (const listener of this._subscribers) {
      try {
        listener(frame);
      } catch (err) {
        // A failing subscriber must not poison the others.
        console.error('touch subscriber failed', err);
      }
    }
  }

  _notifyStatus() {
    // Connection state changes are exposed as count:0 heartbeats so the
    // health pill can react without exposing a separate state channel.
    this._emit({ seq: -1, count: 0, touches: [], connected: this._connected });
  }

  _onMouseEvent(event) {
    // Bridge-connected: ignore mouse so synthetic touches never compete
    // with real ones.
    if (this._connected) {
      return;
    }
    if (event.type === 'pointerdown') {
      this._mouseTouchActive = true;
    } else if (event.type === 'pointerup') {
      this._mouseTouchActive = false;
    }
    if (!this._mouseTouchActive) {
      this._emit({ seq: ++this._mouseSeq, count: 0, touches: [] });
      return;
    }
    const x = event.clientX / window.innerWidth;
    const y = event.clientY / window.innerHeight;
    this._emit({
      seq: ++this._mouseSeq,
      count: 1,
      touches: [{ id: 0, x, y }],
    });
  }
}
