# Nexus Mods API Usage

Which endpoints we consume, split by protocol.

## Sources

- **REST v1 (Swagger):** <https://app.swaggerhub.com/apis-docs/NexusMods/nexus-mods_public_api_params_in_form_data/1.0>
- **GraphQL v2 (Explorer):** <https://graphql.nexusmods.com/#introduction>

## Authentication

All requests carry an `APIKEY` header. Rate limits: 2 500/day, 100/hour, 30/sec.
Headers read: `X-RL-Hourly-Remaining`, `X-RL-Daily-Remaining`, `X-RL-Hourly-Reset`.

## Base URLs

| Protocol   | URL                                       |
|------------|-------------------------------------------|
| REST v1    | `https://api.nexusmods.com/v1/...`        |
| GraphQL v2 | `https://api.nexusmods.com/v2/graphql`    |

---

## REST v1 Endpoints

All methods live in `backend/src/rippermod_manager/nexus/client.py` (`NexusClient`).

### User

| Method | HTTP | Path | Body | Description |
|--------|------|------|------|-------------|
| `validate_key()` | GET | `/v1/users/validate.json` | - | Validate API key, get username and premium status |
| `get_tracked_mods()` | GET | `/v1/user/tracked_mods.json` | - | List mods the user is tracking |
| `get_endorsements()` | GET | `/v1/user/endorsements.json` | - | List mods the user has endorsed |

### Games

| Method | HTTP | Path | Body | Description |
|--------|------|------|------|-------------|
| `get_game_info()` | GET | `/v1/games/{domain}.json` | - | Game metadata (includes category list) |

### Mods

| Method | HTTP | Path | Body | Description |
|--------|------|------|------|-------------|
| `get_mod_info()` | GET | `/v1/games/{domain}/mods/{id}.json` | - | Single mod metadata |
| `get_changelogs()` | GET | `/v1/games/{domain}/mods/{id}/changelogs.json` | - | Version changelogs |
| `get_mod_files()` | GET | `/v1/games/{domain}/mods/{id}/files.json` | - | File list (optional `?category=` filter) |
| `get_updated_mods()` | GET | `/v1/games/{domain}/mods/updated.json?period={p}` | - | Recently updated mods (period: `1d`, `1w`, `1m`) |
| `get_latest_updated()` | GET | `/v1/games/{domain}/mods/latest_updated.json` | - | Latest updated mods |
| `get_trending()` | GET | `/v1/games/{domain}/mods/trending.json` | - | Trending mods |

### Downloads

| Method | HTTP | Path | Body | Description |
|--------|------|------|------|-------------|
| `get_download_links()` | GET | `/v1/games/{domain}/mods/{id}/files/{fid}/download_link.json` | - | CDN URLs (premium-only unless `?key=&expires=` provided) |
| `stream_download()` | GET | _(CDN URL)_ | - | Stream file to disk (separate httpx client) |

### Mutations (write operations)

| Method | HTTP | Path | Body | Description |
|--------|------|------|------|-------------|
| `endorse_mod()` | POST | `/v1/games/{domain}/mods/{id}/endorse.json` | `{"Version": "..."}` | Endorse a mod |
| `abstain_mod()` | POST | `/v1/games/{domain}/mods/{id}/abstain.json` | `{"Version": "..."}` | Withdraw endorsement |
| `track_mod()` | POST | `/v1/user/tracked_mods.json` | `{"domain_name": "...", "mod_id": N}` | Add mod to tracking list |
| `untrack_mod()` | DELETE | `/v1/user/tracked_mods.json` | `{"domain_name": "...", "mod_id": N}` | Remove mod from tracking list |

---

## GraphQL v2 Queries

All methods live in `backend/src/rippermod_manager/nexus/graphql_client.py` (`NexusGraphQLClient`).
Every call is `POST https://api.nexusmods.com/v2/graphql`.

> The v2 API is explicitly marked **"work in progress"** -- the schema can change without notice.
> We only use it for **read queries** (batch lookups and search) that have no REST v1 equivalent.
> All **mutations** (endorse, track, etc.) use REST v1.

### Single mod

| Method | Operation | Variables | Description |
|--------|-----------|-----------|-------------|
| `get_mod()` | `query GetMod` | `modId`, `gameId` | Fetch mod with full fields + requirements |
| `get_mod_files()` | `query GetModFiles` | `modId`, `gameId` | Fetch file list for a mod |

### Batch operations

| Method | Operation | Variables | Description |
|--------|-----------|-----------|-------------|
| `batch_file_hashes()` | `query BatchFileHashes` | `md5s` (up to 500) | MD5 lookup -- returns file info with nested mod data |
| `batch_mods()` | `query BatchMods` | _(inline aliases)_ | Fetch up to 50 mods per query using GraphQL aliases |
| `batch_mods_by_domain()` | `query BatchModsByDomain` | `ids` (`[{gameDomain, modId}]`) | Fetch mods using `legacyModsByDomain` (chunks of 50, falls back to `batch_mods()` on error) |

### Search

| Method | Operation | Variables | Description |
|--------|-----------|-----------|-------------|
| `search_mods()` | `query SearchMods` | `filter` (gameId, name wildcard), `count`, `sort` | Text search mods by name (optional sort by endorsements/downloads/updatedAt) |
| `search_file_contents()` | `query SearchFileContents` | `filter` (gameId, filePathWildcard, fileExtensionExact), `count` | Search inside mod archives by file path or extension |

### Collections

| Method | Operation | Variables | Description |
|--------|-----------|-----------|-------------|
| `search_collections()` | `query SearchCollections` | `filter` (gameDomain), `count` | Search collections for a game via `collectionsV2` |
| `get_collection_revision()` | `query GetCollectionRevision` | `slug`, `revision`, `gameDomain` | Fetch a collection revision with its full mod list |

### GraphQL field fragments

```graphql
# _MOD_FIELDS -- reused by get_mod, batch_mods, batch_file_hashes
uid, modId, name, summary, description, version, author,
createdAt, updatedAt, endorsements, downloads, pictureUrl,
category, modCategory { name }, status

# _MOD_REQUIREMENT_FIELDS -- reused by get_mod, batch_mods
modRequirements {
  nexusRequirements {
    nodes { id, modId, modName, url, notes, externalRequirement, gameId }
  }
}

# _MOD_FILE_FIELDS -- reused by get_mod_files
fileId, name, version, categoryId, category, size, date, description
```

---

## Why REST v1 for mutations?

REST v1 mutation endpoints are **stable and well-documented** (Swagger spec above).
The GraphQL v2 mutation schema is **work in progress** and can break without notice.
We originally migrated mutations to GraphQL in PR #120 but reverted in PR #122 to
reduce exposure to breaking schema changes. Read queries remain on GraphQL v2 because
they provide batch operations and text search not available in REST v1.

## Game ID mapping

GraphQL queries require a numeric `gameId` instead of a domain string:

| Domain | Game ID |
|--------|---------|
| `cyberpunk2077` | `3333` |

Defined in `GAME_ID_MAP` in `graphql_client.py`.
