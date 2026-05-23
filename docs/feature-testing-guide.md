# Feature Reference & Testing Guide — F1–F7 (ElDiablo59 batch)

Seven local mod-management features proposed by Nexus user **ElDiablo59**, plus two
performance follow-ups. Shipped to **both editions** (Full = `main`, Nexus = `nexus-compliant`)
— the features behave identically on both; only their host files differ.

This guide is the single reference for **what each feature does, how it works, and what to
test**. It is grounded in the merged implementation (not assumptions). For traceability, every
feature lists its PRs.

> All seven are local-only (no mod-page content surfaced in-app, no auto-update). The only
> network call across the set is F4's read-only Nexus version lookup, which reuses the
> already-shipped self-update pattern.

> **Gap-closure round (May 2026):** a second pass closed the deferred/partial parts of these
> features — F1 error→mod **attribution**, F6 **undo**, F4 **disabled-state** + **offline
> outdated**, F5 backups on **uninstall/disable/undeploy** (not just deploy), F2 a **"wrong
> directory"** check, and F7 the **remaining disable/uninstall surfaces**. Every **What / How /
> Test / Caveats** below reflects the *current* behavior; both rounds of PRs are in the index.

## How to run (for testing)

```bash
# Backend (terminal 1)
cd backend && uv run uvicorn rippermod_manager.main:app --reload --port 8425
# Desktop app (terminal 2) — backend must be running
cd frontend && npx tauri dev
```

Testing the **Nexus** release: check out `nexus-compliant`. Testing the **Full** release:
check out `main`. (WSL and Windows share the same working tree, so a `git checkout` switches
both.) Most features need a real Cyberpunk 2077 install with frameworks/mods to exercise fully.

## Where the features live (quick map)

| Feature | Backend endpoint | Frontend |
|---|---|---|
| F7 reverse-dep warning | `GET …/install/installed/{mod_id}/dependents` | confirm dialogs in `InstalledModsTable`, `DisableConfirmDialog`, `ArchivesList` |
| F6 activity log + undo | `GET …/{game}/activity`, `POST …/activity/{id}/undo` | **Activity** page (sidebar) |
| F2 health check | `GET …/{game}/health` | `HealthWidget` + Play gate (game page) |
| F3 diagnostics export | `GET /diagnostics` | **Diagnostics** card (Settings) |
| F5 save backups | `…/save-backups` (status/backup-now/restore) | **Save Backups** card (Settings) |
| F4 framework monitor | `GET …/{game}/frameworks` | `FrameworksWidget` (game page) |
| F1 mod error reader | `GET …/{game}/log-errors` | `LogErrorsWidget` (game page) |

All game-scoped endpoints are under `/api/v1/games/{game_name}/…`.

---

## F7 — Reverse dependency warning

**What:** before you **disable or uninstall** a mod, warns which *other installed* mods declare
it as a requirement — so you don't unknowingly break a dependent. It's a warn-with-override
heads-up, not a hard block.

**How:** backend `GET /install/installed/{mod_id}/dependents` reads locally-synced
`NexusModRequirement` rows (no Nexus call). `DependentsWarning` is shown inside the confirm
dialog on every disable/uninstall surface: the **Installed Mods** table (single/bulk/select-all
disable + delete), the **conflicts flow** (`DisableConfirmDialog`, covering its Disable *and*
Uninstall buttons), and the **Archives tab** uninstall (`ArchivesList`).

**Test:**
1. Have two installed mods where **A requires B**, and A's requirement data has been **synced**.
2. Disable or uninstall **B** from the **Installed Mods** table → the confirm dialog lists **A**
   ("based on synced data") and lets you **proceed anyway**. Repeat via bulk + **select-all**.
3. Uninstall **B** from the **Archives tab** → same warning appears.
4. Disable/uninstall **B** from the **conflicts** UI (`DisableConfirmDialog`) → same warning.
5. A mod with no dependents → no warning, proceeds normally.

