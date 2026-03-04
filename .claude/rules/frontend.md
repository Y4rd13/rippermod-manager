---
paths:
  - "frontend/src/**"
---

# Frontend rules

## React patterns
- Use React Query (`@tanstack/react-query`) for all server state — never store API data in Zustand
- Zustand stores are for client-only state (UI, streaming, toasts)
- Mutations go in `hooks/mutations/` — queries in `hooks/queries/`
- Virtualize long lists with `@tanstack/react-virtual` (VirtualTable, VirtualCardGrid)

## Styling
- Tailwind CSS v4 — utility classes only, no CSS modules or styled-components
- Use `cn()` from `lib/utils` for conditional class merging
- Theme tokens: `text-primary`, `text-muted`, `bg-surface-0/1/2`, `border-border`, etc.
- Custom titlebar — window has `decorations: false` in Tauri config

## TypeScript
- `@/*` maps to `./src/*` — always use this alias for imports
- Handle `undefined` from indexed access — strict mode enforces this
- API types live in `types/api.ts`

## Tauri
- Use `@tauri-apps/api` for window, events, filesystem access
- Deep link handler registered for `nxm://` protocol
- CSP restricts `connect-src` to `localhost:8425` and Nexus CDN — don't add new origins without updating CSP
