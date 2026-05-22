# IAM-OS — Project Specification

| | |
|---|---|
| **Project** | IAM-OS — Interactive Wall/Floor appliance software |
| **Status** | Draft v0.1 — pending review |
| **Date** | 2026-05-22 |
| **Owner** | omiximo / InterActiveMove (IAM) |
| **Repository** | `clubeedg-ship-it/iam-os` |
| **Language of this document** | English |

---

## 1. Product Overview

IAM-OS is the software that runs on a **mini PC appliance** powering an
InterActiveMove (IAM) interactive projection installation.

The installation consists of:

- A **mini PC** running IAM-OS.
- A **LiDAR sensor** that scans a flat projection surface (a wall or a floor).
- A **beamer (projector)** that projects content onto that same surface.

When a person moves a hand near the wall (or steps on the floor), the LiDAR
detects the position. IAM-OS converts that detection into a **touch event** and
delivers it to the projected content, making the projection interactive.

IAM-OS provides an operator-facing application to **calibrate** the sensor to
the projection surface, **test** that tracking works, and **select and launch
games** (interactive programs).

Reference product context: <https://iam.abbamarkt.nl>.

## 2. Goals and Non-Goals

### 2.1 Goals

- **G1 — Linux appliance.** IAM-OS targets a lightweight Linux operating system
  on the mini PC. The appliance boots straight into the application with no
  desktop environment. Windows is not a target; it is used only as a temporary
  dual-boot during development and will be removed.
- **G2 — Reliable LiDAR connection.** The connection to the LiDAR sensor must be
  dependable and self-healing, with no manual intervention during normal
  operation. See §6.
- **G3 — Free and open dependency stack.** No paid, closed-source plugin or SDK.
  The LiDAR is driven through open-source libraries or its documented protocol.
- **G4 — Operator application.** A clear interface to calibrate, test, and
  select/launch games.
- **G5 — Professional engineering from day one.** Versioned releases, automated
  CI/CD, reproducible builds, automated tests. No ad-hoc fixes, no hardcoded
  device parameters.
- **G6 — Easy game delivery.** Adding or fixing a game is a routine, pipeline-
  driven change, not a manual deployment.
- **G7 — Developer sandbox.** A way to run and see the UI without physical
  hardware, including a Linux VM that mirrors the appliance.

### 2.2 Non-Goals

- Not a distributable consumer desktop application — IAM-OS is a fixed-hardware
  appliance image.
- Not a Windows product.
- Building new games is out of scope for this specification; this document
  defines the *platform* that runs and delivers games.
- The website (`iam.abbamarkt.nl`) and any cloud/marketing systems are out of
  scope.

## 3. System Architecture

IAM-OS uses a **Linux kiosk appliance** architecture: a minimal Linux OS that
auto-starts a browser in kiosk mode, backed by local background services that
are supervised by `systemd`. There is no Electron or other heavy app runtime —
the operator UI is a locally served web application.

```
                          MINI PC  (IAM-OS, minimal Linux)

  [ LiDAR sensor ] --USB--> ┌─────────────────┐
                            │  lidar-service   │  Python
                            │  (device driver, │  - auto-detect / reconnect
                            │   tracking,      │  - watchdog
                            │   calibration)   │  - emits touch frames
                            └────────┬─────────┘
                                     │ internal touch frames
                            ┌────────▼─────────┐
                            │   touch-bridge   │  emits normalized JSON
                            │                  │  on ws://localhost:8765
                            └────────┬─────────┘
                                     │ WebSocket  {count, touches:[{id,x,y}]}
                            ┌────────▼─────────┐
                            │   web-server     │  serves launcher + games
                            └────────┬─────────┘
                                     │ http://localhost
                            ┌────────▼─────────┐
                            │ Chromium (kiosk) │ ──HDMI──> [ Beamer / wall ]
                            │  Launcher UI     │
                            │  + active game   │
                            └──────────────────┘

  All services run as systemd units with automatic restart.
```

## 4. Components

### 4.1 LiDAR Service (`services/lidar-service/`)

Python service that owns the LiDAR device end to end.

- **Driver abstraction.** A `LidarDriver` interface defines a vendor-agnostic
  contract (connect, stream scans, disconnect, health). Concrete drivers
  implement it (e.g. an RPLIDAR driver). New sensors are added by writing a new
  driver, never by editing core logic.
- **Connection management.** Device and serial parameters are discovered or read
  from configuration — never hardcoded. Includes auto-detection, retry with
  backoff, and a watchdog (see §6).
- **Tracking pipeline.** Raw scans → baseline subtraction → calibration
  transform → clustering → stable touch IDs → touch frames.
- **Output.** Internal touch frames consumed by the touch bridge.
- **Simulation mode.** A built-in simulator emits synthetic touch frames so the
  full stack runs without hardware (see §9).

This service is the hardened successor to the existing `OG-IAM-LiDAR- Tracker`
Python prototype, which is treated as reference material.

### 4.2 Touch Bridge (`services/touch-bridge/`)

Adapts internal touch frames to the **WebSocket touch contract** that games and
the launcher already speak. Listens on `ws://localhost:8765`.

