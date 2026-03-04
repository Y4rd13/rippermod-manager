<p align="center">
  <img src="frontend/src-tauri/icons/128x128.png" alt="RipperMod Manager" width="100" />
</p>

<h1 align="center">RipperMod Manager</h1>

<p align="center">
  A desktop AI-powered mod manager for PC games.<br>
  Scan, group, correlate, and manage your mods with an integrated chat assistant and <a href="https://www.nexusmods.com/">Nexus Mods</a> integration.
</p>

<p align="center">
  Built with Cyberpunk 2077 as the primary target, but designed to support any game on Nexus Mods.
</p>

<p align="center">
  <a href="https://github.com/Y4rd13/rippermod-manager/actions/workflows/ci.yml"><img src="https://github.com/Y4rd13/rippermod-manager/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Y4rd13/rippermod-manager" alt="License" /></a>
</p>

---

## Features

- **Mod Scanner** — Recursively discovers mod files from configured game paths, groups them by name similarity using TF-IDF + DBSCAN clustering, and computes file hashes for integrity tracking.
- **Nexus Mods Integration** — Connects to your Nexus account via SSO, syncs tracked/endorsed mods, fetches mod metadata, and searches Nexus by name via GraphQL v2.
- **Endorse & Track** — Toggle endorse/track status on any mod directly from card buttons, context menus, or the mod detail modal — syncs with the Nexus Mods API in real time.
- **Auto-Correlation** — Matches local mod groups to Nexus downloads using Jaccard similarity + Jaro-Winkler distance scoring, with manual reassign and confirm/reject actions.
- **Mod Installation** — Install mods from downloaded archives with pre-install preview, conflict detection, skip/overwrite resolution, and enable/disable toggling. Includes FOMOD installer wizard for scripted mod packages.
- **Conflict Detection** — Multi-layer conflict engine: file-level overlap detection, redscript annotation analysis, TweakXL conflict scanning, and a conflict inbox for resolution.
- **Load Order** — View and manage archive load order with preference rules, modlist.txt generation, and dry-run previews.
- **Archive Management** — Browse archive contents, link/unlink archives to Nexus mods, delete, and clean up orphaned mod archives from the downloads staging folder.
- **Download Manager** — Download mod archives directly from Nexus Mods with progress tracking, NXM deep link handling, and premium account support.
- **Trending Mods** — Browse trending and recently updated mods from Nexus with one-click install, endorse, or track actions.
- **Endorsed & Tracked Tabs** — Browse your endorsed and tracked mods from Nexus with install actions or direct Nexus links.
- **Mod Detail Modal** — View full mod details including description, files, changelogs, requirements, and action buttons without leaving the app.
- **Profile Manager** — Save, load, export, import, duplicate, and compare mod profiles to switch between mod configurations.
- **Update Checker** — Compares local mod versions against Nexus metadata to surface available updates with one-click download.
- **AI Search** — AI-powered mod matching with configurable OpenAI model and reasoning effort for enhanced scan accuracy.
- **Semantic Search** — ChromaDB vector store indexes mods, Nexus metadata, and correlations for natural-language queries.
- **Chat Assistant** — LangChain-powered agent with tool access to the local mod database and Nexus data, streamed via SSE.
- **Guided Onboarding** — Step-by-step setup for Nexus Mods login, game configuration, and initial mod scan.
- **Custom Titlebar** — Native-feeling Tauri window with custom drag region and window controls.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel, SQLite |
| AI Agent | LangChain, OpenAI (configurable model) |
| Vector Store | ChromaDB (persistent, cosine similarity) |
| Nexus API | REST v1 + GraphQL v2, async httpx, respx (testing) — [endpoint map](docs/nexus-api-usage.md) |
| Matching | scikit-learn (TF-IDF, DBSCAN), jellyfish (Jaro-Winkler) |
| Hashing | xxhash (xxh64) |
| Frontend | React 19, TypeScript 5.9, Vite 7 |
| Styling | Tailwind CSS v4 |
| State | Zustand (client), TanStack React Query (server) |
| Desktop | Tauri v2 (Rust) |
| Bundling | PyInstaller (backend → sidecar .exe), NSIS (Windows installer) |
| Package Manager | uv (backend), npm (frontend) |
| Linting | Ruff (Python), ESLint (TypeScript) |
| Testing | pytest, pytest-asyncio, respx |
| CI/CD | GitHub Actions (consolidated CI gate, automated PR review, release pipeline) |

