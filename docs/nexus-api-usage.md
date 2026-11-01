# Nexus Mods API Usage

Which endpoints we consume, split by protocol.

## Sources

- **REST v1 (Swagger):** <https://app.swaggerhub.com/apis-docs/NexusMods/nexus-mods_public_api_params_in_form_data/1.0>
- **GraphQL v2 (Explorer):** <https://graphql.nexusmods.com/#introduction>

## Authentication

All requests carry an `APIKEY` header.

## Rate limits

Nexus limits user requests to 20,000 per 24-hour period. Once that limit is reached, the limit is
500 requests per hour ([help article 105](https://help.nexusmods.com/article/105-i-have-reached-a-daily-or-hourly-limit-api-requests-have-been-consumed-rate-limit-exceeded-what-does-this-mean)).
The per-second limit of 30/sec (nginx) is not in that article and is not re-verified here.

Headers read: `X-RL-Hourly-Remaining`, `X-RL-Daily-Remaining`, `X-RL-Hourly-Reset`.

## Request identification

`NexusClient` (REST v1) and `NexusGraphQLClient` (GraphQL v2) send the three headers that the code
comment in `backend/src/rippermod_manager/app_info.py` says Nexus asks every third-party app to send.
The usage rules are in the [API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy).

| Header | Value |
|--------|-------|
| `Application-Name` | `RipperMod Manager` |
| `Application-Version` | the app version |
| `User-Agent` | `RipperModManager/<app version>` |

The app version is read from the installed `rippermod-manager` package metadata (`backend/pyproject.toml`).
`scripts/bump-version.sh` writes that version before the release build. It is `dev` when the metadata
is missing. Each client logs `Nexus client identifies as RipperMod Manager <version>` once per process.
The CDN client in `stream_download()` sends neither these headers nor `APIKEY`.

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
| `batch_mods()` | `query BatchMods` | _(inline aliases)_ | Fetch up to 10 mods per query using GraphQL aliases (includes requirements) |
| `batch_mods_by_domain()` | `query BatchModsByDomain` | `ids` (`[{gameDomain, modId}]`) | Two-phase: (1) `legacyModsByDomain` chunks of 25 for mod fields, (2) `batch_mods()` for requirements. Falls back to `batch_mods()` on phase 1 error |

### Search

| Method | Operation | Variables | Description |
|--------|-----------|-----------|-------------|
| `search_mods()` | `query SearchMods` | `filter` (`gameId` as a string, `name` with op `WILDCARD`), `count`, `sort` | Text search mods by name. Optional `sort` is `[{<field>: {direction: DESC}}]` with field `endorsements`, `downloads` or `updatedAt` |
| `search_file_contents()` | `query SearchFileContents` | `filter` (`gameId` as an integer, `filePathWildcard` with op `WILDCARD`, `fileExtensionExact` with op `EQUALS`), `count` | Search inside mod archives by file path or extension |

`WILDCARD` already matches a substring. Send the plain text (`foo`), not `*foo*`: `search_mods` and
`search_file_contents` no longer send literal asterisks.

### Collections

| Method | Operation | Variables | Description |
|--------|-----------|-----------|-------------|
| `search_collections()` | `query SearchCollections` | `filter` (gameDomain), `count` | Search collections for a game via `collectionsV2` |
| `get_collection_revision()` | `query GetCollectionRevision` | `slug`, `revision`, `domainName` | Fetch a collection revision with its full mod list |
| `get_collection_latest_revision()` | `query GetCollectionLatestRevision` | `slug`, `revision`, `domainName` | Update check. Returns only `collection.latestPublishedRevision.revisionNumber` (an `int`, or `None`) |

`domainName` is the game domain string (for example `cyberpunk2077`). `gameDomain` is a filter key in
`search_collections()` and a key of `ids` in `batch_mods_by_domain()`, not a query variable.

### GraphQL field fragments

```graphql
# _MOD_FIELDS -- reused by get_mod, batch_mods, batch_file_hashes
uid, modId, name, summary, description, version, author,
createdAt, updatedAt, endorsements, downloads, pictureUrl,
category, modCategory { name }, status

# _MOD_REQUIREMENT_FIELDS -- reused by get_mod, batch_mods
modRequirements {
  nexusRequirements(offset: 0, count: 50) {
    nodes { id, modId, modName, url, notes, externalRequirement, gameId }
  }
  modsRequiringThisMod(offset: 0, count: 50) {
    nodes { id, modId, modName, url, notes, externalRequirement, gameId }
  }
  dlcRequirements { gameExpansion { id, name }, notes }
}

# _MOD_FILE_FIELDS -- reused by get_mod_files
fileId, name, version, categoryId, category, size, sizeInBytes, date, description
```

`ModFile.size` is kilobytes. The app reads `sizeInBytes` instead: a `BigInt` that GraphQL encodes as a
string, coerced to bytes by `parse_size_in_bytes` in `backend/src/rippermod_manager/services/nexus_helpers.py`.
The collection revision asks `totalSize`, not `fileSize`.

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
