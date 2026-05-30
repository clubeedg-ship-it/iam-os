# IAM-OS Field Validation Procedure

Execute this procedure on the production mini PC + RPLIDAR + projector
installation to validate a tagged IAM-OS image before declaring the
release fit for deployment. The procedure focuses on the three failure
modes most likely to bite in the field:

1. **Kiosk boot path** — does the appliance reach the launcher on cold
   boot, with no operator action.
2. **Calibration end-to-end** — does the four-corner capture flow
   produce a usable preset against a real LiDAR + projection.
3. **LiDAR reliability** — does tracking recover automatically when the
   LiDAR is unplugged mid-operation (specs.md §6 G2 / R3 / R4).

A multi-hour soak is **not** part of this procedure; it is deferred to
a separate run when needed.

## 0. Pre-flight

### Hardware checklist

- [ ] Mini PC: x86_64, UEFI firmware, ≥4 GiB RAM, ≥4 GiB internal
  storage (or boot directly off a USB stick for the test).
- [ ] RPLIDAR with CP210x or FTDI USB serial adapter (A1, C1, S2, S2E
  are all supported).
- [ ] Projector + HDMI cable, aimed at the wall/floor surface.
- [ ] Wired keyboard for the calibration step (or SSH access).
- [ ] USB stick, ≥4 GiB, that you are willing to overwrite.
- [ ] Stopwatch (a phone is fine).
- [ ] Photo capability for screen captures of the projection.

### Get the image

1. Confirm the release workflow has produced an image:
   <https://github.com/clubeedg-ship-it/iam-os/releases>.
2. Download `iam-os-<version>-amd64.img.gz` and the `.sha256` for the
   release under test.
3. Verify the checksum:

   ```sh
   sha256sum -c iam-os-<version>-amd64.img.gz.sha256
   ```

### Flash the USB

On Linux:

```sh
gunzip -c iam-os-<version>-amd64.img.gz | sudo dd of=/dev/sdX bs=4M \
  status=progress conv=fsync
sync
```

On macOS:

```sh
diskutil unmountDisk /dev/diskX
gunzip -c iam-os-<version>-amd64.img.gz | sudo dd of=/dev/rdiskX bs=4m
sync
```

Replace `sdX` / `diskX` with the USB device. **Triple-check the
target** — `dd` to the wrong device is irreversible.

### Boot the mini PC from USB

1. Insert the USB, plug in projector + LiDAR.
2. Power on; press the BIOS boot-menu key (typically `F12`, `F11`,
   `F10`, `Esc`, or `Del`).
3. Select the USB stick. Disable Secure Boot if firmware rejects the
   signed Debian kernel.

## A. Kiosk boot path

**Goal:** the appliance reaches the launcher on cold boot, fullscreen,
with zero operator action. This validates the systemd ordering, the
kiosk service, cage + Chromium, and the udev rule.

### A.1 Steps

1. Power-cycle the mini PC.
2. Start the stopwatch the moment you press the power button.
3. Observe the projection.
4. Stop the stopwatch the moment the launcher's top-bar (IAM-OS brand +
   four tabs + health pill) is visible on the projection.

### A.2 PASS criteria

- [ ] **Boot completes without operator intervention.** No login
  prompt, no GRUB menu held open, no Chromium "Restore tabs?" dialog.
- [ ] **Launcher visible on projection within 90 s.** The health pill
  reads `streaming` (LiDAR is connected) or `connecting` (still
  warming up, but the kiosk itself is there).
- [ ] **No Chromium chrome.** No address bar, no tabs, no infobar —
  cage + the kiosk flags should hide all of it.

### A.3 Capture

- Photograph the projection at T+30 s, T+60 s, T+90 s.
- After kiosk is up, SSH in as `iam-os` and run:

  ```sh
  ssh iam-os@<appliance> 'bash -s' < scripts/appliance-diag.sh
  scp iam-os@<appliance>:/tmp/iam-os-diag-*.tar.gz \
      docs/field-validation/runs/
  ```

- Note the **observed boot time** in `RESULTS.md`.

### A.4 If it fails

- Launcher not visible → SSH in, check `systemctl status iam-os-kiosk`
  and `journalctl -b 0 -u iam-os-kiosk`. The kiosk waits on
  `iam-web-server.service`, which waits on `iam-touch-bridge` and
  `iam-lidar-service`. Find the failing unit, read its journal.
- Chromium "Restore tabs?" appeared → `chromium-kiosk.sh` should have
  rewritten `Default/Preferences`. Inspect the preferences file under
  `/var/lib/iam-os/chromium/Default/Preferences` for the `exit_type`
  and `exited_cleanly` keys.

## B. Calibration end-to-end

**Goal:** capture the four projection corners against a real LiDAR,
save a preset, activate it, verify touches land where the operator
actually touches the surface.

### B.1 Steps

