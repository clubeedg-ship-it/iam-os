#!/bin/bash
# Build a Debian 12 minimal rootfs for the IAM-OS appliance.
#
# Uses mmdebstrap (modern, unprivileged Debian bootstrapper) to produce a
# tarball that contains:
#
#   - a minbase Debian 12 (bookworm) install,
#   - the three IAM-OS Python services under /opt/iam-os/services/,
#     each with its own venv,
#   - the built launcher SPA under /usr/share/iam-os/launcher/,
#   - the games tree under /usr/share/iam-os/games/,
#   - the IAM-OS systemd units, tmpfiles.d, and udev rules,
#   - an unprivileged iam-os user (uid 1000) and the dialout group,
#   - the three IAM-OS services + the kiosk session enabled.
#
# The output is a rootfs tarball. os-image/make-image.sh wraps it into a
# bootable disk image (EFI + ext4 root + systemd-boot); both steps run
# in CI on PR and tag pushes (.github/workflows/ci.yml).
#
# This script is Linux-only: mmdebstrap and (in --architectures) Debian's
# multi-arch toolchain are not available on macOS. On macOS, run it
# inside a Linux VM or rely on CI.

set -euo pipefail

VERSION="${IAM_OS_VERSION:-dev}"
ARCH="${IAM_OS_ARCH:-amd64}"
SUITE="${IAM_OS_SUITE:-bookworm}"
OUT_DIR="${OUT_DIR:-out}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT_ROOT="$REPO_ROOT/$OUT_DIR"
OUT_TAR="$OUT_ROOT/iam-os-${VERSION}-${ARCH}-rootfs.tar"

GIT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [ "$(uname -s)" != "Linux" ]; then
    echo "build.sh: Debian bootstrap requires Linux (host is $(uname -s))" >&2
    echo "build.sh: run inside a Linux VM or rely on CI." >&2
    exit 1
fi

if ! command -v mmdebstrap >/dev/null 2>&1; then
    echo "build.sh: mmdebstrap not found — install it: apt-get install mmdebstrap" >&2
    exit 1
fi

if [ ! -d "$REPO_ROOT/launcher/dist" ]; then
    echo "build.sh: launcher/dist not found — run 'npm --prefix launcher run build' first" >&2
    exit 1
fi

mkdir -p "$OUT_ROOT"

PACKAGES=(
    systemd-sysv
    systemd-boot
    udev
    dbus
    ca-certificates
    chromium
    cage
    iproute2
    locales
    linux-image-amd64
    python3
    python3-venv
    python3-pip
    sudo
)

# Each customize-hook runs in a fresh shell with the rootfs path as $1.
# We use them to copy the IAM-OS payload in, then chroot to create
# users, install venvs, and enable services.

mmdebstrap \
    --architectures="$ARCH" \
    --variant=minbase \
    --include="$(IFS=,; echo "${PACKAGES[*]}")" \
    --customize-hook="chroot \"\$1\" mkdir -p /opt/iam-os /opt/iam-os/os-image /usr/share/iam-os /usr/share/iam-os/launcher /etc/systemd/system/iam-os /etc/tmpfiles.d/iam-os /etc/udev/rules.d/iam-os" \
    --customize-hook="copy-in $REPO_ROOT/services /opt/iam-os/" \
    --customize-hook="copy-in $REPO_ROOT/games /usr/share/iam-os/" \
    --customize-hook="sync-in $REPO_ROOT/launcher/dist /usr/share/iam-os/launcher" \
    --customize-hook="sync-in $REPO_ROOT/os-image/units /etc/systemd/system/iam-os" \
    --customize-hook="sync-in $REPO_ROOT/os-image/tmpfiles.d /etc/tmpfiles.d/iam-os" \
    --customize-hook="sync-in $REPO_ROOT/os-image/udev /etc/udev/rules.d/iam-os" \
    --customize-hook="copy-in $REPO_ROOT/os-image/chromium-kiosk.sh /opt/iam-os/os-image/" \
    --customize-hook="chroot \"\$1\" /bin/bash -euxo pipefail -c '
        getent group iam-os >/dev/null || groupadd --system iam-os
        id iam-os >/dev/null 2>&1 || useradd --system --gid iam-os --groups dialout,tty,video --create-home --home-dir /var/lib/iam-os --shell /usr/sbin/nologin iam-os
        for svc in lidar-service touch-bridge web-server; do
            python3 -m venv \"/opt/iam-os/services/\$svc/.venv\"
            \"/opt/iam-os/services/\$svc/.venv/bin/pip\" install --no-cache-dir --quiet \
                -c \"/opt/iam-os/services/\$svc/constraints.txt\" \
                \"/opt/iam-os/services/\$svc\"
        done
        chown -R iam-os:iam-os /opt/iam-os /var/lib/iam-os
        chmod +x /opt/iam-os/os-image/chromium-kiosk.sh
        mv /etc/systemd/system/iam-os/*.service /etc/systemd/system/
        rmdir /etc/systemd/system/iam-os
        mv /etc/tmpfiles.d/iam-os/*.conf /etc/tmpfiles.d/
        rmdir /etc/tmpfiles.d/iam-os
        mv /etc/udev/rules.d/iam-os/*.rules /etc/udev/rules.d/
        rmdir /etc/udev/rules.d/iam-os
        systemctl enable iam-lidar-service.service iam-touch-bridge.service iam-web-server.service iam-os-kiosk.service
        systemctl set-default graphical.target
        cat > /etc/iam-os-version <<RELEASE
IAM_OS_VERSION=$VERSION
IAM_OS_GIT_SHA=$GIT_SHA
IAM_OS_BUILD_DATE=$BUILD_DATE
IAM_OS_ARCH=$ARCH
IAM_OS_SUITE=$SUITE
RELEASE
        sed -i \"s/^PRETTY_NAME=.*/PRETTY_NAME=\\\"IAM-OS $VERSION (Debian $SUITE)\\\"/\" /etc/os-release
    '" \
    --customize-hook="chroot \"\$1\" apt-get clean && rm -rf \"\$1/var/lib/apt/lists/\"*" \
    "$SUITE" \
    "$OUT_TAR"

gzip -f "$OUT_TAR"
echo "rootfs built: ${OUT_TAR}.gz"
ls -lh "${OUT_TAR}.gz"
