# Dual Release Strategy

RipperMod Manager ships two editions from a single repository: a Full edition for the community and a Nexus edition that satisfies the Nexus Mods file submission guidelines.

## Editions

| Edition | Branch | Tags | App Auto-Updater | Distribution |
|---------|--------|------|------------------|--------------|
| **Full** | `main` | `vX.Y.Z` | Yes (Tauri updater + Gist endpoint) | GitHub Releases, community |
| **Nexus** | `nexus-compliant` | `nexus-vX.Y.Z` | **No** | Nexus Mods page (manual draft → published promotion) |

Each branch has its own independent SemVer track. `main` and `nexus-compliant` are two distinct products that diverge in features, so they version independently — when `main` bumps to `v3.4.0`, `nexus-compliant` does not automatically follow. Each commit on either branch determines its own next version via conventional-commits (`feat:` → minor, `fix:` → patch, `feat!:` → major).

**History note**: tags prior to `nexus-v2.0.0` used the prerelease format `v2.0.0-nexus.N`. semantic-release pins the base on prerelease branches, so the X.Y.Z never moved off `2.0.0` despite real feature/breaking changes on the branch. Migrated to independent SemVer with the `nexus-v` prefix to fix that. Old `v2.0.0-nexus.*` tags remain valid for their respective releases.

### Full Edition (`main`)

The complete application with all features:

- Mod detail modal with description, changelogs, file list
- Trending mods grid and dashboard community activity
- Card images, summaries, endorsement/download counts
- In-app Nexus search, BBCode rendering, file contents preview
- Direct file selection for multi-file mods
- **LLM features**: chat assistant (LangChain + OpenAI), AI-powered scan matching (OpenAI `web_search`), Tavily web-search fallback, ChromaDB vector store
- **In-app auto-updater** via Tauri updater plugin checking a Gist endpoint on startup

### Nexus Edition (`nexus-compliant`)

A Nexus-policy-compliant build:

- Slim modal with thumbnail, name, requirements, and "View on Nexus Mods" CTA
- No trending page, no community activity section, no in-app Nexus search
- Cards retain thumbnails, summaries, and endorsement counts (standard mod manager metadata)
- All card clicks and file selection redirect to nexusmods.com
- Core management features unchanged (install, conflicts, profiles, mod updates checker)
- **No LLM features** — no chat assistant, no OpenAI calls, no Tavily, no ChromaDB
- **No in-app auto-updater** — users download a new installer manually from the Nexus mod page

## NEVER merge between branches

`main` and `nexus-compliant` are **kept intentionally divergent**. The Nexus edition removes user-facing features that exist in the full edition, so `git merge` would either reintroduce removed features (when merging `main → nexus-compliant`) or push compliance-required deletions onto the full edition (when merging `nexus-compliant → main`).

The admin bypass on the branch protection rules exists only for the `semantic-release` and `cla` workflows. It is not for human or agent use.

### How to propagate a fix between editions

Use `git cherry-pick` to bring an individual commit from one branch to the other. Skip cherry-picks that touch files that diverge between editions (see below); recreate those changes manually if needed.

```bash
# Find the commit on main you want in the Nexus edition
git log main --oneline

# Cherry-pick it onto nexus-compliant
git checkout nexus-compliant
git cherry-pick <sha>
# Resolve any conflicts conservatively — drop hunks that touch removed files
git push
```

### Files that diverge between branches

Touching any of these on `main` requires a manual mirror commit on `nexus-compliant` (not a cherry-pick):

