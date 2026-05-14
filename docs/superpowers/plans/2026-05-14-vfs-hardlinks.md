# VFS Hardlinks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move mod content out of the Cyberpunk 2077 game directory into a staging dir, surfaced through NTFS hardlinks (and per-REDmod junctions). Existing copy-installed users migrate without data loss.

**Architecture:** Per-file hardlinks for everything except `mods/<modname>/` (junction-per-mod). Backend Python orchestrates and executes via `os.link()` for hardlinks and a `subprocess.run([...])` (list form, no shell) to `mklink /J` for junctions. Frontend gets a Deploy/Drift UI. Implementation lands on `feat/vfs-hardlinks` off `main` and is cherry-picked to a parallel branch off `nexus-compliant`. No merge until the spike (Phase 0) passes.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, React 19, Tauri v2 (no Rust changes in this plan), `psutil` (new), pytest.

**Implementation note (deviates from spec section 3):** The spec proposed Rust Tauri commands for VFS syscalls. The plan uses Python-only because (a) hardlinks via `os.link()` are stdlib and call the same `CreateHardLinkW` as Rust, (b) we only need junctions for REDmod folders (50 per deploy max), and (c) keeping deploy logic in one process simplifies testing and journaling. Rust can be introduced later if perf/robustness empirically demand it.

---

## File Structure

### Created
- `backend/src/rippermod_manager/services/vfs/__init__.py` — public surface
- `backend/src/rippermod_manager/services/vfs/primitives.py` — hardlink, unlink, junction, remove_junction, verify_link, same_volume, probe_hardlink_support, is_game_running
- `backend/src/rippermod_manager/services/vfs/deploy_service.py` — deploy, undeploy, detect_drift, pre_flight_check, replay_pending_journal
- `backend/src/rippermod_manager/services/vfs/migration.py` — one-time copy-to-hardlink migration
- `backend/src/rippermod_manager/schemas/deploy.py` — Pydantic request/response schemas
- `frontend/src/components/mods/DeployStatusBadge.tsx`
- `frontend/src/components/mods/MigrationWizard.tsx`
- `frontend/src/components/mods/UntrackedFilesDialog.tsx`
- `frontend/src/hooks/use-deploy.ts`
- `backend/tests/services/vfs/__init__.py`
- `backend/tests/services/vfs/test_primitives.py`
- `backend/tests/services/vfs/test_deploy_service.py`
- `backend/tests/services/vfs/test_migration.py`
- `backend/tests/services/vfs/conftest.py` — shared fixtures
- `docs/superpowers/specs/2026-05-14-vfs-hardlinks-spike-results.md` — manually filled during Phase 0

### Modified
- `backend/src/rippermod_manager/constants.py` — add `engine` path
- `backend/src/rippermod_manager/models/install.py` — add columns + DeployJournalEntry
- `backend/src/rippermod_manager/database.py` — schema migrations
- `backend/src/rippermod_manager/services/install_service.py` — split into stage + deploy
- `backend/src/rippermod_manager/services/fomod_install_service.py` — extract to staging
- `backend/src/rippermod_manager/routers/install.py` — new deploy/migrate endpoints
- `backend/pyproject.toml` — add `psutil`
- `frontend/src/components/layout/Titlebar.tsx` — render DeployStatusBadge
- `frontend/src/components/mods/InstalledModsTable.tsx` — drift indicator
- `frontend/src/pages/SettingsPage.tsx` — Deployment section
- `frontend/src/pages/OnboardingPage.tsx` — VFS explainer step
- Frontend launch button handler — call backend deploy endpoint before invoking `launch_game`

---

## Phase 0: Pre-Implementation Spike (manual, no code)

**This phase gates all subsequent phases. Do not start Phase 1 until every spike item is documented as PASS or has a written workaround for FAIL.**

### Task 0.1: Set up a clean spike environment

- [ ] **Step 1: Identify spike machine**

Windows 10 or 11, real Steam install of Cyberpunk 2077 at a known path (record the drive letter), Defender enabled, at least 50 mods of varied types (REDmod, archives, CET, RED4ext, redscript) installed via the current RipperMod build.

- [ ] **Step 2: Snapshot the current install**

```
robocopy "C:\path\to\Cyberpunk 2077" "C:\spike-snapshot" /MIR
```

So you can roll back between spike steps.

- [ ] **Step 3: Create the spike-results doc**

Create `docs/superpowers/specs/2026-05-14-vfs-hardlinks-spike-results.md` with this header:

```markdown
# VFS Spike Results — 2026-05-14

## Environment
- OS: <Windows 10/11 version>
- Game drive: <e.g. D:>
- AppData drive: <e.g. C:>
- Cyberpunk version: <e.g. 2.21>
- Mod count: <e.g. 58>
- AV: Defender real-time on
```

Each spike item gets its own subsection with PASS/FAIL/N-A, evidence (commands, screenshots, log excerpts), and "blockers found".

### Task 0.2: Run the 15 spike items

- [ ] **Item 1: `mklink /J` in non-elevated cmd**

```
mklink /J C:\tmp\spike-junction C:\tmp\spike-target
```
Pass if junction created without UAC prompt and `dir C:\tmp\spike-junction` lists the target's contents.

- [ ] **Item 2: `mklink /J` from a Python subprocess of the running RipperMod**

In Python: invoke `subprocess.run(["cmd", "/c", "mklink", "/J", "C:\\tmp\\a", "C:\\tmp\\b"], capture_output=True, text=True, shell=False)`.
Pass if returncode == 0 and stderr is empty.

- [ ] **Item 3: Cross-drive hardlink fails as expected**

```powershell
New-Item -ItemType HardLink -Path D:\x -Target C:\Windows\System32\notepad.exe
```
Pass if errors with "device does not support" or "cannot create hard link... not on the same volume."

- [ ] **Item 4: REDmod deploy through a `mods/<test>/` junction (KILLER)**

  - Create staging dir outside game: `<game>\downloaded_mods\spike_redmod\`. Drop a valid `info.json` + one `.reds` script in it.
  - Remove any existing `<game>\mods\spike_redmod\`.
  - `mklink /J "<game>\mods\spike_redmod" "<game>\downloaded_mods\spike_redmod"`
  - Run `<game>\tools\redmod\bin\redMod.exe deploy -force` (or however REDmod is invoked in your setup).
  - Pass if `<game>\r6\cache\modded\final.redscripts` is produced AND the mod's script behavior is visible in-game (launch, check for the effect).

- [ ] **Item 5: CET via hardlink of `winmm.dll`**

  - Backup `<game>\bin\x64\winmm.dll` if it exists.
  - Place CET's `winmm.dll` in `<game>\downloaded_mods\spike_cet\bin\x64\winmm.dll`.
  - Hardlink it: in Python `os.link(staging_path, game_path)`.
  - Launch the game. Pass if CET loads (check `<game>\bin\x64\plugins\cyber_engine_tweaks\cyber_engine_tweaks.log` for "Loaded" line).

- [ ] **Item 6: Steam Verify Integrity on junctioned `mods/` (KILLER)**

  - With `mods\spike_redmod` as a junction, run Steam > Cyberpunk > Properties > Installed Files > Verify integrity.
  - Pass = junction survives. Acceptable = junction is wiped to an empty real dir; document the recovery flow (drift detect + redeploy).
  - Fail = Steam errors out or deletes/relocates files outside the junction.

- [ ] **Item 7: Steam Verify on hardlinked mod files (KILLER)**

  - Hardlink one `.archive` file from staging to `<game>\archive\pc\mod\spike.archive`.
  - Run Verify. Pass if hardlink is untouched (`os.path.samefile()` still returns true).

- [ ] **Item 8: Steam patch via SteamCMD downgrade then upgrade**

  - `steamcmd +login <user> +app_update 1091500 -beta <previous_version> validate +quit`
  - Then `+app_update 1091500 validate +quit` to re-upgrade.
  - Pass if hardlinks at mod-only paths survive; drift report flags any breakages at vanilla paths (`engine/`, `bin/x64/winmm.dll` if applicable).

- [ ] **Item 9: CDPR pre-verify cleanup recovery (KILLER)**

  - Manually delete `<game>\mods\spike_redmod`, `<game>\archive\pc\mod\spike.archive`, `<game>\bin\x64\winmm.dll` (the hardlinks).
  - Restart RipperMod. Pass if RipperMod detects missing deployments on next deploy/launch and a one-click "Redeploy" restores everything from staging.

- [ ] **Item 10: Deploy with game running**

  - Launch Cyberpunk2077.exe.
  - From a test script, call the pre-flight check. Pass if it refuses deploy with `GameRunning` error.

- [ ] **Item 11: OneDrive does not follow hardlinks**

  - Put staging dir inside a OneDrive-synced folder.
  - Deploy. Pass if OneDrive does NOT upload the game-dir hardlink copies (junction/hardlink reparse semantics).

- [ ] **Item 12: Defender during 500-file deploy**

  - Generate a synthetic 500-file deploy plan, run it. Pass if no quarantine events in Event Viewer > Applications and Services > Microsoft > Windows > Windows Defender, and total time < 30s.

- [ ] **Item 13: Toggle disable/enable on a hardlink (optional sanity)**

  - Hardlink a file. `os.rename()` it to `.disabled`. Read content via the staging path; confirm unchanged. (Confirms the NTFS rename-of-hardlink invariant. We are NOT using this in the new design, but worth confirming the underlying invariant.)

- [ ] **Item 14: End-to-end migration of a real 100+ mod install (KILLER)**

  - On a copy of a real 100+ mod RipperMod install, manually walk through the migration plan from Phase 5 (without code yet): for each `InstalledMod`, move files from game dir to `downloaded_mods/<staging>/`, then hardlink back.
  - Pass if all 100+ mods migrated, no data loss, deploy verifies, game launches identically.

- [ ] **Item 15: Disable/enable cycle with DB-flag model**

  - Disable a mod via DB flag, call undeploy, confirm hardlinks gone, staging intact, drift report 0 missing for non-disabled mods.
  - Re-enable, call deploy, confirm hardlinks restored.

### Task 0.3: Document blockers and gate

- [ ] **Step 1: Fill spike-results doc with each item's outcome**

PASS/FAIL/WORKAROUND for each item, with evidence.

- [ ] **Step 2: Decision gate**

  - If items 4, 6, 7, 8, 9, 14 are all PASS, proceed to Phase 1.
  - If any KILLER item fails with no workaround, STOP. Revise the spec (probably the design needs to change), do not start implementation.
  - If non-KILLER items fail, document workaround, proceed.

- [ ] **Step 3: Commit the spike-results doc**

```bash
git add docs/superpowers/specs/2026-05-14-vfs-hardlinks-spike-results.md
git commit -m "docs(vfs): pre-implementation spike results"
```

---

## Phase 1: Data Model + Migrations

### Task 1.1: Add `engine` to recognized mod roots

**Files:**
- Modify: `backend/src/rippermod_manager/constants.py:4-12`
- Test: `backend/tests/services/test_archive_layout.py` (existing file)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/test_archive_layout.py`:

