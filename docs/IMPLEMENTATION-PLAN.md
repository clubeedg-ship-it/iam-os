# IAM-OS — Implementation Plan

## Context

`specs.md` (at the repo root) defines IAM-OS as a Linux kiosk appliance and ends
with an 8-phase roadmap (§13) written at a high level. This plan turns that
roadmap into concrete, executable work: real module names, real task lists,
build order, and verification per phase.

The repo started near-greenfield: `specs.md`, a monolithic 412-line Python
prototype, and a binary-only legacy Qt app. The prototype is the reference for
the LiDAR engine but is reimplemented, not adopted — it has the reliability
defects (no watchdog, silent stale data on disconnect, bare `except`, no
logging) that motivated the whole project.

**Outcome:** a phased, reviewable path to a working appliance. Execution
proceeds **one phase at a time** with review between phases — Phase 1 is the
immediate executable unit; later phases are sequenced but not started until
their predecessors land.

## Tech decisions (resolving items left open in `specs.md`)

| Open item | Decision | Reason |
|---|---|---|
| touch-bridge language | **Python** (`websockets` + asyncio) | Same toolchain as lidar-service; shared `TouchFrame`/config; keeps Node off the appliance image |
| Launcher stack | **Vanilla HTML/CSS/ES modules + Vite** (dev/build only) | `specs.md` says no heavy framework; Vite gives HMR for dev, ships plain static `dist/` |
| web-server | **Python** (`aiohttp`) | Third Python service; serves launcher + games + control API |
| Appliance distro | **Debian 12 minimal** (debootstrap) | Stable, scriptable, strong systemd + Chromium support; avoids slow Yocto/Buildroot iteration |
| First LiDAR driver | **RPLIDAR** (`pyrplidar`) | Matches prototype; S2/S2E/C1 are RPLIDAR-family; PAVO2 added later behind the same interface |
| Tooling | pytest + pytest-asyncio, ruff, mypy, ESLint + Prettier, Playwright | Standard, fast |
| lidar→bridge transport | **Unix domain socket** carrying JSON frames; TUIO/UDP dropped | The §4.2 WebSocket contract is the only frozen boundary; an extra UDP/OSC hop adds a second informal contract and drops datagrams silently |

## Phase 1 — Foundation

Branch `phase-1-foundation`.

- **Repo restructure with `git mv`** (preserves history; moves the 184 MB LFS
  pointer correctly): move `OG-IAM-LiDAR- Tracker/` and `IAM-GAME-MENU/` under
  `legacy/`; update the `.gitattributes` LFS path; create the `specs.md` §11
  tree (`services/`, `launcher/`, `games/`, `os-image/`, `sandbox/`, `docs/`);
  copy the stapzone reference game into `legacy/`.
- **Freeze the touch contract — the key deliverable.** Commit
  `docs/touch-contract.md` and `docs/touch-contract.schema.json` (the §4.2
  schema, v1.0.0). The schema makes "frozen" enforceable. Tag `contract-v1.0.0`.
- **CI skeleton** — `.github/workflows/ci.yml` with `lint-python` (ruff),
  `lint-js` (eslint), `test-python` (pytest), and placeholder `validate-games` /
  `build-launcher` jobs.
- Expand `.gitignore`; add `README.md`, `docs/architecture.md`,
  `legacy/README.md`, and this plan as `docs/IMPLEMENTATION-PLAN.md`.

**Exit:** §11 layout in place; `git log --follow` works on moved files; LFS file
intact; CI green; contract tagged `contract-v1.0.0`.

## Phase 2 — LiDAR service (deepest phase)

Reimplement the prototype as a modular package under `services/lidar-service/`,
meeting reliability requirements R1–R8 (`specs.md` §6):

```
pyproject.toml
config/lidar-service.toml      # ALL constants live here (R1)
iam_lidar/
  __main__.py        # CLI: parse args, load config, wire, run
  config.py          # typed TOML loader + env overrides + defaults
  logging_setup.py   # structured JSON logs to stdout/journald (R7)
  drivers/
    base.py          # LidarDriver ABC: connect/scan_frames/disconnect/get_info/is_alive (R8)
    rplidar.py       # concrete pyrplidar driver
    registry.py      # name -> driver class
  connection.py      # ConnectionManager: auto-detect + backoff + watchdog (R2/R3/R4)
  detection/{baseline,clustering,calibration,tracking}.py
  pipeline.py        # scan -> baseline -> calibrate -> cluster -> track
  simulator.py       # SimDriver behind the LidarDriver interface
  health.py          # HealthState + reporter (R6)
  frames.py          # TouchFrame / Touch dataclasses
  output/frame_sink.py   # emits JSON frames over the Unix socket
tests/
```

How each requirement is met:
- **R1** — every prototype literal moves to `lidar-service.toml` (baud list,
  `DIST_MIN/MAX`, `CL_TOL`, `TR_TOL`, `BL_TH`, `MIN_CL/MAX_CL`, watchdog
  timeout, backoff schedule, adapter-match strings). No module-level constants.
- **R2** — auto-detect enumerates `serial.tools.list_ports`, matching
  config-driven adapter descriptions; no hardcoded port.
- **R3** — `ConnectionManager` retries with exponential backoff
  (0.5→1→2→4…cap 30 s), logging every attempt.
- **R4** — a watchdog tracks the last-scan timestamp; on starvation it declares
  the device failed, forces disconnect, and re-initialises — killing the
  prototype's stale-data bug.
