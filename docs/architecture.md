# Architecture

Detailed project layout and component inventory.
For a high-level overview, see the [README](../README.md#architecture).

## Project Structure

```
rippermod-manager/
├── backend/
│   ├── src/rippermod_manager/
│   │   ├── __main__.py              # Standalone entry point (uvicorn)
│   │   ├── main.py                  # FastAPI app, lifespan, CORS, /health
│   │   ├── config.py                # Pydantic settings (AppData paths)
│   │   ├── database.py              # SQLite engine, session factory
│   │   ├── models/                  # SQLModel tables (12 modules)
│   │   │   ├── game.py              #   Game, GameModPath
│   │   │   ├── mod.py               #   ModGroup, ModFile, ModGroupAlias
│   │   │   ├── nexus.py             #   NexusDownload, NexusModMeta, NexusModFile
│   │   │   ├── correlation.py       #   ModNexusCorrelation
│   │   │   ├── download.py          #   DownloadJob
│   │   │   ├── install.py           #   InstalledMod, InstalledFile
│   │   │   ├── profile.py           #   ModProfile, ProfileEntry
│   │   │   ├── settings.py          #   AppSetting, PCSpecs
│   │   │   ├── chat.py              #   ChatMessage
│   │   │   ├── archive_index.py     #   ArchiveIndex (per-archive file listing)
│   │   │   ├── conflict.py          #   ConflictReport, ConflictEntry
│   │   │   └── load_order.py        #   LoadOrderPreference
│   │   ├── schemas/                 # Pydantic request/response models
│   │   ├── routers/                 # FastAPI routers, prefix /api/v1/ (15 routers)
│   │   │   ├── games.py             #   CRUD games + mod paths
│   │   │   ├── mods.py              #   List, scan, correlate, confirm/reject/reassign
│   │   │   ├── nexus.py             #   Sync, search, endorse/track, SSO, mod detail
│   │   │   ├── install.py           #   Install, uninstall, toggle, preview, archives
│   │   │   ├── fomod.py             #   FOMOD installer wizard
│   │   │   ├── conflicts.py         #   Conflict engine, inbox, graph
│   │   │   ├── load_order.py        #   Load order + preferences
│   │   │   ├── downloads.py         #   Download mods from Nexus
│   │   │   ├── profiles.py          #   Save, load, export/import, compare profiles
│   │   │   ├── trending.py          #   Trending mods from Nexus
│   │   │   ├── updates.py           #   Version diff + update check
│   │   │   ├── settings.py          #   App settings + PC specs
│   │   │   ├── onboarding.py        #   Onboarding status + completion
│   │   │   ├── chat.py              #   SSE chat endpoint
│   │   │   └── vector.py            #   Reindex, search, stats
│   │   ├── scanner/service.py       # File discovery + grouping
│   │   ├── matching/                # Mod name matching (5 modules)
│   │   │   ├── grouper.py           # TF-IDF + DBSCAN file grouping
│   │   │   ├── correlator.py        # Local↔Nexus name matching
│   │   │   ├── filename_parser.py   # Nexus filename ID extraction
│   │   │   ├── normalization.py     # Mod name normalization
│   │   │   └── variant_scorer.py    # Multi-signal variant ranking
│   │   ├── nexus/                   # Nexus Mods API clients
│   │   │   ├── client.py            # REST v1 API client (reads + mutations)
│   │   │   └── graphql_client.py    # GraphQL v2 client (batch + search)
│   │   ├── services/                # Business logic (33 modules)
│   │   │   ├── nexus_sync.py        # Sync tracked/endorsed mods
│   │   │   ├── nexus_helpers.py     # GQL→REST adapters, game categories
│   │   │   ├── download_service.py  # Download orchestration + shutdown
│   │   │   ├── download_dates.py    # Download date heuristics
│   │   │   ├── install_service.py   # Mod install/uninstall/toggle logic
│   │   │   ├── fomod_config_parser.py # FOMOD XML config parser
│   │   │   ├── fomod_install_service.py # FOMOD step-based installation
│   │   │   ├── fomod_parser.py      # FOMOD ModuleConfig XML parser
│   │   │   ├── profile_service.py   # Profile save/load/export/import
│   │   │   ├── update_service.py    # Version comparison + update check
│   │   │   ├── conflict_service.py  # File-level conflict detection
│   │   │   ├── conflict_graph_service.py # Conflict graph builder
│   │   │   ├── conflicts_inbox_service.py # Conflict inbox + resolution
│   │   │   ├── conflicts/           # Multi-layer conflict engine
│   │   │   │   ├── detectors.py     #   REDmod, TweakXL, archive overlap
│   │   │   │   └── engine.py        #   Orchestrates all detectors
│   │   │   ├── load_order.py        # Load order + modlist.txt writer
│   │   │   ├── modlist_service.py   # Ordered mod group view
│   │   │   ├── archive_index_service.py # Archive file indexing
│   │   │   ├── archive_conflict_detector.py # Archive-level conflict detection
│   │   │   ├── archive_layout.py    # Archive structure analysis
│   │   │   ├── archive_matcher.py   # MD5 hash matching (Tier 2)
│   │   │   ├── enrichment.py        # Filename ID extraction (Tier 1)
│   │   │   ├── file_list_matcher.py # File list similarity matching
│   │   │   ├── trending_service.py  # Trending mods fetching
│   │   │   ├── ai_search_matcher.py # AI-powered mod matching
│   │   │   ├── web_search_matcher.py # Web search fallback matching
│   │   │   ├── redscript_analysis.py # Redscript annotation conflict analysis
│   │   │   ├── tweakxl_parser.py    # TweakXL YAML parser
│   │   │   ├── tweakxl_conflict_analyzer.py # TweakXL conflict detection
│   │   │   ├── sso_service.py       # Nexus SSO WebSocket handler
│   │   │   ├── settings_helpers.py  # Settings read/write helpers
│   │   │   ├── game_version.py      # Game version detection
│   │   │   └── progress.py          # SSE progress streaming
│   │   ├── vector/                  # Semantic search
│   │   │   ├── store.py             # ChromaDB client + collections
│   │   │   ├── indexer.py           # Index mods/nexus/correlations
│   │   │   └── search.py            # Semantic search queries
│   │   └── agents/orchestrator.py   # LangChain agent + tools
│   ├── rmm-backend.spec            # PyInstaller spec (--onefile)
│   └── tests/                       # 720+ pytest tests across 45 files
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── BackendGate.tsx       # Waits for backend before rendering
│   │   │   ├── ErrorBoundary.tsx     # Catches crashes, shows fallback UI
│   │   │   ├── chat/                 # ChatPanel
│   │   │   ├── layout/              # Sidebar, Titlebar
│   │   │   ├── mods/                # 25 mod-related components
│   │   │   │                        #   NexusModCard, NexusMatchedGrid,
│   │   │   │                        #   InstalledModsTable, ModsTable,
│   │   │   │                        #   ArchivesList, ArchiveTreeModal,
│   │   │   │                        #   ProfileManager, ProfileCompareDialog,
│   │   │   │                        #   ProfileDiffDialog, FomodWizard,
│   │   │   │                        #   TrendingGrid, NexusAccountGrid,
│   │   │   │                        #   ModDetailModal, ModQuickActions,
│   │   │   │                        #   ModCardAction, InstalledModCardAction,
│   │   │   │                        #   UpdatesTable, UpdateDownloadCell,
│   │   │   │                        #   ConflictDialog, ConflictDetailDrawer,
│   │   │   │                        #   ConflictsInbox, CorrelationActions,
│   │   │   │                        #   PreInstallPreview, ReassignDialog,
│   │   │   │                        #   SourceBadge
│   │   │   └── ui/                  # 24 shared UI primitives
│   │   │                            #   Badge, Button, Card, ConfirmDialog,
│   │   │                            #   ContextMenu, Input, Switch, Toast,
│   │   │                            #   VirtualTable, VirtualCardGrid, ...
│   │   ├── pages/
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── GamesPage.tsx
│   │   │   ├── GameDetailPage.tsx
│   │   │   ├── SettingsPage.tsx
│   │   │   ├── UpdatesPage.tsx
│   │   │   └── OnboardingPage.tsx
│   │   ├── hooks/                   # 12 hooks (React Query, useInstallFlow, useFomodWizard, ...)
│   │   ├── stores/                  # Zustand stores
│   │   ├── lib/                     # API client, SSE parser, utils
│   │   ├── router/                  # Routes + OnboardingGuard
│   │   ├── layouts/                 # Root + Onboarding layouts
│   │   └── types/                   # TypeScript API types
│   └── src-tauri/                   # Tauri v2 Rust shell + sidecar lifecycle
├── scripts/
│   ├── build-backend.ps1            # PyInstaller build + sidecar copy
│   ├── ensure-dev-sidecar.ps1       # Dev placeholder for Tauri compile
│   └── bump-version.sh             # Patch version bump helper
├── docs/
│   ├── nexus-api-usage.md           # Nexus Mods REST v1 + GraphQL v2 endpoint map
│   └── nexus-description.bbcode     # Nexus Mods page description
├── .github/workflows/
│   ├── ci.yml                       # Consolidated CI (backend, frontend, Tauri + gate)
│   ├── semantic-release.yml         # Automated versioning + release pipeline
│   ├── pr-title.yml                 # PR title conventional commits validation
│   ├── claude.yml                   # Claude Code interactive (@claude)
│   ├── claude-pr-review.yml         # Automated PR review
│   └── cla.yml                      # Contributor License Agreement check
├── CLAUDE.md                        # AI assistant project context
├── CLA.md                           # Contributor License Agreement
└── LICENSE                          # GPL-3.0
```
