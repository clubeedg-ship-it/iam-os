"""Per-game headless-Chromium smoke test.

Each game in the manifest is opened in a clean Chromium tab. The test
fails if the page raises an uncaught JS exception or its <title> is
empty — that catches a broken bundle, a syntax error, or a stray
runtime crash before merge.

Network noise (WebSocket to a non-existent bridge, Google Fonts in CI)
is ignored: console errors and request failures are not assertions; the
bar is a clean ``pageerror`` channel and a real title.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import Page

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_DIR = _REPO_ROOT / "games"
_LOAD_SETTLE_MS = 800


def _load_manifest() -> list[dict]:
    manifest = json.loads((_GAMES_DIR / "manifest.json").read_text())
    return list(manifest.get("games", []))


def _game_url(game: dict) -> str:
    entry_path = _GAMES_DIR / game["id"] / game["entry"]
    return entry_path.resolve().as_uri()


@pytest.mark.parametrize("game", _load_manifest(), ids=lambda g: g["id"])
def test_game_loads_without_js_errors(page: Page, game: dict) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))

    page.goto(_game_url(game), wait_until="load")
    # Give the page a beat to run its boot script before we sample state.
    # Games may queue work on requestAnimationFrame / setTimeout that
    # would fire after `load` and still throw.
    page.wait_for_timeout(_LOAD_SETTLE_MS)

    title = page.title()
    assert title, f"game {game['id']!r}: <title> is empty"
    assert not errors, f"game {game['id']!r} raised JS errors: {errors}"