| File / Area | Divergence |
|-------------|------------|
| `frontend/src/components/mods/ModDetailModal.tsx` | Full 3-tab modal vs slim actions panel |
| `frontend/src/components/mods/NexusModCard.tsx` | Image/summary/stats vs compact card |
| `frontend/src/components/mods/NexusAccountGrid.tsx` | Opens modal vs opens Nexus URL |
| `frontend/src/components/mods/NexusMatchedGrid.tsx` | Opens modal vs opens Nexus URL |
| `frontend/src/pages/GameDetailPage.tsx` | Has trending tab + AI search toggle vs neither |
| `frontend/src/pages/DashboardPage.tsx` | Has community activity vs removed |
| `frontend/src/pages/SettingsPage.tsx` | Has OpenAI/Tavily/AI/update sections vs none |
| `frontend/src/pages/OnboardingPage.tsx` | 4 steps (Welcome / AI / Nexus / Game) vs 3 steps |
| `frontend/src/hooks/queries.ts` | `useModDetail` / `useTrendingMods` / `useHasOpenaiKey` vs none |
| `frontend/src/hooks/mutations.ts` | `useSaveSettings` etc. vs slimmed |
| `frontend/src/types/api.ts` | Full types vs slimmed types |
| `frontend/src/layouts/RootLayout.tsx` | Renders `ChatPanel` + `UpdateBanner` vs neither |
| `frontend/src/components/layout/Sidebar.tsx` | Has chat button + update badge vs neither |
| `frontend/src/stores/ui-store.ts` | Has `chatPanelOpen` vs none |
| `frontend/src/stores/onboarding-store.ts` | Has `openaiKey` vs none |
| `frontend/src-tauri/Cargo.toml` | Has `tauri-plugin-updater` / `tauri-plugin-process` vs neither |
| `frontend/src-tauri/src/lib.rs` | Registers updater / process plugins vs neither |
| `frontend/src-tauri/tauri.conf.json` | Has `plugins.updater` + `createUpdaterArtifacts` vs neither |
| `frontend/src-tauri/capabilities/default.json` | Has `updater:default` + `process:allow-restart` vs neither |
| `backend/src/rippermod_manager/routers/nexus.py` | Full endpoints (search, mod detail) vs summary-only |
| `backend/src/rippermod_manager/routers/__init__.py` | Registers `chat_router` + `vector_router` vs neither |
| `backend/src/rippermod_manager/routers/onboarding.py` | 4-step flow vs 3-step |
| `backend/src/rippermod_manager/schemas/nexus.py` | Full schemas vs reduced |
| `backend/src/rippermod_manager/schemas/mod.py` | Has `ScanStreamRequest` + `WebSearchResult` vs neither |
| `backend/src/rippermod_manager/config.py` | Has `openai_api_key`, `openai_model`, `tavily_api_key`, `chroma_path` vs none |
| `backend/src/rippermod_manager/services/keyring_service.py` | `SECRET_KEYS` includes openai/tavily vs nexus only |
| `backend/pyproject.toml` | Includes langchain/openai/chromadb/tavily vs none |
| `backend/rmm-backend.spec` | Bundles chromadb/onnxruntime/sse-starlette vs none |
| `backend/.env.example` | Has `RMM_OPENAI_API_KEY` / `RMM_OPENAI_MODEL` vs none |
| `.github/workflows/semantic-release.yml` | Generates `latest.json`, updates Gist, signs artifacts vs none |
| `.github/workflows/ci.yml` | Has `HAS_SIGNING_KEY` env + signed/unsigned tauri builds vs one unconditional build |

### Files that exist only on `main`

These were deleted in the Nexus edition and should not be reintroduced via cherry-pick:

- `backend/src/rippermod_manager/agents/` (LangChain orchestrator)
- `backend/src/rippermod_manager/vector/` (ChromaDB store/indexer/search)
- `backend/src/rippermod_manager/routers/chat.py` and `routers/vector.py`
- `backend/src/rippermod_manager/routers/trending.py`
- `backend/src/rippermod_manager/services/ai_search_matcher.py` and `services/web_search_matcher.py`
- `backend/src/rippermod_manager/services/trending_service.py`
- `backend/src/rippermod_manager/models/chat.py` and `schemas/chat.py`
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/components/layout/UpdateBanner.tsx`
- `frontend/src/components/mods/TrendingGrid.tsx`
- `frontend/src/hooks/use-app-updater.ts`
- `frontend/src/stores/updater-store.ts` and `stores/chat-store.ts`
- `frontend/src/lib/bbcode.ts`

## Release Workflow

### Full Edition Release (automatic)

Releases are fully automated via semantic-release on every push to `main`:

1. Open a PR to `main` with a conventional commit title
2. CI runs (backend lint/test, frontend lint/build, Tauri build)
3. claude[bot] reviews the PR
4. Squash merge to `main`
5. semantic-release analyzes the commit and creates a `vX.Y.Z` tag + GitHub Release
6. The build job compiles the Tauri installer, signs it for the updater, uploads `.exe`, `.sig`, `latest.json` to the release, and updates `stable.json` in the updater Gist

### Nexus Edition Release (build automatic, Nexus upload gated by promotion)

Builds trigger automatically when `nexus-compliant` receives new commits, but the Nexus Mods upload requires the maintainer to manually promote the GitHub Release from draft to published — that publish event fires the upload workflow:

1. Cherry-pick commits onto `nexus-compliant` (or merge a PR opened against `nexus-compliant`)
2. semantic-release creates a `nexus-vX.Y.Z` tag + **draft** GitHub Release (`draftRelease: true` is set on the `nexus-compliant` branch in `.releaserc.js`)
3. The build job compiles the Nexus-compliant installer and uploads the `.exe` to the draft release as an asset
4. **Maintainer review:** check the draft release on GitHub. When ready, click **Publish release**
5. Publishing fires `.github/workflows/upload-nexus.yml` (`on: release: { types: [published] }`). It downloads the `.exe`, wraps it in a `.zip` per Nexus help article 117 (bare `.exe` files are auto-quarantined), and uploads it to the Nexus mod page via the `Nexus-Mods/upload-action`
6. Fallback: the same workflow can be re-run manually via `workflow_dispatch` with a `tag` input (Actions → "Upload to Nexus Mods" → Run workflow)
7. **No `latest.json` is generated, no Gist file is updated, no `.sig` is created.** The Tauri updater plugin is not bundled at all on this edition.

## Versioning

Both branches use [semantic-release](https://github.com/semantic-release/semantic-release) with conventional commits and **independent SemVer tracks** — they version separately because they are two distinct products that share lineage but diverge in features:

- `fix:` = PATCH, `feat:` = MINOR, `feat!:` / `fix!:` = MAJOR, `chore:` / `docs:` / `refactor:` = no release
- `main` produces `vX.Y.Z` tags (e.g. `v3.3.0`, `v3.4.0`)
- `nexus-compliant` produces `nexus-vX.Y.Z` tags (e.g. `nexus-v2.0.0`, `nexus-v2.1.0`)

The distinct tag prefixes prevent collision and let each edition evolve at its own cadence.

### `.releaserc` per branch

Each branch carries its own `.releaserc` because they release independently:

- `main` → `.releaserc.json` with `tagFormat: "v${version}"`, `branches: ["main"]`
- `nexus-compliant` → `.releaserc.js` with `tagFormat: "nexus-v${version}"`, `branches: ["nexus-compliant"]`, and `draftRelease: true` on the GitHub plugin so Nexus uploads stay gated behind manual promotion.

### Historical: prerelease-based versioning

Up to `v2.0.0-nexus.14` the Nexus branch was configured as a semantic-release prerelease branch (`{ channel: "nexus", prerelease: "nexus" }`). semantic-release prerelease branches pin the X.Y.Z base on the first release of the cycle, so the base stayed at `2.0.0` indefinitely while only the `.N` counter bumped — losing the SemVer signal of whether a release was a patch, minor, or major change. The migration to `nexus-vX.Y.Z` restored that signal. Old `v2.0.0-nexus.*` tags remain on the repository for historical traceability.

### `.github/workflows/semantic-release.yml`

The workflow triggers on both branches with per-branch concurrency:

```yaml
on:
  push:
    branches: [main, nexus-compliant]

