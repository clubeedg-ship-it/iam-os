#!/bin/bash
# Boot the just-built IAM-OS image under QEMU and assert that systemd
# reaches multi-user.target with the three IAM-OS services started.
#
# Strategy:
# 1. Extract the kernel + initrd from the image's ESP.
# 2. Boot QEMU with -kernel/-initrd/-append so we can append
#    "clearcpuid=avx,avx2,fma" to the cmdline ONLY in the QEMU run.
#    GitHub runners are TCG-only and TCG does not emulate AVX/AVX2/FMA,
#    so the bundled NumPy wheel hits SIGILL on its first dispatch
#    unless the kernel masks those features from CPUID. The appliance's
#    real boot loader entry stays AVX-friendly.
# 3. Watch the serial log for "Started iam-{lidar,touch-bridge,web}".
#    All three present = boot path is healthy.
#
# Watching the serial log instead of poking /api/status over HTTP
# avoids needing DHCP / port-forward in the guest.

set -euo pipefail

VERSION="${IAM_OS_VERSION:-dev}"
ARCH="${IAM_OS_ARCH:-amd64}"
OUT_DIR="${OUT_DIR:-out}"
BOOT_TIMEOUT="${BOOT_TIMEOUT:-300}"

IMG_GZ="$OUT_DIR/iam-os-${VERSION}-${ARCH}.img.gz"
IMG="$OUT_DIR/iam-os-${VERSION}-${ARCH}.boot.img"
SERIAL_LOG="$OUT_DIR/boot-serial.log"
KERNEL_DIR="$OUT_DIR/boot-extract"

note() { printf '[boot-smoke] %s\n' "$*"; }
fail() { printf '[boot-smoke] FAIL: %s\n' "$*" >&2; exit 1; }

[ -f "$IMG_GZ" ] || fail "image not found: $IMG_GZ"

note "decompressing image for boot"
gunzip -c "$IMG_GZ" > "$IMG"

note "extracting kernel + initrd from ESP"
mkdir -p "$KERNEL_DIR" "$KERNEL_DIR/mnt"
LOOP="$(sudo losetup -fP --show "$IMG")"
sudo mount "${LOOP}p1" "$KERNEL_DIR/mnt"
KERNEL_SRC="$(sudo ls "$KERNEL_DIR/mnt" | grep '^vmlinuz' | sort -V | tail -1)"
INITRD_SRC="$(sudo ls "$KERNEL_DIR/mnt" | grep '^initrd.img' | sort -V | tail -1)"
[ -n "$KERNEL_SRC" ] || { sudo umount "$KERNEL_DIR/mnt"; sudo losetup -d "$LOOP"; fail "no kernel on ESP"; }
[ -n "$INITRD_SRC" ] || { sudo umount "$KERNEL_DIR/mnt"; sudo losetup -d "$LOOP"; fail "no initrd on ESP"; }
sudo cp "$KERNEL_DIR/mnt/$KERNEL_SRC" "$KERNEL_DIR/vmlinuz"
sudo cp "$KERNEL_DIR/mnt/$INITRD_SRC" "$KERNEL_DIR/initrd"
sudo umount "$KERNEL_DIR/mnt"
ROOT_PARTUUID="$(sudo blkid -s PARTUUID -o value "${LOOP}p2")"
sudo losetup -d "$LOOP"
sudo chown "$(id -u):$(id -g)" "$KERNEL_DIR/vmlinuz" "$KERNEL_DIR/initrd"
note "kernel=$KERNEL_SRC initrd=$INITRD_SRC root=PARTUUID=$ROOT_PARTUUID"

CMDLINE="root=PARTUUID=$ROOT_PARTUUID ro console=tty0 console=ttyS0,115200n8 systemd.show_status=yes"
note "kernel cmdline: $CMDLINE"

# QEMU's default "qemu64" CPU only exposes SSE3. NumPy 2.x's baseline
# is x86-64-v2 (SSE4.2), so the bundled wheel SIGILLs on any CPU
# weaker than that — including qemu64. "-cpu max" tells TCG to expose
# every feature it knows how to emulate, which on QEMU 8+ includes
# SSE4.2, AVX, and AVX2. That covers NumPy without touching the
# appliance image.
note "booting under QEMU (TCG -cpu max, headless, serial -> $SERIAL_LOG)"
qemu-system-x86_64 \
    -cpu max \
    -m 2048 \
    -smp 2 \
    -drive "file=$IMG,if=virtio,format=raw" \
    -kernel "$KERNEL_DIR/vmlinuz" \
    -initrd "$KERNEL_DIR/initrd" \
    -append "$CMDLINE" \
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
    rm -rf "$KERNEL_DIR"
}
trap cleanup EXIT

# systemd writes "[ OK ] Started iam-web-server.service ..." but wraps
# the unit name in colour escapes, so a plain literal grep for
# "Started iam-web-server" misses. Strip ANSI before matching.
strip_ansi() {
    sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g'
}

WEB_MARKER='Started iam-web-server'
BRIDGE_MARKER='Started iam-touch-bridge'
LIDAR_MARKER='Started iam-lidar-service'

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
        stripped="$(strip_ansi < "$SERIAL_LOG")"
        if [ "$saw_web" -eq 0 ] && printf '%s\n' "$stripped" | grep -q -F "$WEB_MARKER"; then
            note "marker: web-server"
            saw_web=1
        fi
        if [ "$saw_bridge" -eq 0 ] && printf '%s\n' "$stripped" | grep -q -F "$BRIDGE_MARKER"; then
            note "marker: touch-bridge"
            saw_bridge=1
        fi
        if [ "$saw_lidar" -eq 0 ] && printf '%s\n' "$stripped" | grep -q -F "$LIDAR_MARKER"; then
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
note "last 200 lines of serial log:"
tail -200 "$SERIAL_LOG" 2>/dev/null || echo "(no serial output captured)"
fail "boot did not reach all three IAM-OS service starts within ${BOOT_TIMEOUT}s"
