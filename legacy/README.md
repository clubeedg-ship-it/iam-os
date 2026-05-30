# Legacy / Reference Material

Everything in this directory is **reference-only**. It is not built upon, not
maintained, and not part of the IAM-OS build or appliance image. It is kept so
the new implementation can be checked against prior behaviour. See `specs.md`
§14.

## Contents

- **`og-iam-lidar-tracker/`** — the original Python LiDAR tracking prototype.
  Its logic (RPLIDAR over serial, perspective-transform calibration, clustering,
  touch output) is the basis for the new `services/lidar-service/`, but that
  service is a hardened reimplementation — not a copy. The prototype's known
  defects (no watchdog, silent stale data on disconnect, bare `except`, no
  logging) are exactly what the rewrite fixes.
- **`iam-game-menu/`** — a compiled Qt5/C++ Windows application
  (`LidarTracker.exe`), binary only — no source code is available. Reference for
  observed behaviour only. Contains a 184 MB installer tracked via Git LFS.
- **`stapzone_training_v8_pro.html`** — re-homed in Phase 5 to
  [`../games/stapzone-training/index.html`](../games/stapzone-training/index.html)
  and listed in `games/manifest.json`. Its original Phase 1 role was as the
  reference for the game model and the touch contract; the live, validated
  copy is now under `games/`.
