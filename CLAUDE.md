# RipperMod Manager

Desktop AI-powered mod manager for PC games (focused on Cyberpunk 2077). Scans, groups, correlates, and manages mods with Nexus Mods integration and an LLM chat agent.

## Stack

- **Backend:** FastAPI, Python 3.12, uv, src layout — `backend/src/rippermod_manager/`
- **Frontend:** React 19, TypeScript 5.9 (strict), Vite, Tailwind CSS v4 — `frontend/src/`
- **Desktop:** Tauri v2, Rust — `frontend/src-tauri/`
- **State:** Zustand (client), React Query (server), SQLite (persistence), ChromaDB (vectors)
- **Key deps:** httpx, tenacity (retry), keyring (OS secret store), scikit-learn, jellyfish, langchain

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
- **Matching tiers:** (1) filename ID extraction, (1.5) file content reverse lookup, (2) MD5 hash batch lookup, (3) endorsed/tracked + collection matching + requirement propagation, (4) Jaccard + Jaro-Winkler fuzzy, (5) AI/web search
- **Secrets:** keyring service attempts OS keychain, falls back to SQLite. Keys: `nexus_api_key`, `openai_api_key`, `tavily_api_key`
- **Health:** `/health` (shallow), `/health/deep` (DB + ChromaDB + data_dir writability)
- **Logging:** stderr + `RotatingFileHandler` at `data_dir/logs/rippermod.log` (5 MB × 3)
- Chat agent: LangChain + OpenAI with SSE streaming
- Tauri CSP restricts connections to `localhost:8425`

## Database

- SQLite with WAL mode, `PRAGMA foreign_keys=ON`, `synchronous=NORMAL`
- Single-writer — avoid long-running transactions and blocking operations
- Migrations: column additions in `database.py:_migrate_missing_columns()`, unique indexes in `_migrate_unique_indexes()`
- NEVER use raw SQL for queries accessible from user input — use SQLModel/SQLAlchemy parameterized queries

## Nexus Mods API

See @docs/nexus-api-usage.md for endpoint reference.

- Rate limits: 2,500/day, 100/hour. Track via `X-RL-Hourly-Remaining` / `X-RL-Daily-Remaining`
- REST v1 for mutations (endorse, track, download links); GraphQL v2 for batch reads (file hashes, mod info, search)
- Retry on 429 and 5xx only — NEVER retry 401/403/404
- `NexusRateLimitError` and `NexusPremiumRequiredError` are custom exceptions — catch them explicitly before generic `httpx.HTTPError`

## Testing

- 822+ tests across `backend/tests/` (routers, services, matching, scanner, nexus, archive, vector, agents)
- Fixtures in `tests/conftest.py` — in-memory SQLite, test games, mock clients
- CI runs with `--cov=rippermod_manager --cov-report=term-missing`
- Use `respx` for HTTP mocking — never make real API calls in tests
- Prefer testing a single file: `uv run pytest tests/services/test_foo.py -v`

## Review focus

When reviewing PRs, pay extra attention to:
- **Performance:** Desktop app — avoid unnecessary re-renders, heavy DOM operations, virtualize long lists
- **SQLite concurrency:** Single-writer — watch for blocking operations in async handlers
- **Type safety:** Handle `undefined` from indexed access in TypeScript
- **Security:** CSP compliance, no arbitrary eval, sanitize AI-generated content, no path traversal in archive extraction
- **Nexus API:** Rate limiting, proper error handling, catch specific exceptions before broad ones
- **Vector store:** ChromaDB collection lifecycle, index consistency after data mutations
- **Exception handling:** Use specific types (`httpx.HTTPError`, `OSError`) — only use `except Exception` for shutdown/cleanup and ChromaDB operations
