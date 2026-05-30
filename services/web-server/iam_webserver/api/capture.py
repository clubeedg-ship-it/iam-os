"""Calibration capture session: records sensor-space corners from live touches.

The launcher's calibrate view walks the operator through TL/TR/BR/BL. For
each corner the operator touches the projected target; the launcher posts
``{corner: "tl"}`` and the handler records the current touch's
``raw_x_mm``/``raw_y_mm`` (the bridge strips those before broadcast, so
they only reach the web-server through its private lidar.sock client).
When all four corners have been captured the launcher submits a complete
preset via :mod:`iam_webserver.api.calibration`.

The session lives in process memory: it is operator-driven and short-lived,
and survives a launcher reload while the web-server is up.
"""

from __future__ import annotations

from typing import Protocol

from aiohttp import web

_CORNERS = ("tl", "tr", "br", "bl")


class _LidarCacheView(Protocol):
    latest: dict | None


def register(app: web.Application, *, cache: _LidarCacheView) -> None:
    """Mount the /api/calibration/capture routes on ``app``."""
    captured: dict[str, list[float]] = {}

    async def get_session(_request: web.Request) -> web.Response:
        return web.json_response({"captured": dict(captured)})

    async def capture(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001 — surface any parse failure
            raise web.HTTPBadRequest(reason=f"invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise web.HTTPBadRequest(reason="body must be a JSON object")
        corner = payload.get("corner")
        if corner not in _CORNERS:
            raise web.HTTPBadRequest(
                reason=f"corner must be one of {', '.join(_CORNERS)}"
            )
        frame = cache.latest
        touches = (frame or {}).get("touches") or []
        if not touches:
            raise web.HTTPConflict(reason="no active touch to capture")
        touch = touches[0]
        try:
            raw_x = float(touch["raw_x_mm"])
            raw_y = float(touch["raw_y_mm"])
        except (KeyError, TypeError, ValueError) as exc:
            raise web.HTTPConflict(
                reason="active touch is missing raw mm fields"
            ) from exc
        captured[corner] = [raw_x, raw_y]
        return web.json_response({"captured": dict(captured)})

    async def reset(_request: web.Request) -> web.Response:
        captured.clear()
        return web.Response(status=204)

    app.router.add_get("/api/calibration/capture", get_session)
    app.router.add_post("/api/calibration/capture", capture)
    app.router.add_delete("/api/calibration/capture", reset)