```python
def test_engine_is_recognized_root():
    from rippermod_manager.services.archive_layout import known_roots_for_game

    roots = known_roots_for_game("cyberpunk2077")
    assert "engine" in roots, f"engine missing from {roots}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/services/test_archive_layout.py::test_engine_is_recognized_root -v
```
Expected: FAIL with `assert "engine" in {...}`.

- [ ] **Step 3: Modify `constants.py`**

```python
CYBERPUNK_DEFAULT_PATHS = [
    ("archive/pc/mod", "Main mod archives", True),
    ("bin/x64/plugins/cyber_engine_tweaks/mods", "CET script mods", True),
    ("red4ext/plugins", "RED4ext plugins", True),
    ("r6/scripts", "Redscript mods", True),
    ("r6/tweaks", "TweakXL tweaks", True),
    ("bin/x64/plugins", "ASI/plugin loaders", True),
    ("mods", "REDmod mods", True),
    ("engine", "Engine config tweaks", True),
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/services/test_archive_layout.py::test_engine_is_recognized_root -v
```
Expected: PASS.

- [ ] **Step 5: Run full archive_layout suite to confirm no regression**

```bash
cd backend && uv run pytest tests/services/test_archive_layout.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/rippermod_manager/constants.py backend/tests/services/test_archive_layout.py
git commit -m "feat(vfs): recognize engine/ as a Cyberpunk mod root"
```

### Task 1.2: Extend `InstalledMod` model

**Files:**
- Modify: `backend/src/rippermod_manager/models/install.py:7-27`
- Test: `backend/tests/test_models_install.py` (new)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models_install.py`:

```python
from rippermod_manager.models.install import InstalledMod


def test_installed_mod_has_vfs_fields():
    mod = InstalledMod(game_id=1, name="TestMod")
    assert mod.staging_dir == ""
    assert mod.deployed is False
    assert mod.deploy_drift is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_models_install.py -v
```
Expected: FAIL with `AttributeError` on `staging_dir`.

- [ ] **Step 3: Add fields to `InstalledMod`**

Edit `backend/src/rippermod_manager/models/install.py`, inside the `InstalledMod` class definition, add after the `mod_group_id` field:

```python
    staging_dir: str = Field(default="")
    deployed: bool = Field(default=False)
    deploy_drift: bool = Field(default=False)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_models_install.py::test_installed_mod_has_vfs_fields -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/models/install.py backend/tests/test_models_install.py
git commit -m "feat(vfs): add staging_dir, deployed, deploy_drift to InstalledMod"
```

### Task 1.3: Extend `InstalledModFile` model

**Files:**
- Modify: `backend/src/rippermod_manager/models/install.py:30-37`
- Test: `backend/tests/test_models_install.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_models_install.py`:

```python
from rippermod_manager.models.install import InstalledModFile


def test_installed_mod_file_has_link_metadata():
    f = InstalledModFile(installed_mod_id=1, relative_path="r6/scripts/foo.reds")
    assert f.source_path == ""
    assert f.link_kind == "hardlink"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_models_install.py::test_installed_mod_file_has_link_metadata -v
```
Expected: FAIL.

- [ ] **Step 3: Add fields to `InstalledModFile`**

Edit `backend/src/rippermod_manager/models/install.py`, inside the `InstalledModFile` class:

```python
    source_path: str = Field(default="")
    link_kind: str = Field(default="hardlink")  # hardlink | junction | copy
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_models_install.py::test_installed_mod_file_has_link_metadata -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/models/install.py backend/tests/test_models_install.py
git commit -m "feat(vfs): add source_path and link_kind to InstalledModFile"
```

### Task 1.4: Create `DeployJournalEntry` table

**Files:**
- Modify: `backend/src/rippermod_manager/models/install.py` (add class)
- Test: `backend/tests/test_models_install.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_models_install.py`:

```python
from datetime import datetime, UTC

from rippermod_manager.models.install import DeployJournalEntry


def test_deploy_journal_entry_defaults():
    entry = DeployJournalEntry(
        game_id=1,
        operation="link",
        src="staging/mod/r6/scripts/foo.reds",
        dst="r6/scripts/foo.reds",
    )
    assert entry.status == "pending"
    assert entry.error == ""
    assert isinstance(entry.created_at, datetime)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_models_install.py::test_deploy_journal_entry_defaults -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add `DeployJournalEntry` to `install.py`**

Append to `backend/src/rippermod_manager/models/install.py`:

```python
class DeployJournalEntry(SQLModel, table=True):
    __tablename__ = "deploy_journal"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id", index=True)
    operation: str  # link | unlink | junction | rm_junction
    src: str
    dst: str
    status: str = Field(default="pending")  # pending | done | failed
    error: str = Field(default="")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_models_install.py::test_deploy_journal_entry_defaults -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/models/install.py backend/tests/test_models_install.py
git commit -m "feat(vfs): add DeployJournalEntry write-ahead log table"
```

### Task 1.5: Schema migration in `database.py`

**Files:**
- Modify: `backend/src/rippermod_manager/database.py` (`_migrate_missing_columns`, `_migrate_unique_indexes`)
- Test: `backend/tests/test_database_migrations.py` (likely existing — confirm and extend)

- [ ] **Step 1: Locate the migration function**

```bash
grep -n "_migrate_missing_columns\|deploy_journal" backend/src/rippermod_manager/database.py
```
Note the line range.

- [ ] **Step 2: Write the failing test**

Append (or create) `backend/tests/test_database_migrations.py`:

```python
import sqlite3

from rippermod_manager.database import _migrate_missing_columns


def test_migration_adds_vfs_columns(tmp_path):
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE installed_mods (id INTEGER PRIMARY KEY, game_id INTEGER, name TEXT)")
    conn.execute("CREATE TABLE installed_mod_files (id INTEGER PRIMARY KEY, installed_mod_id INTEGER, relative_path TEXT)")
    conn.commit()

    _migrate_missing_columns(conn)

    cols_mod = {r[1] for r in conn.execute("PRAGMA table_info(installed_mods)").fetchall()}
    cols_file = {r[1] for r in conn.execute("PRAGMA table_info(installed_mod_files)").fetchall()}

    assert {"staging_dir", "deployed", "deploy_drift"} <= cols_mod
    assert {"source_path", "link_kind"} <= cols_file
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_database_migrations.py::test_migration_adds_vfs_columns -v
```
Expected: FAIL.

- [ ] **Step 4: Update `_migrate_missing_columns`**

In `backend/src/rippermod_manager/database.py`, inside `_migrate_missing_columns`, add (after existing migrations for `installed_mods` / `installed_mod_files`):

```python
    _add_column_if_missing(conn, "installed_mods", "staging_dir", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "installed_mods", "deployed", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "installed_mods", "deploy_drift", "INTEGER NOT NULL DEFAULT 0")
    _add_column_if_missing(conn, "installed_mod_files", "source_path", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(conn, "installed_mod_files", "link_kind", "TEXT NOT NULL DEFAULT 'hardlink'")
```

If `_add_column_if_missing` doesn't exist, define it at module top:

```python
def _add_column_if_missing(conn, table, column, ddl):
    cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_database_migrations.py -v
```
Expected: PASS.

- [ ] **Step 6: Verify the `deploy_journal` table is created automatically by SQLModel's `create_all` on first run**

Append to `tests/test_database_migrations.py`:

```python
def test_deploy_journal_table_created():
    from sqlmodel import create_engine
    from rippermod_manager.models.install import DeployJournalEntry  # noqa: F401
    from rippermod_manager.database import init_db

    engine = create_engine("sqlite:///:memory:")
    init_db(engine)

    with engine.connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "deploy_journal" in tables
```

- [ ] **Step 7: Run it**

```bash
cd backend && uv run pytest tests/test_database_migrations.py::test_deploy_journal_table_created -v
```
Expected: PASS.

If `init_db` has a different name, grep for the SQLModel `metadata.create_all` call and adapt.

- [ ] **Step 8: Commit**

```bash
git add backend/src/rippermod_manager/database.py backend/tests/test_database_migrations.py
git commit -m "feat(vfs): migrate vfs columns and create deploy_journal table"
```

---

## Phase 2: VFS Primitives

### Task 2.1: Add `psutil` to backend deps

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Add to `[project.dependencies]`:

```toml
"psutil>=6.0",
```

- [ ] **Step 2: Sync and verify**

```bash
cd backend && uv sync
uv run python -c "import psutil; print(psutil.__version__)"
```
Expected: version printed.

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore(vfs): add psutil for process-running check"
```

### Task 2.2: Scaffold `vfs` package

**Files:**
- Create: `backend/src/rippermod_manager/services/vfs/__init__.py`
- Create: `backend/src/rippermod_manager/services/vfs/primitives.py`
- Create: `backend/tests/services/vfs/__init__.py`
- Create: `backend/tests/services/vfs/conftest.py`

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
mkdir -p backend/src/rippermod_manager/services/vfs backend/tests/services/vfs
touch backend/src/rippermod_manager/services/vfs/__init__.py backend/tests/services/vfs/__init__.py
```

- [ ] **Step 2: Create `primitives.py` with the public surface (stubs)**

```python
"""Low-level VFS primitives: hardlinks, junctions, probes."""

from __future__ import annotations

from pathlib import Path


class VfsError(Exception):
    """Base class for VFS-specific failures."""


class CrossVolumeError(VfsError):
    pass


class AlreadyExistsError(VfsError):
    pass


class NotFoundError(VfsError):
    pass


class PermissionDeniedError(VfsError):
    pass


class FilesystemUnsupportedError(VfsError):
    pass


class GameRunningError(VfsError):
    pass


def hardlink(src: Path, dst: Path) -> None:
    """Create a hardlink at dst pointing to src. Raises VfsError on failure."""
    raise NotImplementedError


def unlink(dst: Path) -> None:
    """Remove a hardlink or regular file at dst. No-op if absent."""
    raise NotImplementedError


def junction(target: Path, link: Path) -> None:
    """Create an NTFS directory junction at `link` pointing to `target`."""
    raise NotImplementedError


def remove_junction(link: Path) -> None:
    """Remove a junction reparse point. Idempotent."""
    raise NotImplementedError


def verify_link(src: Path, dst: Path) -> bool:
    """Return True iff dst is a hardlink (same inode) to src."""
    raise NotImplementedError


def same_volume(a: Path, b: Path) -> bool:
    """Return True iff a and b live on the same NTFS volume."""
    raise NotImplementedError


def probe_hardlink_support(staging_dir: Path, target_dir: Path) -> bool:
    """Canary: write tmp file in staging_dir, hardlink into target_dir, cleanup."""
    raise NotImplementedError


def is_game_running(exe_name: str = "Cyberpunk2077.exe") -> bool:
    """Return True iff a process with the given exe name is running."""
    raise NotImplementedError
```

- [ ] **Step 3: Create `conftest.py` with shared fixtures**

```python
import sys

import pytest


@pytest.fixture
def tmp_volume(tmp_path):
    """Two sibling dirs guaranteed same volume."""
    staging = tmp_path / "staging"
    target = tmp_path / "target"
    staging.mkdir()
    target.mkdir()
    return staging, target


skip_if_not_windows = pytest.mark.skipif(
    sys.platform != "win32",
    reason="VFS primitives are Windows-only",
)
```

