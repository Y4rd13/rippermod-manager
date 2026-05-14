# VFS Spike Results — 2026-05-14

> Template — fill in PASS/FAIL/N-A per item as you run them on real hardware. Items marked KILLER must pass (or have a documented workaround) before any implementation code is merged.

## Environment

- **OS:** <Windows 10 or 11 version>
- **Game drive:** <e.g. D:>
- **AppData drive:** <e.g. C:>
- **Cyberpunk version:** <e.g. 2.21>
- **Mod count:** <e.g. 58>
- **AV:** <Defender real-time on / off / third-party>
- **Steam version:** <e.g. Beta 1715642312>
- **RipperMod version:** <e.g. v2.0.0 from main branch>

## Pre-spike checklist

- [ ] Cyberpunk 2077 fully closed
- [ ] Steam not actively updating Cyberpunk
- [ ] A `robocopy` snapshot of the game dir exists at `C:\spike-snapshot` (for rollback between items)
- [ ] At least 50 mods installed via the current RipperMod build
- [ ] PowerShell + cmd.exe both available

---

## Item 1: `mklink /J` in non-elevated cmd

**Command:**
```
mklink /J C:\tmp\spike-junction C:\tmp\spike-target
```

**Pass criteria:** Junction created without UAC prompt; `dir C:\tmp\spike-junction` lists the target's contents.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<paste command output / screenshot link>

**Blockers:** <none / description>

---

## Item 2: `mklink /J` from a Python subprocess

**Code:**
```python
import subprocess
proc = subprocess.run(
    ["cmd", "/c", "mklink", "/J", "C:\\tmp\\a", "C:\\tmp\\b"],
    capture_output=True,
    text=True,
    shell=False,
    timeout=10,
)
print(proc.returncode, proc.stdout, proc.stderr)
```

**Pass criteria:** `returncode == 0`, stderr empty.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

```
<paste subprocess output>
```

**Blockers:** <none / description>

---

## Item 3: Cross-drive hardlink fails as expected

**Command:**
```powershell
New-Item -ItemType HardLink -Path D:\x -Target C:\Windows\System32\notepad.exe
```

**Pass criteria:** Errors with "device does not support" or "cannot create hard link... not on the same volume."

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<paste error message>

**Blockers:** <none / description>

---

## Item 4: REDmod deploy through `mods/<test>/` junction (KILLER)

**Steps:**

