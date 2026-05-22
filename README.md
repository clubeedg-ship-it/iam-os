# IAM-OS

Software for the InterActiveMove (IAM) interactive projection appliance.

A mini PC running IAM-OS drives a LiDAR sensor and a beamer: the LiDAR scans a
wall or floor, the beamer projects games onto that surface, and hand or foot
positions become touch events that make the projection interactive.

## Documentation

- **[`specs.md`](./specs.md)** — the project specification (source of truth).
- **[`docs/architecture.md`](./docs/architecture.md)** — architecture overview.
- **[`docs/IMPLEMENTATION-PLAN.md`](./docs/IMPLEMENTATION-PLAN.md)** — the phased build plan.
- **[`docs/touch-contract.md`](./docs/touch-contract.md)** — the frozen touch event contract (v1.0.0).

## Repository layout

| Path | Contents |
|---|---|
| `services/lidar-service/` | LiDAR device driver, tracking, calibration (Python) |
| `services/touch-bridge/` | Normalises touch frames onto `ws://localhost:8765` |
| `services/web-server/` | Serves the launcher and games |
| `launcher/` | Operator UI — calibrate, test, select games |
| `games/` | Self-contained HTML games |
| `os-image/` | Minimal Linux appliance image build |
| `sandbox/` | Developer simulation and VM sandbox |
| `docs/` | Specifications and design documents |
| `legacy/` | Reference-only prior code — see [`legacy/README.md`](./legacy/README.md) |

## Architecture in brief

IAM-OS is a **Linux kiosk appliance**: a minimal Linux OS boots straight into a
full-screen Chromium kiosk showing the launcher, backed by three
`systemd`-supervised services. See [`docs/architecture.md`](./docs/architecture.md).

## Status

Early development — **Phase 1 (Foundation)** of the implementation plan. The
`services/`, `launcher/`, and `games/` directories are scaffolding; their code
lands in later phases.
