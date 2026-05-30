# IAM-OS Build & CI Notes

Lessons captured during Phases 6–8 and the v0.1.0 release. Read this before
touching `os-image/build.sh`, `os-image/make-image.sh`, `.github/scripts/
boot-smoke.sh`, or the GitHub workflows — most of these were one-shot bugs
that took several CI iterations to surface and are not obvious from the
code alone.

## mmdebstrap

### `copy-in` and `sync-in` semantics differ

`copy-in <src> <dst>` copies the source path *with its basename* into the
destination directory. So:

```sh
copy-in /host/launcher/dist /usr/share/iam-os/launcher
```

lands the source at `/usr/share/iam-os/launcher/dist/*`, NOT at
`/usr/share/iam-os/launcher/*`. The destination directory must already
exist inside the rootfs.

`sync-in <src> <dst>` copies the *contents* of the source into the
destination (rsync semantics). Use this when you want flat contents:

```sh
sync-in /host/os-image/units /etc/systemd/system/iam-os
```

drops the `.service` files directly into `/etc/systemd/system/iam-os/`.

`build.sh` currently uses both: `copy-in` for `services/`, `games/`,
`os-image/chromium-kiosk.sh` (basename desired); `sync-in` for the unit
directory, tmpfiles.d, udev, and `launcher/dist` (flat contents desired).

### `copy-in` arguments are NOT shell-interpolated

mmdebstrap's special-hook directives (`copy-in`, `sync-in`, `copy-out`,
`extract`) are parsed as token lists; `$1` does NOT expand to the rootfs
path. Only `chroot` hooks expand `$1` because they ARE shell commands.
This is the OPPOSITE of what the mmdebstrap manpage example suggests.

```sh
# WRONG — literal "$1" reaches the helper
--customize-hook="copy-in $REPO/foo \"\$1/dst/\""

# RIGHT — guest path verbatim
--customize-hook="copy-in $REPO/foo /dst/"
```

### `debian-archive-keyring` is not on Ubuntu runners

GitHub's `ubuntu-latest` runners do not ship Debian's archive keyring.
mmdebstrap's first `apt-get update` against bookworm fails with NO_PUBKEY
unless this package is explicitly installed alongside mmdebstrap.

```yaml
- run: sudo apt-get install -y mmdebstrap debian-archive-keyring ...
```

## Image builder (`make-image.sh`)

### Bootloader installed inside chroot, not from the runner

`bootctl install` is run via `sudo chroot <rootfs> bootctl install
--no-variables` so the appliance's *own* systemd-boot binary is the one
written to the ESP. Running the host's `bootctl` against the rootfs's
ESP works in practice but mismatches the appliance's expected
systemd-boot version, which has bitten people elsewhere.

### Kernel + initrd live in `/boot` AND on the ESP

systemd-boot reads kernels from the ESP (not from `/boot`), so we must
explicitly copy `vmlinuz-*` and `initrd.img-*` from `<rootfs>/boot/` to
`<rootfs>/boot/efi/`. systemd-boot doesn't auto-stage them.

### Image versioning under GitHub Actions

`github.ref_name` is `<PR#>/merge` on pull request runs. The slash
breaks any code path that builds a file name from the ref, so sanitize:

```yaml
- run: |
    ref="${GITHUB_REF_NAME//\//-}"
    echo "version=${ref}-$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"
```

## QEMU TCG boot smoke (`.github/scripts/boot-smoke.sh`)

### `-cpu max` is mandatory for NumPy 2.x

NumPy 2.0 raised its compile-time SIMD baseline to **x86-64-v2 (SSE4.2
minimum)**. QEMU's default `qemu64` CPU only exposes through SSE3, so
*any* call into NumPy's `_multiarray_umath.so` traps to SIGILL — at .so
load / dispatcher init, well before NumPy could read
`NPY_DISABLE_CPU_FEATURES` or the dispatcher could pick a SSE2 lane.
Linux `clearcpuid=avx,avx2,fma` on the kernel cmdline does *not* help
either: userspace probes CPUID directly, not Linux's view.

The fix that works: `qemu-system-x86_64 -cpu max`. On QEMU 8.x (Ubuntu
24.04+) `-cpu max` in TCG exposes SSE4.1, SSE4.2, AVX, and AVX2.

### `-kernel` / `-initrd` / `-append` to override the loader

Booting the disk image straight is fine on real UEFI but a hassle to
override in TCG (the systemd-boot loader entry's cmdline is the only
one the kernel sees). We instead loop-mount the image's ESP, copy out
`vmlinuz-*` + `initrd.img-*`, read the root PARTUUID via `blkid`, then
hand them to QEMU with a custom `-append` so CI-specific kernel knobs
(serial console, `systemd.show_status=yes`) don't pollute the appliance.

