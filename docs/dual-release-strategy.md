# Dual Release Strategy

RipperMod Manager ships two editions from a single repository to comply with Nexus Mods API policies while preserving full functionality for community builds.

![Branch & Release Strategy](assets/dual-release-strategy.svg)

## Editions

| Edition | Branch | Tags | Distribution |
|---------|--------|------|-------------|
| **Full** | `main` | `vX.Y.Z` | GitHub Releases, community |
| **Nexus** | `nexus-compliant` | `vX.Y.Z-nexus.N` | Nexus Mods page |

### Full Edition (`main`)

The complete application with all features enabled:

- Mod detail modal with description, changelogs, file list
- Trending mods grid and dashboard community activity
- Card images, summaries, endorsement/download counts
- In-app Nexus search, BBCode rendering, file contents preview
- Direct file selection for multi-file mods

### Nexus Edition (`nexus-compliant`)

A Nexus-policy-compliant build that redirects all discovery to nexusmods.com:

- Slim modal with thumbnail, name, requirements, and "View on Nexus Mods" CTA (no description, changelogs, or file list)
- No trending page, no community activity section, no in-app Nexus search
- Cards retain thumbnails, summaries, and endorsement counts (standard mod manager metadata)
- All card clicks and file selection redirect to nexusmods.com
- Core management features unchanged (install, conflicts, profiles, updates)

## Release Workflow

![Release Workflow](assets/release-workflow.svg)

### Full Edition Release (automatic)

Releases are fully automated via semantic-release on every push to `main`:

1. Create a PR to `main` with a conventional commit title
2. CI runs (backend lint/test, frontend lint/build, Tauri build)
3. claude[bot] reviews the PR
4. Squash merge to `main`
5. semantic-release analyzes the commit, creates a `vX.Y.Z` tag + GitHub Release
6. The build job compiles the Tauri installer and uploads it to the release

### Nexus Edition Release (sync + automatic)

Releases trigger automatically when `nexus-compliant` receives new commits:

1. After a main release, sync the changes:
   ```bash
   git checkout nexus-compliant
   git fetch origin
   git merge origin/main
   ```
2. Resolve any conflicts (typically only in the ~10 divergent files)
3. Push to `nexus-compliant`
4. semantic-release creates a `vX.Y.Z-nexus.N` tag + GitHub Release
5. The build job compiles the Nexus-compliant installer

## Sync Procedure

### When to sync

Sync `nexus-compliant` after each meaningful release on `main` or batch of features. Not every commit needs immediate sync.

### How to sync

```bash
# Switch to the nexus-compliant branch
git checkout nexus-compliant

# Fetch latest from remote
git fetch origin

# Merge main into nexus-compliant
git merge origin/main

# If conflicts occur, resolve them:
#   - For deleted files (TrendingGrid, bbcode.ts, trending router/service):
#     keep them deleted (accept "ours")
#   - For modified files (ModDetailModal, NexusModCard, grids, schemas):
#     keep the nexus-compliant version (slim modal, no browsing props)
#   - For unrelated files (new features, bug fixes):
#     accept the incoming changes from main

# Push to trigger the nexus release
git push
```

### Conflict-prone files

These files diverge between branches and may conflict during sync:

| File | Divergence |
|------|-----------|
| `frontend/src/components/mods/ModDetailModal.tsx` | Full 3-tab modal vs slim actions panel |
| `frontend/src/components/mods/NexusModCard.tsx` | Image/summary/stats vs compact card |
| `frontend/src/components/mods/NexusAccountGrid.tsx` | Opens modal vs opens Nexus URL |
| `frontend/src/components/mods/NexusMatchedGrid.tsx` | Opens modal vs opens Nexus URL |
| `frontend/src/pages/GameDetailPage.tsx` | Has trending tab vs no trending tab |
| `frontend/src/pages/DashboardPage.tsx` | Has community activity vs removed |
| `frontend/src/hooks/queries.ts` | useModDetail/useTrendingMods vs useModSummary |
| `frontend/src/types/api.ts` | Full types vs slimmed types |
| `backend/src/rippermod_manager/routers/nexus.py` | Full endpoints vs summary-only |
| `backend/src/rippermod_manager/schemas/nexus.py` | Full schemas vs reduced schemas |
| `frontend/src-tauri/tauri.conf.json` | Updater endpoint: `stable.json` vs `nexus.json` |

Files that will **never conflict** (most of the codebase):
- Scan/correlation pipeline, matching services
- Install/uninstall, FOMOD, archive management
- Conflict detection, load order, profiles
- Download management, SSO, NXM handler
- Vector store, chat agent
- All Tauri/Rust code

## Versioning

