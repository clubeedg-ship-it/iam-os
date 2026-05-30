# sandbox/

Two ways to run IAM-OS without flashing the appliance.

| Script | What it does | When to use |
|---|---|---|
| `run-fast-loop.sh` | Boots `lidar-service --simulate`, `touch-bridge`, and `web-server` on the host. Launcher opens at `http://127.0.0.1:8080/`. | Daily development. No hardware, no VM, no sudo. Works on Linux and macOS. |
| `run-vm.sh` | Boots the IAM-OS appliance image under QEMU with KVM (Linux) or HVF (macOS) acceleration. | Verifying systemd ordering, the kiosk session, and the udev rule against a real Debian environment before flashing. |

## `run-fast-loop.sh`

```sh
./sandbox/run-fast-loop.sh
```

- Creates the per-service venvs on first run; reuses them after.
- Builds `launcher/dist/` if absent.
- Wires runtime artifacts under `/tmp/iam-os/`: the LiDAR socket, the
  status JSON, the calibration store.
- Logs go to `/tmp/iam-os/logs/{lidar,bridge,web-server}.log`.
- Ctrl-C cleanly stops all three services.

Environment overrides: `IAM_OS_WEB_PORT`, `IAM_OS_BRIDGE_PORT`,
`IAM_OS_RUN_DIR`, `IAM_OS_LOG_DIR`.

## `run-vm.sh`

```sh
./sandbox/run-vm.sh
```

Expects an appliance image at `out/iam-os.qcow2` (overridable via
`IAM_OS_VM_IMAGE`). Until Phase 7 produces a bootable image,
`run-vm.sh` reports the missing piece with a pointer at
`os-image/build.sh`.

Port forwards from the host to the guest:

| Host port | Guest port | Purpose |
|---|---|---|
| 2222 | 22 | SSH into the appliance for diagnostics |
| 18080 | 8080 | Launcher (`/api/status`, `/#/games`, etc.) |
| 18765 | 8765 | Touch contract WebSocket for external games |

Environment overrides: `IAM_OS_VM_RAM`, `IAM_OS_VM_CPUS`,
`IAM_OS_VM_IMAGE`, `IAM_OS_VM_SSH_PORT`, `IAM_OS_VM_HTTP_PORT`,
`IAM_OS_VM_WS_PORT`.