Touch message contract (JSON):

```json
{
  "seq": 1234,
  "count": 1,
  "touches": [
    { "id": 0, "x": 0.42, "y": 0.71 }
  ]
}
```

- `x`, `y` are normalized to the projection surface, range `0.0`–`1.0`.
- `count` is the number of active touches.
- `id` is a stable identifier for the lifetime of a touch.
- `seq` is a monotonically increasing frame counter.

This contract is **frozen** — it is the integration boundary between the
platform and all games. Changes are versioned and backward-compatible.

### 4.3 Launcher UI (`launcher/`)

A lightweight web application — the operator-facing application. Runs full-
screen in Chromium kiosk. Responsibilities:

- **Calibrate** — guided calibration of the LiDAR to the projection surface
  (§7), with named, savable presets.
- **Test** — a live view that visualizes touches so an operator can confirm
  tracking before use.
- **Select & launch games** — a menu of installed games; launching a game hands
  the screen to that game's HTML.
- **Status** — connection/health indicators for the LiDAR service.

Built with a lightweight web stack (no heavy framework required). Consumes the
same `ws://localhost:8765` contract as games, plus a small local control API on
the web server for calibration and service status.

### 4.4 Games (`games/`)

Each game is a **self-contained HTML file** (with its own JS/CSS/assets) that:

- Opens `ws://localhost:8765` and reads the touch contract from §4.2.
- Includes a mouse fallback for development.
- Treats touch coordinates as normalized `0.0`–`1.0`.

This model is taken from the existing `stapzone_training_v8_pro.html` reference
game and is kept deliberately simple and dependency-free.

### 4.5 OS Image & Kiosk (`os-image/`)

A reproducible build of the appliance:

- Minimal Linux base, no desktop environment.
- Auto-login to a kiosk session that launches Chromium full-screen pointed at
  the local launcher.
- All IAM-OS services installed as `systemd` units.
- Output is a flashable image artifact, version-tagged.

### 4.6 Process Supervision

`systemd` supervises `lidar-service`, `touch-bridge`, and `web-server`. Every
unit restarts automatically on failure. The kiosk Chromium session restarts if
it exits. This supervision layer is where the reliability requirement (G2) is
enforced at the OS level.

## 5. Data Flow

1. The LiDAR streams range scans over USB to `lidar-service`.
2. `lidar-service` applies baseline, calibration, and clustering, producing
   internal touch frames.
3. `touch-bridge` normalizes frames into the §4.2 JSON contract and serves them
   on `ws://localhost:8765`.
4. The Launcher UI and the active game connect to that WebSocket and react to
   touches.
5. Chromium renders the launcher/game; the beamer projects it onto the surface.
6. The loop closes: a hand on the surface becomes a touch in the projection.

## 6. LiDAR Connection & Reliability

The reliability requirement (G2) is met by **engineering discipline**, not a
paid plugin. The existing free libraries are assumed adequate; past
unreliability is attributed to a disorganised, unsupervised runtime environment.

Requirements:

- **R1 — No hardcoded device parameters.** Serial port, baud rate, and device
  model come from auto-detection and/or a configuration file.
- **R2 — Auto-detection.** On start, the service discovers the LiDAR by scanning
  available serial devices and matching known adapters.
- **R3 — Auto-reconnect.** On any disconnect or read error, the service retries
  with exponential backoff and recovers without operator action.
- **R4 — Watchdog.** If scans stop arriving within a defined timeout, the
  service treats the device as failed and re-initialises it.
- **R5 — Supervised process.** `systemd` restarts the service if the process
  itself dies (§4.6).
- **R6 — Health reporting.** The service exposes its connection state so the
  launcher can display it and so failures are observable.
- **R7 — Structured logging.** All connection events are logged for diagnosis;
  no silent failures.
- **R8 — Vendor-agnostic.** The reconnection and health logic lives above the
  `LidarDriver` interface, so it applies to any supported sensor.

Acceptance target: after an unplanned device disconnect, tracking resumes
automatically within a few seconds with no operator intervention.

## 7. Calibration

Calibration maps the LiDAR's coordinate space to the normalized projection
surface so that a touch lands where the user expects.

- The operator marks the **four corners** of the projection surface.
- A **perspective transform** maps sensor space → normalized `0.0`–`1.0` space.
- Calibrations are stored as **named presets** (e.g. one per installation site
  or per surface), selectable from the launcher.
- The active preset is persisted and reloaded on boot.

This generalises the approach in the existing Python prototype
(`calibration.json` presets + OpenCV perspective transform) into a guided UI
flow with no hardcoded flip or corner values.

## 8. Game Model & Adding Games

Games are HTML files that conform to §4.4. Adding or fixing a game is a routine
change:

1. Add or edit the game's HTML under `games/`.
2. Open a pull request.
3. CI validates the game (file structure, that it loads, contract usage).
4. On merge, the game is packaged into the next build/release.

The launcher discovers installed games from a manifest, so no launcher code
changes are needed to add a game.

## 9. Development Environment & Sandbox

Two tiers, so the UI can be seen and the appliance validated without the
physical installation:

