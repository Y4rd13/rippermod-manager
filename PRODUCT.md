# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

(Tauri v2 desktop shell on Windows rendering a React web UI; the design language is web, not native Windows.)

## Users

Any Cyberpunk 2077 modder on Windows PC, from someone installing a first mod to a veteran with a library of 200+ mods. The common situation: mods already sit in the game folder, installed by hand or by other tools, spread across `archive/pc/mod`, `mods`, `r6/scripts`, `red4ext`, `bin` and others, with no record of which Nexus page each came from. The job is to see that library, tie it to Nexus, keep it updated, and launch the game without something breaking. First-run setup matters as much as managing a large library.

## Product Purpose

A desktop mod manager that scans, groups, correlates and manages mods with Nexus Mods integration. Success means the user can answer "what do I have installed, where did it come from, is it current, and will the game launch" without managing files by hand.

## Positioning

RipperMod adopts the library the user already has. It scans the game folder, groups scattered loose files into mods, and links them to their Nexus pages through a multi-tier pipeline (filename IDs, MD5 hash lookup, file content reverse lookup, endorsed/tracked sync, collection matching, requirement propagation, fuzzy matching), then brings them under management in place ("Adopt in Place", `services/adopt_service.py`) without reinstalling. It understands Cyberpunk 2077 mod types natively: REDmod (auto-compiles via `redMod.exe deploy`), TweakXL, redscript annotations, archive load order.

Decided from repository evidence when the owner delegated the choice (2026-10-29). Deploying through a staging folder plus hardlinks is a capability, not the differentiator, because other managers also deploy that way.

## Operating Context

- Runs locally on the user's Windows PC next to Steam/GOG installs of Cyberpunk 2077; the game folder is the source of truth the app reads and writes through hardlinks and REDmod junctions.
- Requires a Nexus Mods account (SSO login); premium status changes whether downloads can start in-app. Nexus API limits (2,500/day, 100/hour) are a hard budget.
- Typical sessions: first-run onboarding (Nexus login, game setup, first scan), then short maintenance passes before playing (updates, conflicts, pre-launch Health check), and occasional large operations (adopt, profile switch, deploy).
- Main surfaces: Dashboard, Games, Game detail tabs (Installed, Archives, Health, Updates, Conflicts, Profiles, Matched, Endorsed, Tracked), Updates, Activity, Settings, Onboarding.
- Two editions: the Nexus edition (`nexus-compliant` branch, distributed on Nexus as mod 27781) has no in-app LLM features and no auto-updater; the Full edition lives on `main`.

## Capabilities and Constraints

- Install from archives with pre-install preview and a FOMOD wizard; enable/disable, uninstall, profiles, update checks, downloads (including NXM links), conflict engine and inbox, load order, diagnostics export, pre-launch Health check.
- Nexus edition constraint: no auto-download or auto-install of app updates; the app only notifies and links to the Nexus page.
- The game directory must stay vanilla apart from managed links; never delete or overwrite files the user did not ask to touch.
- Desktop app on a single SQLite writer: long lists (thousands of files) must stay responsive.
- Window minimum size 900x600, default 1280x800, custom titlebar.

## Brand Commitments

- Name: RipperMod Manager ("a ripperdoc for your mod library").
- Voice: Cyberpunk slang ("choom", "preem", "gonk") is for the Nexus page and marketing articles only. In-app copy is plain, clear and neutral.
- App icon: `frontend/src-tauri/icons/`.

## Evidence on Hand

- Nexus page description and Getting Started article: `docs/nexus-description.bbcode`, `docs/nexus-article-getting-started.bbcode`.
- Real user feedback lives on the Nexus posts and bugs tabs of mod 27781 and in GitHub issues.
- No testimonials, user counts or benchmarks are recorded in the repo; do not invent them.

## Product Principles

1. Respect what is already on disk: read and adopt before asking the user to reinstall anything.
2. Never break the game: every destructive or game-folder operation is previewable, reversible, and refuses while the game is running.
3. Make provenance visible: each mod shows where it came from and how confident the match is.
4. Spend the Nexus API budget carefully: batch reads, cache, and never retry what cannot succeed.
5. Plain language in the app, flavor on the storefront.