## Project Structure

```
rippermod-manager/
├── backend/                 # FastAPI + Python 3.12
│   ├── src/rippermod_manager/
│   │   ├── models/          # 12 SQLModel table modules
│   │   ├── schemas/         # Pydantic request/response models
│   │   ├── routers/         # 15 API routers (67 endpoints)
│   │   ├── services/        # 35 business logic modules
│   │   ├── scanner/         # File discovery + grouping
│   │   ├── matching/        # TF-IDF, correlation, filename parsing
│   │   ├── nexus/           # REST v1 + GraphQL v2 API clients
│   │   ├── vector/          # ChromaDB indexing + search
│   │   └── agents/          # LangChain chat agent
│   └── tests/               # 720+ tests across 45 files
├── frontend/                # React 19 + TypeScript + Vite
│   ├── src/
│   │   ├── components/      # 25 mod components, 24 UI primitives
│   │   ├── pages/           # 6 pages
│   │   ├── hooks/           # 12 hooks (React Query, install, FOMOD, ...)
│   │   ├── stores/          # Zustand stores
│   │   └── lib/             # API client, SSE parser, utils
│   └── src-tauri/           # Tauri v2 Rust shell + sidecar lifecycle
├── docs/                    # Architecture, Nexus API map
├── scripts/                 # Build + release helpers
└── .github/workflows/       # CI, release, PR review, CLA
```