Both branches use [semantic-release](https://github.com/semantic-release/semantic-release) with conventional commits:

- `fix:` = PATCH, `feat:` = MINOR, `feat!:` / `fix!:` = MAJOR
- `main` produces stable versions: `v1.22.0`, `v1.23.0`, `v2.0.0`
- `nexus-compliant` produces prerelease versions: `v2.0.0-nexus.1`, `v2.0.0-nexus.2`

The `nexus` channel ensures versions never collide between branches.

## CI Configuration

### `.releaserc.json`

```json
{
  "branches": [
    "main",
    { "name": "nexus-compliant", "channel": "nexus", "prerelease": "nexus" }
  ]
}
```

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

## Auto-Updater Channels

Each edition checks a separate JSON endpoint for updates, hosted in a shared [GitHub Gist](https://gist.github.com/Y4rd13/94a555b2a282fca409c1eb0e0b828eb6):

| Edition | Gist File | Tauri Endpoint |
|---------|-----------|---------------|
| Full | `stable.json` | `https://gist.githubusercontent.com/Y4rd13/.../raw/stable.json` |
| Nexus | `nexus.json` | `https://gist.githubusercontent.com/Y4rd13/.../raw/nexus.json` |

### How it works

1. The release workflow builds the Tauri installer and generates `latest.json`
2. After uploading release assets, a final step updates the correct Gist file:
   - `main` → writes `stable.json`
   - `nexus-compliant` → writes `nexus.json`
3. Each edition's `tauri.conf.json` points to its own Gist URL
4. The Tauri updater plugin checks this endpoint on launch and prompts the user if a new version is available

### Why a Gist instead of `/releases/latest/`

GitHub's `/releases/latest/download/latest.json` always points to the **most recent release globally**, regardless of channel. If a nexus release is published after a stable release, both editions would receive the nexus update (or vice versa). The Gist provides stable, channel-specific URLs that each workflow updates independently.

### Authentication

The Gist update step uses a classic PAT (`GIST_TOKEN` repository secret) with `gist` scope. Fine-grained tokens have a [known bug](https://github.com/cli/cli/issues/7803) with Gist operations and should not be used.

## Nexus API Policy Compliance

The Nexus edition is designed to comply with the [Nexus Mods API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy) and the [Terms of Service](https://help.nexusmods.com/article/18-terms-of-service).

### Policy requirement

The API Acceptable Use Policy prohibits:

> "Fetching data en-masse with the intent to **rehost** this information on your own service (i.e. scraping)"

Additionally, any usage that is "detrimental to the modding community or Nexus Mods" is prohibited at their sole discretion.

### What the Nexus edition removes

These features replicate Nexus mod pages and reduce the need for users to visit nexusmods.com:

| Removed Feature | Reason |
|----------------|--------|
| Full mod description (BBCode rendered) | Replicates the mod page "Description" tab |
| Changelogs (full version history) | Replicates the mod page "Changelogs" tab |
| File list with descriptions and preview | Replicates the mod page "Files" tab |
| Trending mods page | Replicates nexusmods.com trending/latest pages |
| In-app Nexus search (frontend) | Replicates nexusmods.com search functionality |
| File contents preview proxy | Proxies Nexus file metadata service |
| Community activity dashboard section | Aggregates trending data as a browsing feature |

### What the Nexus edition keeps

These features are standard mod manager metadata that [Vortex](https://www.nexusmods.com/about/vortex/) (the official Nexus mod manager) also displays, and do not constitute content rehosting:

| Kept Feature | Justification |
|-------------|---------------|
| Mod thumbnail images on cards | Metadata preview — Vortex shows the same |
| Summary text (1-2 lines, truncated) | Search snippet — equivalent to what Google shows |
| Endorsement and download counts | Basic statistics — Vortex shows these |
| Author name, version, category | Standard mod management metadata |
| Mod requirements (dependencies) | Functional for dependency management |
| Endorse/track actions | **Generates engagement for Nexus** |
| NXM download handler | **Drives download traffic through Nexus** |
| Slim modal with "View on Nexus Mods" CTA | **Redirects users to nexusmods.com** |

### How browsing is redirected to Nexus

Every user interaction that would previously show Nexus content in-app now redirects to nexusmods.com:

- **Clicking a mod card** → opens the mod page on nexusmods.com
- **File selection** (mods with multiple files) → opens the Nexus files tab
- **"View on Nexus Mods" button** → prominent CTA in the mod actions modal
- **Context menu "View on Nexus"** → opens the mod page in the system browser

### Policy sources

- [API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy)
- [Terms of Service](https://help.nexusmods.com/article/18-terms-of-service)
- [File Submission Guidelines](https://help.nexusmods.com/article/28-file-submission-guidelines)

## Publishing to Nexus Mods

When submitting or updating the Nexus Mods page:

1. Build from the `nexus-compliant` branch (or use the `-nexus.N` GitHub Release)
2. The Nexus edition does **not** replicate mod page content (descriptions, changelogs, file lists, trending, search)
3. All discovery actions redirect users to nexusmods.com
4. Endorse/track mutations generate engagement for Nexus
5. Downloads for free users go through the NXM protocol (user visits Nexus to download)
