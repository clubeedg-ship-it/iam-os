#!/bin/bash
# Boot the IAM-OS appliance image under QEMU.
#
# Phase 6 produces a rootfs tarball via os-image/build.sh, not yet a
# flashable disk image — bootloader + partition table are Phase 7 work.
# Until then, this script expects a disk image at out/iam-os.qcow2 (or
# whatever IAM_OS_VM_IMAGE points at). When that file exists it boots
# the VM with a sane KVM-or-TCG default; otherwise it points the user at
# the missing piece.
#
# Works on Linux (qemu-system-x86_64, KVM when available) and macOS
# (qemu-system-x86_64 from brew, HVF accel).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="${IAM_OS_VM_IMAGE:-$REPO_ROOT/out/iam-os.qcow2}"
RAM="${IAM_OS_VM_RAM:-2048}"
CPUS="${IAM_OS_VM_CPUS:-2}"
SSH_PORT="${IAM_OS_VM_SSH_PORT:-2222}"
HTTP_PORT="${IAM_OS_VM_HTTP_PORT:-18080}"
WS_PORT="${IAM_OS_VM_WS_PORT:-18765}"

note() { printf '[run-vm] %s\n' "$*"; }
fail() { printf '[run-vm] error: %s\n' "$*" >&2; exit 1; }

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
    fail "qemu-system-x86_64 not found — install qemu (Linux: apt install qemu-system-x86; macOS: brew install qemu)"
fi

if [ ! -f "$IMAGE" ]; then
    cat >&2 <<EOF
[run-vm] no appliance image found at:
[run-vm]   $IMAGE
[run-vm]
[run-vm] Phase 6 produces a rootfs tarball, not a bootable image. To boot
[run-vm] in QEMU you currently need to:
[run-vm]
[run-vm]   1. Run os-image/build.sh on a Linux host to get
[run-vm]      out/iam-os-<version>-amd64-rootfs.tar.gz
[run-vm]   2. Convert it to a bootable qcow2 with a bootloader
[run-vm]      (planned for Phase 7 — script not yet committed).
[run-vm]   3. Re-run this script with IAM_OS_VM_IMAGE pointing at the
[run-vm]      resulting qcow2.
[run-vm]
[run-vm] For day-to-day development without the VM, use
[run-vm] sandbox/run-fast-loop.sh — same stack, no kernel.
EOF
    exit 1
fi

ACCEL=()
case "$(uname -s)" in
    Linux)
        # Use KVM when /dev/kvm is accessible; fall back to TCG.
        if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
            ACCEL+=( -enable-kvm -cpu host )
        else
            note "KVM unavailable; falling back to TCG (slow)"
        fi
        ;;
    Darwin)
        ACCEL+=( -accel hvf -cpu host )
        ;;
esac

note "booting $IMAGE"
note "host:$HTTP_PORT -> guest:8080 (launcher)"
note "host:$WS_PORT -> guest:8765 (touch contract)"
note "host:$SSH_PORT -> guest:22 (operator ssh)"

exec qemu-system-x86_64 \
    "${ACCEL[@]}" \
    -m "$RAM" \
    -smp "$CPUS" \
    -drive "file=$IMAGE,if=virtio,format=qcow2" \
    -netdev "user,id=net0,hostfwd=tcp::$SSH_PORT-:22,hostfwd=tcp::$HTTP_PORT-:8080,hostfwd=tcp::$WS_PORT-:8765" \
    -device virtio-net-pci,netdev=net0 \
    -device virtio-gpu \
    -device qemu-xhci \
    -device usb-tablet \
    -display default,show-cursor=on \
    -serial mon:stdio
