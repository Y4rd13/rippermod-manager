# Nexus Mods API Compliance

RipperMod Manager (Nexus Edition) is designed to comply with all Nexus Mods policies. This document details what was changed, what was kept, and how each decision aligns with the official policies.

## What was removed

The following features replicate Nexus mod page content and have been removed from the Nexus Edition:

- **Full mod descriptions** (BBCode rendered), changelogs, and file lists are no longer displayed in-app
- **The trending/recently updated mods page** has been removed entirely
- **In-app Nexus search** has been removed from the user-facing interface
- **The file contents preview proxy** has been removed
- **The community activity dashboard section** has been removed

## How browsing now redirects to Nexus

Every discovery interaction sends users directly to nexusmods.com:

- **Clicking any mod card** opens the mod page directly on nexusmods.com
- **File selection** for multi-file mods redirects to the Nexus files tab
- A prominent **"View on Nexus Mods" button** is the primary action in the mod management modal
- All **context menu "View" actions** open nexusmods.com in the system browser

## What the app still shows

Standard mod manager metadata — the same data [Vortex](https://www.nexusmods.com/about/vortex/) and other approved mod managers display:

- Mod thumbnails, author name, version, and category on cards
- A 1-2 line summary snippet and endorsement count
- Mod requirements/dependencies for install management
- Endorse and track buttons (which generate engagement for Nexus)

## What the app focuses on

The Nexus Edition is a **mod manager**, not a mod browser:

- Local mod installation, conflict detection, load order management, and profiles
- All downloads for free users go through the NXM protocol (users visit Nexus to download)
- The scan & correlate pipeline works internally to map local files to Nexus IDs without displaying any page content

## How we comply with Nexus policies

### API Acceptable Use Policy

> Source: [API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy)

- The app does not "fetch data en-masse with the intent to rehost" — no mod page content (descriptions, changelogs, file lists) is stored or displayed to users
- The metadata we display (thumbnails, summaries, endorsement counts) is the same standard metadata that Vortex and other approved mod managers show, and does not replace the need to visit nexusmods.com
- Every discovery interaction redirects users to nexusmods.com, increasing traffic rather than reducing it
- Endorse and track actions are prominently available, generating direct engagement for Nexus
- The NXM download protocol ensures free users always visit nexusmods.com to initiate downloads
- The app does not send blank or impersonating request metadata

### Terms of Service

> Source: [Terms of Service](https://help.nexusmods.com/article/18-terms-of-service)

- API keys are never stored server-side — they remain on the user's local machine via OS keychain
- All connections are authenticated through the official Nexus SSO flow
- Rate limits are respected with retry logic (3 attempts, exponential backoff) and we track `X-RL-Hourly-Remaining` / `X-RL-Daily-Remaining` headers

### File Submission Guidelines

> Source: [File Submission Guidelines](https://help.nexusmods.com/article/28-file-submission-guidelines)

- We do not redistribute or rehost any Nexus-hosted files or content
- All mod downloads are fetched directly from Nexus CDN via the official API endpoints
