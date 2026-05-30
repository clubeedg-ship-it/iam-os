"""Tests for the games manifest validator.

The validator is the PR gate for games/: a manifest entry that points
at a missing file, fails the schema, or omits the frozen WebSocket
contract URL must be caught before merge.
"""

import json
from pathlib import Path

from validate_games import validate

_VALID_HTML = (
    '<!doctype html><html><head><title>Demo</title></head>'
    '<body><script>'
    "const ws = new WebSocket('ws://localhost:8765');"
    '</script></body></html>'
)


def _write_manifest(games_dir: Path, games: list[dict]) -> None:
    (games_dir / "manifest.json").write_text(json.dumps({"games": games}))


def _write_schema(games_dir: Path) -> None:
    repo_schema = Path(__file__).resolve().parents[2] / "games" / "manifest.schema.json"
    (games_dir / "manifest.schema.json").write_text(repo_schema.read_text())


def _game_dir(games_dir: Path, slug: str) -> Path:
    path = games_dir / slug
    path.mkdir()
    return path


def test_empty_manifest_validates(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _write_manifest(tmp_path, [])
    assert validate(tmp_path) == []


def test_well_formed_game_validates(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _game_dir(tmp_path, "demo")
    (tmp_path / "demo" / "index.html").write_text(_VALID_HTML)
    _write_manifest(
        tmp_path,
        [
            {
                "id": "demo",
                "name": "Demo Game",
                "entry": "index.html",
                "version": "1.0.0",
            }
        ],
    )
    assert validate(tmp_path) == []


def test_missing_manifest_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    errors = validate(tmp_path)
    assert any("manifest.json" in err for err in errors)


def test_malformed_manifest_json_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    (tmp_path / "manifest.json").write_text("not json")
    errors = validate(tmp_path)
    assert any("invalid json" in err.lower() for err in errors)


def test_schema_violation_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    # id is not a kebab slug
    _write_manifest(
        tmp_path,
        [{"id": "Bad ID", "name": "X", "entry": "index.html", "version": "1.0.0"}],
    )
    errors = validate(tmp_path)
    assert any("schema" in err.lower() for err in errors)


def test_missing_version_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _write_manifest(
        tmp_path,
        [{"id": "demo", "name": "Demo", "entry": "index.html"}],
    )
    errors = validate(tmp_path)
    assert any("schema" in err.lower() for err in errors)


def test_missing_entry_file_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _game_dir(tmp_path, "demo")  # no index.html
    _write_manifest(
        tmp_path,
        [
            {
                "id": "demo",
                "name": "Demo",
                "entry": "index.html",
                "version": "1.0.0",
            }
        ],
    )
    errors = validate(tmp_path)
    assert any("index.html" in err and "missing" in err.lower() for err in errors)


def test_missing_game_directory_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _write_manifest(
        tmp_path,
        [
            {
                "id": "ghost",
                "name": "Ghost",
                "entry": "index.html",
                "version": "1.0.0",
            }
        ],
    )
    errors = validate(tmp_path)
    assert any("ghost" in err.lower() for err in errors)


def test_entry_without_contract_url_is_reported(tmp_path: Path) -> None:
    """Each game's entry HTML must reference the frozen WebSocket URL."""
    _write_schema(tmp_path)
    _game_dir(tmp_path, "silent")
    (tmp_path / "silent" / "index.html").write_text(
        "<!doctype html><title>Silent</title>"
    )
    _write_manifest(
        tmp_path,
        [
            {
                "id": "silent",
                "name": "Silent",
                "entry": "index.html",
                "version": "1.0.0",
            }
        ],
    )
    errors = validate(tmp_path)
    assert any("ws://localhost:8765" in err for err in errors)


def test_missing_thumbnail_file_is_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _game_dir(tmp_path, "demo")
    (tmp_path / "demo" / "index.html").write_text(_VALID_HTML)
    _write_manifest(
        tmp_path,
        [
            {
                "id": "demo",
                "name": "Demo",
                "entry": "index.html",
                "version": "1.0.0",
                "thumbnail": "thumb.png",
            }
        ],
    )
    errors = validate(tmp_path)
    assert any("thumb.png" in err for err in errors)


def test_duplicate_ids_are_reported(tmp_path: Path) -> None:
    _write_schema(tmp_path)
    _game_dir(tmp_path, "demo")
    (tmp_path / "demo" / "index.html").write_text(_VALID_HTML)
    _write_manifest(
        tmp_path,
        [
            {
                "id": "demo",
                "name": "Demo A",
                "entry": "index.html",
                "version": "1.0.0",
            },
            {
                "id": "demo",
                "name": "Demo B",
                "entry": "index.html",
                "version": "1.0.0",
            },
        ],
    )
    errors = validate(tmp_path)
    assert any("duplicate" in err.lower() for err in errors)


def test_repo_manifest_validates() -> None:
    """The committed games/manifest.json must pass validation at all times."""
    games_dir = Path(__file__).resolve().parents[2] / "games"
    assert validate(games_dir) == []
