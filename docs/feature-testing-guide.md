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
| F7 reverse-dep warning | `GET …/install/installed/{mod_id}/dependents` | confirm dialogs in `InstalledModsTable` |
| F6 activity log | `GET …/{game}/activity` | **Activity** page (sidebar) |
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
`NexusModRequirement` rows (no Nexus call). Frontend `InstalledModsTable` calls `useDependents` /
`collectExternalDependents` and shows `DependentsWarning` inside the confirm dialog on: single
uninstall, bulk uninstall, single disable, bulk disable, and the **select-all** disable path.

**Test:**
1. Have two installed mods where **A requires B**, and A's requirement data has been **synced**
   (A was correlated/synced so its `modRequirements` are stored locally).
2. Disable or uninstall **B** → the confirm dialog lists **A** as a dependent ("based on synced
   data") and lets you **proceed anyway**.
3. Select B together with other mods and bulk-disable / bulk-delete → the warning aggregates all
   external dependents of the selection. Repeat via **select-all**.
4. A mod with no dependents → no warning, proceeds normally.

**Caveats / expected:** the warning is overridable (not a block). Completeness depends on sync —
if A's requirements were never synced, B can under-report. Only mods with a `nexus_mod_id` count.

**PRs:** nexus #244, #246, #248 → main #245, #247, #249.

---

## F6 — Change / activity log

**What:** a per-game, timestamped history of meaningful actions: install, uninstall, enable,
disable, deploy, undeploy, and update-download.

**How:** `ActivityLog` table (auto-created), `record_activity()` called at the choke points
(`install_service` install/uninstall/toggle, `download_service`, the deploy handler in
`routers/install.py`). `GET /{game}/activity` returns newest-first and prunes to the last 1000
per game on read. Frontend: an **Activity** page in the sidebar (History icon).

**Test:**
1. Install a mod → Activity page shows an `install` entry (mod name + timestamp).
2. Disable / enable it → `disable` / `enable` entries.
3. Deploy → a `deploy` entry (with file count); Undeploy → `undeploy`.
4. Download an update (Updates tab) → a `download` entry.
5. Restart the app → entries persist (stored in SQLite).

**Caveats / expected:** read-only in v1 (no undo buttons). Per-game, newest-first, retention 1000.

**PRs:** nexus #250 → main #251.

---

## F2 — Unified health / pre-launch check

**What:** scans for the problems that most often break a launch and (a) shows them in a widget on
the game page, (b) warns before **Play** if anything critical is found.

**How:** `GET /{game}/health` runs four checkers — missing/disabled **requirements**, **outdated**
mods, incomplete **install integrity** (enabled-but-not-deployed / drift), and **foreign/untracked**
files — returning `{issues, critical, warning, info, ok}`. Frontend: `HealthWidget` on the game
page; the **Play** button → `handleLaunch` fetches `/health` and, if there are **critical** issues,
shows a warn-with-override dialog (`launchGate`) before `runDeployAndLaunch` (deploy → `launch_game`).

**Test:**
1. Open a game page → `HealthWidget` shows "No issues found" or a list with critical/warning/info
   counts and a suggested fix per issue.
2. Create a problem — e.g. disable a required mod/framework, leave an enabled mod undeployed, or
   have an outdated mod — and confirm it appears in the widget.
3. Click **Play** while a **critical** issue exists → a dialog warns ("N critical issues may stop
   mods from working") and lists them, with an override to proceed → then deploys + launches.
4. Click **Play** with no critical issues → launches directly.

**Caveats / expected:** the launch gate is warn-with-override, not a hard block.

**PRs:** nexus #252 → main #253. *(Handler later moved to a threadpool — see perf follow-ups.)*

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

**What:** snapshots your Cyberpunk 2077 saves **before each deploy** so a bad mod can't cost you
progress, plus a manual **Backup now** and one-click **Restore**. On by default; keeps the **10**
most recent.

**How:** `save_backup_service` does a real `shutil.copytree` (not a hardlink) into
`data_dir/save_backups/<timestamp>/saves` with a `manifest.json`. A content signature
(relpath:size:mtime) drives **dedupe**; rolling retention keeps 10. The pre-deploy hook in
`deploy()` is **deduped + best-effort** (a backup failure never aborts a deploy) and gated to the
`cyberpunk2077` game. Restore refuses while the game is running, takes a `pre-restore` safety
snapshot first, then copies the backup over the live folder (overwriting same-named saves; it does
not delete newer ones). Save-folder default: `%USERPROFILE%/Saved Games/CD Projekt Red/Cyberpunk
2077/`, overridable. Endpoints: `GET /save-backups`, `POST /save-backups/backup-now`,
`POST /save-backups/restore`. Frontend: a **Save Backups** card in Settings (toggle, folder +
Change…, Backup now, list + Restore).

**Test:**
1. Settings → **Save Backups** → shows the resolved save folder, "found" status, and the toggle (on).
2. **Backup now** → a backup appears in the list (timestamp, file count, size); verify the files
   exist under `…/com.rippermod.app/save_backups/<timestamp>/saves/`.
3. Trigger a **deploy** from the game page → a `pre-deploy` backup is created. Deploy again without
   changing saves → **no** new backup (dedupe).
4. **Restore** (game **closed**): pick a backup → confirm → your saves are replaced; a `pre-restore`
   snapshot is created first.
5. **Restore** while the game is **running** → refused (409 / error toast).
6. Create more than 10 backups → only the 10 newest remain (retention).
7. **Change…** → pick another folder → status updates; clearing the override falls back to default.

**Caveats / expected:** backups are real byte copies. A backup failure never blocks a deploy.
Auto-backup only fires for Cyberpunk 2077.

**PRs:** nexus #257 → main #258.

---

## F4 — Framework mod monitor

**What:** a per-game widget showing install status + version of the 6 core frameworks (RED4ext,
redscript, ArchiveXL, TweakXL, Codeware, Cyber Engine Tweaks), flagging **missing** and **outdated**.

**How:** `detect_frameworks` checks an on-disk marker per framework and reads its version with
`pefile` (RED4ext `red4ext/RED4ext.dll`, CET `bin/x64/plugins/cyber_engine_tweaks.asi`, and
ArchiveXL/TweakXL/Codeware `red4ext/plugins/<Name>/<Name>.dll`). **redscript** (`engine/tools/scc.exe`)
has no on-disk version source → existence-only. Latest versions come from one read-only GraphQL
batch (best-effort; cached). `GET /{game}/frameworks`. Frontend: `FrameworksWidget` on the game page.

**Test:**
1. Game page → the **Frameworks** widget lists the 6 with installed/missing + version (e.g. RED4ext
   1.29.1, ArchiveXL 1.26.2, TweakXL 1.11.3, Codeware 1.19.1, CET 1.37.1). **redscript** shows
   "installed (version unknown)".
2. With a Nexus key + online → frameworks behind the latest show an **outdated** badge + the latest
   version (e.g. RED4ext 1.29.1 → 1.30.0).
3. Without a key / offline → shows installed + version, no outdated (graceful, no error).
4. Remove/rename a framework's marker file → it shows **not installed** + a Nexus link.
5. Click a framework's Nexus link → opens its mod page in the browser.

**Caveats / expected:** versions read without launching the game. **redscript never shows outdated**
(no on-disk version). Verified Nexus ids: RED4ext 2380, CET 107, redscript 1511, ArchiveXL 4198,
TweakXL 4197, Codeware 7780.

**PRs:** nexus #262 (+ version-normalize fix #264) → main #263.

---

## F1 — In-app mod error reader

**What:** a per-game widget surfacing warnings/errors parsed from the framework log files, grouped
by source, so you can see what's broken without opening logs.

**How:** `log_reader_service` reads the latest log per source and parses with **tolerant** per-format
regex — a line that doesn't match is skipped (formats are external/volatile). Sources + formats
(verified against a real install):
- **spdlog** `[ts] [name-or-pid] [level] msg` — `red4ext/logs/red4ext-*.log` and
  `red4ext/plugins/{ArchiveXL,TweakXL,Codeware}/<Name>.log`.
- **CET** `[ts UTC±] [level] [func] [pid] msg` — `cyber_engine_tweaks/{cyber_engine_tweaks,scripting}.log`.
- **redscript** `[LEVEL - date] msg` — `r6/logs/redscript_rCURRENT.log`.

Keeps `error` + `warning` (spdlog `critical` → error); caps **50 per source** (so one noisy log
can't drown the rest) and 300 total; newest-first. `GET /{game}/log-errors`. Frontend:
`LogErrorsWidget` on the game page (scrollable, **Refresh**, severity icons, source badges).

**Test:**
1. Launch the game at least once (logs are written on launch), then return to the app.
2. Game page → the **Mod errors** widget lists recent errors/warnings grouped by source (e.g.
   "ArchiveXL: Can't resolve mappin…", TweakXL warnings/errors, RED4ext crash reports if any).
3. **Refresh** → re-reads the logs (after a new game session, new errors appear).
4. No errors → "no recent errors".

**Caveats / expected:** read on demand (no live tail). Tolerant parsing won't crash on unknown
lines. **No mod attribution in v1** (the `mod_name` field is always null — deferred). redscript
compile errors show the summary line only (multi-line detail not captured), and redscript has no
version.

**PRs:** nexus #265 (+ critical-level fix #267) → main #266.

---

## Performance follow-ups

Surfaced during the F3 review: several route handlers were `async def` but did purely blocking
work, stalling the event loop (and the desktop UI).

- **perf(health)** — `health` handler → plain `def` (Starlette runs it in a threadpool). nexus #256 → main #259.
- **perf(install)** — all 18 `install.py` handlers → plain `def`, so install/deploy/uninstall no
  longer freeze the backend during long operations. nexus #260 → main #261.
- Both also corrected `.claude/rules/backend.md`, whose "MUST be `async def`" rule (with an inverted
  rationale) had caused the pattern.

**Test:** start a long install or deploy → the app/UI stays responsive (other requests aren't frozen).

---

## Known caveats & deferred follow-ups

- **F1 mod attribution** — telling *which mod* caused an error is deferred. Name-substring matching
  was too noisy; a reliable path-based version (via the file-ownership map) is the planned follow-up.
- **F1 redscript errors** — only the summary line is captured (multi-line compile detail isn't).
- **F4 redscript version** — not readable on disk; shown as existence-only.
- **F1/F4 format volatility** — log/version formats are external and change across framework
  versions. Parsers are tolerant (unknown lines skipped), but a framework update could change a
  format until the parser is updated.

## PR index

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

Roadmap epic: **#243**.
