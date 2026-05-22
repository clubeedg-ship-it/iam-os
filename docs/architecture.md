# IAM-OS Architecture

A developer-facing summary. The authoritative specification is
[`../specs.md`](../specs.md) (§3–§6); where they differ, `specs.md` wins.

## Shape

IAM-OS is a **Linux kiosk appliance**. The mini PC boots a minimal Linux OS with
no desktop environment, auto-logs in, and launches Chromium full-screen showing
the web-based Launcher UI. Three background services — all supervised by
`systemd` with automatic restart — do the work.

```
                          MINI PC  (IAM-OS, minimal Linux)

  [ LiDAR sensor ] --USB--> ┌──────────────────┐
                            │  lidar-service   │  device driver, tracking,
                            │                  │  calibration, watchdog
                            └────────┬─────────┘
                                     │ internal touch frames (Unix socket)
                            ┌────────▼─────────┐
                            │   touch-bridge   │  normalises to the contract
                            └────────┬─────────┘
                                     │ ws://localhost:8765
                            ┌────────▼─────────┐
                            │   web-server     │  serves launcher + games
                            └────────┬─────────┘
                                     │ http://localhost
                            ┌────────▼─────────┐
                            │ Chromium (kiosk) │ ──HDMI──> [ beamer / surface ]
                            │ launcher + game  │
                            └──────────────────┘
```

## Components

1. **lidar-service** (Python) — owns the LiDAR device behind a vendor-agnostic
   `LidarDriver` interface: auto-detection, exponential-backoff reconnect, a
   scan watchdog, and health reporting. Runs the tracking pipeline (baseline →
   calibration → clustering → touch IDs) and emits internal touch frames.
2. **touch-bridge** (Python) — adapts internal frames to the frozen WebSocket
   touch contract and broadcasts them on `ws://localhost:8765`.
3. **web-server** (Python) — serves the launcher and games and exposes a small
   control API (LiDAR status, calibration presets, game manifest).

The Launcher UI and the games are web clients of `ws://localhost:8765`.

## Data flow

LiDAR scan → lidar-service (track) → internal frames → touch-bridge (normalise)
→ `ws://localhost:8765` → launcher / active game → Chromium → beamer → surface.
A hand on the surface becomes a touch in the projection.

## Key boundaries

- **Touch contract** ([`touch-contract.md`](./touch-contract.md)) — the frozen
  interface between the platform and games; the single most important boundary.
- **`LidarDriver` interface** — isolates vendor-specific sensor code, so a new
  sensor needs only a new driver, not changes to the pipeline.

## Reliability

The "always works" requirement is met by engineering discipline, not a paid
plugin: config-driven parameters (no hardcoded device values), auto-reconnect
with backoff, a scan watchdog that kills stale data, `systemd` supervision, and
structured logging. See `specs.md` §6.
