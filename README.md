<p align="center">
  <img src="frontend/src-tauri/icons/128x128.png" alt="Chat Nexus Mod Manager" width="100" />
</p>

<h1 align="center">Chat Nexus Mod Manager</h1>

<p align="center">
  A desktop AI-powered mod manager for PC games.<br>
  Scan, group, correlate, and manage your mods with an integrated chat assistant and <a href="https://www.nexusmods.com/">Nexus Mods</a> integration.
</p>

<p align="center">
  Built with Cyberpunk 2077 as the primary target, but designed to support any game on Nexus Mods.
</p>

<p align="center">
  <a href="https://github.com/Y4rd13/chat-nexus-mod-manager/actions/workflows/ci.yml"><img src="https://github.com/Y4rd13/chat-nexus-mod-manager/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Y4rd13/chat-nexus-mod-manager" alt="License" /></a>
</p>

---

## Features

- **Mod Scanner** — Recursively discovers mod files from configured game paths, groups them by name similarity using TF-IDF + DBSCAN clustering, and computes file hashes for integrity tracking.
- **Nexus Mods Integration** — Validates API keys, syncs tracked/endorsed mods, fetches mod metadata, and checks for available updates.
- **Auto-Correlation** — Matches local mod groups to Nexus downloads using Jaccard similarity + Jaro-Winkler distance scoring.
- **Mod Installation** — Install mods from downloaded archives with conflict detection, skip/overwrite resolution, and enable/disable toggling.
- **Download Manager** — Download mod archives directly from Nexus Mods with progress tracking and premium account support.
- **Endorsed & Tracked Tabs** — Browse your endorsed and tracked mods from Nexus with install actions or direct Nexus links.
- **Profile Manager** — Save, load, export, and import mod profiles to switch between mod configurations.
- **Update Checker** — Compares local mod versions against Nexus metadata to surface available updates with one-click download.
- **Semantic Search** — ChromaDB vector store indexes mods, Nexus metadata, and correlations for natural-language queries.
- **Chat Assistant** — LangChain-powered agent with tool access to the local mod database and Nexus data, streamed via SSE.
- **Guided Onboarding** — Step-by-step setup for API keys, game configuration, and initial mod scan.
- **Custom Titlebar** — Native-feeling Tauri window with custom drag region and window controls.

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12, FastAPI, SQLModel, SQLite |
| AI Agent | LangChain, OpenAI (configurable model) |
| Vector Store | ChromaDB (persistent, cosine similarity) |
| Nexus API | async httpx, respx (testing) |
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
| CI/CD | GitHub Actions (lint, test, Tauri build, release pipeline) |

## Project Structure