> Full file-level tree: [docs/architecture.md](docs/architecture.md)

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js 22+](https://nodejs.org/)
- [Rust](https://rustup.rs/) (for Tauri desktop builds)
- [Nexus Mods account](https://www.nexusmods.com/) (free — sign in via SSO)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Y4rd13/rippermod-manager.git
cd rippermod-manager
```

### 2. Backend setup

```bash
cd backend
uv sync                  # Install dependencies
uv sync --extra test     # Include test dependencies

# Start the dev server
uv run uvicorn rippermod_manager.main:app --reload --port 8425
```

The API will be available at `http://localhost:8425`. The SQLite database and ChromaDB are auto-created at `%LOCALAPPDATA%\RipperModManager\` on Windows (or `~/.local/share/RipperModManager/` on Linux) on first startup.

> **Tip:** Set `RMM_DATA_DIR=./data` in `backend/.env` to use a local data directory instead.

### 3. Frontend setup

```bash
cd frontend
npm install

# Development (browser only, connects to backend at :8425)
npm run dev              # Vite dev server at http://localhost:1420

# Development (Tauri desktop window)
npx tauri dev
```

### 4. Configuration

On first launch, the onboarding flow will guide you through:

1. **Nexus Mods login** — Sign in with your Nexus Mods account via SSO
2. **Game setup** — Configure your game install path (Cyberpunk 2077 auto-detects from Steam, GOG, and Epic)
3. **Initial scan** — Discovers and groups your installed mods

Credentials are stored in the local SQLite database and masked in the settings UI.

## Development

### Backend commands

```bash
cd backend
uv run uvicorn rippermod_manager.main:app --reload --port 8425   # Dev server
uv run ruff check src/ tests/                                         # Lint
uv run ruff format src/ tests/                                        # Format
uv run pytest tests/ -v                                               # Tests (720+ tests)
```

### Frontend commands

```bash
cd frontend
npm run dev          # Vite dev server (port 1420)
npm run build        # TypeScript check + Vite build
npm run lint         # ESLint
npx tauri dev        # Tauri desktop window
npx tauri build      # Production desktop build
```

### Building for Production

The release build produces a standalone Windows installer (NSIS `.exe`) with the Python backend bundled as a sidecar:

```powershell
# 1. Build backend as standalone .exe
cd backend
uv sync --extra build
uv run pyinstaller rmm-backend.spec --clean --noconfirm

# 2. Copy sidecar to Tauri binaries
.\scripts\build-backend.ps1

# 3. Build Tauri installer
cd frontend
npx tauri build
# Output: frontend/src-tauri/target/release/bundle/nsis/*.exe
```

Releases are handled automatically by `semantic-release` — merging a conventional commit to `main` triggers versioning, changelog generation, and a GitHub release with the installer attached.

### API Endpoints

All endpoints are prefixed with `/api/v1/`.

<details>
<summary><strong>Games</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/` | List all configured games |
| `POST` | `/games/` | Add a new game |
| `GET` | `/games/{name}` | Get game details |
| `DELETE` | `/games/{name}` | Remove a game |
| `GET` | `/games/{name}/version` | Get detected game version |
| `POST` | `/games/validate-path` | Validate a game install path |

</details>

<details>
<summary><strong>Mods</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/mods/` | List mod groups with files |
| `POST` | `/games/{name}/mods/scan` | Scan and group mod files |
| `POST` | `/games/{name}/mods/scan-stream` | Scan with SSE progress streaming |
| `POST` | `/games/{name}/mods/correlate` | Match mods to Nexus downloads |
| `PATCH` | `/games/{name}/mods/{id}/correlation/confirm` | Confirm a correlation |
| `DELETE` | `/games/{name}/mods/{id}/correlation` | Reject correlation |
| `PUT` | `/games/{name}/mods/{id}/correlation` | Reassign mod to different Nexus ID |

</details>

<details>
<summary><strong>Install</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/install/available` | List archives available for installation |
| `GET` | `/games/{name}/install/installed` | List all installed mods |
| `POST` | `/games/{name}/install/` | Install a mod from an archive |
| `DELETE` | `/games/{name}/install/installed/{id}` | Uninstall a mod |
| `PATCH` | `/games/{name}/install/installed/{id}/toggle` | Enable/disable a mod |
| `GET` | `/games/{name}/install/preview` | Preview files before installation |
| `GET` | `/games/{name}/install/conflicts` | Check for file conflicts |
| `GET` | `/games/{name}/install/archives/{filename}/contents` | Browse archive file tree |
| `PUT` | `/games/{name}/install/archives/{filename}/nexus-link` | Link archive to Nexus mod |
| `DELETE` | `/games/{name}/install/archives/{filename}/nexus-link` | Remove Nexus link |
| `DELETE` | `/games/{name}/install/archives/{filename}` | Delete an archive |
| `POST` | `/games/{name}/install/archives/cleanup-orphans` | Clean up unused archives |
| `GET` | `/games/{name}/install/redscript-conflicts` | Analyze redscript annotation conflicts |

</details>

<details>
<summary><strong>FOMOD</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/install/fomod/config` | Parse and return FOMOD configuration |
| `POST` | `/games/{name}/install/fomod/preview` | Preview files with FOMOD selections |
| `POST` | `/games/{name}/install/fomod/install` | Install archive with FOMOD selections |

</details>

<details>
<summary><strong>Downloads</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/games/{name}/downloads/` | Start a download from Nexus |
| `GET` | `/games/{name}/downloads/` | List download jobs |
| `GET` | `/games/{name}/downloads/{id}` | Get download job details |
| `POST` | `/games/{name}/downloads/{id}/cancel` | Cancel a download |
| `POST` | `/games/{name}/downloads/from-mod` | Download from mod detail page |

</details>

<details>
<summary><strong>Profiles</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/profiles/` | List saved profiles |
| `POST` | `/games/{name}/profiles/` | Save current state as a profile |
| `GET` | `/games/{name}/profiles/{id}` | Get profile details |
| `DELETE` | `/games/{name}/profiles/{id}` | Delete a profile |
| `PATCH` | `/games/{name}/profiles/{id}` | Update profile name/description |
| `POST` | `/games/{name}/profiles/{id}/load` | Load a profile |
| `POST` | `/games/{name}/profiles/{id}/preview` | Preview profile load changes |
| `POST` | `/games/{name}/profiles/{id}/export` | Export profile as JSON |
| `POST` | `/games/{name}/profiles/{id}/duplicate` | Duplicate a profile |
| `POST` | `/games/{name}/profiles/import` | Import profile from JSON |
| `POST` | `/games/{name}/profiles/compare` | Compare two profiles |

</details>

<details>
<summary><strong>Nexus Mods</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/nexus/sync-history/{name}` | Sync tracked/endorsed mods |
| `GET` | `/nexus/downloads/{name}` | List synced downloads (filterable by `?source=endorsed\|tracked`) |
| `GET` | `/nexus/downloads/{name}/search` | Search synced downloads by name |
| `GET` | `/nexus/search/{name}` | Search Nexus Mods by name (GraphQL v2) |
| `GET` | `/nexus/mods/{domain}/{mod_id}/detail` | Get full mod detail with files and changelogs |
| `GET` | `/nexus/file-contents-preview?url=...` | Proxy Nexus file content preview |
| `POST` | `/nexus/{name}/mods/{mod_id}/endorse` | Endorse a mod |
| `POST` | `/nexus/{name}/mods/{mod_id}/abstain` | Remove endorsement |
| `POST` | `/nexus/{name}/mods/{mod_id}/track` | Track a mod |
| `DELETE` | `/nexus/{name}/mods/{mod_id}/track` | Untrack a mod |
| `POST` | `/nexus/sso/start` | Start Nexus SSO session |
| `GET` | `/nexus/sso/poll/{uuid}` | Poll SSO session status |
| `DELETE` | `/nexus/sso/{uuid}` | Cancel SSO session |

</details>

<details>
<summary><strong>Conflicts</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/conflicts/` | Detect conflicts between installed mods |
| `GET` | `/games/{name}/conflicts/between` | Compare two specific mods |
| `GET` | `/games/{name}/conflicts/summary` | Persisted conflict report (filterable by kind/severity) |
| `POST` | `/games/{name}/conflicts/reindex` | Trigger full conflict re-scan |
| `GET` | `/games/{name}/conflicts/archive-summaries` | Per-archive conflict summaries |
| `GET` | `/games/{name}/conflicts/archive-details/{filename}` | Per-resource conflict details |
| `GET` | `/games/{name}/conflicts/graph` | Conflict graph visualization data |
| `GET` | `/games/{name}/conflicts/inbox` | List conflict inbox summaries |
| `GET` | `/games/{name}/conflicts/inbox/{mod_id}` | Detailed conflicts for a mod |
| `POST` | `/games/{name}/conflicts/inbox/{mod_id}/resolve` | Resolve conflicts by reinstalling |
| `POST` | `/games/{name}/conflicts/inbox/{mod_id}/dismiss` | Dismiss mod's conflicts |
| `DELETE` | `/games/{name}/conflicts/inbox/{mod_id}/dismiss` | Restore dismissed mod to inbox |

</details>

<details>
<summary><strong>Load Order</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/load-order/` | Full archive load order with conflicts |
| `GET` | `/games/{name}/load-order/modlist` | Ordered mod groups and preferences |
| `POST` | `/games/{name}/load-order/prefer/preview` | Dry-run load order preference |
| `POST` | `/games/{name}/load-order/prefer` | Add preference and write modlist.txt |
| `DELETE` | `/games/{name}/load-order/preferences` | Remove all preferences |
| `DELETE` | `/games/{name}/load-order/preferences/{winner}/{loser}` | Remove single preference |

</details>

<details>
<summary><strong>Trending</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/trending/` | Get trending and recently updated mods |

</details>

<details>
<summary><strong>Updates</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/updates/` | List available updates |
| `POST` | `/games/{name}/updates/check` | Refresh update data from Nexus |

</details>

<details>
<summary><strong>Settings, Onboarding, Chat, Vector</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET/PUT` | `/settings/` | Read/update app settings |
| `GET` | `/settings/specs` | Get stored PC specs |
| `POST` | `/settings/specs/capture` | Store PC specs |
| `GET` | `/onboarding/status` | Get onboarding progress |
| `POST` | `/onboarding/complete` | Complete onboarding |
| `POST` | `/onboarding/reset` | Reset onboarding status |
| `POST` | `/chat/` | Chat with AI assistant (SSE) |
| `GET` | `/chat/history` | Get chat history |
| `POST` | `/vector/reindex` | Rebuild vector store index |
| `GET` | `/vector/search?q=...` | Semantic search |
| `GET` | `/vector/stats` | Vector collection statistics |

</details>

### Testing

The backend has a comprehensive test suite with 720+ tests across 45 test files covering all modules:

```bash
cd backend
uv sync --extra test
uv run pytest -v
```

Tests use an in-memory SQLite database and patched ChromaDB for full isolation. External API calls are mocked with [respx](https://github.com/lundberg/respx).

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  Tauri v2 Shell                  │
│  ┌───────────────────────────────────────────┐   │
│  │            React Frontend                 │   │
│  │  Zustand ─── React Query ─── SSE Parser   │   │
│  │  ErrorBoundary ─── BackendGate            │   │
│  └──────────────────┬────────────────────────┘   │
│                     │                            │
│          Sidecar Lifecycle Manager                │
│  (spawn → health poll → events → kill on close)  │
└─────────────────────┼────────────────────────────┘
                      │ HTTP / SSE (localhost:8425)
┌─────────────────────┼────────────────────────────┐
│    FastAPI Backend (PyInstaller sidecar .exe)     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Routers  │ │ Scanner  │ │   Chat Agent     │  │
│  │(15 APIs) │ │ Grouper  │ │ (LangChain+OAI)  │  │
│  │          │ │Correlator│ │   7 tools        │  │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │
│       │             │               │             │
│  ┌────┴─────────────┴───────────────┴──────────┐  │
│  │              SQLite (SQLModel)              │  │
│  │       %LOCALAPPDATA%/RipperModManager    │  │
│  └──────────────────┬──────────────────────────┘  │
│                     │                             │
│  ┌──────────────────┴──────────────────────────┐  │
│  │           ChromaDB Vector Store             │  │
│  │  mod_groups │ nexus_mods │ correlations     │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │         Nexus Mods API (httpx)              │  │
│  │  REST v1 (mutations) │ GraphQL v2 (queries) │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

### Desktop Distribution

In production, the app ships as a single Windows installer (NSIS):

- **Frontend** → bundled by Vite into static assets inside the Tauri shell
- **Backend** → compiled by PyInstaller into `rmm-backend.exe`, embedded as a Tauri sidecar
- **Startup** → Tauri spawns the sidecar, health-polls `/health`, emits `backend-ready` event
- **Shutdown** → Cancels active downloads, disposes DB engine, releases ChromaDB, kills sidecar
- **Data** → Stored in `%LOCALAPPDATA%\RipperModManager\` (DB, ChromaDB, downloads)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes following the code style in [CLAUDE.md](CLAUDE.md)
4. Run tests (`cd backend && uv run pytest -v`)
5. Commit using [conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, etc.)
6. Open a Pull Request — CI Gate must pass and an automated review is required before merge

All contributors must agree to the [Contributor License Agreement](CLA.md) before their PR can be merged. The `main` branch is protected: direct pushes, force pushes, and deletions are blocked.

## License

This project is licensed under the **GNU General Public License v3.0**. See [LICENSE](LICENSE) for details.