1. Confirm the LiDAR is plugged in and the appliance is on the launcher.
2. Open the launcher's calibrate view. Locally, that means switching
   the projected page; remotely (SSH tunnel), browse
   `http://localhost:8080/#/calibrate` via `ssh -L
   8080:127.0.0.1:8080`.
3. The four corner targets render at the projection bounds. The
   "Current corner" indicator highlights one.
4. Have a person stand in front of the surface and touch the
   highlighted corner with a hand.
5. Click **Capture corner** in the launcher. The captured raw
   `(x, y) mm` appears below the corner marker, the corner turns green.
6. Repeat for all four corners (TL → TR → BR → BL).
7. Enter a preset name `field-test-<YYYYMMDD>` and click
   **Save & activate**.
8. Switch to the **Test** view. With calibration active, touch
   different points on the projection surface.

### B.2 PASS criteria

- [ ] **All four corners capture on first attempt** with no "no active
  touch" errors.
- [ ] **Preset saves and activates without HTTP error.** Status pill in
  the top bar shows `streaming`; status view shows
  `active_preset: field-test-...`.
- [ ] **Test-view touches land within ~10 cm of the actual hand
  position** at each corner and center.

### B.3 Capture

- Photograph the projection during the test view, showing the touch
  dot vs. the operator's hand.
- The saved preset file, retrievable via SSH:

  ```sh
  cat /var/lib/iam-os/calibration/field-test-*.json
  cat /var/lib/iam-os/calibration/active.json
  ```

- Run `appliance-diag.sh` again after calibration to capture the
  status file with `active_preset` filled in.

### B.4 If it fails

- "No active touch" on capture → the LiDAR sees no touch within range.
  Move the hand closer or further from the surface, check
  `cluster_min_points` in the lidar-service config (defaults expect a
  hand-sized cluster).
- Test-view touches drift from actual position → likely an axis
  orientation issue; toggle `invertX` / `invertY` in the therapist
  panel (still in the lidar config; future work surfaces this in the
  launcher).
- Touches appear at `(0.5, 0.5)` regardless of where you touch →
  calibration not loaded. Check `journalctl -u iam-lidar-service` for
  the "calibration: installed preset" line.

## C. LiDAR unplug reliability — the headline test

**Goal:** unplug the LiDAR mid-tracking; tracking resumes automatically.
This is the specs.md §6 acceptance target, and the main reason for the
whole rewrite.

### C.1 Steps (repeat 3 times)

1. With calibration active, sit on the Test view; verify a touch shows
   when you wave a hand at the surface.
2. Yank the LiDAR USB cable. Start the stopwatch the moment the cable
   physically separates.
3. Watch the health pill in the launcher. It should transition
   `streaming → stale → connecting` (or `failed`).
4. Plug the cable back in.
5. Stop the stopwatch the moment a hand wave again produces a touch
   in the Test view.
6. Record the elapsed time in `RESULTS.md`.

### C.2 PASS criteria

For **each** of the three repeats:

- [ ] **Tracking resumes ≤ 10 s after replug.** PASS threshold per the
  spec's "within a few seconds".
- [ ] **No operator action required** beyond replugging the cable. No
  manual restart, no SSH, no power-cycle.
- [ ] **Health pill returns to `streaming`** within the same window.

**IDEAL:** ≤ 5 s — indicates the watchdog + ConnectionManager
backoff are tight against the hardware's USB re-enumeration latency.

### C.3 Capture

- The `appliance-diag.sh` bundle captured immediately AFTER the third
  repeat — `journal-iam-os-this-boot.log` will contain the
  `health: streaming -> stale -> connecting -> streaming` transitions
  for all three trials, dated.
- Note any deviation from the expected health sequence.

### C.4 If it fails

- Tracking does not resume → check `journalctl -u iam-lidar-service`:
  the ConnectionManager should log
  `watchdog: no scan within Xs` then `connect failed: ...` then
  successful reconnect. If it loops on failure, the udev rule may not
  have re-symlinked `/dev/iam-lidar`; verify with `ls -l /dev/iam-lidar`
  after the replug.
- Tracking resumes but takes > 10 s → record the actual time; this is
  a tunable. The default backoff is `0.5 s → 1 → 2 → 4 → ...`; consider
  shortening `backoff_max_s` or `connect_timeout_s` in the config.

## D. Post-flight

1. Copy the `appliance-diag.sh` bundles produced during each test into
   `docs/field-validation/runs/<YYYYMMDD>/`.
2. Fill in `docs/field-validation/RESULTS-TEMPLATE.md` and commit it
   as `docs/field-validation/runs/<YYYYMMDD>/RESULTS.md`.
3. If every PASS criterion was met, tag the validated release:

   ```sh
   git tag -a v0.1.0-validated -m "Field validation passed on <YYYY-MM-DD>"
   git push origin v0.1.0-validated
   ```

4. If anything failed, do **not** tag; open an issue describing the
   defect and link to the journal evidence.
