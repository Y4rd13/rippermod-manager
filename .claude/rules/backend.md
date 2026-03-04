---
paths:
  - "backend/**"
---

# Backend rules

## FastAPI patterns
- Route handlers MUST be `async def` — sync functions block the event loop
- Use `Depends(get_session)` for DB sessions — never create sessions manually in handlers
- Return Pydantic/SQLModel schemas from endpoints, not raw dicts
- B008 is ignored in routers (FastAPI `Depends()` in default args is intentional)

## Nexus API calls
- Always use `async with NexusClient(api_key) as client:` — never create bare instances
- Catch `NexusRateLimitError` BEFORE `httpx.HTTPError` in exception chains
- Check `client.hourly_remaining` before batch operations — stop at < 5 remaining
- REST v1 for mutations, GraphQL v2 for batch reads — never mix them up

## Database
- All DDL migrations go in `database.py` — never modify schema outside that file
- Use `session.exec(select(...))` pattern — avoid raw SQL unless it's a PRAGMA or migration
- Commit is the caller's responsibility unless explicitly documented otherwise
- `set_setting()` handles keyring + SQLite transparently — prefer it over direct `AppSetting` writes

## Error handling
- `except httpx.HTTPError` for API calls
- `except OSError` for file I/O
- `except Exception` ONLY for: shutdown/cleanup, ChromaDB ops, keyring ops, top-level scan handler
- NEVER use bare `except:` (no exception type)

## Adding dependencies
- Add to `backend/pyproject.toml` under `[project.dependencies]`
- Optional deps go in `[project.optional-dependencies]` (search, dev, test, build)
- Run `uv sync` to update `uv.lock` — always commit the lockfile
