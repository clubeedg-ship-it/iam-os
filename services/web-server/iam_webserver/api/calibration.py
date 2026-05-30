"""Calibration preset CRUD + active-pointer routes.

The web-server owns the preset store on disk; lidar-service polls
``active_pointer_path`` and reloads the named preset on change. Writes
here are atomic (write-and-rename) so a concurrent poll on lidar's side
never sees a half-written document.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from aiohttp import web

_log = logging.getLogger(__name__)

# Preset names map to filenames. Restrict them to a safe identifier set so
# the route handler cannot be tricked into writing or reading outside the
# presets directory.
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_DOT_NAMES = {".", ".."}


def _is_valid_name(name: object) -> bool:
    return (
        isinstance(name, str)
        and name not in _DOT_NAMES
        and bool(_NAME_PATTERN.match(name))
        and "/" not in name
        and "\\" not in name
    )


def _validate_corners(raw: object, label: str) -> list[list[float]]:
    if not isinstance(raw, list) or len(raw) != 4:
        raise ValueError(f"{label} must be a list of 4 [x, y] points")
    corners: list[list[float]] = []
    for point in raw:
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError(f"{label} entries must be [x, y] pairs")
        try:
            corners.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} values must be numeric") from exc
    return corners


def _validate_preset(payload: object) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("body must be a JSON object")
    name = payload.get("name")
    if not _is_valid_name(name):
        raise ValueError("name must be a safe identifier (A-Z, a-z, 0-9, _.-)")
    return {
        "name": name,
        "source_corners": _validate_corners(
            payload.get("source_corners"), "source_corners"
        ),
        "dest_corners": _validate_corners(
            payload.get("dest_corners"), "dest_corners"
        ),
    }


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def _read_active(active_pointer_path: Path) -> str:
    try:
        data = json.loads(active_pointer_path.read_text())
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return ""
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        return data["name"]
    return ""


def register(
    app: web.Application,
    *,
    presets_dir: Path | str,
    active_pointer_path: Path | str,
) -> None:
    """Mount the /api/calibration/* routes on ``app``."""
    presets_dir = Path(presets_dir)
    active_pointer_path = Path(active_pointer_path)

    def preset_path(name: str) -> Path:
        # _is_valid_name has already vetted the name; this is belt-and-braces.
        if not _is_valid_name(name):
            raise web.HTTPBadRequest(reason="invalid preset name")
        return presets_dir / f"{name}.json"

    async def list_presets(_request: web.Request) -> web.Response:
        presets: list[dict] = []
        if presets_dir.is_dir():
            for entry in sorted(presets_dir.iterdir()):
                if entry.suffix != ".json" or entry.name == "active.json":
                    continue
                try:
                    presets.append(json.loads(entry.read_text()))
                except (OSError, json.JSONDecodeError) as exc:
                    _log.warning("skipping unreadable preset %s: %s", entry, exc)
        return web.json_response(
            {"presets": presets, "active": _read_active(active_pointer_path)}
        )

    async def get_preset(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        path = preset_path(name)
        try:
            return web.json_response(json.loads(path.read_text()))
        except FileNotFoundError:
            raise web.HTTPNotFound(reason=f"preset {name!r} not found") from None

    async def create_preset(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise web.HTTPBadRequest(reason=f"invalid JSON: {exc}") from exc
        try:
            preset = _validate_preset(payload)
        except ValueError as exc:
            raise web.HTTPBadRequest(reason=str(exc)) from exc
        _atomic_write(preset_path(preset["name"]), preset)
        return web.json_response(preset, status=201)

    async def delete_preset(request: web.Request) -> web.Response:
        name = request.match_info["name"]
        path = preset_path(name)
        try:
            path.unlink()
        except FileNotFoundError:
            raise web.HTTPNotFound(reason=f"preset {name!r} not found") from None
        return web.Response(status=204)

    async def get_active(_request: web.Request) -> web.Response:
        return web.json_response({"active": _read_active(active_pointer_path)})

    async def set_active(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except json.JSONDecodeError as exc:
            raise web.HTTPBadRequest(reason=f"invalid JSON: {exc}") from exc
        name = payload.get("name") if isinstance(payload, dict) else None
        if not _is_valid_name(name):
            raise web.HTTPBadRequest(reason="name must be a safe identifier")
        if not preset_path(name).is_file():
            raise web.HTTPNotFound(reason=f"preset {name!r} not found")
        _atomic_write(active_pointer_path, {"name": name})
        return web.json_response({"active": name})

    app.router.add_get("/api/calibration/presets", list_presets)
    app.router.add_post("/api/calibration/presets", create_preset)
    app.router.add_get("/api/calibration/presets/{name}", get_preset)
    app.router.add_delete("/api/calibration/presets/{name}", delete_preset)
    app.router.add_get("/api/calibration/active", get_active)
    app.router.add_post("/api/calibration/active", set_active)
