/**
 * Thin wrapper around the web-server's /api/* routes.
 *
 * All requests are same-origin in production (the web-server hosts the
 * SPA). During `npm run dev` Vite proxies /api and /games to the running
 * web-server, so the same paths work in both modes.
 */

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (response.status === 204) {
    return null;
  }
  const text = await response.text();
  let payload = null;
  try {
    payload = text.length > 0 ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  if (!response.ok) {
    const reason =
      (payload && typeof payload === 'object' && 'reason' in payload
        ? payload.reason
        : null) || response.statusText;
    const error = new Error(`${response.status} ${reason}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export const api = {
  status: () => request('/api/status'),
  listPresets: () => request('/api/calibration/presets'),
  getPreset: (name) =>
    request(`/api/calibration/presets/${encodeURIComponent(name)}`),
  savePreset: (preset) =>
    request('/api/calibration/presets', {
      method: 'POST',
      body: JSON.stringify(preset),
    }),
  deletePreset: (name) =>
    request(`/api/calibration/presets/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),
  getActive: () => request('/api/calibration/active'),
  setActive: (name) =>
    request('/api/calibration/active', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  getCapture: () => request('/api/calibration/capture'),
  captureCorner: (corner) =>
    request('/api/calibration/capture', {
      method: 'POST',
      body: JSON.stringify({ corner }),
    }),
  resetCapture: () =>
    request('/api/calibration/capture', { method: 'DELETE' }),
  listGames: () => request('/api/games'),
};