- **R6** — `HealthState` logged on transition and published for the launcher.
- **R7** — structured JSON logging; no `print`, no bare `except`.
- **R8** — all reconnect/health logic sits above the `LidarDriver` ABC, so it
  applies to RPLIDAR now and other sensors later.

Detection is a faithful port of the prototype's `Detect` class, split into
modules. The hardcoded calibration flip is removed — orientation becomes part of
the saved preset. The OpenCV GUI is dropped; visualization moves to the launcher.

**Verification (no hardware):** unit tests for clustering, calibration,
tracking, and backoff; `test_pipeline_e2e` runs `SimDriver` through the
pipeline. Manual: `python -m iam_lidar --simulate`, kill the sim mid-run, and
confirm auto-recovery in the logs.

## Phase 3 — Touch bridge

`services/touch-bridge/` — Python, `websockets`. `source.py` reads JSON frames
from the Unix socket produced by lidar-service; `contract.py` builds the §4.2
JSON, assigns the monotonic `seq`, clamps `x,y` to `[0,1]`; `server.py` runs the
`websockets` server on `ws://localhost:8765` for multiple clients. On upstream
loss it emits `count:0` empty frames, never stale data. Stays a separate
`systemd` unit.

**Verification:** `test_contract.py` validates every message against
`touch-contract.schema.json`; `test_server.py` confirms a client receives valid
frames from `SimDriver`. Manual: run sim lidar + bridge, then open the stapzone
game and confirm it reacts to synthetic touches.

## Phase 4 — Launcher UI

`launcher/` (Vite + vanilla JS) — four views (`calibrate`, `test`, `games`,
`status`) plus shared `ws-client.js` (§4.2 consumer + mouse fallback) and
`api.js`. `services/web-server/` (Python `aiohttp`) serves `launcher/dist` +
`games/` and exposes `GET /api/status`, `GET/POST /api/calibration/presets`,
`POST /api/calibration/active`, `GET /api/games`. Add `build-launcher` to CI.

## Phase 5 — Game integration

`games/` — define `manifest.json` (id / name / entry / thumbnail / version);
re-home the stapzone game to `games/stapzone-training/` with a manifest entry.
Write `scripts/validate_games.py` plus a Playwright headless smoke test, and
wire `validate-games` into the CI PR gate. The launcher reads the manifest, so
adding a game needs no launcher code change.

## Phase 6 — OS image + sandbox

`os-image/` — `build.sh` scripts a Debian 12 minimal image (debootstrap, no
desktop). Install the three services as `systemd` units with `Restart=always`
and correct ordering; add a kiosk session unit and a `udev` rule for serial
access; output a version-tagged `.img`. `sandbox/` — `run-fast-loop.sh` (host
sim stack) and `run-vm.sh` (QEMU/UTM boots the real image, with fault
injection).

## Phase 7 — CI/CD hardening

Promote CI to the full `specs.md` §10 pipeline. PR: lint + unit tests + game
validation + launcher build. Merge to `main`: version-bump, build/package all
components, build the OS image, publish a semver-tagged release artifact. Pin
dependencies; embed build metadata.

## Phase 8 — Field validation

Flash the mini PC, remove the Windows dual-boot, calibrate with a real RPLIDAR.
Verify the §6 acceptance target: unplug the LiDAR mid-operation and confirm
tracking resumes within a few seconds with no operator action. Multi-hour soak;
record in `docs/field-validation.md`; tag the validated release.

## Build / dependency order

- The **touch contract freezes at the end of Phase 1** — prerequisite for
  Phases 2–5.
- **Parallelizable:** Phase 4 can be developed alongside Phases 2–3 against a
  stub WebSocket emitting schema-valid frames.
- **Strictly sequential:** 2→3; 5 needs 4's manifest consumer; 6 needs 2–5
  installable; 7 needs 2–6's build steps; 8 needs 6–7 plus hardware.

## Verification strategy

`SimDriver` makes the whole stack run with **no hardware** until Phase 8. CI on
every PR runs pytest units + sim integration; bridge output and game usage are
validated against `touch-contract.schema.json`; plus ESLint/Prettier, launcher
build, the game validator, and a Playwright smoke test. The VM sandbox (Phase 6)
validates appliance behaviour with fault injection. Phase 8 is the only hardware
step.

## Key risks

| Risk | Mitigation |
|---|---|
| **LiDAR reliability** — the prototype's no-watchdog / silent-stale-data / bare-`except` defects | Phase 2 `ConnectionManager`: exponential backoff, watchdog + forced re-init, `systemd Restart=always`, structured logs; Phase 8 explicitly tests unplug→auto-recover |
| Unknown production sensor | `LidarDriver` ABC isolates vendor code; confirm the target model during Phase 2 |
| Contract churn breaking games/launcher | Freeze the contract end of Phase 1 with a machine-readable schema; CI asserts conformance; changes versioned + backward-compatible |
| History/LFS loss during restructure | `git mv` only; verify `git lfs ls-files` + `git log --follow` |
| Calibration regressions from removing the hardcoded flip | Flip moves into the saved preset; unit-test calibration with known fixtures |

## Notes

- Each phase lands on its own branch and is reviewed before the next begins.
- Open questions U1–U5 in `specs.md` §15 are carried into the phases that need
  them; none block Phase 1.
