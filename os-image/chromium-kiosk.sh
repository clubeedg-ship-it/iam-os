#!/bin/sh
# Launch Chromium as the IAM-OS kiosk.
#
# Invoked by iam-os-kiosk.service via cage. The flags strip every UI hint
# that this is a browser — no popups, no first-run wizard, no infobars,
# no swipe-back gestures, no update checks. The user data directory is
# in the iam-os home so a profile survives reboots; the "exited cleanly"
# preference is rewritten before each launch so a previous crash does
# not produce a restore-tabs dialog the operator cannot dismiss.

set -eu

URL="${IAM_OS_KIOSK_URL:-http://localhost:8080/}"
PROFILE_DIR="${IAM_OS_KIOSK_PROFILE:-/var/lib/iam-os/chromium}"

mkdir -p "$PROFILE_DIR/Default"

# Suppress the "Chromium did not shut down correctly" recovery prompt
# after a power cycle: rewrite the relevant Preferences keys before each
# launch. If the file is absent or malformed it stays absent — Chromium
# will create a fresh one.
PREF="$PROFILE_DIR/Default/Preferences"
if [ -f "$PREF" ]; then
    sed -i \
        -e 's/"exit_type":"[^"]*"/"exit_type":"Normal"/' \
        -e 's/"exited_cleanly":false/"exited_cleanly":true/' \
        "$PREF"
fi

# Pick whichever Chromium binary exists in this image.
for candidate in chromium chromium-browser /usr/bin/chromium /usr/bin/chromium-browser; do
    if command -v "$candidate" >/dev/null 2>&1; then
        CHROMIUM="$candidate"
        break
    fi
done

if [ -z "${CHROMIUM:-}" ]; then
    echo "chromium-kiosk: no chromium binary found in PATH" >&2
    exit 1
fi

exec "$CHROMIUM" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-pinch \
    --disable-features=TranslateUI \
    --disable-translate \
    --overscroll-history-navigation=0 \
    --no-first-run \
    --no-default-browser-check \
    --password-store=basic \
    --check-for-update-interval=31536000 \
    --user-data-dir="$PROFILE_DIR" \
    --start-fullscreen \
    "$URL"