- **Fast loop (host machine).** Run `lidar-service` in **simulation mode** plus
  `touch-bridge`, `web-server`, and the launcher directly on the developer's
  machine. The UI opens in a normal browser; synthetic touches drive it. No
  hardware, no VM. This is the day-to-day development environment.
- **Integration sandbox (Linux VM).** A Linux **virtual machine** (e.g. QEMU /
  UTM) runs the full appliance configuration — the OS image, `systemd` units,
  and Chromium kiosk — so the real appliance behaviour can be verified before
  flashing the mini PC. This is where the UI is seen exactly as it will run on
  the device.

Both tiers are scripted and reproducible under `sandbox/`.

## 10. CI/CD

Automated with **GitHub Actions**.

- **On pull request:** lint (Python + JS), run unit tests, validate game HTML
  files against the §4.4 model, build the launcher.
- **On merge to `main`:** build and version all components, package games, build
  the appliance OS image, and publish a tagged release artifact.
- **Releases** are versioned (semantic versioning) so any appliance can be
  traced to an exact build.
- **Adding a game** flows through the same pipeline — drop an HTML file, open a
  PR, merge, release.

No manual builds or manual deployments.

## 11. Repository Structure (target)

```
iam-os/
├── specs.md                  # this document
├── README.md
├── .gitignore                # to be added
├── .gitattributes            # Git LFS config (large binaries)
├── services/
│   ├── lidar-service/        # Python: driver, tracking, calibration, watchdog
│   └── touch-bridge/         # internal frames -> ws://localhost:8765
├── launcher/                 # operator web app: calibrate / test / select
├── games/                    # standalone HTML games + manifest
├── os-image/                 # minimal Linux build, kiosk + systemd units
├── sandbox/                  # simulate-mode tooling + Linux dev VM
├── docs/
├── legacy/                   # reference-only material (see §14)
└── .github/workflows/        # CI/CD pipelines
```

The current top-level folders (`IAM-GAME-MENU/`, `OG-IAM-LiDAR- Tracker/`) will
be reorganised into this structure during implementation; see §14.

## 12. Technology Stack

| Layer | Choice |
|---|---|
| Appliance OS | Minimal Linux distribution (selection during planning) |
| Process supervision | `systemd` |
| LiDAR service | Python 3 (open-source LiDAR libraries / documented protocol) |
| Touch bridge | Python or Node — WebSocket server |
| Launcher UI | Lightweight web application (HTML/CSS/JS) |
| Games | Self-contained HTML files |
| Display | Chromium in kiosk mode |
| CI/CD | GitHub Actions |
| Large binaries | Git LFS |
| Dev sandbox | Host simulation mode + Linux VM (QEMU/UTM) |

## 13. Roadmap (indicative phases)

1. **Foundation** — repository restructure, `.gitignore`, CI skeleton, the §4.2
   touch contract frozen.
2. **LiDAR service** — `LidarDriver` abstraction, auto-detect, reconnect,
   watchdog, simulation mode; ported and hardened from the Python prototype.
3. **Touch bridge** — WebSocket server implementing the touch contract.
4. **Launcher UI** — calibrate, test, select/launch games; status display.
5. **Game integration** — package the reference game; define the game manifest
   and validation.
6. **Appliance OS image** — minimal Linux, kiosk session, `systemd` units, the
   Linux VM sandbox.
7. **CI/CD hardening** — full build/release pipeline, versioned image artifacts.
8. **Field validation** — install on the mini PC, validate reliability targets.

## 14. Legacy / Reference Assets

These are kept for reference only. They are not built upon and not maintained:

- **`IAM-GAME-MENU/`** — a compiled Qt5/C++ Windows application (`LidarTracker.exe`)
  with no source code available. Reference only.
- **`OG-IAM-LiDAR- Tracker/`** — the Python LiDAR tracking prototype. Its logic
  (RPLIDAR over serial, perspective-transform calibration, clustering, TUIO
  output) is the **basis** for the new `lidar-service`, but it is reimplemented
  to meet §6, not adopted as-is.
- **`stapzone_training_v8_pro.html`** — an existing single-file training game.
  Reference for the §4.4 game model and the §4.2 touch contract.

## 15. Open Questions / Unknowns

To be resolved during planning:

- **U1 — LiDAR model(s).** The exact sensor model(s) in the production fleet are
  not yet documented. The changelog of the legacy app references RPLIDAR
  S2 / S2E / C1 and SIMINICS PAVO2. The driver abstraction (§4.1) covers this,
  but the first concrete driver target must be confirmed.
- **U2 — The paid closed-source plugin.** The vendor and identity of the paid
  plugin (and whether it is the legacy app's `NUISensorBase.dll`) are not
  documented. IAM-OS does not depend on it; this is recorded only to confirm
  nothing carries it forward.
- **U3 — Projection surface.** Whether installations are wall, floor, or both
  per site — affects calibration UX wording and game layout assumptions.
- **U4 — Game catalogue.** Where the existing game library lives and how many
  games must be migrated to the §4.4 model.
- **U5 — Linux distribution.** The specific minimal Linux base for the appliance
  image is to be selected during the Foundation phase.