```
chat-nexus-mod-manager/
├── backend/
│   ├── src/chat_nexus_mod_manager/
│   │   ├── __main__.py              # Standalone entry point (uvicorn)
│   │   ├── main.py                  # FastAPI app, lifespan, CORS, /health
│   │   ├── config.py                # Pydantic settings (AppData paths)
│   │   ├── database.py              # SQLite engine, session factory
│   │   ├── models/                  # SQLModel tables
│   │   │   ├── game.py              #   Game, GameModPath
│   │   │   ├── mod.py               #   ModGroup, ModFile, ModGroupAlias
│   │   │   ├── nexus.py             #   NexusDownload, NexusModMeta
│   │   │   ├── correlation.py       #   ModNexusCorrelation
│   │   │   ├── settings.py          #   AppSetting, PCSpecs
│   │   │   └── chat.py              #   ChatMessage
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── routers/                 # FastAPI routers (prefix /api/v1/)
│   │   │   ├── games.py             #   CRUD games + mod paths
│   │   │   ├── mods.py              #   List, scan, correlate mods
│   │   │   ├── nexus.py             #   Validate, connect, sync Nexus
│   │   │   ├── install.py           #   Install, uninstall, toggle mods
│   │   │   ├── downloads.py         #   Download mods from Nexus
│   │   │   ├── profiles.py          #   Save, load, export/import profiles
│   │   │   ├── updates.py           #   Version diff + update check
│   │   │   ├── settings.py          #   App settings + PC specs
│   │   │   ├── onboarding.py        #   Onboarding status + completion
│   │   │   ├── chat.py              #   SSE chat endpoint
│   │   │   └── vector.py            #   Reindex, search, stats
│   │   ├── scanner/service.py       # File discovery + grouping
│   │   ├── matching/
│   │   │   ├── grouper.py           # TF-IDF + DBSCAN file grouping
│   │   │   └── correlator.py        # Local↔Nexus name matching
│   │   ├── nexus/client.py          # Async Nexus Mods API client
│   │   ├── services/
│   │   │   ├── nexus_sync.py        # Sync tracked/endorsed mods
│   │   │   └── download_service.py  # Download orchestration + shutdown
│   │   ├── vector/
│   │   │   ├── store.py             # ChromaDB client + collections
│   │   │   ├── indexer.py           # Index mods/nexus/correlations
│   │   │   └── search.py            # Semantic search queries
│   │   └── agents/orchestrator.py   # LangChain agent + tools
│   ├── cnmm-backend.spec            # PyInstaller spec (--onefile)
│   └── tests/                       # 305 pytest tests
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── BackendGate.tsx       # Waits for backend before rendering
│   │   │   ├── ErrorBoundary.tsx     # Catches crashes, shows fallback UI
│   │   │   ├── chat/                 #   ChatPanel
│   │   │   ├── layout/              #   Sidebar, Titlebar
│   │   │   ├── mods/                #   NexusModCard, NexusMatchedGrid,
│   │   │   │                        #   NexusAccountGrid, InstalledModsTable,
│   │   │   │                        #   ArchivesList, ProfileManager,
│   │   │   │                        #   ConflictDialog, ModsTable
│   │   │   └── ui/                  #   Badge, Button, Card, Input, Toast
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── GamesPage.tsx
│   │   │   ├── GameDetailPage.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   ├── UpdatesPage.tsx
│   │   │   └── OnboardingPage.tsx
│   │   ├── hooks/                   # React Query hooks + useInstallFlow
│   │   ├── stores/                  # Zustand stores
│   │   ├── lib/                     # API client, SSE parser, utils
│   │   ├── router/                  # Routes + OnboardingGuard
│   │   ├── layouts/                 # Root + Onboarding layouts
│   │   └── types/                   # TypeScript API types
│   └── src-tauri/                   # Tauri v2 Rust shell + sidecar lifecycle
├── scripts/
│   ├── build-backend.ps1            # PyInstaller build + sidecar copy
│   └── ensure-dev-sidecar.ps1       # Dev placeholder for Tauri compile
├── .github/workflows/
│   ├── ci.yml                       # Backend + Frontend + Tauri build
│   ├── release.yml                  # Tag-triggered release pipeline
│   ├── claude.yml                   # Claude Code interactive (@claude)
│   └── claude-pr-review.yml         # Automated PR review
├── CLAUDE.md                        # AI assistant project context
├── CLA.md                           # Contributor License Agreement
└── LICENSE                          # MIT
```

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js 22+](https://nodejs.org/)
- [Rust](https://rustup.rs/) (for Tauri desktop builds)
- [Nexus Mods API key](https://www.nexusmods.com/users/myaccount?tab=api+access) (free personal key)
- [OpenAI API key](https://platform.openai.com/api-keys) (optional — only for chat assistant)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Y4rd13/chat-nexus-mod-manager.git
cd chat-nexus-mod-manager
```

### 2. Backend setup

```bash
cd backend
uv sync                  # Install dependencies
uv sync --extra test     # Include test dependencies

# Start the dev server
uv run uvicorn chat_nexus_mod_manager.main:app --reload --port 8425
```

The API will be available at `http://localhost:8425`. The SQLite database and ChromaDB are auto-created at `%LOCALAPPDATA%\ChatNexusModManager\` on Windows (or `~/.local/share/ChatNexusModManager/` on Linux) on first startup.

> **Tip:** Set `CNMM_DATA_DIR=./data` in `backend/.env` to use a local data directory instead.

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

1. **OpenAI API key** — Powers the chat assistant (optional)
2. **Nexus Mods API key** — Enables mod tracking and metadata sync
3. **Game setup** — Configure your game install path (Cyberpunk 2077 auto-detects from Steam, GOG, and Epic)
4. **Initial scan** — Discovers and groups your installed mods

API keys are stored in the local SQLite database and masked in the settings UI.

## Development

### Backend commands

```bash
cd backend
uv run uvicorn chat_nexus_mod_manager.main:app --reload --port 8425   # Dev server
uv run ruff check src/ tests/                                         # Lint
uv run ruff format src/ tests/                                        # Format
uv run pytest tests/ -v                                               # Tests (305 tests)
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
uv run pyinstaller cnmm-backend.spec --clean --noconfirm

# 2. Copy sidecar to Tauri binaries
.\scripts\build-backend.ps1

# 3. Build Tauri installer
cd frontend
npx tauri build
# Output: frontend/src-tauri/target/release/bundle/nsis/*.exe
```

Or push a version tag to trigger the automated release pipeline:

```bash
git tag v1.0.0
git push --tags
# → GitHub Actions builds and creates a draft release with the installer
```

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

</details>

<details>
<summary><strong>Mods</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/mods/` | List mod groups with files |
| `POST` | `/games/{name}/mods/scan` | Scan and group mod files |
| `POST` | `/games/{name}/mods/scan-stream` | Scan with SSE progress streaming |
| `POST` | `/games/{name}/mods/correlate` | Match mods to Nexus downloads |

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
| `GET` | `/games/{name}/install/conflicts` | Check for file conflicts |

</details>

<details>
<summary><strong>Downloads</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/games/{name}/downloads/` | Start a download from Nexus |
| `GET` | `/games/{name}/downloads/` | List download jobs |
| `GET` | `/games/{name}/downloads/{id}` | Get download job details |
| `POST` | `/games/{name}/downloads/{id}/cancel` | Cancel a download |

</details>

<details>
<summary><strong>Profiles</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/{name}/profiles/` | List saved profiles |
| `POST` | `/games/{name}/profiles/` | Save current state as a profile |
| `GET` | `/games/{name}/profiles/{id}` | Get profile details |
| `DELETE` | `/games/{name}/profiles/{id}` | Delete a profile |
| `POST` | `/games/{name}/profiles/{id}/load` | Load a profile |
| `POST` | `/games/{name}/profiles/{id}/export` | Export profile as JSON |
| `POST` | `/games/{name}/profiles/import` | Import profile from JSON |

</details>

<details>
<summary><strong>Nexus Mods</strong></summary>

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/nexus/validate` | Validate a Nexus API key |
| `POST` | `/nexus/connect` | Validate and store a Nexus key |
| `POST` | `/nexus/sync-history/{name}` | Sync tracked/endorsed mods |
| `GET` | `/nexus/downloads/{name}` | List synced downloads (filterable by `?source=endorsed\|tracked`) |

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
| `POST` | `/chat/` | Chat with AI assistant (SSE) |
| `GET` | `/chat/history` | Get chat history |
| `POST` | `/vector/reindex` | Rebuild vector store index |
| `GET` | `/vector/search?q=...` | Semantic search |
| `GET` | `/vector/stats` | Vector collection statistics |

</details>

### Testing

The backend has a comprehensive test suite with 305 tests across 25 test files covering all modules:

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
│  │(11 APIs) │ │ Grouper  │ │ (LangChain+OAI)  │  │
│  │          │ │Correlator│ │   7 tools        │  │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │
│       │             │               │             │
│  ┌────┴─────────────┴───────────────┴──────────┐  │
│  │              SQLite (SQLModel)              │  │
│  │       %LOCALAPPDATA%/ChatNexusModManager    │  │
│  └──────────────────┬──────────────────────────┘  │
│                     │                             │
│  ┌──────────────────┴──────────────────────────┐  │
│  │           ChromaDB Vector Store             │  │
│  │  mod_groups │ nexus_mods │ correlations     │  │
│  └─────────────────────────────────────────────┘  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │         Nexus Mods API (httpx)              │  │
│  └─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────┘
```

### Desktop Distribution

In production, the app ships as a single Windows installer (NSIS):

- **Frontend** → bundled by Vite into static assets inside the Tauri shell
- **Backend** → compiled by PyInstaller into `cnmm-backend.exe`, embedded as a Tauri sidecar
- **Startup** → Tauri spawns the sidecar, health-polls `/health`, emits `backend-ready` event
- **Shutdown** → Cancels active downloads, disposes DB engine, releases ChromaDB, kills sidecar
- **Data** → Stored in `%LOCALAPPDATA%\ChatNexusModManager\` (DB, ChromaDB, downloads)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes following the code style in [CLAUDE.md](CLAUDE.md)
4. Run tests (`cd backend && uv run pytest -v`)
5. Commit using [conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, etc.)
6. Open a Pull Request

All contributors must agree to the [Contributor License Agreement](CLA.md) before their PR can be merged.

## License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.
