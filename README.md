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

**All 8 phases of the [implementation plan](docs/IMPLEMENTATION-PLAN.md) are
complete and `v0.1.0` is released**: foundation, lidar-service with R1–R8
reliability, touch-bridge, launcher SPA + web-server, game integration with
validate-games gate, Debian 12 appliance image with systemd-supervised
services + cage/Chromium kiosk, tag-triggered release pipeline with QEMU
boot smoke, and the field validation procedure.

- Latest release (flashable `.img.gz` + checksum):
  <https://github.com/clubeedg-ship-it/iam-os/releases/tag/v0.1.0>
- Field validation procedure: [`docs/field-validation/PROCEDURE.md`](docs/field-validation/PROCEDURE.md)
- Build / CI notes (mmdebstrap, QEMU TCG, NumPy, systemd quirks):
  [`docs/build-notes.md`](docs/build-notes.md)
- Host dev loop (no hardware): `./sandbox/run-fast-loop.sh`
