# VFS: Per-File Hardlinks + Per-REDmod Junctions

**Status:** Design (pending pre-implementation spike)
**Date:** 2026-05-14
**Owner:** @Y4rd13
**Editions:** Full (`main`) + Nexus (`nexus-compliant`) — identical implementation, propagated by cherry-pick. No merge between branches.

## 1. Problem

RipperMod Manager currently extracts mod archives directly into the Cyberpunk 2077 install directory (`install_service.install_mod`, `backend/src/rippermod_manager/services/install_service.py:63`). This:

- Pollutes the game directory with mod content.
- Makes profile switching expensive (file renames per mod).
- Breaks Steam "Verify integrity of game files" workflows when users follow CDPR's recommended pre-verify cleanup, which deletes `/mods`, `/r6`, `/red4ext`, `/archive/pc/mod`, `bin/x64/winmm.dll`, `bin/x64/version.dll`.
- Conflicts with the dominant user expectation set by MO2 / Vortex: "the mod manager keeps my game folder clean."
- Was explicitly flagged by Nexus user feedback: *"i'll wait till the mods folder could be outside the game dir"*.

We need to keep mod content in a staging directory and surface it inside the game directory through a mechanism that:

1. Does not require admin / elevation.
2. Does not require a custom kernel driver or alpha-quality user-mode VFS.
3. Coexists with vanilla files in mixed directories (`r6/`, `bin/x64/`, `archive/pc/`).
4. Survives Steam updates and (where possible) Steam Verify.
5. Allows REDmod, RED4ext, CET, redscript, and TweakXL to load mods without behavior change.
6. Is reversible: uninstalling RipperMod leaves no orphans.

## 2. Goals

- Mod files live in `<game>/downloaded_mods/<staging>/<mod>/...`; the game directory contains only **links** to them at the canonical mod paths.
- Install, uninstall, enable/disable, and profile switch operations do not copy file content.
- Existing installs migrate in place without data loss or game restart.
- Code is identical across the Full and Nexus editions.
- Implementation is feasible without admin privileges and without a custom launcher (Steam "Play" button keeps working).

## Non-goals (this spec)

- Linux / SteamOS support — RipperMod is Windows-only by construction (`config.py:12`, `frontend/src-tauri/src/lib.rs:24,43,105,154` all `#[cfg(target_os = "windows")]`). A future spec can add OverlayFS bind-mounts; not now.
- True kernel-level VFS (USVFS / minifilter driver / WinFsp). Rejected in the validation report: alpha-quality crash surface, proxy-launcher requirement, AV false positives, no offsetting win for Cyberpunk.
- Cross-volume staging. Today's staging dir is always a child of `game.install_path` (`install_service.py:44`), so same-volume is automatic. Cross-volume staging stays out of scope; if a future user requests it, we add an `AppSetting` override with same-volume validation at write time.
- Auto-managed proxy DLLs (`winmm.dll` / `version.dll` at `bin/x64/` root) get the same hardlink treatment as any other mod file — no special-case logic.

## 3. Architectural Decision

**Per-file hardlinks for every file, with one exception: `mods/<modname>/` directories get per-mod NTFS junctions.**

| Surface | Mechanism | Why |
|---|---|---|
| `archive/pc/mod/*.archive` | hardlink per file | Mod-only dir, simple file overlay |
| `r6/scripts/`, `r6/tweaks/` | hardlink per file | Mod-only |
| `red4ext/plugins/`, `bin/x64/plugins/` | hardlink per file | Mod-only |
| `bin/x64/cyber_engine_tweaks/mods/` | hardlink per file | Mod-only |
| `bin/x64/winmm.dll`, `version.dll`, `dinput8.dll` | hardlink (single file at the root of a mixed dir) | Mixed dir — must not junction parent |
| `engine/config/...` | hardlink per file | Mixed dir — must not junction parent |
| `mods/<modname>/` (REDmod) | **junction** to `staging/<mod>/mods/<modname>/` | REDmod folders contain hundreds of small files in deep subtrees; one junction per REDmod is cleaner than N hardlinks. Junctions are transparent to `redmod.exe deploy`. |

### Why hardlinks (validated against alternatives)

The validation pass (`see research below in §15`) confirmed:

- **Mixed dirs kill directory-level junctions.** Vanilla CDPR ships `r6/cache/final.redscripts`, `bin/x64/Cyberpunk2077.exe`, `bin/x64/CrashReporter/`, `archive/pc/content/`, `archive/pc/ep1/`. A junction over `r6/` or `bin/x64/` hides vanilla content; a junction over `archive/pc/` hides `content/` and `ep1/`.
- **CET drops `winmm.dll` at the `bin/x64/` root.** No subdirectory junction can deploy a single sibling file alongside vanilla `Cyberpunk2077.exe`. Hardlinks handle this in one mechanism.
- **Vortex chose this exact model for Cyberpunk 2077.** [`cyberpunk2077_ext_redux`](https://github.com/E1337Kat/cyberpunk2077_ext_redux) disables symlink, leaves hardlink+copy. Per the modding wiki: *"For 99% of Cyberpunk mods, Hardlink is the correct setting."*
- **Same-volume constraint is satisfied by construction.** `downloaded_mods/` always lives under `game.install_path`. No code change needed to guarantee this.
- **NTFS rename semantics preserve the existing `.disabled` toggle pattern.** Renaming one hardlink updates only that directory entry; the staging copy and the inode are untouched.
- **Steam Verify is benign for hardlinks at mod-only paths.** Steam's depot manifest does not include `mods/`, `archive/pc/mod/`, `r6/scripts/`, `r6/tweaks/`, `red4ext/`, `bin/x64/plugins/`. Hardlinks there are invisible to Verify. The risk surface is `winmm.dll`/`version.dll`/`engine/config/...` — if a future game patch ships any of those paths, Verify will replace the hardlinked file. Mitigation: drift-detection on launch, redeploy from staging.

### Implementation language

**Rust in Tauri (`src-tauri/src/vfs.rs`)** for the syscalls. **Python in FastAPI** for orchestration.

| Concern | Python | Rust (Tauri command) |
|---|---|---|
| Archive extraction to staging | ✅ existing code | — |
| Conflict resolution, manifest, DB writes | ✅ existing | — |
| Write-ahead journal (`deploy.log`) | ✅ | — |
| `modlist.txt` generation | ✅ existing | — |
| Hardlink create / delete | ❌ (200 IPC calls = 2-5s) | ✅ batch in-process |
| Junction create / delete | — | ✅ via `junction` crate v2.0.0 |
| Same-volume check | — | ✅ `MetadataExt::volume_serial_number()` |
| Game-process-running guard | — | ✅ `sysinfo` crate |
| Filesystem-supports-hardlinks probe (canary) | — | ✅ |

Justification: deployment is a batch syscall workload. Rust hard-link-creation on 200+ files runs in <100ms; HTTP-marshalled Python calls per file are visibly slow. Rust's `io::Error::kind()` maps cleanly to a typed `VfsError` enum the frontend can match on. `#[cfg(target_os = "windows")]` makes the platform gate compile-time-checked.

## 4. Data Model Changes

### `InstalledModFile` (`backend/src/rippermod_manager/models/install.py:30`)

Add:

```python
source_path: str = Field(default="")  # relative path under <game>/downloaded_mods/<staging>/<mod>/
link_kind: str = Field(default="hardlink")  # "hardlink" | "junction" | "copy"
```

Migration in `database.py::_migrate_missing_columns`:
- Add columns with defaults so old rows remain valid.
- On first migration, backfill `source_path` for existing installs (see §9).

### `InstalledMod` (`backend/src/rippermod_manager/models/install.py:7`)

Add:

```python
staging_dir: str = Field(default="")  # relative to <game>/downloaded_mods/, e.g. "Phantom_Liberty_HUD_Improvements"
deployed: bool = Field(default=False)  # True iff links exist in game dir
deploy_drift: bool = Field(default=False)  # True if a deploy/undeploy operation was started but failed mid-way and a journal replay is pending
```

### New table: `deploy_journal`

```python
class DeployJournalEntry(SQLModel, table=True):
    __tablename__ = "deploy_journal"
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    operation: str  # "link" | "unlink" | "junction" | "rm_junction"
    src: str  # staging-relative path
    dst: str  # game-relative path
    status: str  # "pending" | "done" | "failed"
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

Purpose: write-ahead log for atomic batched deploys. On startup, replay rows where `status="pending"` by removing the partial target (idempotent) and clearing the journal. TxF is deprecated; this is the modern replacement (per Microsoft Learn).

### `CYBERPUNK_DEFAULT_PATHS` (`backend/src/rippermod_manager/constants.py:4`)

Add `engine` as a recognized mod root. Otherwise INI-tweak mods (e.g., Nexus #7330 "General Performance Improvements") classify as `UNKNOWN` in `detect_layout()`. This is an existing gap, surfaced by the VFS work.

```python
CYBERPUNK_DEFAULT_PATHS = [
    ("archive/pc/mod", "Main mod archives", True),
    ("bin/x64/plugins/cyber_engine_tweaks/mods", "CET script mods", True),
    ("red4ext/plugins", "RED4ext plugins", True),
    ("r6/scripts", "Redscript mods", True),
    ("r6/tweaks", "TweakXL tweaks", True),
    ("bin/x64/plugins", "ASI/plugin loaders", True),
    ("mods", "REDmod mods", True),
    ("engine", "Engine config tweaks", True),  # NEW
]
```

## 5. Components

### 5.1 New: `services/deploy_service.py` (Python)

Responsibilities:

- `extract_to_staging(game, archive_path, ...)` — replaces the "write to game dir" half of `install_mod`. Extracts to `<game>/downloaded_mods/<staging>/<mod>/<relpath>`. Returns `(staging_dir, file_list)`. Inherits FOMOD path-traversal guards.
- `deploy(game, session, mods=None)` — computes link plan, writes journal rows, invokes Tauri `vfs_batch_link`, marks success in DB. If `mods=None`, deploys all enabled mods.
- `undeploy(game, session, mods=None)` — inverse; unlinks files and removes junctions.
- `detect_drift(game, session) -> DriftReport` — for each enabled `InstalledMod`, checks each `InstalledModFile`:
  - `link_kind="hardlink"`: `os.path.samefile(<staging>/<src>, <game>/<dst>)` → if False, mark `missing`.
  - `link_kind="junction"`: `junction_target_matches(<game>/<dst>, <staging>/<src>)` via Tauri call.
  - Returns counts: `total`, `linked`, `missing`, `foreign` (file exists at dst but is not our link).
- `pre_flight_check(game) -> PreflightReport` — runs:
  - Game-process-running check (`vfs_is_game_running` Tauri command).
  - Filesystem-hardlink-supported canary in staging dir.
  - Same-volume check (always true today, but assert anyway).
  - Free disk space estimate.

### 5.2 Modified: `services/install_service.py`

- `install_mod` is split into two phases:
  1. **Stage** — extract to `<game>/downloaded_mods/<staging>/<mod>/`; create `InstalledMod` + `InstalledModFile` rows with `source_path` set, `deployed=False`.
  2. **Deploy** (optional immediate, default ON) — call `deploy_service.deploy(game, session, mods=[installed])`.

  The signature stays compatible: same return shape, same exceptions. New optional kwarg `auto_deploy: bool = True`.

- `uninstall_mod` calls `deploy_service.undeploy(game, session, mods=[mod])` first, then removes the staging subtree and the DB rows.

- `toggle_mod` no longer renames files. It flips `installed_mod.disabled` and calls `deploy_service.deploy(game, session)` (or undeploy for the disabled set). Rationale: the existing `.disabled` rename trick *would* still work on hardlinks (point 4 of the gap-fill research), but conflating disable with deploy is cleaner — disable becomes a DB-level operation, deploy becomes the single point where filesystem state changes.

### 5.3 Modified: `services/fomod_install_service.py`

Same pattern as `install_mod`: extract to staging, defer link to `deploy_service`. FOMOD's existing path-traversal guards apply unchanged (`fomod_install_service.py:336-347`).

### 5.4 New Tauri commands: `frontend/src-tauri/src/vfs.rs`

```rust
#[tauri::command]
fn vfs_hardlink(src: PathBuf, dst: PathBuf) -> Result<(), VfsError>;

#[tauri::command]
fn vfs_unlink(dst: PathBuf) -> Result<(), VfsError>;

#[tauri::command]
fn vfs_junction(target: PathBuf, link: PathBuf) -> Result<(), VfsError>;

#[tauri::command]
fn vfs_remove_junction(link: PathBuf) -> Result<(), VfsError>;

#[tauri::command]
fn vfs_batch(ops: Vec<VfsOp>) -> Vec<VfsOpResult>;

#[tauri::command]
fn vfs_same_volume(a: PathBuf, b: PathBuf) -> Result<bool, VfsError>;

#[tauri::command]
fn vfs_probe_hardlink_support(staging_dir: PathBuf, target_dir: PathBuf) -> Result<bool, VfsError>;

#[tauri::command]
fn vfs_is_game_running(exe_name: String) -> bool;

#[tauri::command]
fn vfs_verify_link(src: PathBuf, dst: PathBuf) -> Result<bool, VfsError>;
```

`VfsError` enum (mapped from `io::Error::kind()`):

```rust
enum VfsError {
    CrossVolume,      // ErrorKind::CrossesDevices (EXDEV)
    AlreadyExists,    // EEXIST
    NotFound,         // ENOENT
    PermissionDenied, // EACCES
    NotNtfs,          // (detected pre-flight; not from a single op)
    FilesystemUnsupported, // canary failed
    GameRunning,      // pre-flight refused
    Other(String),
}
```

Crate deps in `frontend/src-tauri/Cargo.toml`:

```toml
[target.'cfg(windows)'.dependencies]
junction = "2"        # NTFS reparse points, no admin
sysinfo = "0.32"      # process-running check
```

Both Windows-only via `[target.'cfg(windows)']`. Linux/macOS builds compile to stubs that return `VfsError::Other("not implemented on this platform")`.

The IPC contract is documented in `frontend/src/lib/api.ts` as typed `VfsCommand` wrappers around `invoke()`.

### 5.5 Modified: `routers/install.py`

New endpoints:

```
POST /api/v1/games/{id}/deploy           # idempotent full deploy
POST /api/v1/games/{id}/undeploy
GET  /api/v1/games/{id}/deploy/status    # returns DriftReport
POST /api/v1/games/{id}/migrate-to-vfs   # one-time migration from copy to hardlink (§9)
```

Existing endpoints (`/install`, `/uninstall`, `/toggle`, `/preview`) keep their shape; they now call into `deploy_service` under the hood.

### 5.6 Frontend changes

**New components:**

- `frontend/src/components/mods/DeployStatusBadge.tsx` — titlebar indicator: "Deployed (47)", "Drift detected", "Not deployed". Reuses `useQuery` patterns.
- `frontend/src/components/mods/MigrationWizard.tsx` — one-time flow on first run after upgrade (see §9).
- `frontend/src/components/mods/UntrackedFilesDialog.tsx` — when migration finds files in the game dir not owned by any `InstalledMod`, prompt: adopt / ignore / delete.

**Modified components:**

- `frontend/src/components/mods/InstalledModsTable.tsx` — drop the "Disabled" rename indicator (no longer accurate); show "Pending redeploy" dot if `deploy_drift=true`.
- `frontend/src/components/layout/Titlebar.tsx` — add `DeployStatusBadge`. Auto-deploy on game launch (toggle in Settings, default ON).
- `frontend/src/pages/SettingsPage.tsx` — add a section: "Deployment" → toggle "Auto-deploy on launch", button "Verify deployment" (runs drift detection), button "Undeploy all" (for clean uninstall of RipperMod).
- `frontend/src/pages/OnboardingPage.tsx` — add a step: "RipperMod keeps your game folder clean. Mods are staged in `downloaded_mods/` and linked into the game directory only when you Deploy."

**Edition divergence:** zero. The components above are not in the "Files that diverge between branches" table in `docs/dual-release-strategy.md`. The implementation is identical on `main` and `nexus-compliant` and propagates via cherry-pick.

## 6. Workflows

### 6.1 Install (new flow)

1. User picks an archive from `downloaded_mods/`.
2. `POST /api/v1/install` → backend:
   a. `extract_to_staging()` writes files under `<game>/downloaded_mods/<staging>/<mod>/...`
   b. Creates `InstalledMod` + `InstalledModFile` rows with `source_path`, `link_kind`, `deployed=False`
   c. If `auto_deploy=True` (default): calls `deploy_service.deploy(game, mods=[installed])`
      - Writes `deploy_journal` rows with `status=pending`
      - Calls `vfs_batch` Tauri command with the link plan
      - Per-op result → mark journal row `done` or `failed`
      - On all-done: set `installed.deployed=True`
3. Returns `InstallResult` with new fields `staged: bool`, `deployed: bool`, `failed_ops: list`.

### 6.2 Uninstall (new flow)

1. `POST /api/v1/uninstall/{mod_id}` → backend:
   a. Calls `deploy_service.undeploy(game, mods=[mod])` — removes hardlinks/junctions, journals each op.
   b. Removes staging subtree `<game>/downloaded_mods/<staging>/<mod>/`.
   c. Deletes DB rows (`InstalledModFile` cascade, `ArchiveEntryIndex` cleanup, `ProfileEntry` cleanup, `LoadOrderPreference` cleanup — existing logic).
2. Returns `UninstallResult`.

### 6.3 Toggle (enable/disable) — semantics change

- Disable: set `disabled=True`, call `deploy_service.undeploy(mods=[mod])`. Staging files untouched.
- Enable: set `disabled=False`, call `deploy_service.deploy(mods=[mod])`.
- Profile switch: bulk toggle + single `deploy_service.deploy()` call computing the diff. Near-instant.

### 6.4 Deploy from scratch (e.g. after Steam Verify wiped links)

1. `POST /api/v1/games/{id}/deploy` (or auto on game launch)
2. `pre_flight_check()` — refuse if game is running.
3. For each enabled `InstalledMod`:
   - For each `InstalledModFile`: enqueue `(op="link", src=staging_full, dst=game_full)` or `(op="junction", ...)` for REDmod folders.
4. `vfs_batch(ops)` → Rust executes in-process.
5. Update journal + DB.
6. Frontend SSE stream emits progress per N ops.

### 6.5 Migration (existing user upgrading from pre-VFS RipperMod)

See §9.

## 7. Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| Game process running during deploy/undeploy | Refuse, surface "Close Cyberpunk 2077 to continue" toast |
| Hardlink target dst already exists, is NOT our hardlink (untracked file in game dir) | Refuse this single op, mark `failed`, surface in drift report. User resolves via "Untracked Files" dialog (adopt / ignore / delete dst then retry). |
| Hardlink target dst already exists and IS our hardlink to the right source | No-op, mark `done`. Deploy is idempotent. |
| Cross-volume hardlink (`EXDEV`) | Shouldn't happen by construction; if it does, mark `failed` with `CrossVolume`, surface "Staging dir is on a different drive than the game" message |
| Filesystem doesn't support hardlinks (canary failed) | Refuse deploy with `FilesystemUnsupported`; log instruction "RipperMod requires NTFS" |
| 1023-hardlink-per-inode limit | NTFS limit. Realistic only if a single staging file is linked to >1023 destinations — impossible by our design (one staging file → exactly one destination). Log if seen, mark `failed`. |
| Game patches replace `winmm.dll` / `version.dll` / `engine/config/...` | Hardlink at that path is broken (the inode behind the staging side is intact, but Steam wrote a fresh vanilla file at dst). Drift detection picks this up; one-click "Redeploy" restores. |
| Junction target dir already exists at `mods/<modname>/` (e.g. existing REDmod) | Refuse this op, surface "Existing REDmod folder at <path> — adopt or move". |
| Journal replay on startup | For each `pending` row, idempotent rollback: try to unlink dst if it's a hardlink to src; ignore if not. Then clear the row. |
| Power loss mid-deploy | Same as above — journal replay on next start. No torn state. |
| User manually deletes a hardlink in game dir | Drift detection flags it; user sees "1 missing file in mod X", "Redeploy" button. |
| User manually edits a hardlinked file in game dir | Inodes are shared — edit propagates to staging. Drift detection cannot see this (same inode, same content). Documented limitation. |
| Steam Verify replaces a hardlinked vanilla path (`winmm.dll`) | Hardlink is now broken (different inode). Drift detection picks up. Redeploy fixes. |
| Mod ships at `engine/config/...` and `detect_layout()` rejects it | Add `engine` to `CYBERPUNK_DEFAULT_PATHS` (this spec). |

## 8. Testing Strategy

### Unit tests (Python backend, ~50-60 new/modified)

- `tests/services/test_deploy_service.py` (NEW):
  - `test_deploy_creates_journal_then_clears`
  - `test_undeploy_removes_links_keeps_staging`
  - `test_deploy_idempotent`
  - `test_pre_flight_refuses_when_game_running` (mock `vfs_is_game_running`)
  - `test_drift_detection_missing_link`
  - `test_drift_detection_foreign_file_at_dst`
  - `test_engine_root_recognized` (touches `archive_layout.detect_layout`)

- `tests/services/test_install_service.py` (~28 tests):
  - Existing tests adapted for two-phase install (stage → deploy).
  - Mock Tauri command boundary with a Python fake `VfsBackend` that performs real `os.link()` calls so end-to-end behavior is verifiable in pytest.

- `tests/services/test_fomod_install_service.py` (~22 tests):
  - Same adaptation. FOMOD path-traversal guards continue to apply pre-staging.

- `tests/services/test_toggle.py`:
  - `test_toggle_no_longer_renames_in_game_dir`
  - `test_toggle_round_trip_idempotent`

- `tests/services/test_migration.py` (NEW):
  - `test_migrate_existing_install_moves_files_to_staging_and_hardlinks`
  - `test_migrate_resumes_after_partial_failure`
  - `test_migrate_detects_untracked_files`

### Integration tests (Rust)

- `src-tauri/src/vfs.rs` unit tests under `#[cfg(test)]`:
  - `test_hardlink_creates_then_unlink_removes`
  - `test_junction_create_target_observable_via_get_target`
  - `test_same_volume_true_for_sibling_dirs`
  - `test_cross_volume_returns_false` (skip if test runner is single-volume)
  - `test_hardlink_probe_canary` (write + link + cleanup in tmp)
  - `test_is_game_running_negative_case`

### End-to-end (manual spike — see §11)

Real Windows machine, real Cyberpunk install. Documented separately.

## 9. Migration Plan (existing users)

Existing users have `InstalledMod` rows whose files live **inside the game dir** (copy-installed). On first launch after upgrade, run a one-time migration.

### Migration flow

1. **Pre-flight**:
   - Game process not running (refuse if so, prompt to close).
   - Disk space: sum size of all files owned by `InstalledMod` rows; require 1.1× free in `<game>/downloaded_mods/`.
   - Hardlink canary (same probe as deploy).
2. **Plan**: for each `InstalledMod` row, determine `staging_dir = "<mod_name_safe>"`. For each `InstalledModFile`:
   - `src` = current location in game dir.
   - `dst` = `<game>/downloaded_mods/<staging_dir>/<relative_path>`.
   - Plan: `move src → dst`, then `hardlink dst → src`.
3. **Execute** (per mod, journaled):
   a. For each file: rename src → dst (atomic on NTFS for same-volume).
   b. For each file: hardlink dst → src.
   c. If any step fails partway: replay journal in reverse, restoring src.
4. **Untracked files**:
   - Walk known mod roots (`CYBERPUNK_DEFAULT_PATHS`) in the game dir.
   - For each file not owned by any `InstalledModFile`: report to user via `UntrackedFilesDialog`. Three actions per file: **adopt** (create an `InstalledMod` row for it, then migrate as above), **ignore** (leave it; mark as out-of-RipperMod), **delete**.
5. **Mark complete**: set `AppSetting vfs_migration_completed_at = <ts>`.

### Rollback

If the user wants to revert to the old copy-install model (e.g. uninstalling RipperMod):

- Tauri command or button "Undeploy all and unstage":
  1. `deploy_service.undeploy(game, mods=all_enabled)` — removes links.
  2. For each `InstalledModFile`: move from staging back to game dir (reverses the migration).
  3. Removes `downloaded_mods/<staging>/` subtrees.
  4. Optional: delete RipperMod DB.

This leaves the game dir in the same shape as a pre-VFS RipperMod install.

## 10. Dual-Edition Rollout

Per `docs/dual-release-strategy.md`:

- **Develop on `feat/vfs-hardlinks`** off `main`. All commits land here first.
- After spike + tests pass + claude[bot] review on `main`'s PR:
  1. Cherry-pick the merged squash commit onto a new branch `feat/vfs-hardlinks-nexus` off `nexus-compliant`.
  2. Resolve any frontend conflicts in divergent files (`Sidebar.tsx`, `RootLayout.tsx`, `GameDetailPage.tsx`, `DashboardPage.tsx`, `NexusModCard.tsx`, etc.). The deploy UI additions are net-new and shouldn't conflict in most of those files; conflicts will be limited to the few lines we add to `Sidebar.tsx` and `Titlebar.tsx`.
  3. Open a second PR against `nexus-compliant`.
- **Never merge between branches.** Always cherry-pick.

The backend code (`install_service.py`, `fomod_install_service.py`, `modlist_service.py`, `models/install.py`, `models/game.py`, `constants.py`, `archive_layout.py`, and all new files) is **byte-identical** across editions (confirmed by `git diff main..nexus-compliant -- <those paths>` returning empty). Cherry-pick is mechanical for the backend; the conflicts are confined to frontend.

**No release until both branches are validated.** Specifically:

1. Pre-implementation spike (§11) passes on a real Windows + Cyberpunk machine.
2. Backend tests pass on both branches.
3. claude[bot] approves both PRs.
4. Manual smoke test on a real install with ≥50 mods on each edition.
5. Only then squash-merge → semantic-release publishes v3.0.0 on `main` and v3.0.0-nexus.1 on `nexus-compliant` (both **breaking**, given migration touches existing file layouts).

## 11. Pre-Implementation Spike Checklist (gate — no code until passed)

These cannot be resolved from research alone. They require a real Windows machine with a real Steam install of Cyberpunk 2077. **Implementation does not start until every item is ✅ or has a documented workaround.**

| # | Test | Pass criteria |
|---|---|---|
| 1 | `mklink /J` in non-elevated cmd | Junction created without elevation prompt |
| 2 | `junction` crate v2 from a Tauri app | Junction created from compiled binary |
| 3 | `New-Item -ItemType HardLink -Target D:\x C:\y` cross-drive | Errors with same-volume requirement (expected fail) |
| 4 | REDmod deploy through a `mods/test/` junction | `r6/cache/modded/` produced, mod loads in-game |
| 5 | CET load via hardlinked `bin/x64/winmm.dll` | Game launches, `cyber_engine_tweaks.log` is written |
| 6 | **Steam Verify on a junctioned `mods/foo/` tree** | Either junction survives, OR junction wiped (document outcome). If wiped → drift-detection + redeploy on next launch must recover transparently. |
| 7 | **Steam Verify on hardlinked mod files at mod-only paths** | Hardlinks untouched (expected). |
| 8 | Cyberpunk Steam patch via SteamCMD downgrade→upgrade | Hardlinks survive at mod-only paths; vanilla-path hardlinks (winmm/version/engine) may break — drift report flags them |
| 9 | CDPR pre-verify cleanup ("delete /mods /r6 /red4ext /archive/pc/mod") | RipperMod detects missing dst on next launch, "Redeploy" restores state from staging |
| 10 | Deploy with `Cyberpunk2077.exe` running | Refused with clear error |
| 11 | OneDrive following hardlinks | OneDrive does NOT upload staging copy (expected — reparse-point behavior) |
| 12 | Defender real-time scan during 500-file deploy | No quarantine, completes in <30s |
| 13 | Toggle (disable/enable) on a hardlinked file via the `.disabled` rename | Optional — confirms NTFS rename-of-hardlink semantics in practice. (We are not using this anymore in the new design, but worth confirming the underlying invariant.) |
| 14 | **End-to-end migration of a real 100+ mod install** | All files migrated, no data loss, deploy verifies, game launches identically |
| 15 | Disable→Enable cycle with new DB-flag model | Drift report goes 0 → N → 0; no file content changes on disk |

**Items 4, 6, 7, 8, 9, 14 are the killers.** Failure on any of them forces a design revision before implementation continues.

The spike produces a written report at `docs/superpowers/specs/2026-05-14-vfs-hardlinks-spike-results.md` with PASS/FAIL per item, screenshots of any anomalies, and a "blockers found" list.

## 12. Open Questions / Must-Spike

1. **REDmod load order file format.** RipperMod writes `archive/pc/mod/modlist.txt` today. REDmod has its own `r6/cache/modded/MO_REDmod_load_order.txt` convention (per MO2). RipperMod does **not** generate this today (`grep` for `MO_REDmod_load_order` returns zero). If the per-`mods/<modname>/` junctioning will let REDmod see multiple deployed REDmods, we may need to add this writer. Resolution: spike step #4 — run a multi-REDmod deploy and check what REDmod's deployer expects.
2. **Steam Verify behavior on junctioned `mods/`.** Officially undocumented. Spike step #6. If Steam destroys the junctions, we keep the design (drift + redeploy) but document the UX impact: "Don't run Verify on Cyberpunk if RipperMod has REDmods deployed; use 'Verify Mods' in RipperMod instead."
3. **AV ASR rules on heavy hardlink workloads.** Vortex has anecdotal reports (issues #7652, #6334) of Windows Defender locking freshly-linked files. The canary probe doesn't catch ASR-specific behavior. Spike step #12.
4. **Game patch reset of `r6/cache/`.** redscript wiki says cache is "automatically reset after game updates" but doesn't specify whether Steam wipes it or whether redscript rebuilds on next launch. Spike step #8.
5. **`engine/` mod prevalence.** We add `engine` to `CYBERPUNK_DEFAULT_PATHS` to cover the long tail. Question: are there other long-tail mod roots we don't know about? Mitigation: when `detect_layout()` returns `UNKNOWN`, surface to user via existing layout review UI; collect telemetry over time.

## 13. Out of Scope

- USVFS / minifilter driver / WinFsp / ProjFS — rejected.
- Linux / SteamOS — separate spec.
- Cross-volume staging — defer until user requests.
- Multi-game support (the design generalizes to any game with mod-only roots, but only Cyberpunk is wired up).
- Mod merging / overwrite resolution UI changes — existing conflict engine handles this at the DB level; only the deploy step is new.

## 14. Risks & Open Decisions

| Risk | Mitigation |
|---|---|
| Spike fails on Steam Verify (#6, #7) | Worst case: REDmod junctions get wiped by Verify. Design survives — drift detection + auto-redeploy on launch. Document the friction. |
| Spike fails on REDmod multi-mod load order (#4) | Add `MO_REDmod_load_order.txt` writer; small extension to `modlist_service.py`. |
| Migration corrupts a real user's install | One-time migration is journaled and rollback-able. Ship as opt-in for the first release; auto-trigger after telemetry confirms reliability. |
| Frontend conflicts during cherry-pick to `nexus-compliant` | Limited to `Sidebar.tsx` + `Titlebar.tsx` per the divergence table; mechanical to resolve. |
| User runs Steam Verify mid-deploy | Pre-flight check refuses concurrent deploys; if Verify is invoked between deploys, drift detection picks up next time. |
| `engine/` introduction breaks layout detection on existing archives | `detect_layout()` returns `UNKNOWN` today for engine-only archives, falling through to a generic install. Adding `engine` as a root strictly enlarges the detection surface — no regression. |
| Disk space on staging | Pre-flight check estimates and refuses if low. |

## 15. Validation Trail

This design is the output of three sequential research passes documented in agent transcripts (sub-agents `a0ee22348d27fb2ab`, `a1829140b19ea35c2`, `aed6d0e05d43d054f`). Each pass refined or refuted the previous:

- **Pass 1** proposed directory-level junctions. **Refuted** in pass 2.
- **Pass 2** refuted directory junctions on three grounds: mixed dirs (vanilla/mod coexistence), `bin/x64/` root proxy DLLs, same-volume constraint surprises. Proposed per-file hardlinks + per-REDmod-folder junctions (this design).
- **Pass 3** filled engineering gaps: Rust `junction` crate v2 vs `mklink /J`, NTFS rename/delete semantics for hardlinks, Vortex's actual fallback logic, FOMOD path safety, missing `engine/` root, Tauri-vs-Python language choice, same-volume by construction.

Key external sources:

- [junction crate v2 on lib.rs](https://lib.rs/crates/junction)
- [Microsoft Learn: Hard Links and Junctions](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions)
- [Microsoft Learn: CreateHardLinkW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw)
- [Microsoft Learn: Deprecation of Transactional NTFS](https://learn.microsoft.com/en-us/windows/win32/fileio/deprecation-of-txf)
- [Rust std::fs::hard_link](https://doc.rust-lang.org/std/fs/fn.hard_link.html)
- [Python os.link](https://docs.python.org/3.12/library/os.html#os.link), [os.path.samefile](https://docs.python.org/3.12/library/os.path.html#os.path.samefile)
- [Vortex hardlink_activator source](https://github.com/Nexus-Mods/Vortex/blob/master/src/renderer/src/extensions/hardlink_activator/index.ts)
- [Cyberpunk Vortex extension `cyberpunk2077_ext_redux`](https://github.com/E1337Kat/cyberpunk2077_ext_redux)
- [Cyberpunk Modding Wiki: troubleshooting](https://wiki.redmodding.org/cyberpunk-2077-modding/for-mod-users/user-guide-troubleshooting)
- [MO2 Cyberpunk plugin](https://github.com/ModOrganizer2/modorganizer-basic_games/blob/master/games/game_cyberpunk2077.py)
- [sysinfo crate](https://crates.io/crates/sysinfo)

## 16. Estimated Effort

| Phase | Days |
|---|---|
| Pre-implementation spike (real-hardware) | 2-3 |
| Backend: `deploy_service` + manifest changes + journal | 5 |
| Backend: install/uninstall/toggle rewrite | 3 |
| Backend: migration tool | 5 |
| Rust: `vfs.rs` Tauri commands | 3 |
| Frontend: deploy UI + drift badge + Settings | 4 |
| Frontend: migration wizard + untracked-files dialog | 3 |
| Testing (unit + e2e) + docs | 3 |
| Cherry-pick + Nexus-edition resolution + second PR review | 1 |
| **Total** | **29-30** |

## 17. Acceptance Criteria

The feature ships only when:

1. Spike checklist (§11) is fully passed (or has documented workarounds for any ❌).
2. Both Full and Nexus PRs are reviewed by claude[bot] and all review threads resolved.
3. Backend test suite passes on both branches.
4. A manual smoke test on a real Windows machine with ≥50 mods passes on both editions.
5. `docs/dual-release-strategy.md` is updated with VFS-specific notes.
6. `CLAUDE.md` is updated with VFS architecture notes.
7. `README.md` and Nexus mod-page bbcode are updated to advertise the feature.