**Caveats / expected:** overridable (not a block). Completeness depends on sync — un-synced
requirements can under-report; only mods with a `nexus_mod_id` count. `ConflictDetailDrawer`'s
"Remove old version" is **intentionally** unguarded: it only fires for a superseded duplicate,
whose dependents are inherited by the replacing version (same `nexus_mod_id`), so a warning there
would be a false alarm.

**PRs:** original nexus #244/#246/#248 → main #245/#247/#249 · gap-closure nexus #270 → main #272.

---

## F6 — Change / activity log (+ undo)

**What:** a per-game, timestamped history of meaningful actions (install, uninstall, enable,
disable, deploy, undeploy, download), with **one-click undo** for the reversible ones.

**How:** `ActivityLog` table, `record_activity()` at the choke points. `GET /{game}/activity`
returns newest-first, pruned to the last 1000 per game. **Undo** (`POST /{game}/activity/{id}/undo`)
reverses an entry — **Tier A+B**: enable/disable → toggle back, install → uninstall, uninstall →
reinstall from the original archive. It re-validates current state, records the inverse as its own
(non-undoable) row, and 409s on a stale entry (mod gone, archive missing) or a double-undo.
Deploy/undeploy/download are **not** undoable. Frontend: an **Activity** page (sidebar, History
icon) with a per-row **Undo** button + confirm, and an "Undone" badge on reversed rows.

**Test:**
1. Install a mod → an `Installed` row appears (mod name + timestamp).
2. Disable / enable it → `Disabled` / `Enabled` rows. Deploy/Undeploy → those rows. Download an
   update → a `Downloaded` row. Restart the app → entries persist (SQLite).
3. **Undo** an `Installed` row → the mod is uninstalled; the row shows **"Undone"** and an
   `Undid` row is appended.
4. **Undo** a `Disabled` row → the mod is re-enabled.
5. **Undo** an `Uninstalled` row → the mod is **reinstalled** from its archive (note: prior load
   order / enabled state are *not* restored — the confirm says so). Delete the archive first, then
   try → refused with a clear error.
6. Deploy/undeploy/download rows have **no** Undo button.

**Caveats / expected:** undo is one-shot per row (guarded by `undone_at`). Rows recorded *before*
the gap-closure migration aren't undoable (no captured metadata). Per-game, newest-first, retention 1000.

**PRs:** original nexus #250 → main #251 · gap-closure (undo) nexus #279 → main #280.

---

## F2 — Unified health / pre-launch check

**What:** scans for the problems that most often break a launch and (a) shows them in a widget on
the game page, (b) warns before **Play** if anything critical is found.

**How:** `GET /{game}/health` runs **five** checkers — missing/disabled **requirements**,
**outdated** mods, incomplete **install integrity** (enabled-but-not-deployed / drift),
**foreign/untracked** files, and **misplaced files** (the "wrong directory" check) — returning
`{issues, critical, warning, info, ok}`. The misplaced-files check is DB-only + offline: it flags
enabled mods whose files land under **no recognized mod root** (`archive/bin/red4ext/r6/mods/engine`)
— `warning` if *all* files are misplaced (the mod is inert), `info` if some are. Frontend:
`HealthWidget`; the **Play** button → `handleLaunch` fetches `/health` and, on **critical** issues,
shows a warn-with-override dialog (`launchGate`) before deploy + launch.

**Test:**
1. Open a game page → `HealthWidget` shows "No issues found" or a list with counts + a suggested
   fix per issue.
2. Create a problem — disable a required mod/framework, leave an enabled mod undeployed, or have an
   outdated mod — and confirm it appears.