- [ ] **Step 4: Confirm the package imports**

```bash
cd backend && uv run python -c "from rippermod_manager.services.vfs import primitives; print(primitives.VfsError)"
```
Expected: `<class 'rippermod_manager.services.vfs.primitives.VfsError'>`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/services/vfs backend/tests/services/vfs
git commit -m "feat(vfs): scaffold vfs primitives module"
```

### Task 2.3: Implement `hardlink` and `unlink`

**Files:**
- Modify: `backend/src/rippermod_manager/services/vfs/primitives.py`
- Test: `backend/tests/services/vfs/test_primitives.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/services/vfs/test_primitives.py`:

```python
import os
from pathlib import Path

import pytest

from rippermod_manager.services.vfs.primitives import (
    AlreadyExistsError,
    NotFoundError,
    hardlink,
    unlink,
)


def test_hardlink_creates_link(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hello")
    dst = target / "a.txt"

    hardlink(src, dst)

    assert dst.exists()
    assert os.path.samefile(src, dst)


def test_hardlink_raises_if_dst_exists(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hello")
    dst = target / "a.txt"
    dst.write_text("existing")

    with pytest.raises(AlreadyExistsError):
        hardlink(src, dst)


def test_hardlink_raises_if_src_missing(tmp_volume):
    staging, target = tmp_volume
    src = staging / "missing.txt"
    dst = target / "a.txt"

    with pytest.raises(NotFoundError):
        hardlink(src, dst)


def test_unlink_removes_link(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hello")
    dst = target / "a.txt"
    hardlink(src, dst)

    unlink(dst)

    assert not dst.exists()
    assert src.exists()  # staging untouched
    assert src.read_text() == "hello"


def test_unlink_is_idempotent_when_absent(tmp_volume):
    _, target = tmp_volume
    dst = target / "ghost.txt"

    unlink(dst)  # should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v
```
Expected: 5 FAIL with `NotImplementedError`.

- [ ] **Step 3: Implement `hardlink` and `unlink`**

Edit `backend/src/rippermod_manager/services/vfs/primitives.py`, replace the stubs:

```python
import os


def hardlink(src: Path, dst: Path) -> None:
    if not src.exists():
        raise NotFoundError(f"source missing: {src}")
    if dst.exists():
        raise AlreadyExistsError(f"destination exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except FileExistsError as exc:
        raise AlreadyExistsError(str(exc)) from exc
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    except OSError as exc:
        if getattr(exc, "winerror", None) == 17:  # ERROR_NOT_SAME_DEVICE
            raise CrossVolumeError(f"{src} and {dst} are not on the same volume") from exc
        if getattr(exc, "winerror", None) == 1 or "not supported" in str(exc).lower():
            raise FilesystemUnsupportedError(str(exc)) from exc
        if getattr(exc, "winerror", None) == 5:
            raise PermissionDeniedError(str(exc)) from exc
        raise VfsError(str(exc)) from exc


def unlink(dst: Path) -> None:
    try:
        dst.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise VfsError(str(exc)) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v
```
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/services/vfs/primitives.py backend/tests/services/vfs/test_primitives.py
git commit -m "feat(vfs): implement hardlink and unlink primitives"
```

### Task 2.4: Implement `verify_link`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/services/vfs/test_primitives.py`:

```python
from rippermod_manager.services.vfs.primitives import verify_link


def test_verify_link_true_for_hardlink(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hi")
    dst = target / "a.txt"
    hardlink(src, dst)

    assert verify_link(src, dst) is True


def test_verify_link_false_for_separate_files(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hi")
    dst = target / "a.txt"
    dst.write_text("hi")  # same content, different inode

    assert verify_link(src, dst) is False


def test_verify_link_false_when_dst_missing(tmp_volume):
    staging, target = tmp_volume
    src = staging / "a.txt"
    src.write_text("hi")
    dst = target / "missing.txt"

    assert verify_link(src, dst) is False
```

- [ ] **Step 2: Run to verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py::test_verify_link_true_for_hardlink -v
```
Expected: FAIL.

- [ ] **Step 3: Implement `verify_link`**

```python
def verify_link(src: Path, dst: Path) -> bool:
    try:
        return os.path.samefile(src, dst)
    except (FileNotFoundError, OSError):
        return False
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k verify_link
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/services/vfs/primitives.py backend/tests/services/vfs/test_primitives.py
git commit -m "feat(vfs): implement verify_link via samefile"
```

### Task 2.5: Implement `same_volume`

- [ ] **Step 1: Write the failing test**

Append to test file:

```python
from rippermod_manager.services.vfs.primitives import same_volume


def test_same_volume_true_for_siblings(tmp_volume):
    staging, target = tmp_volume
    assert same_volume(staging, target) is True


def test_same_volume_returns_value_for_missing_paths(tmp_path):
    # Function should not raise even if paths don't exist yet — use closest existing ancestor
    a = tmp_path / "nope_a"
    b = tmp_path / "nope_b"
    assert same_volume(a, b) is True
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k same_volume
```

- [ ] **Step 3: Implement**

```python
def _existing_ancestor(p: Path) -> Path:
    p = p.resolve(strict=False)
    while not p.exists() and p != p.parent:
        p = p.parent
    return p


def same_volume(a: Path, b: Path) -> bool:
    try:
        sa = os.stat(_existing_ancestor(a))
        sb = os.stat(_existing_ancestor(b))
        return sa.st_dev == sb.st_dev
    except OSError as exc:
        raise VfsError(str(exc)) from exc
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k same_volume
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/services/vfs/primitives.py backend/tests/services/vfs/test_primitives.py
git commit -m "feat(vfs): implement same_volume check via st_dev"
```

### Task 2.6: Implement `probe_hardlink_support`

- [ ] **Step 1: Test**

```python
from rippermod_manager.services.vfs.primitives import probe_hardlink_support


def test_probe_returns_true_when_supported(tmp_volume):
    staging, target = tmp_volume
    assert probe_hardlink_support(staging, target) is True


def test_probe_leaves_no_files(tmp_volume):
    staging, target = tmp_volume
    probe_hardlink_support(staging, target)
    assert list(staging.iterdir()) == []
    assert list(target.iterdir()) == []
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k probe
```

- [ ] **Step 3: Implement**

```python
def probe_hardlink_support(staging_dir: Path, target_dir: Path) -> bool:
    staging_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    canary = staging_dir / ".rmm_canary.tmp"
    link = target_dir / ".rmm_canary.link"
    try:
        canary.write_bytes(b"x")
        try:
            os.link(canary, link)
        except OSError:
            return False
        return True
    finally:
        link.unlink(missing_ok=True)
        canary.unlink(missing_ok=True)
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k probe
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): implement probe_hardlink_support canary"
```

### Task 2.7: Implement `is_game_running`

- [ ] **Step 1: Test**

Append:

```python
from unittest.mock import patch

from rippermod_manager.services.vfs.primitives import is_game_running


def test_is_game_running_false_when_no_match():
    with patch("rippermod_manager.services.vfs.primitives.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = []
        assert is_game_running("Cyberpunk2077.exe") is False


def test_is_game_running_true_when_match():
    class FakeProc:
        info = {"name": "Cyberpunk2077.exe"}

    with patch("rippermod_manager.services.vfs.primitives.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = [FakeProc()]
        assert is_game_running("Cyberpunk2077.exe") is True


def test_is_game_running_case_insensitive():
    class FakeProc:
        info = {"name": "CYBERPUNK2077.EXE"}

    with patch("rippermod_manager.services.vfs.primitives.psutil") as mock_psutil:
        mock_psutil.process_iter.return_value = [FakeProc()]
        assert is_game_running("Cyberpunk2077.exe") is True
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k is_game_running
```

- [ ] **Step 3: Implement**

In `primitives.py`, add at top:

```python
import psutil
```

Implement:

```python
def is_game_running(exe_name: str = "Cyberpunk2077.exe") -> bool:
    needle = exe_name.lower()
    for proc in psutil.process_iter(attrs=["name"]):
        name = (proc.info.get("name") or "").lower()
        if name == needle:
            return True
    return False
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k is_game_running
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): implement is_game_running via psutil"
```

### Task 2.8: Implement `junction` and `remove_junction`

- [ ] **Step 1: Test (Windows-only)**

Append:

```python
from rippermod_manager.services.vfs.primitives import junction, remove_junction


@skip_if_not_windows
def test_junction_creates_traversable_link(tmp_volume):
    staging, target = tmp_volume
    inner = staging / "inner"
    inner.mkdir()
    (inner / "file.txt").write_text("ok")

    link = target / "link"
    junction(inner, link)

    assert (link / "file.txt").read_text() == "ok"


@skip_if_not_windows
def test_remove_junction_removes_link_but_keeps_target(tmp_volume):
    staging, target = tmp_volume
    inner = staging / "inner"
    inner.mkdir()
    (inner / "file.txt").write_text("ok")
    link = target / "link"
    junction(inner, link)

    remove_junction(link)

    assert not link.exists()
    assert (inner / "file.txt").read_text() == "ok"


@skip_if_not_windows
def test_remove_junction_idempotent_when_absent(tmp_volume):
    _, target = tmp_volume
    link = target / "ghost"
    remove_junction(link)  # must not raise
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k junction
```

- [ ] **Step 3: Implement**

In `primitives.py`, import at top:

```python
import subprocess
```

Add the functions:

```python
def junction(target: Path, link: Path) -> None:
    if not target.is_dir():
        raise NotFoundError(f"junction target must be an existing directory: {target}")
    if link.exists():
        raise AlreadyExistsError(f"junction link path exists: {link}")
    link.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        shell=False,
        timeout=10,
    )
    if proc.returncode != 0:
        raise VfsError(f"mklink /J failed: {proc.stderr.strip() or proc.stdout.strip()}")


def remove_junction(link: Path) -> None:
    if not link.exists():
        return
    try:
        os.rmdir(link)
    except OSError as exc:
        raise VfsError(f"could not remove junction {link}: {exc}") from exc
```

Note: `subprocess.run([...], shell=False)` (list-form, no shell) is safe — cmd.exe is invoked as a process, not via shell parsing. Path args are passed as separate argv entries; no quoting/escaping required.

- [ ] **Step 4: Verify PASS (Windows only — Linux/CI will skip)**

```bash
cd backend && uv run pytest tests/services/vfs/test_primitives.py -v -k junction
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): implement junction and remove_junction via mklink /J"
```

---

## Phase 3: Deploy Service

### Task 3.1: Schemas for deploy

**Files:**
- Create: `backend/src/rippermod_manager/schemas/deploy.py`

- [ ] **Step 1: Test**

Create `backend/tests/test_schemas_deploy.py`:

```python
from rippermod_manager.schemas.deploy import (
    DeployOp,
    DeployPlan,
    DeployReport,
    DriftReport,
    PreflightReport,
)


def test_deploy_op_roundtrip():
    op = DeployOp(operation="link", src="staging/foo", dst="r6/scripts/foo")
    assert op.operation == "link"


def test_preflight_report_defaults():
    r = PreflightReport()
    assert r.ok is True
    assert r.reasons == []


def test_drift_report_counters():
    r = DriftReport(total=10, linked=8, missing=2, foreign=0)
    assert r.is_clean is False
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/test_schemas_deploy.py -v
```

- [ ] **Step 3: Implement**

Create `backend/src/rippermod_manager/schemas/deploy.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


OpKind = Literal["link", "unlink", "junction", "rm_junction"]


class DeployOp(BaseModel):
    operation: OpKind
    src: str  # staging-relative for link/junction; ignored for unlink/rm_junction
    dst: str  # game-relative
    installed_mod_id: int | None = None


class DeployPlan(BaseModel):
    game_id: int
    ops: list[DeployOp] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.ops


class DeployOpResult(BaseModel):
    op: DeployOp
    status: Literal["done", "failed"]
    error: str = ""


class DeployReport(BaseModel):
    total: int
    done: int
    failed: int
    results: list[DeployOpResult] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return self.failed == 0


class DriftReport(BaseModel):
    total: int
    linked: int
    missing: int
    foreign: int  # file exists at dst but is not our link
    by_mod: dict[int, dict[str, int]] = Field(default_factory=dict)

    @property
    def is_clean(self) -> bool:
        return self.missing == 0 and self.foreign == 0


class PreflightReport(BaseModel):
    ok: bool = True
    reasons: list[str] = Field(default_factory=list)
    game_running: bool = False
    hardlink_supported: bool = True
    same_volume: bool = True
    free_disk_bytes: int = 0
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/test_schemas_deploy.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/schemas/deploy.py backend/tests/test_schemas_deploy.py
git commit -m "feat(vfs): add deploy schemas"
```

### Task 3.2: `pre_flight_check`

**Files:**
- Create: `backend/src/rippermod_manager/services/vfs/deploy_service.py`
- Create: `backend/tests/services/vfs/test_deploy_service.py`

- [ ] **Step 1: Test**

```python
from pathlib import Path
from unittest.mock import patch

from rippermod_manager.models.game import Game
from rippermod_manager.services.vfs.deploy_service import pre_flight_check


def make_game(tmp_path: Path) -> Game:
    install = tmp_path / "game"
    (install / "downloaded_mods").mkdir(parents=True)
    return Game(id=1, name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install))


def test_pre_flight_clean(tmp_path):
    g = make_game(tmp_path)
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        r = pre_flight_check(g)
    assert r.ok is True
    assert r.game_running is False


def test_pre_flight_refuses_if_game_running(tmp_path):
    g = make_game(tmp_path)
    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=True):
        r = pre_flight_check(g)
    assert r.ok is False
    assert r.game_running is True
    assert any("running" in s.lower() for s in r.reasons)
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_deploy_service.py -v -k pre_flight
```

- [ ] **Step 3: Implement skeleton + `pre_flight_check`**

Create `backend/src/rippermod_manager/services/vfs/deploy_service.py`:

```python
"""Orchestrates VFS deployment: planning, journaling, execution."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from rippermod_manager.models.game import Game
from rippermod_manager.schemas.deploy import PreflightReport
from rippermod_manager.services.vfs.primitives import (
    is_game_running,
    probe_hardlink_support,
    same_volume,
)

logger = logging.getLogger(__name__)

GAME_EXE = "Cyberpunk2077.exe"


def pre_flight_check(game: Game) -> PreflightReport:
    report = PreflightReport()
    install = Path(game.install_path)
    staging = install / "downloaded_mods"
    staging.mkdir(parents=True, exist_ok=True)

    if is_game_running(GAME_EXE):
        report.ok = False
        report.game_running = True
        report.reasons.append("Cyberpunk 2077 is running — close it before deploying.")

    try:
        sv = same_volume(staging, install)
    except Exception as exc:  # noqa: BLE001 — file I/O envelope
        sv = False
        report.reasons.append(f"could not check volume: {exc}")
    report.same_volume = sv
    if not sv:
        report.ok = False
        report.reasons.append("Staging dir and game dir are on different volumes; hardlinks require same volume.")

    try:
        report.hardlink_supported = probe_hardlink_support(staging, install)
    except Exception as exc:  # noqa: BLE001
        report.hardlink_supported = False
        report.reasons.append(f"hardlink probe failed: {exc}")
    if not report.hardlink_supported:
        report.ok = False
        report.reasons.append("Filesystem does not support hardlinks (NTFS required).")

    try:
        report.free_disk_bytes = shutil.disk_usage(install).free
    except OSError:
        report.free_disk_bytes = 0

    return report
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/services/vfs/test_deploy_service.py -v -k pre_flight
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/rippermod_manager/services/vfs/deploy_service.py backend/tests/services/vfs/test_deploy_service.py
git commit -m "feat(vfs): implement pre_flight_check"
```

### Task 3.3: `plan_deploy`

Computes a `DeployPlan` from enabled InstalledMods.

- [ ] **Step 1: Test**

Add fixtures to `backend/tests/services/vfs/conftest.py`:

```python
from sqlmodel import Session, SQLModel, create_engine

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile, DeployJournalEntry  # noqa: F401


@pytest.fixture
def in_memory_engine():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def in_memory_session(in_memory_engine):
    with Session(in_memory_engine) as s:
        yield s


@pytest.fixture
def sample_game(in_memory_session, tmp_path):
    install = tmp_path / "game"
    (install / "downloaded_mods").mkdir(parents=True)
    g = Game(name="Cyberpunk 2077", domain_name="cyberpunk2077", install_path=str(install))
    in_memory_session.add(g)
    in_memory_session.commit()
    in_memory_session.refresh(g)
    return g
```

Append to `test_deploy_service.py`:

```python
from sqlmodel import Session

from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.deploy_service import plan_deploy


def test_plan_includes_hardlink_for_each_file(in_memory_session, sample_game):
    session: Session = in_memory_session
    game = sample_game
    mod = InstalledMod(
        game_id=game.id,
        name="TestMod",
        staging_dir="TestMod",
        disabled=False,
        deployed=False,
    )
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="r6/scripts/foo.reds",
        source_path="r6/scripts/foo.reds",
        link_kind="hardlink",
    ))
    session.commit()

    plan = plan_deploy(game, session)

    assert len(plan.ops) == 1
    assert plan.ops[0].operation == "link"
    assert plan.ops[0].src.endswith("downloaded_mods/TestMod/r6/scripts/foo.reds")
    assert plan.ops[0].dst.endswith("r6/scripts/foo.reds")


def test_plan_skips_disabled_mods(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    mod = InstalledMod(game_id=game.id, name="Off", staging_dir="Off", disabled=True)
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="a", source_path="a"))
    session.commit()

    plan = plan_deploy(game, session)
    assert plan.is_empty


def test_plan_uses_junction_for_redmod_subtrees(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    mod = InstalledMod(game_id=game.id, name="MyREDmod", staging_dir="MyREDmod")
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="mods/MyREDmod/info.json",
        source_path="mods/MyREDmod/info.json",
        link_kind="junction",
    ))
    session.commit()

    plan = plan_deploy(game, session)
    junction_ops = [op for op in plan.ops if op.operation == "junction"]
    assert len(junction_ops) == 1
    assert junction_ops[0].dst.endswith("mods/MyREDmod")
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_deploy_service.py -v -k plan_
```

- [ ] **Step 3: Implement `plan_deploy`**

Append to `deploy_service.py`:

```python
from sqlmodel import Session, select

from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.schemas.deploy import DeployOp, DeployPlan


def plan_deploy(game: Game, session: Session) -> DeployPlan:
    install = Path(game.install_path)
    staging_root = install / "downloaded_mods"

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
        )
    ).all()

    plan = DeployPlan(game_id=game.id)
    junction_dirs_seen: set[str] = set()

    for mod in mods:
        _ = mod.files  # touch relationship
        for f in mod.files:
            src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
            dst = install / f.relative_path.replace("\\", "/")
            if f.link_kind == "junction":
                parts = f.relative_path.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    redmod_dst = install / "mods" / parts[1]
                    redmod_src = staging_root / mod.staging_dir / "mods" / parts[1]
                    key = str(redmod_dst)
                    if key in junction_dirs_seen:
                        continue
                    junction_dirs_seen.add(key)
                    plan.ops.append(DeployOp(
                        operation="junction",
                        src=str(redmod_src),
                        dst=str(redmod_dst),
                        installed_mod_id=mod.id,
                    ))
                    continue
            plan.ops.append(DeployOp(
                operation="link",
                src=str(src),
                dst=str(dst),
                installed_mod_id=mod.id,
            ))

    return plan
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/services/vfs/test_deploy_service.py -v -k plan_
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): implement plan_deploy from installed-mod manifest"
```

### Task 3.4: `execute_plan` with journaling

- [ ] **Step 1: Test**

Append:

```python
from rippermod_manager.models.install import DeployJournalEntry
from rippermod_manager.services.vfs.deploy_service import execute_plan
from rippermod_manager.schemas.deploy import DeployPlan, DeployOp


def test_execute_plan_creates_hardlinks_and_journals(in_memory_session, sample_game, tmp_path):
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "TestMod" / "r6" / "scripts"
    staging.mkdir(parents=True)
    src = staging / "foo.reds"
    src.write_text("// test")

    plan = DeployPlan(game_id=game.id, ops=[
        DeployOp(operation="link",
                 src=str(src),
                 dst=str(Path(game.install_path) / "r6" / "scripts" / "foo.reds"),
                 installed_mod_id=1),
    ])

    report = execute_plan(plan, session)

    assert report.failed == 0
    assert report.done == 1
    dst = Path(game.install_path) / "r6" / "scripts" / "foo.reds"
    assert dst.exists()
    journal = session.exec(select(DeployJournalEntry).where(DeployJournalEntry.game_id == game.id)).all()
    assert all(j.status == "done" for j in journal)


def test_execute_plan_failure_marks_journal_failed(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    plan = DeployPlan(game_id=game.id, ops=[
        DeployOp(operation="link",
                 src="/does/not/exist.txt",
                 dst=str(Path(game.install_path) / "r6" / "scripts" / "ghost.reds"),
                 installed_mod_id=1),
    ])

    report = execute_plan(plan, session)

    assert report.failed == 1
    journal = session.exec(select(DeployJournalEntry).where(DeployJournalEntry.status == "failed")).all()
    assert len(journal) == 1
```

- [ ] **Step 2: Verify FAIL**

```bash
cd backend && uv run pytest tests/services/vfs/test_deploy_service.py -v -k execute_plan
```

- [ ] **Step 3: Implement**

Append to `deploy_service.py`:

```python
from rippermod_manager.models.install import DeployJournalEntry
from rippermod_manager.schemas.deploy import DeployOpResult, DeployReport
from rippermod_manager.services.vfs.primitives import (
    VfsError,
    hardlink,
    junction,
    remove_junction,
    unlink,
)


def execute_plan(plan: DeployPlan, session: Session) -> DeployReport:
    results: list[DeployOpResult] = []

    for op in plan.ops:
        entry = DeployJournalEntry(
            game_id=plan.game_id,
            operation=op.operation,
            src=op.src,
            dst=op.dst,
            status="pending",
        )
        session.add(entry)
        session.flush()

        try:
            if op.operation == "link":
                hardlink(Path(op.src), Path(op.dst))
            elif op.operation == "unlink":
                unlink(Path(op.dst))
            elif op.operation == "junction":
                junction(Path(op.src), Path(op.dst))
            elif op.operation == "rm_junction":
                remove_junction(Path(op.dst))
            else:
                raise VfsError(f"unknown op: {op.operation}")
            entry.status = "done"
            results.append(DeployOpResult(op=op, status="done"))
        except VfsError as exc:
            entry.status = "failed"
            entry.error = str(exc)
            results.append(DeployOpResult(op=op, status="failed", error=str(exc)))

        session.add(entry)

    session.commit()
    done = sum(1 for r in results if r.status == "done")
    failed = sum(1 for r in results if r.status == "failed")
    return DeployReport(total=len(results), done=done, failed=failed, results=results)
```

- [ ] **Step 4: Verify PASS**

```bash
cd backend && uv run pytest tests/services/vfs/test_deploy_service.py -v -k execute_plan
```

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): execute deploy plans with write-ahead journaling"
```

### Task 3.5: `deploy(game, session)` orchestrator

- [ ] **Step 1: Test**

```python
from rippermod_manager.services.vfs.deploy_service import deploy


def test_deploy_full_round_trip(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game

    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    from rippermod_manager.models.install import InstalledMod, InstalledModFile
    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo", disabled=False, deployed=False)
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="r6/scripts/a.reds",
        source_path="r6/scripts/a.reds",
        link_kind="hardlink",
    ))
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        report = deploy(game, session)

    assert report.failed == 0
    session.refresh(mod)
    assert mod.deployed is True
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
def deploy(game: Game, session: Session) -> DeployReport:
    pre = pre_flight_check(game)
    if not pre.ok:
        return DeployReport(total=0, done=0, failed=0, results=[])
    plan = plan_deploy(game, session)
    report = execute_plan(plan, session)
    if report.is_clean:
        mods = session.exec(
            select(InstalledMod).where(
                InstalledMod.game_id == game.id,
                InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
            )
        ).all()
        for m in mods:
            m.deployed = True
            m.deploy_drift = False
            session.add(m)
        session.commit()
    return report
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): deploy orchestrator marks mods deployed on success"
```

### Task 3.6: `undeploy(game, session)`

- [ ] **Step 1: Test**

```python
from rippermod_manager.services.vfs.deploy_service import undeploy


def test_undeploy_removes_links_keeps_staging(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging_root = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging_root.mkdir(parents=True)
    (staging_root / "a.reds").write_text("// a")
    dst_dir = Path(game.install_path) / "r6" / "scripts"
    dst_dir.mkdir(parents=True)
    os.link(staging_root / "a.reds", dst_dir / "a.reds")

    from rippermod_manager.models.install import InstalledMod, InstalledModFile
    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo", deployed=True)
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="r6/scripts/a.reds",
        source_path="r6/scripts/a.reds",
    ))
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        undeploy(game, session)

    assert not (dst_dir / "a.reds").exists()
    assert (staging_root / "a.reds").exists()
    session.refresh(mod)
    assert mod.deployed is False
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
def undeploy(game: Game, session: Session) -> DeployReport:
    pre = pre_flight_check(game)
    if pre.game_running:
        return DeployReport(total=0, done=0, failed=0, results=[])

    install = Path(game.install_path)
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.deployed.is_(True),  # type: ignore[union-attr]
        )
    ).all()

    ops: list[DeployOp] = []
    junction_dirs_seen: set[str] = set()
    for mod in mods:
        _ = mod.files
        for f in mod.files:
            dst = install / f.relative_path.replace("\\", "/")
            if f.link_kind == "junction":
                parts = f.relative_path.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    redmod_dst = install / "mods" / parts[1]
                    key = str(redmod_dst)
                    if key in junction_dirs_seen:
                        continue
                    junction_dirs_seen.add(key)
                    ops.append(DeployOp(operation="rm_junction", src="", dst=str(redmod_dst), installed_mod_id=mod.id))
                    continue
            ops.append(DeployOp(operation="unlink", src="", dst=str(dst), installed_mod_id=mod.id))

    plan = DeployPlan(game_id=game.id, ops=ops)
    report = execute_plan(plan, session)

    if report.is_clean:
        for m in mods:
            m.deployed = False
            session.add(m)
        session.commit()
    return report
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): undeploy clears links and unmarks deployed flag"
```

### Task 3.7: `detect_drift`

- [ ] **Step 1: Test**

```python
from rippermod_manager.services.vfs.deploy_service import detect_drift


def test_drift_clean_after_deploy(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    from rippermod_manager.models.install import InstalledMod, InstalledModFile
    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo")
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="r6/scripts/a.reds",
        source_path="r6/scripts/a.reds",
    ))
    session.commit()

    with patch("rippermod_manager.services.vfs.deploy_service.is_game_running", return_value=False):
        deploy(game, session)

    drift = detect_drift(game, session)
    assert drift.is_clean
    assert drift.linked == 1
    assert drift.missing == 0


def test_drift_detects_missing_link(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    staging = Path(game.install_path) / "downloaded_mods" / "Demo" / "r6" / "scripts"
    staging.mkdir(parents=True)
    (staging / "a.reds").write_text("// a")

    from rippermod_manager.models.install import InstalledMod, InstalledModFile
    mod = InstalledMod(game_id=game.id, name="Demo", staging_dir="Demo", deployed=True)
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="r6/scripts/a.reds",
        source_path="r6/scripts/a.reds",
    ))
    session.commit()

    drift = detect_drift(game, session)
    assert drift.missing == 1
    assert drift.linked == 0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
from rippermod_manager.schemas.deploy import DriftReport
from rippermod_manager.services.vfs.primitives import verify_link


def detect_drift(game: Game, session: Session) -> DriftReport:
    install = Path(game.install_path)
    staging_root = install / "downloaded_mods"

    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.disabled.is_(False),  # type: ignore[union-attr]
        )
    ).all()

    total = linked = missing = foreign = 0
    by_mod: dict[int, dict[str, int]] = {}

    for mod in mods:
        _ = mod.files
        m_linked = m_missing = m_foreign = 0
        for f in mod.files:
            total += 1
            src = staging_root / mod.staging_dir / f.source_path.replace("\\", "/")
            dst = install / f.relative_path.replace("\\", "/")
            if not dst.exists():
                missing += 1
                m_missing += 1
                continue
            if f.link_kind == "hardlink":
                if verify_link(src, dst):
                    linked += 1
                    m_linked += 1
                else:
                    foreign += 1
                    m_foreign += 1
            elif f.link_kind == "junction":
                if dst.is_dir():
                    linked += 1
                    m_linked += 1
                else:
                    missing += 1
                    m_missing += 1
        if mod.id is not None:
            by_mod[mod.id] = {"linked": m_linked, "missing": m_missing, "foreign": m_foreign}

    return DriftReport(total=total, linked=linked, missing=missing, foreign=foreign, by_mod=by_mod)
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): detect_drift reports missing/foreign links per mod"
```

### Task 3.8: `replay_pending_journal` (startup hook)

- [ ] **Step 1: Test**

```python
from rippermod_manager.services.vfs.deploy_service import replay_pending_journal


def test_replay_clears_pending_entries(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    session.add(DeployJournalEntry(
        game_id=game.id,
        operation="link",
        src="/nope",
        dst=str(Path(game.install_path) / "r6" / "scripts" / "ghost.reds"),
        status="pending",
    ))
    session.commit()

    replay_pending_journal(game, session)

    pending = session.exec(
        select(DeployJournalEntry).where(DeployJournalEntry.status == "pending")
    ).all()
    assert len(pending) == 0
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
def replay_pending_journal(game: Game, session: Session) -> None:
    pending = session.exec(
        select(DeployJournalEntry).where(
            DeployJournalEntry.game_id == game.id,
            DeployJournalEntry.status == "pending",
        )
    ).all()
    for entry in pending:
        try:
            if entry.operation == "link":
                unlink(Path(entry.dst))
            elif entry.operation == "junction":
                remove_junction(Path(entry.dst))
        except VfsError as exc:
            logger.warning("journal replay rollback failed for %s: %s", entry.dst, exc)
        entry.status = "failed"
        entry.error = entry.error or "rolled back by journal replay"
        session.add(entry)
    session.commit()
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Wire into FastAPI startup**

In `backend/src/rippermod_manager/main.py`, inside the lifespan startup phase, after DB init:

```python
    from rippermod_manager.services.vfs.deploy_service import replay_pending_journal
    from rippermod_manager.models.game import Game
    with Session(engine) as session:
        for g in session.exec(select(Game)).all():
            replay_pending_journal(g, session)
```

(adapt the import context to the surrounding code).

- [ ] **Step 6: Commit**

```bash
git commit -am "feat(vfs): replay pending journal entries on app startup"
```

---

## Phase 4: install/uninstall/toggle Rewrite

### Task 4.1: Extract-to-staging in `install_mod`

**Files:**
- Modify: `backend/src/rippermod_manager/services/install_service.py:63-253` (`install_mod`)

- [ ] **Step 1: Test** — write new test before refactor

Add fixture (or extend) in `backend/tests/conftest.py`:

```python
@pytest.fixture
def sample_archive(tmp_path):
    archive = tmp_path / "SampleMod-v1.zip"
    import zipfile
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("r6/scripts/foo.reds", "// sample")
    return archive
```

Append to `backend/tests/services/test_install_service.py`:

```python
def test_install_mod_writes_to_staging_not_game_dir(tmp_game, sample_archive):
    """After install, files live in <game>/downloaded_mods/<staging>/..., hardlinked into game dir."""
    game, session = tmp_game
    result = install_mod(game, sample_archive, session)

    staging = Path(game.install_path) / "downloaded_mods" / result.installed_mod_name_safe
    assert any(staging.rglob("*.reds")), "no files in staging"

    installed = session.exec(
        select(InstalledMod).where(InstalledMod.name == "SampleMod")
    ).one()
    for f in installed.files:
        src = staging / f.source_path
        dst = Path(game.install_path) / f.relative_path
        assert os.path.samefile(src, dst)
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Refactor `install_mod` to stage + deploy**

Concretely, the change to `install_service.py::install_mod`:

1. Replace the loop that writes `target.write_bytes(data)` (around line 166-167) with one that writes to `staging_root / safe_name / normalised`.
2. After extraction, immediately invoke `deploy_service.deploy(game, session)`.
3. Set `installed.staging_dir = safe_name`, set `InstalledModFile.source_path = normalised`, default `link_kind = "hardlink"`. For paths starting with `mods/`, set `link_kind = "junction"`.

Add helper at module top:

```python
import re

def _safe_dir_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "mod"
```

Add `installed_mod_name_safe: str` to `InstallResult` in `backend/src/rippermod_manager/schemas/install.py`.

Replace the body of the extraction loop (after the `valid_entries` pre-filter loop, where the second loop iterates and writes files):

```python
    safe_name = _safe_dir_name(parsed.name)
    staging_root = Path(game.install_path) / "downloaded_mods" / safe_name
    staging_root.mkdir(parents=True, exist_ok=True)

    extracted_paths: list[str] = []
    for entry, normalised, normalised_lower in valid_entries:
        data = file_contents.get(entry.filename)
        if data is None:
            logger.warning("Batch read missed entry: %s", entry.filename)
            skipped += 1
            continue
        staging_target = staging_root / normalised
        staging_target.parent.mkdir(parents=True, exist_ok=True)
        staging_target.write_bytes(data)
        extracted_paths.append(normalised)
        # NOTE: we no longer write to game_dir / normalised here. deploy_service handles linking.
```

After the extraction loop, before creating the `InstalledMod` record, set `staging_dir`:

```python
    installed = InstalledMod(
        game_id=game.id,
        name=parsed.name,
        staging_dir=safe_name,
        source_archive=archive_path.name,
        nexus_mod_id=parsed.nexus_mod_id,
        upload_timestamp=parsed.upload_timestamp,
        installed_version=parsed.version or "",
    )
    session.add(installed)
    session.flush()
```

When creating `InstalledModFile` rows:

```python
    for rel in extracted_paths:
        link_kind = "junction" if rel.startswith("mods/") and "/" in rel else "hardlink"
        session.add(InstalledModFile(
            installed_mod_id=installed.id,
            relative_path=rel,
            source_path=rel,
            link_kind=link_kind,
        ))
    session.commit()
```

After commit, before the existing `index_mod_archives` call:

```python
    from rippermod_manager.services.vfs import deploy_service
    deploy_service.deploy(game, session)
```

Update `InstallResult` return to include `installed_mod_name_safe=safe_name`.

- [ ] **Step 4: Run tests to verify**

```bash
cd backend && uv run pytest tests/services/test_install_service.py -v
```

Several existing tests will need updating to reflect that files live in staging. Update them to assert on staging path + hardlink semantics (`os.path.samefile`).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): install_mod extracts to staging and deploys via hardlinks"
```

### Task 4.2: Uninstall via undeploy

**Files:**
- Modify: `backend/src/rippermod_manager/services/install_service.py::uninstall_mod`

- [ ] **Step 1: Test**

```python
def test_uninstall_removes_links_and_staging(tmp_game, sample_archive):
    game, session = tmp_game
    result = install_mod(game, sample_archive, session)
    installed = session.exec(select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)).one()

    uninstall_mod(installed, game, session)

    assert not (Path(game.install_path) / "r6" / "scripts" / "foo.reds").exists()
    assert not (Path(game.install_path) / "downloaded_mods" / result.installed_mod_name_safe).exists()
    assert session.exec(select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)).first() is None
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Refactor `uninstall_mod`**

Replace the file-deletion loop (around `install_service.py:267-282`) with:

```python
def uninstall_mod(installed_mod, game, session):
    from rippermod_manager.services.vfs.primitives import remove_junction
    from rippermod_manager.services.vfs.primitives import unlink as vfs_unlink

    install = Path(game.install_path)
    _ = installed_mod.files
    for f in installed_mod.files:
        dst = install / f.relative_path.replace("\\", "/")
        if f.link_kind == "junction":
            parts = f.relative_path.replace("\\", "/").split("/")
            if len(parts) >= 2 and parts[0] == "mods":
                try:
                    remove_junction(install / "mods" / parts[1])
                except VfsError:
                    logger.warning("could not remove junction %s", dst)
                continue
        try:
            vfs_unlink(dst)
        except VfsError:
            logger.warning("could not unlink %s", dst)

    staging_dir = install / "downloaded_mods" / installed_mod.staging_dir
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    from sqlalchemy import delete as sa_delete
    from rippermod_manager.models.load_order import LoadOrderPreference
    from rippermod_manager.models.profile import ProfileEntry
    from rippermod_manager.services.archive_index_service import remove_index_for_mod
    from rippermod_manager.services.modlist_service import write_modlist

    file_count = len(installed_mod.files)
    remove_index_for_mod(session, installed_mod.id)
    mod_id = installed_mod.id
    session.exec(sa_delete(ProfileEntry).where(ProfileEntry.installed_mod_id == mod_id))
    session.exec(sa_delete(LoadOrderPreference).where(
        (LoadOrderPreference.winner_mod_id == mod_id) | (LoadOrderPreference.loser_mod_id == mod_id)
    ))
    session.delete(installed_mod)
    session.commit()
    write_modlist(game, session)
    return UninstallResult(files_deleted=file_count, directories_removed=0)
```

Add the imports `shutil`, `VfsError` at module top if missing.

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): uninstall removes links and staging subtree"
```

### Task 4.3: Toggle becomes DB-flag + per-mod redeploy

- [ ] **Step 1: Test**

```python
def test_toggle_disable_undeploys(tmp_game, sample_archive):
    game, session = tmp_game
    result = install_mod(game, sample_archive, session)
    installed = session.exec(select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)).one()

    toggle_mod(installed, game, session)

    assert installed.disabled is True
    assert not (Path(game.install_path) / "r6" / "scripts" / "foo.reds").exists()
    assert (Path(game.install_path) / "downloaded_mods" / result.installed_mod_name_safe / "r6" / "scripts" / "foo.reds").exists()


def test_toggle_re_enable_redeploys(tmp_game, sample_archive):
    game, session = tmp_game
    result = install_mod(game, sample_archive, session)
    installed = session.exec(select(InstalledMod).where(InstalledMod.id == result.installed_mod_id)).one()
    toggle_mod(installed, game, session)  # disable
    toggle_mod(installed, game, session)  # enable

    assert installed.disabled is False
    assert (Path(game.install_path) / "r6" / "scripts" / "foo.reds").exists()
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Refactor `toggle_mod`**

```python
def toggle_mod(installed_mod, game, session, *, commit=True):
    from rippermod_manager.services.vfs import deploy_service
    from rippermod_manager.services.vfs.primitives import remove_junction
    from rippermod_manager.services.vfs.primitives import unlink as vfs_unlink

    should_disable = not installed_mod.disabled
    installed_mod.disabled = should_disable
    session.add(installed_mod)
    if commit:
        session.commit()

    if should_disable:
        install = Path(game.install_path)
        _ = installed_mod.files
        for f in installed_mod.files:
            dst = install / f.relative_path.replace("\\", "/")
            if f.link_kind == "junction":
                parts = f.relative_path.replace("\\", "/").split("/")
                if len(parts) >= 2 and parts[0] == "mods":
                    try:
                        remove_junction(install / "mods" / parts[1])
                    except VfsError:
                        pass
                    continue
            try:
                vfs_unlink(dst)
            except VfsError:
                pass
        installed_mod.deployed = False
    else:
        deploy_service.deploy(game, session)

    session.add(installed_mod)
    if commit:
        session.commit()

    from rippermod_manager.services.modlist_service import write_modlist
    write_modlist(game, session)
    action = "Disabled" if should_disable else "Enabled"
    logger.info("%s '%s'", action, installed_mod.name)
    return ToggleResult(disabled=should_disable, files_affected=len(installed_mod.files))
```

- [ ] **Step 4: Run tests**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): toggle_mod is DB-driven with per-mod deploy/undeploy"
```

### Task 4.4: FOMOD installer extracts to staging

**Files:**
- Modify: `backend/src/rippermod_manager/services/fomod_install_service.py`

- [ ] **Step 1: Read `fomod_install_service.py` to find the extraction site**

```bash
grep -n "is_relative_to\|write_bytes\|extracted_paths" backend/src/rippermod_manager/services/fomod_install_service.py
```

- [ ] **Step 2: Apply the same stage-then-deploy pattern as `install_mod`**

Replace the loop that writes into `game_dir` with one that writes into `<game>/downloaded_mods/<staging>/`. Record `source_path` on each `InstalledModFile`. Call `deploy_service.deploy(game, session)` at the end.

- [ ] **Step 3: Run FOMOD tests**

```bash
cd backend && uv run pytest tests/services/test_fomod_install_service.py -v
```

Adapt failing assertions to check staging + hardlink semantics.

- [ ] **Step 4: Commit**

```bash
git commit -am "feat(vfs): FOMOD installer extracts to staging then deploys"
```

---

## Phase 5: Migration Tool

### Task 5.1: Plan migration for an existing copy-install

**Files:**
- Create: `backend/src/rippermod_manager/services/vfs/migration.py`
- Create: `backend/tests/services/vfs/test_migration.py`

- [ ] **Step 1: Test**

```python
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import select

from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.migration import migrate_to_vfs


def test_migration_moves_files_to_staging_and_hardlinks(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    install = Path(game.install_path)
    (install / "r6" / "scripts").mkdir(parents=True)
    (install / "r6" / "scripts" / "foo.reds").write_text("// pre-vfs")
    mod = InstalledMod(game_id=game.id, name="Legacy", staging_dir="", deployed=False)
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(
        installed_mod_id=mod.id,
        relative_path="r6/scripts/foo.reds",
        source_path="",
        link_kind="hardlink",
    ))
    session.commit()

    with patch("rippermod_manager.services.vfs.migration.is_game_running", return_value=False):
        report = migrate_to_vfs(game, session)
    assert report.migrated_files == 1

    staging_file = install / "downloaded_mods" / "Legacy" / "r6" / "scripts" / "foo.reds"
    game_file = install / "r6" / "scripts" / "foo.reds"
    assert staging_file.exists()
    assert game_file.exists()
    assert os.path.samefile(staging_file, game_file)

    session.refresh(mod)
    assert mod.staging_dir == "Legacy"
    f = session.exec(select(InstalledModFile).where(InstalledModFile.installed_mod_id == mod.id)).one()
    assert f.source_path == "r6/scripts/foo.reds"
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement `migrate_to_vfs`**

Create `backend/src/rippermod_manager/services/vfs/migration.py`:

```python
"""One-time migration from copy-install (files in game dir) to staged hardlinks."""

from __future__ import annotations

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from rippermod_manager.models.game import Game
from rippermod_manager.models.install import InstalledMod, InstalledModFile
from rippermod_manager.services.vfs.primitives import hardlink, is_game_running

logger = logging.getLogger(__name__)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "mod"


@dataclass
class MigrationReport:
    migrated_mods: int = 0
    migrated_files: int = 0
    skipped_files: int = 0
    errors: list[str] = field(default_factory=list)


def migrate_to_vfs(game: Game, session: Session) -> MigrationReport:
    if is_game_running():
        return MigrationReport(errors=["Cyberpunk 2077 is running. Close it and retry."])

    install = Path(game.install_path)
    staging_root = install / "downloaded_mods"
    staging_root.mkdir(parents=True, exist_ok=True)

    report = MigrationReport()
    mods = session.exec(
        select(InstalledMod).where(
            InstalledMod.game_id == game.id,
            InstalledMod.staging_dir == "",
        )
    ).all()

    for mod in mods:
        safe = _safe(mod.name)
        staging = staging_root / safe
        _ = mod.files
        ok = True
        moved: list[tuple[Path, Path]] = []
        for f in mod.files:
            game_path = install / f.relative_path.replace("\\", "/")
            staging_path = staging / f.relative_path.replace("\\", "/")
            if not game_path.exists():
                report.skipped_files += 1
                continue
            staging_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(game_path, staging_path)
                hardlink(staging_path, game_path)
                moved.append((staging_path, game_path))
                report.migrated_files += 1
                f.source_path = f.relative_path
                session.add(f)
            except OSError as exc:
                logger.error("migration failed for %s: %s", game_path, exc)
                report.errors.append(f"{game_path}: {exc}")
                ok = False
                for sp, gp in moved:
                    try:
                        if gp.exists():
                            gp.unlink()
                        shutil.move(sp, gp)
                    except OSError:
                        logger.exception("rollback failed for %s", gp)
                break
        if ok:
            mod.staging_dir = safe
            mod.deployed = True
            session.add(mod)
            report.migrated_mods += 1
    session.commit()
    return report
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): one-time migration from copy-install to staged hardlinks"
```

### Task 5.2: Untracked-files detection

- [ ] **Step 1: Test**

```python
from rippermod_manager.services.vfs.migration import find_untracked_files


def test_finds_files_not_owned_by_any_mod(in_memory_session, sample_game):
    session = in_memory_session
    game = sample_game
    install = Path(game.install_path)
    (install / "r6" / "scripts").mkdir(parents=True)
    (install / "r6" / "scripts" / "owned.reds").write_text("// a")
    (install / "r6" / "scripts" / "rogue.reds").write_text("// b")

    mod = InstalledMod(game_id=game.id, name="Mod", staging_dir="Mod")
    session.add(mod)
    session.flush()
    session.add(InstalledModFile(installed_mod_id=mod.id, relative_path="r6/scripts/owned.reds", source_path="r6/scripts/owned.reds"))
    session.commit()

    result = find_untracked_files(game, session)
    rogues = set(result)
    assert "r6/scripts/rogue.reds" in rogues
    assert "r6/scripts/owned.reds" not in rogues
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

Append to `migration.py`:

```python
from rippermod_manager.constants import CYBERPUNK_DEFAULT_PATHS


def find_untracked_files(game: Game, session: Session) -> list[str]:
    install = Path(game.install_path)
    owned: set[str] = set()
    rows = session.exec(
        select(InstalledModFile)
        .join(InstalledMod, InstalledModFile.installed_mod_id == InstalledMod.id)
        .where(InstalledMod.game_id == game.id)
    ).all()
    for f in rows:
        owned.add(f.relative_path.replace("\\", "/").lower())

    untracked: list[str] = []
    for root_rel, _label, _enabled in CYBERPUNK_DEFAULT_PATHS:
        root = install / root_rel
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(install).as_posix().lower()
                if rel not in owned:
                    untracked.append(rel)
    return sorted(untracked)
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): find untracked files in known mod roots"
```

---

## Phase 6: API Routers

### Task 6.1: Deploy endpoints

**Files:**
- Modify: `backend/src/rippermod_manager/routers/install.py`

- [ ] **Step 1: Test** — append to `backend/tests/routers/test_install.py`:

```python
def test_deploy_endpoint(client, tmp_game_with_mod):
    game_id = tmp_game_with_mod
    resp = client.post(f"/api/v1/games/{game_id}/deploy")
    assert resp.status_code == 200
    body = resp.json()
    assert "done" in body
    assert "failed" in body


def test_deploy_status_endpoint(client, tmp_game_with_mod):
    game_id = tmp_game_with_mod
    resp = client.get(f"/api/v1/games/{game_id}/deploy/status")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"total", "linked", "missing", "foreign"}


def test_undeploy_endpoint(client, tmp_game_with_mod):
    game_id = tmp_game_with_mod
    resp = client.post(f"/api/v1/games/{game_id}/undeploy")
    assert resp.status_code == 200
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement endpoints**

In `backend/src/rippermod_manager/routers/install.py`, add:

```python
from rippermod_manager.services.vfs import deploy_service
from rippermod_manager.schemas.deploy import DeployReport, DriftReport


@router.post("/games/{game_id}/deploy", response_model=DeployReport)
async def deploy_game(game_id: int, session: Session = Depends(get_session)):
    game = session.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return deploy_service.deploy(game, session)


@router.post("/games/{game_id}/undeploy", response_model=DeployReport)
async def undeploy_game(game_id: int, session: Session = Depends(get_session)):
    game = session.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return deploy_service.undeploy(game, session)


@router.get("/games/{game_id}/deploy/status", response_model=DriftReport)
async def deploy_status(game_id: int, session: Session = Depends(get_session)):
    game = session.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return deploy_service.detect_drift(game, session)
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): expose deploy, undeploy, deploy/status endpoints"
```

### Task 6.2: Migration endpoint

- [ ] **Step 1: Test**

```python
def test_migrate_endpoint(client, tmp_game_with_pre_vfs_install):
    game_id = tmp_game_with_pre_vfs_install
    resp = client.post(f"/api/v1/games/{game_id}/migrate-to-vfs")
    assert resp.status_code == 200
    body = resp.json()
    assert "migrated_mods" in body
```

- [ ] **Step 2: Verify FAIL**

- [ ] **Step 3: Implement**

```python
from rippermod_manager.services.vfs import migration as vfs_migration


@router.post("/games/{game_id}/migrate-to-vfs")
async def migrate(game_id: int, session: Session = Depends(get_session)):
    game = session.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    report = vfs_migration.migrate_to_vfs(game, session)
    return {
        "migrated_mods": report.migrated_mods,
        "migrated_files": report.migrated_files,
        "skipped_files": report.skipped_files,
        "errors": report.errors,
    }


@router.get("/games/{game_id}/untracked-files")
async def untracked(game_id: int, session: Session = Depends(get_session)):
    game = session.get(Game, game_id)
    if not game:
        raise HTTPException(404, "Game not found")
    return {"files": vfs_migration.find_untracked_files(game, session)}
```

- [ ] **Step 4: Verify PASS**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(vfs): expose migrate-to-vfs and untracked-files endpoints"
```

---

## Phase 7: Frontend

### Task 7.1: `useDeploy` hooks

**Files:**
- Create: `frontend/src/hooks/use-deploy.ts`

- [ ] **Step 1: Implement**

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface DriftReport {
  total: number;
  linked: number;
  missing: number;
  foreign: number;
  by_mod: Record<string, { linked: number; missing: number; foreign: number }>;
}

export interface DeployReport {
  total: number;
  done: number;
  failed: number;
  results: Array<{ op: { operation: string; src: string; dst: string }; status: string; error: string }>;
}

export function useDeployStatus(gameId: number | null) {
  return useQuery<DriftReport, Error>({
    queryKey: ["deploy-status", gameId],
    queryFn: () => api.get(`/api/v1/games/${gameId}/deploy/status`),
    enabled: gameId !== null,
    refetchInterval: 30_000,
  });
}

export function useDeploy(gameId: number | null) {
  const qc = useQueryClient();
  return useMutation<DeployReport, Error, void>({
    mutationFn: () => api.post(`/api/v1/games/${gameId}/deploy`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deploy-status", gameId] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameId] });
    },
  });
}

export function useUndeploy(gameId: number | null) {
  const qc = useQueryClient();
  return useMutation<DeployReport, Error, void>({
    mutationFn: () => api.post(`/api/v1/games/${gameId}/undeploy`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deploy-status", gameId] });
    },
  });
}

export function useMigrateToVfs(gameId: number | null) {
  const qc = useQueryClient();
  return useMutation<{ migrated_mods: number; migrated_files: number; errors: string[] }, Error, void>({
    mutationFn: () => api.post(`/api/v1/games/${gameId}/migrate-to-vfs`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deploy-status", gameId] });
      qc.invalidateQueries({ queryKey: ["installed-mods", gameId] });
    },
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/hooks/use-deploy.ts
git commit -m "feat(vfs): add deploy hooks for React Query"
```

### Task 7.2: DeployStatusBadge component

**Files:**
- Create: `frontend/src/components/mods/DeployStatusBadge.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useDeploy, useDeployStatus } from "@/hooks/use-deploy";
import { Button } from "@/components/ui/Button";
import { CheckCircle, AlertTriangle, RotateCcw } from "lucide-react";

export function DeployStatusBadge({ gameId }: { gameId: number | null }) {
  const { data: status } = useDeployStatus(gameId);
  const deploy = useDeploy(gameId);

  if (!status) return null;

  if (status.total === 0) {
    return <span className="text-xs text-text-muted">No mods deployed</span>;
  }

  if (status.missing === 0 && status.foreign === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-success">
        <CheckCircle size={14} /> Deployed ({status.linked})
      </span>
    );
  }

  return (
    <div className="inline-flex items-center gap-2 text-xs">
      <span className="inline-flex items-center gap-1 text-warning">
        <AlertTriangle size={14} /> Drift: {status.missing} missing
      </span>
      <Button
        size="sm"
        variant="secondary"
        loading={deploy.isPending}
        onClick={() => deploy.mutate()}
      >
        <RotateCcw size={12} /> Redeploy
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/mods/DeployStatusBadge.tsx
git commit -m "feat(vfs): DeployStatusBadge with drift detection and redeploy"
```

### Task 7.3: Titlebar integration

**Files:**
- Modify: `frontend/src/components/layout/Titlebar.tsx`

- [ ] **Step 1: Add badge**

```tsx
// Import at top:
import { DeployStatusBadge } from "@/components/mods/DeployStatusBadge";
import { useUIStore } from "@/stores/ui-store";
import { useGames } from "@/hooks/queries";

// Inside Titlebar, near other status elements:
function ActiveGameDeployBadge() {
  const activeGameName = useUIStore((s) => s.activeGameName);
  const { data: games = [] } = useGames();
  const game = games.find((g) => g.name === activeGameName) ?? null;
  return <DeployStatusBadge gameId={game?.id ?? null} />;
}

// Render <ActiveGameDeployBadge /> in the titlebar.
```

- [ ] **Step 2: Verify in `npm run dev`** — start the dev server, confirm the badge appears.

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(vfs): render DeployStatusBadge in titlebar for active game"
```

### Task 7.4: SettingsPage Deployment section

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add a new Card before the existing AboutCard**

```tsx
function DeploymentCard() {
  const activeGameName = useUIStore((s) => s.activeGameName);
  const { data: games = [] } = useGames();
  const game = games.find((g) => g.name === activeGameName);
  const status = useDeployStatus(game?.id ?? null);
  const deploy = useDeploy(game?.id ?? null);
  const undeploy = useUndeploy(game?.id ?? null);

  if (!game) return null;

  return (
    <Card>
      <h2 className="text-lg font-semibold text-text-primary mb-4">Deployment</h2>
      <div className="space-y-3">
        <p className="text-sm text-text-secondary">
          Mods are staged in <code>downloaded_mods/</code> and linked into the game directory at deploy time. Your game folder stays clean.
        </p>
        {status.data && (
          <div className="text-xs text-text-muted font-mono">
            {status.data.linked} linked · {status.data.missing} missing · {status.data.foreign} foreign
          </div>
        )}
        <div className="flex gap-2">
          <Button size="sm" loading={deploy.isPending} onClick={() => deploy.mutate()}>
            Deploy
          </Button>
          <Button size="sm" variant="secondary" loading={undeploy.isPending} onClick={() => undeploy.mutate()}>
            Undeploy
          </Button>
        </div>
      </div>
    </Card>
  );
}
```

Render `<DeploymentCard />` inside the existing `SettingsPage` JSX before `<AboutCard />`.

- [ ] **Step 2: Commit**

```bash
git commit -am "feat(vfs): add Deployment section to SettingsPage"
```

### Task 7.5: MigrationWizard component

**Files:**
- Create: `frontend/src/components/mods/MigrationWizard.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useState } from "react";
import { useMigrateToVfs } from "@/hooks/use-deploy";
import { Button } from "@/components/ui/Button";

export function MigrationWizard({ gameId, onDone }: { gameId: number; onDone: () => void }) {
  const migrate = useMigrateToVfs(gameId);
  const [report, setReport] = useState<{ migrated_mods: number; migrated_files: number; errors: string[] } | null>(null);

  if (report) {
    return (
      <div className="space-y-3">
        <h3 className="text-lg font-semibold">Migration complete</h3>
        <p>Migrated {report.migrated_mods} mods ({report.migrated_files} files).</p>
        {report.errors.length > 0 && (
          <details>
            <summary className="text-danger text-sm">Errors ({report.errors.length})</summary>
            <ul className="text-xs">
              {report.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </details>
        )}
        <Button onClick={onDone}>Done</Button>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold">Migrate to clean game folder?</h3>
      <p className="text-sm text-text-secondary">
        RipperMod will move your installed mod files from the game directory to <code>downloaded_mods/</code> and link them back. The game sees the same files; your game folder stays clean.
      </p>
      <p className="text-xs text-text-muted">Make sure Cyberpunk 2077 is not running.</p>
      <Button
        loading={migrate.isPending}
        onClick={() =>
          migrate.mutate(undefined, {
            onSuccess: (r) => setReport(r),
          })
        }
      >
        Migrate now
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/mods/MigrationWizard.tsx
git commit -m "feat(vfs): one-time MigrationWizard component"
```

### Task 7.6: UntrackedFilesDialog (basic)

**Files:**
- Create: `frontend/src/components/mods/UntrackedFilesDialog.tsx`

- [ ] **Step 1: Implement**

```tsx
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function UntrackedFilesDialog({ gameId, onClose }: { gameId: number; onClose: () => void }) {
  const { data, isLoading } = useQuery<{ files: string[] }, Error>({
    queryKey: ["untracked-files", gameId],
    queryFn: () => api.get(`/api/v1/games/${gameId}/untracked-files`),
  });

  if (isLoading) return <p>Scanning…</p>;
  const files = data?.files ?? [];
  return (
    <div className="space-y-3 max-w-2xl">
      <h3 className="text-lg font-semibold">Untracked files</h3>
      {files.length === 0 ? (
        <p className="text-sm text-success">No untracked files in known mod roots.</p>
      ) : (
        <>
          <p className="text-sm text-text-secondary">
            These files exist in your game's mod directories but are not owned by any RipperMod-installed mod. They were either added manually or remain from a previous tool.
          </p>
          <ul className="text-xs font-mono max-h-64 overflow-auto">
            {files.map((p) => <li key={p}>{p}</li>)}
          </ul>
        </>
      )}
      <button onClick={onClose} className="text-accent text-sm underline">Close</button>
    </div>
  );
}
```

A richer adopt/ignore/delete UI is deferred to a follow-up plan. This MVP version just lists them, which already enables informed user decisions.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/mods/UntrackedFilesDialog.tsx
git commit -m "feat(vfs): UntrackedFilesDialog MVP (list-only)"
```

### Task 7.7: Auto-deploy on game launch

**Files:**
- Modify: whichever frontend file holds the "Launch Game" button

- [ ] **Step 1: Locate the launch handler**

```bash
grep -rn "launch_game" frontend/src
```

- [ ] **Step 2: Before invoking Tauri `launch_game`, call deploy**

```tsx
const deploy = useDeploy(gameId);
const handleLaunch = async () => {
  try {
    await deploy.mutateAsync();
  } catch {
    return;
  }
  await invoke("launch_game");
};
```

- [ ] **Step 3: Commit**

```bash
git commit -am "feat(vfs): auto-deploy before launching game"
```

---

## Phase 8: Documentation Updates

### Task 8.1: Update CLAUDE.md and architecture.md

**Files:**
- Modify: `CLAUDE.md` — add VFS architecture bullet
- Modify: `docs/architecture.md` — add `services/vfs/` entry and mention `deploy_journal` table

- [ ] **Step 1: Patch CLAUDE.md**

Under `## Architecture`, append:

```markdown
- **VFS deployment**: mods are extracted to `<install>/downloaded_mods/<staging>/` and surfaced in the game dir via NTFS hardlinks (and junctions for REDmod folders). `services/vfs/` orchestrates plan → journal → execute. Idempotent; survives crashes via journal replay.
```

- [ ] **Step 2: Patch architecture.md**

Add to the project structure tree under `services/`:

```
│   │   │   ├── vfs/
│   │   │   │   ├── primitives.py     # hardlink, junction, probe
│   │   │   │   ├── deploy_service.py # plan, execute, drift, journal
│   │   │   │   └── migration.py      # one-time copy→hardlink
```

And add to the Database section:

```markdown
- `deploy_journal` table: write-ahead log of pending VFS ops (replayed on startup)
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/architecture.md
git commit -m "docs(vfs): update CLAUDE.md and architecture.md with VFS components"
```

### Task 8.2: Update README + Nexus bbcode

**Files:**
- Modify: `README.md`
- Modify: `docs/nexus-description.bbcode`

- [ ] **Step 1: README — add the clean-folder claim**

```markdown
### Clean game folder

RipperMod keeps mod content in a managed staging dir (`<install>/downloaded_mods/`) and links into the game directory only when deployed. Steam "Verify integrity" only sees vanilla files. Profile switching is instant.
```

- [ ] **Step 2: nexus-description.bbcode — append same bullet under features**

- [ ] **Step 3: Commit**

```bash
git commit -am "docs(vfs): advertise clean-game-folder in README and Nexus description"
```

---

## Phase 9: Cherry-pick to `nexus-compliant`

### Task 9.1: Run all tests and lint on `feat/vfs-hardlinks`

- [ ] **Step 1: Backend**

```bash
cd backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pytest tests/ -v --tb=short
```

All pass.

- [ ] **Step 2: Frontend**

```bash
cd frontend && npm run lint && npm run build
```

All pass.

- [ ] **Step 3: Manual smoke test**

Open Tauri app, install a mod, verify it's in `downloaded_mods/`, hardlinks in game dir, launch game, mod loads.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin feat/vfs-hardlinks
```

### Task 9.2: Open PR against `main`

- [ ] **Step 1: Use `gh pr create`**

```bash
gh pr create --base main --title "feat(vfs)!: stage mods outside game dir, link in with hardlinks + REDmod junctions" --body "$(cat <<'EOF'
## Summary
- Mods now extract to `<install>/downloaded_mods/<staging>/` and surface in the game dir via NTFS hardlinks
- REDmod folders use NTFS junctions (one per mod)
- Adds `services/vfs/` package with primitives, deploy service, and migration tool
- One-time migration moves existing copy-installed mods into the new layout

## Breaking change
- DB schema migrates (new columns, new `deploy_journal` table). Existing rows backfill on startup.
- Existing users prompted to run the migration before deploy works.

## Test plan
- [x] Backend test suite passes (pytest)
- [x] Frontend lint + build pass
- [ ] Manual smoke test on real Windows install
- [ ] Spike checklist completed: see `docs/superpowers/specs/2026-05-14-vfs-hardlinks-spike-results.md`
- [ ] claude[bot] review approved
EOF
)"
```

- [ ] **Step 2: Wait for claude[bot] PR review and resolve every comment**

Per `MEMORY.md` rules: NEVER merge until ALL review threads are resolved.

### Task 9.3: Cherry-pick to `nexus-compliant`

- [ ] **Step 1: After `main` PR is approved (but BEFORE merging), create the Nexus branch**

```bash
git fetch origin
git checkout -b feat/vfs-hardlinks-nexus origin/nexus-compliant
```

- [ ] **Step 2: Cherry-pick all commits from `feat/vfs-hardlinks`**

```bash
git log --reverse feat/vfs-hardlinks --not nexus-compliant --format="%H" > /tmp/vfs-commits.txt
while read sha; do git cherry-pick "$sha" || break; done < /tmp/vfs-commits.txt
```

- [ ] **Step 3: Resolve conflicts**

Expected conflict files (per `docs/dual-release-strategy.md`):
- `frontend/src/components/layout/Sidebar.tsx`
- `frontend/src/components/layout/Titlebar.tsx` (if Nexus edition diverges)
- `frontend/src/pages/SettingsPage.tsx` (if Nexus has different sections)

Resolve by keeping the Nexus-edition's existing divergences and applying only the VFS-related additions. After each conflict resolution:

```bash
git add <file> && git cherry-pick --continue
```

- [ ] **Step 4: Run tests on the Nexus branch**

```bash
cd backend && uv run pytest tests/ -v --tb=short
cd ../frontend && npm run lint && npm run build
```

- [ ] **Step 5: Push and open second PR**

```bash
git push -u origin feat/vfs-hardlinks-nexus
gh pr create --base nexus-compliant --title "feat(vfs)!: stage mods outside game dir (Nexus edition)" --body "Cherry-pick of #<full-PR-number> for the Nexus edition. See that PR for details."
```

- [ ] **Step 6: Wait for second claude[bot] review and resolve every comment**

### Task 9.4: Both PRs merge together

- [ ] **Step 1: Once both PRs approved and all threads resolved, squash-merge `main` PR first**

This triggers semantic-release on `main` → `v3.0.0`.

- [ ] **Step 2: Then squash-merge `nexus-compliant` PR**

This triggers semantic-release on `nexus-compliant` → `v3.0.0-nexus.1` and upload to Nexus mod page.

- [ ] **Step 3: Verify**

- Both GitHub Releases created.
- Nexus mod page updated with new version.
- Gist `stable.json` updated for Full edition.
- Test the auto-update flow on a Full-edition install.

---

## Acceptance criteria

The feature ships only when:

1. Spike checklist (Phase 0) fully passed or documented workarounds for any FAIL
2. Both Full and Nexus PRs reviewed by claude[bot] and all threads resolved
3. Backend test suite passes on both branches
4. Manual smoke test on a real Windows machine with 50+ mods passes on both editions
5. `docs/dual-release-strategy.md`, `CLAUDE.md`, `README.md`, Nexus bbcode all updated