1. Create `<game>\downloaded_mods\spike_redmod\` with a valid `info.json` and one `.reds` script (your choice — any small mod will do, or build a stub).
2. Remove any existing `<game>\mods\spike_redmod\`.
3. `mklink /J "<game>\mods\spike_redmod" "<game>\downloaded_mods\spike_redmod"`
4. Run `<game>\tools\redmod\bin\redMod.exe deploy -force` (adjust per your REDmod install).
5. Launch the game.

**Pass criteria:**
- `<game>\r6\cache\modded\final.redscripts` is produced
- Mod's script behavior is visible in-game

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<paste redmod.exe output / cache file timestamp / in-game observation>

**Blockers:** <none / description>

---

## Item 5: CET via hardlink of `winmm.dll`

**Steps:**

1. Backup `<game>\bin\x64\winmm.dll` if present.
2. Place CET's `winmm.dll` at `<game>\downloaded_mods\spike_cet\bin\x64\winmm.dll`.
3. From Python: `os.link("<game>\\downloaded_mods\\spike_cet\\bin\\x64\\winmm.dll", "<game>\\bin\\x64\\winmm.dll")`
4. Launch the game.

**Pass criteria:** CET loads — check `<game>\bin\x64\plugins\cyber_engine_tweaks\cyber_engine_tweaks.log` for a "Loaded" / startup line.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

```
<paste relevant log lines>
```

**Blockers:** <none / description>

---

## Item 6: Steam Verify Integrity on junctioned `mods/` (KILLER)

**Steps:**

1. With `<game>\mods\spike_redmod` as a junction (from item 4), run Steam → Cyberpunk 2077 → Properties → Installed Files → Verify integrity.
2. After Steam finishes, check whether the junction still exists and traverses.

**Pass criteria:**
- **PASS** = junction survives, contents traversable
- **ACCEPTABLE** = junction wiped to empty real dir; document the recovery flow (drift detect + redeploy)
- **FAIL** = Steam errors out or deletes/relocates files outside the junction

**Result:** <PASS / ACCEPTABLE / FAIL / N-A>

**Evidence:**

<screenshot of Steam Verify result + post-verify dir listing>

**Blockers:** <none / description>

---

## Item 7: Steam Verify on hardlinked mod files (KILLER)

**Steps:**

1. Hardlink one `.archive` file from staging to `<game>\archive\pc\mod\spike.archive`:
   ```
   New-Item -ItemType HardLink -Path "<game>\archive\pc\mod\spike.archive" -Target "<game>\downloaded_mods\spike\foo.archive"
   ```
2. Run Steam Verify.
3. After verify, run `os.path.samefile(staging_path, game_path)` in Python.

**Pass criteria:** `samefile()` still returns `True` — Steam did not touch the hardlink.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

```
<paste samefile() output and any verify-found-discrepancy reports from Steam>
```

**Blockers:** <none / description>

---

## Item 8: Steam patch via SteamCMD downgrade then upgrade

**Steps:**

1. Identify a previous Cyberpunk depot version (e.g., previous beta branch).
2. `steamcmd +login <user> +app_update 1091500 -beta <previous_version> validate +quit`
3. `steamcmd +login <user> +app_update 1091500 validate +quit`
4. Check the hardlinks and junctions you created in items 4-7.

**Pass criteria:**
- Hardlinks at mod-only paths (`archive/pc/mod/spike.archive`, etc.) survive
- Drift report flags any breakages at vanilla paths (`engine/`, `bin/x64/winmm.dll` if applicable)

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<paste SteamCMD output + post-patch link survival check>

**Blockers:** <none / description>

---

## Item 9: CDPR pre-verify cleanup recovery (KILLER)

**Steps:**

1. Manually delete (per CDPR's official pre-verify cleanup guide):
   - `<game>\mods\spike_redmod` (junction)
   - `<game>\archive\pc\mod\spike.archive` (hardlink)
   - `<game>\bin\x64\winmm.dll` (hardlink)
2. Start RipperMod.
3. Trigger a "Verify deployment" or "Redeploy" action.

**Pass criteria:** RipperMod detects the missing deployments and a one-click "Redeploy" restores everything from staging without re-downloading anything.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<screenshot of drift report + post-redeploy state>

**Blockers:** <none / description>

---

## Item 10: Deploy with game running

**Steps:**

1. Launch `Cyberpunk2077.exe`.
2. From a Python test script using `psutil`, call:
   ```python
   import psutil
   running = any(p.info["name"].lower() == "cyberpunk2077.exe" for p in psutil.process_iter(["name"]))
   ```
3. Confirm it returns `True`.
4. Attempt a deploy via the planned `pre_flight_check`.

**Pass criteria:** Pre-flight refuses with a `GameRunningError` (or equivalent ok=False, game_running=True).

**Result:** <PASS / FAIL / N-A>

**Evidence:**

```
<paste pre_flight_check output>
```

**Blockers:** <none / description>

---

## Item 11: OneDrive does not follow hardlinks

**Steps:**

1. Move the staging dir inside a OneDrive-synced folder, OR ensure `downloaded_mods/` lives under OneDrive.
2. Deploy hardlinks from there into the (non-OneDrive) game dir.
3. Check OneDrive's status icons and upload activity over 10 minutes.

**Pass criteria:** OneDrive does NOT upload the game-dir hardlink copies. Expected behavior per Windows reparse-point semantics.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<screenshot of OneDrive sync status + activity feed>

**Blockers:** <none / description>

---

## Item 12: Defender during 500-file deploy

**Steps:**

1. Generate a synthetic deploy plan with 500 small files (script: write 500 random `.txt` files to staging, then hardlink each into a temp game dir).
2. Run with Defender real-time scanning enabled.
3. Time the operation; check Event Viewer → Applications and Services → Microsoft → Windows → Windows Defender for quarantine events.

**Pass criteria:**
- No quarantine events
- Total time < 30s

**Result:** <PASS / FAIL / N-A>

**Evidence:**

```
Time: <X seconds>
Defender events: <count and any flagged paths>
```

**Blockers:** <none / description>

---

## Item 13: Toggle disable/enable on a hardlink (optional sanity)

**Steps:**

1. Hardlink a file from staging to game dir.
2. `os.rename(game_path, game_path + ".disabled")`
3. Read content via the staging path. Confirm unchanged.

**Pass criteria:** Staging file content is identical. Confirms NTFS rename-of-hardlink semantics.

> Note: we are NOT using rename-disable in the new design. This is just sanity-confirming the invariant in case we need it later.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<paste before/after content + hash>

**Blockers:** <none / description>

---

## Item 14: End-to-end migration of a real 100+ mod install (KILLER)

**Steps:**

1. On a **copy** of a real 100+ mod RipperMod install (use `robocopy /MIR` to back up first):
2. Walk through the migration plan from Phase 5 of the implementation plan manually:
   - For each `InstalledMod`, move files from game dir to `downloaded_mods/<safe_name>/`
   - Hardlink each file back to its game-dir path
3. Launch the game. Verify mods load identically.

**Pass criteria:**
- All 100+ mods migrated, no data loss
- `os.path.samefile()` returns True for every migrated file
- Game launches with all mods functional

**Result:** <PASS / FAIL / N-A>

**Evidence:**

```
Mods migrated: <count>
Files migrated: <count>
Game launch: <success / failure>
In-game mod sanity check: <which mods you confirmed work>
```

**Blockers:** <none / description>

---

## Item 15: Disable/enable cycle with DB-flag model

**Steps:**

1. Disable a mod via DB flag (set `InstalledMod.disabled = True`).
2. Call `undeploy` for that mod's files (or all undeploy).
3. Confirm hardlinks gone from game dir, staging intact.
4. Confirm drift report = 0 missing for non-disabled mods (only the disabled mod is "out").
5. Re-enable (set `disabled = False`).
6. Call `deploy`. Confirm hardlinks restored.

**Pass criteria:** Disable removes links, staging untouched; enable restores links from staging.

**Result:** <PASS / FAIL / N-A>

**Evidence:**

<paste drift report before/during/after>

**Blockers:** <none / description>

---

## Decision Gate

After completing all 15 items:

| Item | KILLER? | Result |
|---|---|---|
| 1 | no | |
| 2 | no | |
| 3 | no | |
| **4** | **yes** | |
| 5 | no | |
| **6** | **yes** | |
| **7** | **yes** | |
| **8** | **yes** | |
| **9** | **yes** | |
| 10 | no | |
| 11 | no | |
| 12 | no | |
| 13 | no | |
| **14** | **yes** | |
| 15 | no | |

**Gate criteria:**
- All KILLER items (4, 6, 7, 8, 9, 14) PASS or ACCEPTABLE: **proceed to merge Phase 1+ code**
- Any KILLER FAIL with no workaround: **STOP**. Revise the design spec before merging.
- Non-KILLER FAIL: document workaround in `## Workarounds` below, proceed.

## Workarounds

<For each FAIL: describe the workaround that lets the design ship anyway, or the limitation we accept.>

## Decision

<Final call: PROCEED / REVISE / STOP — with one-sentence justification.>

**Decided by:** <Y4rd13>
**Date:** <YYYY-MM-DD>
