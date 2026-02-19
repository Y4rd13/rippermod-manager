# Chat Nexus Mod Manager

A desktop AI-powered mod manager for PC games. Scan, group, correlate, and manage your mods with an integrated chat assistant and [Nexus Mods](https://www.nexusmods.com/) integration.

Built with Cyberpunk 2077 as the primary target, but designed to support any game on Nexus Mods.

## Features

- **Mod Scanner** — Recursively discovers mod files from configured game paths, groups them by name similarity using TF-IDF + DBSCAN clustering, and computes file hashes for integrity tracking.
- **Nexus Mods Integration** — Validates API keys, syncs tracked/endorsed mods, fetches mod metadata, and checks for available updates.
- **Auto-Correlation** — Matches local mod groups to Nexus downloads using Jaccard similarity + Jaro-Winkler distance scoring.
- **Semantic Search** — ChromaDB vector store indexes mods, Nexus metadata, and correlations for natural-language queries.
- **Chat Assistant** — LangChain-powered agent with tool access to the local mod database and Nexus data, streamed via SSE.
- **Update Checker** — Compares local mod versions against Nexus metadata to surface available updates.
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
| Package Manager | uv (backend), npm (frontend) |
| Linting | Ruff (Python), ESLint (TypeScript) |
| Testing | pytest, pytest-asyncio, respx |

## Project Structure

```
chat-nexus-mod-manager/
├── backend/
│   ├── src/chat_nexus_mod_manager/
│   │   ├── main.py                 # FastAPI app, lifespan, CORS
│   │   ├── config.py               # Pydantic settings (env vars)
│   │   ├── database.py             # SQLite engine, session factory
│   │   ├── models/                 # SQLModel tables
│   │   │   ├── game.py             #   Game, GameModPath
│   │   │   ├── mod.py              #   ModGroup, ModFile, ModGroupAlias
│   │   │   ├── nexus.py            #   NexusDownload, NexusModMeta
│   │   │   ├── correlation.py      #   ModNexusCorrelation
│   │   │   ├── settings.py         #   AppSetting, PCSpecs
│   │   │   └── chat.py             #   ChatMessage
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── routers/                # FastAPI routers (prefix /api/v1/)
│   │   │   ├── games.py            #   CRUD games + mod paths
│   │   │   ├── mods.py             #   List, scan, correlate mods
│   │   │   ├── nexus.py            #   Validate, connect, sync Nexus
│   │   │   ├── settings.py         #   App settings + PC specs
│   │   │   ├── onboarding.py       #   Onboarding status + completion
│   │   │   ├── updates.py          #   Version diff + update check
│   │   │   ├── chat.py             #   SSE chat endpoint
│   │   │   └── vector.py           #   Reindex, search, stats
│   │   ├── scanner/service.py      # File discovery + grouping
│   │   ├── matching/
│   │   │   ├── grouper.py          # TF-IDF + DBSCAN file grouping
│   │   │   └── correlator.py       # Local↔Nexus name matching
│   │   ├── nexus/client.py         # Async Nexus Mods API client
│   │   ├── services/nexus_sync.py  # Sync tracked/endorsed mods
│   │   ├── vector/
│   │   │   ├── store.py            # ChromaDB client + collections
│   │   │   ├── indexer.py          # Index mods/nexus/correlations
│   │   │   └── search.py           # Semantic search queries
│   │   └── agents/orchestrator.py  # LangChain agent + tools
│   └── tests/                      # 127 pytest tests
│       ├── conftest.py             # In-memory SQLite fixtures
│       ├── matching/               # Grouper + correlator tests
│       ├── scanner/                # File scanner tests
│       ├── nexus/                  # Nexus API client tests (respx)
│       ├── services/               # Nexus sync tests
│       ├── routers/                # All 8 router test files
│       ├── vector/                 # Indexer + search tests
│       └── agents/                 # Orchestrator tool tests
├── frontend/
│   ├── src/
│   │   ├── components/             # UI components
│   │   │   ├── chat/               #   ChatPanel
│   │   │   ├── layout/             #   Sidebar, Titlebar
│   │   │   ├── mods/               #   ModsTable
│   │   │   └── ui/                 #   Badge, Button, Card, Input
│   │   ├── pages/                  # Route pages
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── GamesPage.tsx
│   │   │   ├── GameDetailPage.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   ├── UpdatesPage.tsx
│   │   │   └── OnboardingPage.tsx
│   │   ├── hooks/                  # React Query hooks
│   │   ├── stores/                 # Zustand stores
│   │   ├── lib/                    # API client, SSE parser, utils
│   │   ├── router/                 # Routes + OnboardingGuard
│   │   ├── layouts/                # Root + Onboarding layouts
│   │   └── types/                  # TypeScript API types
│   └── src-tauri/                  # Tauri v2 Rust shell
├── CLAUDE.md                       # AI assistant project context
├── CLA.md                          # Contributor License Agreement
└── .github/workflows/              # CI, CLA, Claude review
```

## Prerequisites

- [Python 3.12+](https://www.python.org/)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Node.js 22+](https://nodejs.org/)
- [Rust](https://rustup.rs/) (for Tauri desktop builds)
- [Nexus Mods API key](https://www.nexusmods.com/users/myaccount?tab=api+access) (free personal key)
- [OpenAI API key](https://platform.openai.com/api-keys) (for chat assistant)

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

The API will be available at `http://localhost:8425`. The SQLite database is auto-created at `backend/data/cnmm.db` on first startup.

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

1. **OpenAI API key** — Powers the chat assistant
2. **Nexus Mods API key** — Enables mod tracking and metadata sync
3. **Game setup** — Configure your game install path (Cyberpunk 2077 auto-detects 7 default mod directories)
4. **Initial scan** — Discovers and groups your installed mods

API keys are stored in the local SQLite database and masked in the settings UI.

## Development

### Backend commands

```bash
cd backend
uv run uvicorn chat_nexus_mod_manager.main:app --reload --port 8425   # Dev server
uv run ruff check src/ tests/                                         # Lint
uv run ruff format src/ tests/                                        # Format
uv run pytest tests/ -v                                               # Tests (127 tests)
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

### API Endpoints

All endpoints are prefixed with `/api/v1/`.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/games/` | List all configured games |
| `POST` | `/games/` | Add a new game |
| `GET` | `/games/{name}` | Get game details |
| `DELETE` | `/games/{name}` | Remove a game |
| `GET` | `/games/{name}/mods/` | List mod groups with files |
| `POST` | `/games/{name}/mods/scan` | Scan and group mod files |
| `POST` | `/games/{name}/mods/correlate` | Match mods to Nexus downloads |
| `GET` | `/games/{name}/updates/` | List available updates |
| `POST` | `/games/{name}/updates/check` | Refresh update data from Nexus |
| `POST` | `/nexus/validate` | Validate a Nexus API key |
| `POST` | `/nexus/connect` | Validate and store a Nexus key |
| `POST` | `/nexus/sync-history/{name}` | Sync tracked/endorsed mods |
| `GET` | `/nexus/downloads/{name}` | List synced Nexus downloads |
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

### Testing

The backend has a comprehensive test suite with 127 tests covering all modules:

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
│  └──────────────────┬────────────────────────┘   │
└─────────────────────┼────────────────────────────┘
                      │ HTTP / SSE
┌─────────────────────┼────────────────────────────┐
│              FastAPI Backend                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ Routers  │ │ Scanner  │ │   Chat Agent     │  │
│  │ (8 APIs) │ │ Grouper  │ │ (LangChain+OAI)  │  │
│  │          │ │Correlator│ │   7 tools        │  │
│  └────┬─────┘ └────┬─────┘ └───────┬──────────┘  │
│       │             │               │             │
│  ┌────┴─────────────┴───────────────┴──────────┐  │
│  │              SQLite (SQLModel)              │  │
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

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Make your changes following the code style in [CLAUDE.md](CLAUDE.md)
4. Run tests (`cd backend && uv run pytest -v`)
5. Commit using [conventional commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, etc.)
6. Open a Pull Request

All contributors must agree to the [Contributor License Agreement](CLA.md) before their PR can be merged.

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

See [CLA.md](CLA.md) for contributor licensing terms.
