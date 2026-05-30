#!/bin/bash
# Capture the IAM-OS appliance state for a Phase 8 field validation run.
#
# Designed to be run over SSH on the appliance, e.g.:
#
#   ssh iam-os@<host> 'bash -s' < scripts/appliance-diag.sh
#   scp iam-os@<host>:/tmp/iam-os-diag-*.tar.gz docs/field-validation/runs/
#
# Captures everything a reviewer needs to confirm what was running when
# the test executed: version + git SHA from /etc/iam-os-version, the
# four IAM-OS systemd units' status, the lidar status JSON, USB device
# enumeration, kernel ring buffer entries about the LiDAR adapter, and
# the boot's journald log filtered to the IAM-OS units.
#
# Read-only: no sudo required, no state changes on the appliance.

set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_DIR="/tmp/iam-os-diag-$STAMP"
TAR="/tmp/iam-os-diag-$STAMP.tar.gz"

mkdir -p "$OUT_DIR"

capture() {
    local name="$1"
    shift
    {
        printf '## $ %s\n' "$*"
        printf '## (captured %sZ)\n\n' "$(date -u +%Y-%m-%dT%H:%M:%S)"
        "$@" 2>&1 || printf '\n## (exit %d)\n' "$?"
    } > "$OUT_DIR/$name.txt"
}

# Version and identity.
cp /etc/iam-os-version "$OUT_DIR/iam-os-version.txt" 2>/dev/null \
    || echo "no /etc/iam-os-version present" > "$OUT_DIR/iam-os-version.txt"
capture os-release       cat /etc/os-release
capture uname            uname -a
capture uptime           uptime

# IAM-OS service health.
for unit in iam-lidar-service iam-touch-bridge iam-web-server iam-os-kiosk; do
    capture "systemctl-$unit" systemctl status "$unit.service" --no-pager
done
capture systemd-default-target  systemctl get-default

# Runtime artifacts.
if [ -f /run/iam-os/lidar-status.json ]; then
    cp /run/iam-os/lidar-status.json "$OUT_DIR/lidar-status.json"
fi
capture run-iam-os-dir   ls -lR /run/iam-os

# Hardware / kernel view of the LiDAR adapter.
capture lsusb            lsusb
capture lsusb-tree       lsusb -t
capture dev-tty          ls -l /dev/iam-lidar /dev/ttyUSB* 2>/dev/null
capture dmesg-lidar      dmesg -T --color=never \
    | grep -iE 'lidar|cp210|ftdi|usbserial|ttyusb' || true

# Networking (so the dev host's SSH/IP context is recorded).
capture ip-addr          ip -brief address

# This-boot logs for the IAM-OS units, including the kiosk's cage stderr.
journalctl -b 0 --no-pager \
    -u iam-lidar-service.service \
    -u iam-touch-bridge.service \
    -u iam-web-server.service \
    -u iam-os-kiosk.service \
    > "$OUT_DIR/journal-iam-os-this-boot.log" 2>&1 || true

# The full this-boot journal as well (smaller appliance, fine to ship).
journalctl -b 0 --no-pager > "$OUT_DIR/journal-this-boot.log" 2>&1 || true

# Bundle.
tar -czf "$TAR" -C /tmp "$(basename "$OUT_DIR")"
rm -rf "$OUT_DIR"

echo "diag bundle: $TAR"
ls -lh "$TAR"
