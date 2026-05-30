# Field Validation Results — IAM-OS &lt;version&gt;

Copy this template to `docs/field-validation/runs/<YYYYMMDD>/RESULTS.md`
and fill it in during the run. Commit it once the procedure is complete.

## Test identity

| | |
|---|---|
| **Tester** | |
| **Date (UTC)** | |
| **Site / installation** | |
| **Image version** | (from `/etc/iam-os-version`'s `IAM_OS_VERSION=`) |
| **Image git SHA** | (from `/etc/iam-os-version`'s `IAM_OS_GIT_SHA=`) |
| **Procedure version (commit SHA)** | (the commit of `PROCEDURE.md` you followed) |

## Hardware under test

| | |
|---|---|
| **Mini PC make / model** | |
| **CPU / RAM** | |
| **RPLIDAR model** | (e.g. A1, C1, S2, S2E) |
| **USB serial adapter** | (CP210x / FTDI / other) |
| **USB cable** | (length, brand if relevant) |
| **Projector make / model** | |
| **Projection surface** | (wall / floor; material) |

## A. Kiosk boot path

| Question | Result |
|---|---|
| Boot time to launcher (s) | |
| Launcher visible without operator action | PASS / FAIL |
| No Chromium chrome visible | PASS / FAIL |
| No "Restore tabs?" dialog | PASS / FAIL |

**Diag bundle:** `runs/<date>/iam-os-diag-A.tar.gz`
**Photos:** `runs/<date>/A-boot-T30.jpg`, `A-boot-T60.jpg`, `A-boot-T90.jpg`

**Observations:**

> _Anything notable — slow disk, BIOS quirk, missed Secure Boot toggle._

## B. Calibration end-to-end

| Question | Result |
|---|---|
| All 4 corners captured first try | PASS / FAIL |
| Preset saved + activated cleanly | PASS / FAIL |
| Test-view touches land within ~10 cm of hand | PASS / FAIL |

**Preset filename:** `field-test-<YYYYMMDD>.json`
**Diag bundle:** `runs/<date>/iam-os-diag-B.tar.gz`
**Photos:** `runs/<date>/B-calibrate.jpg`, `B-test-view.jpg`

**Observations:**

> _Did orientation need invertX/invertY? Any drift between captures?_

## C. LiDAR unplug reliability

Three repeats. Record observed recovery time (seconds from cable
replug to first touch reappearing in Test view).

| Repeat | Recovery time (s) | Verdict |
|---|---|---|
| 1 | | PASS ≤ 10 / IDEAL ≤ 5 / FAIL |
| 2 | | PASS ≤ 10 / IDEAL ≤ 5 / FAIL |
| 3 | | PASS ≤ 10 / IDEAL ≤ 5 / FAIL |
| **Mean** | | |
| **Max** | | |

| Question | Result |
|---|---|
| No operator action required beyond replug | PASS / FAIL |
| Health pill returned to `streaming` each time | PASS / FAIL |
| Journal shows expected health transitions | PASS / FAIL |

**Diag bundle (after repeat 3):** `runs/<date>/iam-os-diag-C.tar.gz`

**Observations:**

> _Any repeat that took unusually long? Any USB enumerate-once-then-fail?_

## Disposition

- [ ] **Validated for release.** All three test areas passed; tagging
  the image as `v<version>-validated`.
- [ ] **Validation incomplete.** A test failed or could not be
  completed; details below; do not tag.

**Notes for the next field run / for the release notes:**

> _What changed compared to a previous validation? Things to watch out
> for on the next install? Suggested follow-up issues to file._
