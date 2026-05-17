# RipperMod Manager

Desktop mod manager for PC games (focused on Cyberpunk 2077). Scans, groups, correlates, and manages mods with Nexus Mods integration. This branch is the Nexus edition: no in-app LLM features and no app auto-updater, per Nexus file submission guidelines.

## Stack

- **Backend:** FastAPI, Python 3.12, uv, src layout — `backend/src/rippermod_manager/`
- **Frontend:** React 19, TypeScript 5.9 (strict), Vite, Tailwind CSS v4 — `frontend/src/`
- **Desktop:** Tauri v2, Rust — `frontend/src-tauri/`
- **State:** Zustand (client), React Query (server), SQLite (persistence)
- **Key deps:** httpx, tenacity (retry), keyring (OS secret store), scikit-learn, jellyfish

## Commands

```bash
# Backend
cd backend && uv run uvicorn rippermod_manager.main:app --reload --port 8425
cd backend && uv run ruff check src/ tests/
cd backend && uv run ruff format src/ tests/
cd backend && uv run pytest tests/ -v --tb=short

# Frontend
cd frontend && npm run dev       # Vite dev (port 1420)
cd frontend && npm run build     # tsc + vite build
cd frontend && npm run lint      # ESLint
cd frontend && npx tauri dev     # Tauri desktop (backend must be running)
```

## Code style

### Python
- Ruff: line-length 100, rules `E F I UP B SIM RUF`
- B008 ignored in `routers/*.py` (FastAPI `Depends()` pattern)
- Type hints required on public functions
- Async-first: use `async def` for route handlers
- Imports sorted by isort via Ruff

### TypeScript
- Strict mode enabled
- Path alias: `@/*` → `./src/*`
- Unused vars prefixed with `_` are allowed

### Conventions
- Commit messages: English, conventional commits
- Allowed types: `feat`, `fix`, `perf`, `refactor`, `chore`, `docs`, `style`, `test`, `build`, `ci`, `revert`
- Breaking changes: `feat!:` or `fix!:` → MAJOR bump. `feat:` → MINOR. `fix:` → PATCH. All others → no release
- Squash merge — PR title becomes the commit on main (semantic-release reads it)
- All code, comments, and commits in English

## Architecture

See @docs/architecture.md for a full inventory of routers, services, models.

- Backend API: `http://localhost:8425/api/v1/`
- **Nexus API:** dual-client — REST v1 (`nexus/client.py`) for CRUD, GraphQL v2 (`nexus/graphql_client.py`) for batch queries. Both use tenacity retry (3 attempts, exponential 2–30s) on 429/5xx
- **Scan pipeline:** file discovery → TF-IDF + DBSCAN grouping → multi-tier matching → correlation
- **Matching tiers:** (1) filename ID extraction, (1.5) file content reverse lookup, (2) MD5 hash batch lookup, (3) endorsed/tracked + collection matching + requirement propagation, (4) Jaccard + Jaro-Winkler fuzzy
- **Secrets:** keyring service attempts OS keychain, falls back to SQLite. Keys: `nexus_api_key`
- **Health:** `/health` (shallow), `/health/deep` (DB + data_dir writability)
- **Logging:** stderr + `RotatingFileHandler` at `data_dir/logs/rippermod.log` (5 MB × 3)
- **VFS deployment:** mods are extracted to `<install>/downloaded_mods/<staging>/` and surfaced in the game dir via NTFS hardlinks (and junctions for REDmod folders). `services/vfs/` orchestrates `plan → journal → execute`. Idempotent; survives crashes via `deploy_journal` replay on app startup. After a clean execute, `deploy()` also invokes `redmod_deploy(game)` (runs `tools/redmod/bin/redMod.exe deploy -reportProgress`) if any enabled mod owns files under `mods/`, so REDmod scripts/tweaks compile without user intervention. `detect_drift()` reports `linked / missing / foreign` per mod and caches junction-root probes so REDmod files don't get falsely flagged.
- **Archive layout transform:** every consumer of `services/archive_layout.detect_layout` (install, conflict checking, conflict graph, conflicts inbox, preview endpoint) must funnel paths through `apply_layout_transform(rel_path, layout_result)`. It composes `strip_prefix` + `add_prefix` (the latter is set to `"mods"` for REDmod archives packaged as `<modname>/info.json` at the zip root) and returns `None` for entries outside the wrapper so callers skip them uniformly.
- **App update notification:** `hooks/use-app-update-check.ts` reads the existing `useModSummary(27781)` (RipperMod's own Nexus listing) and compares against `__APP_VERSION__` via `lib/version.ts` (handles `v` prefix and git-describe suffix). Surfaces a dismissible top banner (`components/AppUpdateBanner.tsx`), a Settings notice, and a once-per-session startup toast. Pure read against the Nexus API — no auto-download or auto-install (Nexus distribution policy).
- Tauri CSP restricts connections to `localhost:8425`

## Database

- SQLite with WAL mode, `PRAGMA foreign_keys=ON`, `synchronous=NORMAL`
- Single-writer — avoid long-running transactions and blocking operations
- Migrations: column additions in `database.py:_migrate_missing_columns()`, unique indexes in `_migrate_unique_indexes()`
- `deploy_journal` table: write-ahead log of pending VFS ops (replayed on startup to recover from crashes mid-deploy)
- NEVER use raw SQL for queries accessible from user input — use SQLModel/SQLAlchemy parameterized queries

## Nexus Mods API

See @docs/nexus-api-usage.md for endpoint reference.

- Rate limits: 2,500/day, 100/hour. Track via `X-RL-Hourly-Remaining` / `X-RL-Daily-Remaining`
- REST v1 for mutations (endorse, track, download links); GraphQL v2 for batch reads (file hashes, mod info, search)
- Retry on 429 and 5xx only — NEVER retry 401/403/404
- `NexusRateLimitError` and `NexusPremiumRequiredError` are custom exceptions — catch them explicitly before generic `httpx.HTTPError`

## Testing

- 900+ tests across `backend/tests/` (routers, services, matching, scanner, nexus, archive, vfs)
- Fixtures in `tests/conftest.py` — in-memory SQLite, test games, mock clients
- CI runs with `--cov=rippermod_manager --cov-report=term-missing`
- Use `respx` for HTTP mocking — never make real API calls in tests
- Prefer testing a single file: `uv run pytest tests/services/test_foo.py -v`

## Review focus

When reviewing PRs, pay extra attention to:
- **Performance:** Desktop app — avoid unnecessary re-renders, heavy DOM operations, virtualize long lists
- **SQLite concurrency:** Single-writer — watch for blocking operations in async handlers
- **Type safety:** Handle `undefined` from indexed access in TypeScript
- **Security:** CSP compliance, no arbitrary eval, no path traversal in archive extraction
- **Nexus API:** Rate limiting, proper error handling, catch specific exceptions before broad ones
- **Exception handling:** Use specific types (`httpx.HTTPError`, `OSError`) — only use `except Exception` for shutdown/cleanup
