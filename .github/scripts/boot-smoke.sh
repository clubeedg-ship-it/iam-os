#!/bin/bash
# Boot the just-built IAM-OS image under QEMU and assert that systemd
# reaches multi-user.target with the three IAM-OS services started.
#
# We watch the serial console output rather than poking the launcher
# over HTTP: a port forward into the guest needs the guest to have a
# DHCP-configured network interface, and configuring DHCP in the
# appliance image purely to satisfy CI smoke would change the
# appliance's actual surface. The serial log proves the boot path
# without that detour.

set -euo pipefail

VERSION="${IAM_OS_VERSION:-dev}"
ARCH="${IAM_OS_ARCH:-amd64}"
OUT_DIR="${OUT_DIR:-out}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-300}"

IMG_GZ="$OUT_DIR/iam-os-${VERSION}-${ARCH}.img.gz"
IMG="$OUT_DIR/iam-os-${VERSION}-${ARCH}.boot.img"
SERIAL_LOG="$OUT_DIR/boot-serial.log"

note() { printf '[boot-smoke] %s\n' "$*"; }
fail() { printf '[boot-smoke] FAIL: %s\n' "$*" >&2; exit 1; }

[ -f "$IMG_GZ" ] || fail "image not found: $IMG_GZ"

note "decompressing image for boot"
gunzip -c "$IMG_GZ" > "$IMG"

for candidate in /usr/share/OVMF/OVMF_CODE.fd /usr/share/ovmf/OVMF.fd /usr/share/qemu/OVMF.fd; do
    if [ -f "$candidate" ]; then
        OVMF="$candidate"
        break
    fi
done
[ -n "${OVMF:-}" ] || fail "OVMF firmware not found — install package ovmf"

note "booting under QEMU (TCG, headless, serial -> $SERIAL_LOG)"
qemu-system-x86_64 \
    -m 2048 \
    -smp 2 \
    -bios "$OVMF" \
    -drive "file=$IMG,if=virtio,format=raw" \
    -nographic \
    -serial "file:$SERIAL_LOG" \
    -monitor none \
    > /dev/null 2>&1 &
QEMU_PID=$!

# shellcheck disable=SC2329  # invoked indirectly via trap.
cleanup() {
    if kill -0 "$QEMU_PID" 2>/dev/null; then
        note "stopping QEMU (pid $QEMU_PID)"
        kill -TERM "$QEMU_PID" 2>/dev/null || true
        sleep 1
        kill -KILL "$QEMU_PID" 2>/dev/null || true
    fi
    rm -f "$IMG"
}
trap cleanup EXIT

# The markers we expect from a healthy boot. systemd's status lines are
# locale-stable English under our cmdline.
WEB_MARKER='Started iam-web-server.service'
BRIDGE_MARKER='Started iam-touch-bridge.service'
LIDAR_MARKER='Started iam-lidar-service.service'

note "watching serial log for IAM-OS service starts (timeout ${BOOT_TIMEOUT}s)"
deadline=$(( $(date +%s) + BOOT_TIMEOUT ))
saw_web=0
saw_bridge=0
saw_lidar=0

while [ "$(date +%s)" -lt "$deadline" ]; do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        note "QEMU exited before all markers seen"
        break
    fi
    if [ -f "$SERIAL_LOG" ]; then
        if [ "$saw_web" -eq 0 ] && grep -q -F "$WEB_MARKER" "$SERIAL_LOG" 2>/dev/null; then
            note "marker: web-server"
            saw_web=1
        fi
        if [ "$saw_bridge" -eq 0 ] && grep -q -F "$BRIDGE_MARKER" "$SERIAL_LOG" 2>/dev/null; then
            note "marker: touch-bridge"
            saw_bridge=1
        fi
        if [ "$saw_lidar" -eq 0 ] && grep -q -F "$LIDAR_MARKER" "$SERIAL_LOG" 2>/dev/null; then
            note "marker: lidar-service"
            saw_lidar=1
        fi
        if [ "$saw_web" -eq 1 ] && [ "$saw_bridge" -eq 1 ] && [ "$saw_lidar" -eq 1 ]; then
            note "all three IAM-OS services started — BOOT SMOKE PASSED"
            exit 0
        fi
    fi
    sleep 2
done

note "missing markers — web=$saw_web bridge=$saw_bridge lidar=$saw_lidar"
note "last 150 lines of serial log:"
tail -150 "$SERIAL_LOG" 2>/dev/null || echo "(no serial output captured)"
fail "boot did not reach all three IAM-OS service starts within ${BOOT_TIMEOUT}s"
