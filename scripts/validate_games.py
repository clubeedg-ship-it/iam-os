"""Validate the IAM-OS games manifest.

PR gate for ``games/``: rejects a manifest that fails the JSON Schema,
points at a missing game directory or entry file, fails to reference
the frozen WebSocket touch contract, declares a missing thumbnail, or
lists duplicate ids. Importable from tests and runnable as a CLI.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import jsonschema

# The frozen WebSocket URL games must connect to (docs/touch-contract.md).
_CONTRACT_URL = "ws://localhost:8765"


def validate(games_dir: Path | str) -> list[str]:
    """Validate ``games_dir`` and return a list of human-readable errors.

    An empty list means the manifest, every referenced entry HTML, and
    every declared thumbnail are present and well-formed.
    """
    games_dir = Path(games_dir)
    manifest_path = games_dir / "manifest.json"
    schema_path = games_dir / "manifest.schema.json"

    errors: list[str] = []

    if not manifest_path.is_file():
        errors.append(f"manifest.json not found at {manifest_path}")
        return errors

    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"manifest.json: invalid JSON: {exc}")
        return errors

    if not schema_path.is_file():
        errors.append(f"manifest.schema.json not found at {schema_path}")
        return errors

    try:
        schema = json.loads(schema_path.read_text())
    except json.JSONDecodeError as exc:
        errors.append(f"manifest.schema.json: invalid JSON: {exc}")
        return errors

    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as exc:
        path = " / ".join(str(p) for p in exc.absolute_path) or "<root>"
        errors.append(f"manifest.json: schema violation at {path}: {exc.message}")
        # Schema errors mean we cannot trust the shape of `games[]` for the
        # per-game checks below; stop here rather than risk noisy follow-ups.
        return errors

    games = manifest.get("games", [])

    duplicates = [name for name, count in Counter(g["id"] for g in games).items() if count > 1]
    for dup in duplicates:
        errors.append(f"manifest.json: duplicate id {dup!r}")

    for game in games:
        slug = game["id"]
        game_dir = games_dir / slug
        if not game_dir.is_dir():
            errors.append(f"game {slug!r}: directory missing at {game_dir}")
            continue

        entry_rel = game["entry"]
        entry_path = game_dir / entry_rel
        if not entry_path.is_file():
            errors.append(
                f"game {slug!r}: entry file missing: {entry_rel}"
            )
        else:
            try:
                entry_text = entry_path.read_text(encoding="utf-8", errors="ignore")
            except OSError as exc:
                errors.append(f"game {slug!r}: cannot read {entry_rel}: {exc}")
            else:
                if _CONTRACT_URL not in entry_text:
                    errors.append(
                        f"game {slug!r}: {entry_rel} does not reference the "
                        f"frozen contract URL {_CONTRACT_URL}"
                    )

        thumbnail = game.get("thumbnail")
        if thumbnail and not (game_dir / thumbnail).is_file():
            errors.append(
                f"game {slug!r}: declared thumbnail missing: {thumbnail}"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    """CLI: validate ``games/`` (or path passed as the first argument)."""
    args = sys.argv[1:] if argv is None else argv
    if args:
        games_dir = Path(args[0])
    else:
        games_dir = Path(__file__).resolve().parent.parent / "games"
    errors = validate(games_dir)
    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        print(f"\n{len(errors)} validation error(s) in {games_dir}", file=sys.stderr)
        return 1
    print(f"games manifest at {games_dir} is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