3. **Misplaced files:** install a mod whose archive has no recognized layout (files outside
   `archive/`, `bin/`, `r6/`, …) → a `misplaced_files` issue ("none of its N files are under a
   recognized mod folder"). A normally-laid-out mod produces none.
4. Click **Play** with a **critical** issue → warn-with-override dialog → deploy + launch. With no
   critical issues → launches directly.

**Caveats / expected:** the launch gate is warn-with-override, not a hard block. **"Version
mismatch" (mod-vs-game-patch compatibility) is deliberately NOT implemented** — Nexus exposes no
per-mod compatible-game-version (GraphQL or REST) and no patch date is stored, so any heuristic
would be a false-positive generator. The accurate coverage we keep: "newer version on Nexus" (info)
+ "missing required framework" (critical).

**PRs:** original nexus #252 → main #253 · gap-closure (misplaced-files) nexus #277 → main #278.
*(Handler runs in a threadpool — see perf follow-ups.)*

---

## F3 — Diagnostics / support export

**What:** one button that bundles everything needed for a bug report into a single JSON file —
**no secrets**.

**How:** `GET /diagnostics` (`build_diagnostics`) assembles: `system` (OS / Python / CPU / RAM via
`psutil`+`platform`), `games[]` (install path, game version, installed mods, load order), and
`log_tail` (last 500 lines of `rippermod.log`). Each section is best-effort (a probe failure
degrades gracefully). Frontend: a **Diagnostics** card in Settings → "Export diagnostics" → OS save
dialog → JSON (with `app_version` from `__APP_VERSION__` merged in).

**Test:**
1. Settings → **Diagnostics** → **Export diagnostics** → choose a path → a JSON file is written.
2. Open it: confirm `generated_at`, `system`, `games` (with mods + load order + game version),
   `log_tail` (array), and `app_version`.
3. **Secret check:** search the file for your Nexus API key — it must **not** appear anywhere.

**Caveats / expected:** fully offline (no Nexus calls). A failing section is partial, not a crash.

**PRs:** nexus #254 → main #255.

---

## F5 — Save game backups

**What:** snapshots your Cyberpunk 2077 saves **before each risky change** so a bad mod can't cost
you progress, plus a manual **Backup now** and one-click **Restore**. On by default; keeps the
**15** most recent.

**How:** `save_backup_service` does a real `shutil.copytree` (not a hardlink) into
`data_dir/save_backups/<timestamp>/saves` with a `manifest.json`. A content signature
(relpath:size:mtime) drives **dedupe**; rolling retention keeps 15. The best-effort hook
`maybe_backup_before(reason=…)` runs before **deploy** (`pre-deploy`), **uninstall**
(`pre-uninstall`), **disable** (`pre-disable`), and **undeploy** (`pre-undeploy`) — a backup
failure never aborts the operation, and it's gated to the `cyberpunk2077` game. Restore refuses
while the game is running, takes a `pre-restore` snapshot first, then copies the backup over the
live folder (overwriting same-named saves; it does not delete newer ones). Save-folder default:
`%USERPROFILE%/Saved Games/CD Projekt Red/Cyberpunk 2077/`, overridable. Endpoints:
`GET /save-backups`, `POST /save-backups/backup-now`, `POST /save-backups/restore`. Frontend: a
**Save Backups** card in Settings (toggle, folder + Change…, Backup now, list + Restore).

**Test:**
1. Settings → **Save Backups** → shows the resolved save folder, "found" status, and the toggle (on).
2. **Backup now** → a backup appears (timestamp, reason, file count, size); verify the files exist
   under `…/com.rippermod.app/save_backups/<timestamp>/saves/`.
3. Trigger a **deploy** → a `pre-deploy` backup. **Uninstall** / **disable** a mod / **undeploy** →
   a `pre-uninstall` / `pre-disable` / `pre-undeploy` backup (visible by `reason` in the list).
4. Do two risky actions in a row without changing saves → only **one** backup (dedupe).
5. **Restore** (game **closed**): pick a backup → confirm → saves replaced; a `pre-restore` snapshot
   is taken first. **Restore** while the game is **running** → refused (409 / error toast).
6. Create more than 15 backups → only the 15 newest remain (retention).
7. **Change…** → pick another folder → status updates; clearing the override falls back to default.

**Caveats / expected:** backups are real byte copies. A backup failure never blocks the operation.
Auto-backup fires only for Cyberpunk 2077, and only on the destructive actions above (enable and
install are additive → no backup).

**PRs:** original nexus #257 → main #258 · gap-closure (uninstall/disable/undeploy + retention 15)
nexus #273 → main #276.

---

## F4 — Framework mod monitor

**What:** a per-game widget showing install status + version of the 6 core frameworks (RED4ext,
redscript, ArchiveXL, TweakXL, Codeware, Cyber Engine Tweaks), flagging **missing**, **disabled**,
and **outdated** (the latter even offline).

**How:** `detect_frameworks` checks an on-disk marker per framework and reads its version with
`pefile`. **redscript** (`engine/tools/scc.exe`) has no on-disk version → existence-only. A
`manager_status` is derived by joining each framework's `nexus_mod_id` to the manager's
`InstalledMod`/`disabled` state: **active** (marker present), **deploy_pending** (installed +
enabled but not yet deployed), **disabled** (installed but disabled), **not_installed**. Latest
versions come from one read-only GraphQL batch when a key is configured, and **fall back to the
`NexusModMeta` cache when offline** (the response carries `latest_is_cached`). `GET /{game}/frameworks`.

**Test:**
1. Game page → the **Frameworks** widget lists the 6 with status + version (e.g. RED4ext 1.29.1,
   ArchiveXL 1.26.2, TweakXL 1.11.3, Codeware 1.19.1, CET 1.37.1). **redscript** shows "installed
   (version unknown)".
2. With a Nexus key + online → frameworks behind the latest show an **outdated** badge + the latest
   version (e.g. RED4ext 1.29.1 → 1.30.0).
3. **Disable** a framework's mod in the manager (so its files aren't deployed) → it shows
   **disabled** (distinct from "not installed"). A freshly installed-but-undeployed framework shows
   **deploy_pending**.
