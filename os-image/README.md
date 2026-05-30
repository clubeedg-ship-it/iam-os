# os-image/

Everything needed to turn the IAM-OS source tree into a Debian 12 appliance.

## Contents

| Path | What it is |
|---|---|
| `units/iam-lidar-service.service` | systemd unit for `lidar-service`, runs as `iam-os` in the `dialout` group, `Restart=always`. |
| `units/iam-touch-bridge.service` | systemd unit for `touch-bridge`, `Requires=` lidar. |
| `units/iam-web-server.service` | systemd unit for `web-server`, `Requires=` bridge. |
| `units/iam-os-kiosk.service` | Wayland kiosk session (cage + Chromium) on tty1, `Restart=always`. |
| `tmpfiles.d/iam-os.conf` | Owns `/run/iam-os/` so the services find a stable runtime dir. |
| `udev/99-iam-lidar.rules` | Symlinks the LiDAR USB serial as `/dev/iam-lidar`, grants `dialout` access. |
| `chromium-kiosk.sh` | The Chromium command line — no infobars, no first-run, no update checks, the previous-crash "restore tabs" prompt suppressed. |
| `build.sh` | mmdebstrap-based Debian 12 rootfs builder. Linux-only. |

## What `build.sh` does

Produces a rootfs tarball at `out/iam-os-<version>-amd64-rootfs.tar.gz`:

1. mmdebstrap a minbase Debian 12 (`bookworm`) with `systemd-sysv`, `udev`,
   `chromium`, `cage`, `python3-venv`, etc.
2. Copies `services/`, `launcher/dist/`, `games/`, and this directory's
   units / tmpfiles / udev / kiosk script into the rootfs.
3. Creates the unprivileged `iam-os` user (`dialout`, `tty`, `video`).
4. Creates a venv per service and `pip install`s the package into it.
5. Enables the three service units and the kiosk session; sets the default
   target to `graphical.target` so a flashed image boots straight into the
   launcher.

Output is a **rootfs tarball**, not a bootable `.img`. The bootloader,
partition table, and EFI system partition are deferred to Phase 7
(CI/CD hardening), so currently the tarball is what the `sandbox/run-vm.sh`
script consumes once you wrap it in a disk image yourself.

## Why these dependency choices

| Choice | Reason |
|---|---|
| Debian 12 (`bookworm`) minbase | Stable, scriptable, systemd-first, strong Chromium and Wayland support; matches `docs/IMPLEMENTATION-PLAN.md` tech decisions. |
| mmdebstrap (vs `debootstrap`) | Runs unprivileged; produces reproducible tarballs; works in containers and on CI runners. |
| cage (vs Xorg + window manager) | Single-app Wayland kiosk; no panel, no decorations, no escape hatch — matches the appliance threat model. |
| Chromium (vs Firefox) | Smaller in `minbase`, faster startup, matches the reference game and launcher CSS. |

## Why no bootable image in Phase 6

The implementation plan explicitly scopes Phase 7 to *CI/CD hardening
including building the OS image*; Phase 6 is the kiosk + supervision
layer the image needs. Wrapping the rootfs in a flashable disk requires
GRUB / systemd-boot setup, partition tooling (`parted`, `mkfs.ext4`,
loop devices), and signed EFI handling — all of which is meaningful
work that belongs with the release pipeline, not with the OS layout.