### Watch the serial log, not the network

The appliance's web-server binds to `127.0.0.1` (correct for the
kiosk). QEMU's `user` network `hostfwd` only forwards packets that
*arrive on the guest's routable IP*, which means the appliance is
unreachable over hostfwd. Also: the appliance image has no DHCP
client — bringing a DHCP client into the image purely to satisfy CI
would change the appliance's actual surface.

So the boot smoke does not poll HTTP. It writes the QEMU serial to a
file, strips ANSI escapes, and greps for `Started iam-lidar-service`,
`Started iam-touch-bridge`, and `Started iam-web-server`. All three
present = boot path healthy.

### Strip ANSI before grep

systemd's status writer wraps unit names in colour escapes:

```
[<ESC>[0;32m  OK  <ESC>[0m] Started <ESC>[0;1;39miam-web-server.service<ESC>[0m - ...
```

So `grep -F "Started iam-web-server.service"` against the raw log never
matches. Strip ANSI first:

```sh
sed -E 's/\x1b\[[0-9;]*[A-Za-z]//g'
```

And shorten the marker (`Started iam-web-server` — no `.service`) so a
line that systemd truncated to `Started iam-web-server.ser…` still
matches.

## systemd unit gotchas

### `Environment=` values with whitespace MUST be quoted

```ini
# WRONG — only "FOO=a" reaches the process; "b c" gets dropped as
# extra unrelated tokens.
Environment=FOO=a b c

# RIGHT
Environment="FOO=a b c"
```

We hit this with `NPY_DISABLE_CPU_FEATURES` before realising NumPy
ignored it anyway (see "QEMU TCG" above).

### Kiosk service depends on `iam-web-server`, not on graphics

`iam-os-kiosk.service` `Requires=iam-web-server.service`, so the kiosk
session waits for the launcher to be up before cage launches Chromium.
This is enough on the appliance; in CI the kiosk service starts but
cage may fail to find a usable DRM device, which is fine — the boot
smoke only checks the three service-start markers.

## CI quirks

### ShellCheck info-level noise

SC2317 ("Command appears to be unreachable") and SC2329 ("Function
invoked indirectly via trap") fire on every cleanup-via-trap handler
we write. They are info-level diagnostics — ShellCheck exits non-zero
on info too, but they are legitimate idioms.

CI calls `shellcheck --severity=warning` so info diagnostics don't
block; real bugs (warning / error / style) still fail.

### `systemd-analyze verify` flags appliance-only paths

The IAM-OS units point `ExecStart=` at `/opt/iam-os/services/.../venv/
python` and `/usr/bin/cage` — paths that exist only inside the
appliance image, not on the GitHub runner. `systemd-analyze verify`
reports "is not executable: No such file or directory" for each, and
exits non-zero. Filter that one expected line:

```yaml
real="$(printf '%s\n' "$raw" | grep -Ev 'is not executable: No such file' || true)"
if [ -n "$real" ]; then status=1; fi
```

## Ventoy on Debian (for the on-site flash)

Captured here because someone *will* hit it again.

- `mkexfatfs` binary doesn't exist on Debian 12+: `exfatprogs` ships
  `mkfs.exfat` only. Ventoy 1.1.12 still calls `mkexfatfs`.
- A shim at `/usr/local/sbin/mkexfatfs` works:

  ```sh
  #!/bin/sh
  if [ "$#" = 1 ] && [ "$1" = "-V" ]; then
      exec /usr/sbin/mkfs.exfat -V >/dev/null 2>&1 || exit 0
  fi
  exec /usr/sbin/mkfs.exfat "$@"
  ```

  The `-V` early-return is because `mkfs.exfat -V` in exfatprogs 1.2.9
  prints the version but returns exit 1; Ventoy expects exit 0.
- Run Ventoy with `LC_ALL=C LANG=C` if SSH-ing from macOS, otherwise
  the inherited `LANG=en_US.UTF-8` triggers
  "failed to init locale/codeset" on the Debian box.

## Pinned dependency policy

`services/<svc>/constraints.txt` pins runtime versions only. Dev tools
(`pytest`, `ruff`, `pytest-asyncio`, `jsonschema`) are intentionally
NOT in the constraints — they are not installed in the appliance, and
pinning them here would either drift from CI's dev install or require
keeping two pins in sync. Bump via:

```sh
.venv/bin/pip install -e .
.venv/bin/pip freeze --exclude-editable \
  | grep -vE '^(pytest|ruff|mypy|Pygments|iniconfig|pluggy|packaging)' \
  > constraints.txt
```