4. **Offline / no key** but a latest version was cached earlier → still flags **outdated** (marked
   as cached). With no cache and no key → installed + version, no outdated (graceful, no error).
5. Remove/rename a framework's marker → **not installed** + a Nexus link. Click a link → opens its
   mod page.

**Caveats / expected:** versions read without launching the game. **redscript never shows outdated**
(no on-disk version). Offline `outdated` is best-effort — only as good as what's cached in
`NexusModMeta` (framework metadata is cached opportunistically, so it may be empty). Verified Nexus
ids: RED4ext 2380, CET 107, redscript 1511, ArchiveXL 4198, TweakXL 4197, Codeware 7780.

**PRs:** original nexus #262 (+ fix #264) → main #263 · gap-closure (disabled + offline) nexus #271
(+ type refactor #275) → main #274.

---

## F1 — In-app mod error reader (+ attribution)

**What:** a per-game widget surfacing warnings/errors parsed from the framework log files, grouped
by source, **attributing each error to the responsible mod where possible** — so you can see
what's broken (and which mod) without opening logs.

**How:** `log_reader_service` reads the latest log per source and parses with **tolerant**
per-format regex (unmatched lines skipped). Sources: spdlog (RED4ext + ArchiveXL/TweakXL/Codeware),
CET, redscript. Keeps `error` + `warning` (spdlog `critical` → error); caps 50/source + 300 total;
newest-first. **Attribution** (gap-closure): the router builds a game-relative-path → mod-name map
(`get_file_ownership_map`) and each error whose line carries an on-disk path is matched to the
owning mod — redscript `.reds`, RED4ext plugin DLL, TweakXL (stateful, via the preceding
`Reading "<x>.yaml"` line), CET `mods/<name>` (directory match). `GET /{game}/log-errors`. Frontend:
`LogErrorsWidget` (scrollable, **Refresh**, severity icons, source badge, **mod-name badge** when
attributed).

**Test:**
1. Launch the game at least once (logs are written on launch), then return to the app.
2. Game page → the **Mod errors** widget lists recent errors/warnings grouped by source.
3. **Attribution:** for an error whose line names a file owned by an installed mod (e.g. a redscript
   `.reds` error, a TweakXL yaml issue, a CET mod error), the row shows an **accent mod-name badge**.
   Errors with no on-disk path (most ArchiveXL/Codeware lines) show **no** badge — that's expected.
4. **Refresh** → re-reads the logs (after a new game session, new errors appear).
5. No errors → "no recent errors".

**Caveats / expected:** read on demand (no live tail). Attribution is **best-effort and never
guesses** — a miss leaves the row unattributed (no badge), never wrong. **ArchiveXL/Codeware**
(virtual depot paths) and CET `scripting.log` Lua errors carry no on-disk path → unattributable.
redscript compile errors show the summary line only (multi-line detail not captured), and redscript
has no version.

**PRs:** original nexus #265 (+ fix #267) → main #266 · gap-closure (attribution) nexus #281 → main #282.

---

## Performance follow-ups

Surfaced during the F3 review: several route handlers were `async def` but did purely blocking
work, stalling the event loop (and the desktop UI).

- **perf(health)** — `health` handler → plain `def` (Starlette runs it in a threadpool). nexus #256 → main #259.
- **perf(install)** — all 18 `install.py` handlers → plain `def`, so install/deploy/uninstall no
  longer freeze the backend during long operations. nexus #260 → main #261.
- Both also corrected `.claude/rules/backend.md`, whose "MUST be `async def`" rule (with an inverted
  rationale) had caused the pattern. (The activity-undo handler follows the corrected rule: plain `def`.)

**Test:** start a long install or deploy → the app/UI stays responsive (other requests aren't frozen).

---

## Known caveats & remaining limits

The gap-closure round resolved the major deferrals (F1 attribution, F6 undo, F4 disabled/offline,
F5 risky-change backups, F2 misplaced-files, F7 all surfaces). What remains, by design:

- **F1 — unattributable sources.** ArchiveXL/Codeware error lines carry virtual depot paths (not
  on-disk paths), and CET `scripting.log` Lua errors carry no path — these stay unattributed. Multi-
  line redscript compile detail is still summary-line only.
- **F2 — no game-patch version-mismatch check.** Not derivable from available data (see F2 caveats).
- **F4 — redscript version** is not readable on disk (existence-only); offline `outdated` is only as
  good as the `NexusModMeta` cache.
- **F6 — undo scope.** Tier A+B only (enable/disable/install/uninstall). Deploy/undeploy aren't
  undoable (game-scoped, not per-event); undo-uninstall restores files but not prior load
  order / enabled state.
- **F1/F4 — format volatility.** Log/version formats are external and change across framework
  versions. Parsers are tolerant (unknown lines skipped), but a framework update could change a
  format until the parser is updated.

## PR index

**Original round:**

| Item | nexus | main |
|---|---|---|
| F7 reverse-dep warning (+ follow-up fixes) | #244 / #246 / #248 | #245 / #247 / #249 |
| F6 activity log | #250 | #251 |
| F2 health check | #252 | #253 |
| F3 diagnostics export | #254 | #255 |
| F5 save backups | #257 | #258 |
| F4 framework monitor (+ fix #264) | #262 | #263 |
| F1 mod error reader (+ fix #267) | #265 | #266 |
| perf(health) | #256 | #259 |
| perf(install) | #260 | #261 |

**Gap-closure round:**

| Item | nexus | main |
|---|---|---|
| F7 dependents on conflict + archive paths | #270 | #272 |
| F4 disabled-state + offline outdated (+ type refactor #275) | #271 | #274 |
| F5 backups on uninstall/disable/undeploy | #273 | #276 |
| F2 "misplaced files" (wrong-directory) check | #277 | #278 |
| F6 activity undo (Tier A+B) | #279 | #280 |
| F1 error→mod attribution | #281 | #282 |

Roadmap epic: **#243**.