concurrency:
  group: release-${{ github.ref_name }}
  cancel-in-progress: false
```

This allows releases on both branches to run independently without blocking each other.

## Auto-Updater (Full edition only)

The Full edition checks a JSON endpoint for updates, hosted in a [GitHub Gist](https://gist.github.com/Y4rd13/94a555b2a282fca409c1eb0e0b828eb6):

| Edition | Gist File | Tauri Endpoint |
|---------|-----------|---------------|
| Full | `stable.json` | `https://gist.githubusercontent.com/Y4rd13/.../raw/stable.json` |
| Nexus | _(no updater bundled)_ | _(none)_ |

### How it works

1. The release workflow on `main` builds the Tauri installer and generates `latest.json`
2. After uploading release assets, a final step writes `stable.json` in the Gist
3. The Full-edition `tauri.conf.json` points to the `stable.json` URL
4. The Tauri updater plugin checks this endpoint on launch and prompts the user when a new version is available

### Why a Gist instead of `/releases/latest/`

GitHub's `/releases/latest/download/latest.json` always points to the **most recent release globally**, regardless of channel. The Gist provides stable, channel-specific URLs that the workflow updates independently.

### Authentication

The Gist update step uses a classic PAT (`GIST_TOKEN` repository secret) with `gist` scope. Fine-grained tokens have a [known bug](https://github.com/cli/cli/issues/7803) with Gist operations and should not be used.

## Nexus API Policy Compliance

See [nexus-compliance.md](nexus-compliance.md) for the full list of compliance removals and their rationale.

### Policy sources

- [API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy)
- [Terms of Service](https://help.nexusmods.com/article/18-terms-of-service)
- [File Submission Guidelines](https://help.nexusmods.com/article/28-file-submission-guidelines)

## Publishing to Nexus Mods

When submitting or updating the Nexus Mods page:

1. Build from the `nexus-compliant` branch (or use the corresponding `nexus-vX.Y.Z` GitHub Release)
2. The Nexus edition does **not** replicate mod page content (descriptions, changelogs, file lists, trending, search), and does **not** auto-update or contact any LLM
3. All discovery actions redirect users to nexusmods.com
4. Endorse/track mutations generate engagement for Nexus
5. Downloads for free users go through the NXM protocol (user visits Nexus to download)
6. The `upload-nexus` workflow uploads each `nexus-vX.Y.Z` installer (zip-wrapped per help article 117) to the Nexus file group only after the maintainer manually publishes the corresponding draft GitHub Release. Re-runnable via `workflow_dispatch` with a `tag` input.
