# CLAUDE.md

## Project overview

Chat Nexus Mod Manager is a desktop AI-powered mod manager for PC games (focused on Cyberpunk 2077). It combines a chat agent backend with Nexus Mods integration to scan, group, correlate, and manage mods.

- **Backend:** FastAPI (Python 3.12, uv, src layout at `backend/src/chat_nexus_mod_manager/`)
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS v4 (`frontend/`)
- **Desktop shell:** Tauri v2 (Rust, `frontend/src-tauri/`)
- **State:** Zustand for client state, React Query for server state, SQLite for persistence
- **Vector store:** ChromaDB for semantic mod search

## Commands

```bash
# Backend
cd backend && uv run uvicorn chat_nexus_mod_manager.main:app --reload --port 8425  # Dev server
cd backend && uv run ruff check src/ tests/    # Lint
cd backend && uv run ruff format src/ tests/   # Format
cd backend && uv run pytest tests/ -v          # Tests

# Frontend
cd frontend && npm run dev         # Vite dev (port 1420)
cd frontend && npm run build       # tsc + vite build
cd frontend && npm run lint        # ESLint
cd frontend && npx tauri dev       # Tauri desktop window
```

## Code style

### Python (backend)
- Ruff: line-length 100, rules `E F I UP B SIM RUF`
- Type hints required on public functions
- Async-first: use `async def` for route handlers
- Imports sorted by isort via Ruff

### TypeScript (frontend)
- Strict mode enabled
- Path alias: `@/*` maps to `./src/*`
- Unused vars prefixed with `_` are allowed

### General
- Commit messages: English, conventional commits (`feat:`, `fix:`, `perf:`, `refactor:`, `chore:`, `docs:`)
- All code, comments, and commits in English

## Architecture notes

- Backend API at `http://localhost:8425`, prefix `/api/v1/`
- Chat agent uses LangChain + OpenAI with SSE streaming
- Nexus Mods API client uses async httpx with `APIKEY` header
- Scanner groups mod files using TF-IDF + DBSCAN clustering
- Correlator matches local mods to Nexus downloads via Jaccard + Jaro-Winkler
- ChromaDB stores embeddings for semantic search across mods, Nexus metadata, and correlations
- Tauri CSP restricts connections to `localhost:8425`

## Review focus areas

When reviewing PRs, pay extra attention to:
- **Performance:** Desktop app — avoid unnecessary re-renders and heavy DOM operations
- **SQLite concurrency:** Single-writer — watch for blocking operations
- **Type safety:** Handle `undefined` from indexed access
- **Security:** CSP compliance, no arbitrary eval, sanitize AI-generated content
- **Nexus API:** Rate limiting, proper error handling for 429/5xx responses
- **Vector store:** ChromaDB collection lifecycle, index consistency after data mutations
