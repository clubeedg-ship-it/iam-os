/**
 * Updates the top-bar health pill from /api/status, polled at 1Hz.
 */

import { api } from './api.js';

const POLL_MS = 1000;

export class HealthPill {
  constructor(element) {
    this.element = element;
    this._timer = null;
    this._stopped = false;
  }

  start() {
    this._stopped = false;
    this._tick();
  }

  stop() {
    this._stopped = true;
    if (this._timer !== null) {
      clearTimeout(this._timer);
      this._timer = null;
    }
  }

  async _tick() {
    try {
      const data = await api.status();
      const state = data?.lidar?.state || 'unknown';
      this.element.dataset.state = state;
      this.element.textContent = state;
    } catch {
      this.element.dataset.state = 'failed';
      this.element.textContent = 'api error';
    }
    if (!this._stopped) {
      this._timer = window.setTimeout(() => this._tick(), POLL_MS);
    }
  }
}
