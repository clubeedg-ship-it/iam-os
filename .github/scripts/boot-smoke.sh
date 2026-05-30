#!/bin/bash
# Boot the just-built IAM-OS image under QEMU and assert that the launcher
# becomes reachable. Catches the regression class where the rootfs is well
# formed but the image does not actually boot — exactly the bug Phase 8
# would otherwise discover in person on real hardware.
#
# Headless, TCG (no KVM in standard GitHub runners). Waits up to BOOT_TIMEOUT
# seconds for GET /api/status to return 200 on the forwarded launcher port.

set -euo pipefail

VERSION="${IAM_OS_VERSION:-dev}"
ARCH="${IAM_OS_ARCH:-amd64}"
OUT_DIR="${OUT_DIR:-out}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-180}"
HTTP_PORT="${HTTP_PORT:-18080}"

IMG_GZ="$OUT_DIR/iam-os-${VERSION}-${ARCH}.img.gz"
IMG="$OUT_DIR/iam-os-${VERSION}-${ARCH}.boot.img"

note() { printf '[boot-smoke] %s\n' "$*"; }
fail() { printf '[boot-smoke] FAIL: %s\n' "$*" >&2; exit 1; }

[ -f "$IMG_GZ" ] || fail "image not found: $IMG_GZ"

note "decompressing image for boot"
gunzip -c "$IMG_GZ" > "$IMG"

# OVMF firmware path varies; check both Ubuntu default and the older split path.
for candidate in /usr/share/OVMF/OVMF_CODE.fd /usr/share/ovmf/OVMF.fd /usr/share/qemu/OVMF.fd; do
    if [ -f "$candidate" ]; then
        OVMF="$candidate"
        break
    fi
done
[ -n "${OVMF:-}" ] || fail "OVMF firmware not found — install package ovmf"

note "booting under QEMU (TCG, headless, http forward :$HTTP_PORT -> :8080)"
qemu-system-x86_64 \
    -m 2048 \
    -smp 2 \
    -bios "$OVMF" \
    -drive "file=$IMG,if=virtio,format=raw" \
    -netdev "user,id=net0,hostfwd=tcp::$HTTP_PORT-:8080" \
    -device virtio-net-pci,netdev=net0 \
    -nographic \
    -serial mon:stdio \
    -monitor none \
    > "$OUT_DIR/boot-serial.log" 2>&1 &
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

note "polling http://127.0.0.1:$HTTP_PORT/api/status (timeout ${BOOT_TIMEOUT}s)"
deadline=$(( $(date +%s) + BOOT_TIMEOUT ))
while [ "$(date +%s)" -lt "$deadline" ]; do
    if ! kill -0 "$QEMU_PID" 2>/dev/null; then
        note "QEMU exited before /api/status came up"
        tail -50 "$OUT_DIR/boot-serial.log" || true
        fail "QEMU exited prematurely"
    fi
    if curl -fsS --max-time 2 "http://127.0.0.1:$HTTP_PORT/api/status" >/dev/null 2>&1; then
        body="$(curl -s "http://127.0.0.1:$HTTP_PORT/api/status")"
        note "launcher responded: $body"
        note "BOOT SMOKE PASSED"
        exit 0
    fi
    sleep 2
done

note "timed out after ${BOOT_TIMEOUT}s; tail of serial log:"
tail -100 "$OUT_DIR/boot-serial.log" || true
fail "launcher did not respond within ${BOOT_TIMEOUT}s"
