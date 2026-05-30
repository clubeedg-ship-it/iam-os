/**
 * Tiny hash-based router.
 *
 * Each view registers a render(container, context) function. On hash
 * change the active view's teardown() is called (if returned), then the
 * new view's render runs. Hash routing keeps the launcher single-URL
 * from the server's perspective and dodges history.pushState
 * permissions inside Chromium kiosk.
 */

export class Router {
  constructor(container) {
    this.container = container;
    this.routes = new Map();
    this.defaultRoute = null;
    this._activeTeardown = null;
    this._activeName = null;
    this._handler = () => this._render();
  }

  add(name, render) {
    this.routes.set(name, render);
    if (this.defaultRoute === null) {
      this.defaultRoute = name;
    }
    return this;
  }

  start(context = {}) {
    this.context = context;
    window.addEventListener('hashchange', this._handler);
    this._render();
  }

  stop() {
    window.removeEventListener('hashchange', this._handler);
    if (typeof this._activeTeardown === 'function') {
      this._activeTeardown();
      this._activeTeardown = null;
    }
  }

  go(name) {
    window.location.hash = `#/${name}`;
  }

  get activeName() {
    return this._activeName;
  }

  _render() {
    const name = this._parseHash();
    const renderer = this.routes.get(name) || this.routes.get(this.defaultRoute);
    if (typeof this._activeTeardown === 'function') {
      try {
        this._activeTeardown();
      } catch (err) {
        console.error('view teardown failed', err);
      }
      this._activeTeardown = null;
    }
    this.container.innerHTML = '';
    this._activeName = name in (renderer ? { [name]: 1 } : {})
      ? name
      : this.defaultRoute;
    this._highlightTabs();
    const teardown = renderer?.(this.container, this.context);
    if (typeof teardown === 'function') {
      this._activeTeardown = teardown;
    }
  }

  _parseHash() {
    const raw = window.location.hash || '';
    const trimmed = raw.replace(/^#\/?/, '');
    return trimmed || this.defaultRoute;
  }

  _highlightTabs() {
    const tabs = document.querySelectorAll('.tabs a[data-view]');
    for (const tab of tabs) {
      tab.classList.toggle('active', tab.dataset.view === this._activeName);
    }
  }
}
