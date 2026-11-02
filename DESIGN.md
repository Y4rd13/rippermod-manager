---
name: RipperMod Manager
description: Dark, dense desktop console for adopting, matching and deploying a Cyberpunk 2077 mod library.
colors:
  surface-0: "#0a0a0f"
  surface-1: "#12121a"
  surface-2: "#1a1a25"
  surface-3: "#242430"
  border: "#2a2a3a"
  border-bright: "#3a3a4a"
  accent: "#5b5ee8"
  accent-hover: "#4f52dc"
  accent-text: "#818cf8"
  info: "#38bdf8"
  success: "#22c55e"
  warning: "#f59e0b"
  danger: "#ef4444"
  text-primary: "#f1f1f6"
  text-secondary: "#b8bdc9"
  text-muted: "#8b8fa0"
typography:
  display:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1.875rem"
    fontWeight: 700
    lineHeight: 1.2
  headline:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.33
  title:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.56
  body:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.43
  body-dense:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.33
  label:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    letterSpacing: "0.025em"
  micro:
    fontFamily: "IBM Plex Sans, Segoe UI, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 500
  mono:
    fontFamily: "IBM Plex Mono, Consolas, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
  full: "9999px"
spacing:
  xxs: "2px"
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  card: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-2}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  button-ghost-hover:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-primary}"
  button-danger:
    backgroundColor: "rgb(239 68 68 / 0.1)"
    textColor: "{colors.danger}"
    rounded: "{rounded.lg}"
    padding: "8px 16px"
  button-sm:
    typography: "{typography.body-dense}"
    padding: "4px 10px"
  button-lg:
    padding: "10px 24px"
  card:
    backgroundColor: "{colors.surface-1}"
    rounded: "{rounded.xl}"
    padding: "{spacing.card}"
  input:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.text-primary}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
  input-search:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.lg}"
    padding: "6px 32px"
  badge-neutral:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-success:
    backgroundColor: "rgb(34 197 94 / 0.1)"
    textColor: "{colors.success}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-warning:
    backgroundColor: "rgb(245 158 11 / 0.1)"
    textColor: "{colors.warning}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  badge-danger:
    backgroundColor: "rgb(239 68 68 / 0.1)"
    textColor: "{colors.danger}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.text-muted}"
    typography: "{typography.body-dense}"
    rounded: "{rounded.full}"
    padding: "4px 12px"
  chip-active:
    backgroundColor: "{colors.accent}"
    textColor: "#ffffff"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    rounded: "{rounded.lg}"
    padding: "8px 12px"
  nav-item-active:
    backgroundColor: "rgb(91 94 232 / 0.1)"
    textColor: "{colors.accent-text}"
  tab:
    textColor: "{colors.text-muted}"
    typography: "{typography.body}"
    padding: "8px 16px"
  tab-active:
    textColor: "{colors.accent-text}"
  dialog:
    backgroundColor: "{colors.surface-1}"
    rounded: "{rounded.xl}"
    padding: "{spacing.xl}"
  toast:
    backgroundColor: "{colors.surface-1}"
    rounded: "{rounded.lg}"
    padding: "12px 16px"
    width: "320px"
  switch:
    backgroundColor: "{colors.surface-3}"
    rounded: "{rounded.full}"
    height: "20px"
    width: "36px"
  titlebar:
    backgroundColor: "{colors.surface-0}"
    height: "36px"
---

<!-- Scan mode, 2026-10-29; updated 2026-11-02 for the UI pass (branch feat/pasada-ui): IBM Plex,
AA tokens, the 11px floor, the game status strip, sticky tabs, Dialog and lib/labels.ts. Values come from
shipped code (frontend/src/index.css @theme, components/ui, components/mods, pages). Usage counts
are from the 2026-10-29 scan unless a section says otherwise. -->

# Design System: RipperMod Manager

## Overview

**Creative North Star: "The Ripperdoc's Console"**

RipperMod is a dark, cool-tinted workstation: four near-black surfaces with a faint blue-violet cast (hue about 285 in OKLCH), one indigo accent, and three status colors. It is built for long maintenance sessions over libraries of hundreds of mods, so the interface is dense by default: 404 of the 458 font-size utilities in the codebase are `text-xs` or `text-sm`, rows are virtualized, and most controls sit at 32 to 36px tall.

The mood is precise, calm and utilitarian: it reads as a professional tool, not a game skin. The visual language carries no neon, glitch, scanline or chromatic-aberration effects anywhere in the shipped CSS, and PRODUCT.md keeps Cyberpunk flavor out of in-app copy. That absence is a deliberate anti-reference (owner decision, 2026-10-29): no Cyberpunk HUD styling in the app. Character comes instead from giving the product's own ideas their own visual forms: diagnostics read like instrument readouts (Health, Frameworks, deploy drift), and provenance (match method and confidence) gets a dedicated form such as a confidence meter and a method glyph, never the same chip as a category tag. This follows from the Operate mode (precision and restraint over expression), from PRODUCT.md's "plain language in the app", and from user trust concerns on the Nexus page, where a gimmicky skin would read as less trustworthy.

Depth comes from stepping the surface ladder and drawing 1px borders, not from shadows. Color is reserved for meaning: indigo marks the active thing (current nav item, selected tab, primary action, checked control), and green, amber and red mark state.

**Key Characteristics:**
- Dark only. No light theme exists in the code.
- Four-step tonal surface ladder plus two border steps, all with the same cool hue.
- One accent (indigo) for selection and primary action; status colors only for state.
- Dense type in IBM Plex Sans: 12px and 14px carry the interface, 11px is the floor, 24px bold is the page-title ceiling.
- Tinted status treatment: 10% fill, 20 to 40% border, full-strength text.
- Flat at rest; shadows only on floating layers (toasts, menus, bulk bar, modals) and the primary button's accent glow.

## Colors

A cool, near-monochrome dark palette with a single indigo signal and conventional traffic-light status colors.

### Primary
- **Indigo Signal** (`accent`, `#5b5ee8`): the only brand hue as a fill or line. Primary buttons, active tab underline, active filter chip, checked checkbox, radio and switch, focus rings (`ring-accent`), the 10% tint behind the active nav item. White on Indigo Signal measures 4.99:1.
- **Indigo Press** (`accent-hover`, `#4f52dc`): hover fill of the primary button, one step darker; white on it measures 5.88:1. Never used as a text color.
- **Indigo Text** (`accent-text`, `#818cf8`): indigo used as text or icon color: links and inline actions, the active nav item and tab label, accent icons. 5.14:1 on Lifted up to 6.62:1 on Void, and 5.7:1 on the active nav tint. Every `text-accent` became `text-accent-text`; a guard test (`src/test/style-floor.test.ts`) fails on a bare `text-accent`.
- **Sky** (`info`, `#38bdf8`): informational accents only, such as the "Tracked" source badge (`bg-info/15 text-info`).

### Neutral
- **Void** (`surface-0`): app background, `main` content area, titlebar, and the inner background of the selected view-mode toggle. 48 uses.
- **Panel** (`surface-1`): sidebar, cards, dialogs, toasts, context menus, inputs, download footer. 59 uses.
- **Raised** (`surface-2`): hover fill for rows, nav items and ghost buttons; search input and sort select backgrounds; image placeholders. 112 uses, the most common surface.
- **Lifted** (`surface-3`): secondary button, neutral badge, unchecked switch track. 25 uses.
- **Hairline** (`border`): the default 1px border on every card, input, dialog, table divider and the sidebar edge. 168 uses.
- **Hairline Bright** (`border-bright`): checkbox and radio outlines, scrollbar thumb hover. 1 utility use plus index.css.
- **Bone** (`text-primary`): headings, values, primary labels. 179 uses, 17.5:1 on Void.
- **Ash** (`text-secondary`, `#b8bdc9`): body copy, form labels, inactive nav items. 9.9:1 on Panel, 8.15:1 on Lifted.
- **Smoke** (`text-muted`): metadata, placeholders, inactive tabs, empty-state copy. 311 uses, the most used text color; 6.2:1 on Void and 5.4:1 on Raised.

### Status
- **Online Green** (`success`): installed, deployed, linked, healthy, up to date.
- **Amber Alert** (`warning`): updates available, matched-but-unconfirmed, drift, medium-confidence match. Solid amber always takes black text.
- **Flatline Red** (`danger`): conflicts, critical health findings, errors, destructive actions, low-confidence match, titlebar close hover.

### Named Rules
**The One Signal Rule.** Indigo is the only hue that means "selected" or "act here". Status colors never stand in for selection, and indigo never stands in for status, except the info toast.

**The Text Contrast Rule.** Every text color passes 4.5:1 on the surface it sits on. Indigo as text is always `accent-text`; text on a solid amber fill is black (9.78:1); text on a solid green fill is Void (`text-surface-0`, 8.67:1), never white (2.28:1). Muted rows are shown with Smoke text and a label, never with opacity.

**The Tinted Status Rule.** Status is shown as a tint, not a fill: background at 10 to 15% (`bg-success/10`), border at 20 to 40%, text at full strength. A solid status fill (`prominent` badge) is the exception for counts that must be read at a glance.

## Typography

**Display and Body Font:** IBM Plex Sans (`--font-sans: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif`), one variable font covering weights 100 to 700.
**Mono Font:** IBM Plex Mono (`--font-mono: "IBM Plex Mono", Consolas, ui-monospace, monospace`), weights 400 and 500, for file paths, archive names, hashes and versions (`font-mono`).

Both ship with the app from `frontend/public/fonts/ibm-plex/`: the unmodified Latin1 split woff2 files from IBM's npm packages (`@ibm/plex-sans-variable@0.2.0`, `@ibm/plex-mono@2.5.0`) and IBM's `OFL.txt` beside them (SIL OFL 1.1, Reserved Font Name "Plex"). `index.css` declares the `@font-face` rules with `font-display: swap`, served from the app's own origin, which the Tauri CSP allows. No external font origin, no Fontsource and no hand subsetting: those would be blocked by the CSP or count as a modified font.

**Character:** a neutral grotesque used at small sizes with medium and semibold weights for hierarchy; nothing expressive.

### Hierarchy
- **Display** (700, 30px / 1.875rem): onboarding welcome heading only (`OnboardingPage`).
- **Headline** (700, 24px / 1.5rem): one `h1` per page (Dashboard, Games, game name, Updates, Activity, Settings) and dashboard stat values.
- **Title** (600, 18px / 1.125rem): card titles, dialog titles, empty-state titles.
- **Body** (400 to 500, 14px / 0.875rem): buttons (md), inputs, nav items, tabs, dialog messages, context menu items.
- **Body dense** (400 to 500, 12px / 0.75rem): the workhorse, 251 uses: table cells, card metadata, badges, chips, small buttons, helper and error text.
- **Label** (600, 11px, uppercase, `tracking-wide`): section eyebrows in Health and Frameworks widgets ("Needs attention", "Up to date").
- **Micro** (500, 11px): sidebar "Manager" wordmark line, source badges, compact tile metadata, FOMOD type tags, status-strip labels.

Weight distribution: `font-medium` 125, `font-semibold` 55, `font-bold` 23. Numbers in counts and progress use `tabular-nums`.

### Named Rules
**The Small Type Rule.** 14px is the default and 12px is the dense default; anything above 18px is a page title or a stat value, never body.

**Text floor: 11px.** No text in the UI is smaller than 11px. Every smaller arbitrary size is gone from `frontend/src`, and the guard test in `src/test/style-floor.test.ts` fails on any `text-[Npx]` below 11.

## Layout

A fixed desktop shell (window minimum 900x600, default 1280x800):

- **Titlebar:** custom, 36px tall, Void background, bottom hairline, draggable; window controls are 40x36 hit areas on the right, close turns solid red on hover.
- **Sidebar:** Panel background with a right hairline, 208px wide, collapsing to 56px (icons only) with a 200ms width transition. Five nav items, logo and wordmark on top, an optional accent-tinted update pill at the bottom.
- **Main:** Void background, 24px padding on all sides, scrolls independently; gains 64px bottom padding when the download queue footer (40px collapsed bar, fixed to the bottom) is present.
- **Game detail:** a title row (a "Games ›" breadcrumb link, the game `h1`, then the version badge and install path in 12px below it, with Play and Scan & Correlate on the right), the game status strip, the one-line adopt banner, then a sticky underline tab strip and the tab content. Blocks are spaced 16px (`space-y-4`). The tab strip pins to the top of `main` while the page scrolls (`sticky -top-6`, which offsets main's 24px padding). Measured 2026-11-02 with the adopt banner visible: the tab strip starts at 241px CSS at 1280x800 and 311px at 900x600 (limits 260 and 320).

Spacing follows Tailwind's 4px grid. The observed rhythm: 8px gap between sibling controls (`gap-2`, 134 uses), 4 to 6px inside compact groups, 12px between related blocks, 16px (`mb-4`) under headers, 20px card padding, 24px page and dialog padding. Vertical stacks use `space-y-2` to `space-y-6`.

Responsive behavior is minimal and grid-only: card grids step columns at `sm`, `md`, `lg` and `xl` (for example the Dashboard stat row goes from 2 to 3 to 5 columns at `sm` and `lg`). Long lists and card grids are virtualized (`VirtualTable`, `VirtualCardGrid`). Dialogs center over a 50% black scrim, cap at 85vh and use `max-w-sm` (confirm dialogs) up to `max-w-3xl` (collection preview).

## Elevation & Depth

The system is flat and tonal. Depth is conveyed by moving up the surface ladder (Void, Panel, Raised, Lifted) and by 1px Hairline borders; hover states raise an element one surface step instead of adding a shadow. Shadows are reserved for elements that float above the page and for one signature glow.

### Shadow Vocabulary
- **Accent glow** (`box-shadow: 0 1px 3px 0 rgb(91 94 232 / 0.3), 0 1px 2px -1px rgb(91 94 232 / 0.3)`, hover `0 4px 6px -1px rgb(91 94 232 / 0.4), 0 2px 4px -2px rgb(91 94 232 / 0.4)`): primary button only. Prominent badges use the same small glow in their status color.
- **Float** (`box-shadow: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)`): toasts and context menus.
- **Modal** (`box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)`): the two collection dialogs (preview and install progress); the other dialogs ship without a shadow and rely on the scrim.
- **Bulk bar** (`box-shadow: 0 25px 50px -12px rgb(0 0 0 / 0.25)`): the floating bulk-action bar.
- **Focus ring** (`box-shadow: 0 0 0 2px #0a0a0f, 0 0 0 4px #5b5ee8`): checkbox and radio focus; Tailwind `ring-2 ring-accent` elsewhere.

### Named Rules
**The Tonal Stack Rule.** A surface that sits on another surface is one step lighter and carries a Hairline border. Reach for a shadow only when the element floats over content (toast, menu, bulk bar, dialog).

## Shapes

Softly rounded rectangles, with radius growing with the size of the container:

- **4px** (`rounded`, 91 uses): inline tags, `kbd` keys, skeleton blocks, small icon buttons, checkboxes.
- **6px** (`rounded-md`, 34 uses plus split halves): compact controls such as the view-mode toggle buttons, sidebar collapse button and the hand-rolled install/update split buttons.
- **8px** (`rounded-lg`, 78 uses): the control radius: buttons, inputs, selects, nav items, toasts, context menus.
- **12px** (`rounded-xl`, 38 uses): containers: cards, dialogs, mod cards, the bulk-action bar.
- **Pill** (`rounded-full`, 31 uses): badges, filter chips, switch track and thumb, status dots (6px).

Borders are always 1px Hairline at rest; selection is shown with a 2px accent bottom border on tabs and an accent-tinted border (30 to 40%) on hovered or flagged cards. Mod images are clipped to the card (`overflow-hidden`), 160px tall on full cards and 16:9 on compact tiles.

## Components

### Buttons
Quiet and compact; the primary is the only one with color and glow.
- **Shape:** gently rounded (8px), inline-flex with an 8px icon gap, medium weight.
- **Primary:** Indigo Signal fill, white text, accent glow; hover lifts to Indigo Lift with a larger glow.
- **Secondary:** Lifted fill, Bone text, transparent border; hover drops to Raised and shows a 40% accent border.
- **Ghost:** transparent, Ash text; hover fills Raised and turns Bone.
- **Danger:** 10% red tint with red text; hover 20% tint. Used for every confirm in `ConfirmDialog`, including warnings.
- **Sizes:** sm 4px 10px at 12px, md 8px 16px at 14px, lg 10px 24px at 16px.
- **Focus / Disabled:** 2px accent ring on `focus-visible`; disabled at 50% opacity with a not-allowed cursor. While loading, a 16px spinner appears before the label and the button is disabled.

### Chips (Filter chips)
- **Style:** pills, 4px 12px, 12px medium text, Raised fill with Smoke text; optional count at 70% opacity in tabular numerals.
- **State:** active is solid Indigo Signal with white text; inactive hover steps to Lifted and Ash. Single and multi-select share one look.

### Badges
- **Style:** pills, 2px 8px, 12px medium, 1px border, tinted per the Tinted Status Rule; neutral is Lifted with Ash text.
- **Prominent:** solid status fill at 90% with a small status-colored glow (white text on green and red, black on amber).
- **Confidence badge:** green at 90% and above, amber at 75% and above, red below, with a check, triangle or cross icon and the percentage. It is the visible form of the "make provenance visible" principle.

### Cards / Containers
- **Corner Style:** 12px.
- **Background:** Panel on Void.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px Hairline; clickable cards add a focus ring with a Void offset.
- **Internal Padding:** 20px; card header has 16px bottom margin and an 18px semibold title.

### Mod card (signature)
The Nexus mod card: Panel, 12px radius, image on top (160px, cover-cropped, inline SVG placeholder on error), 16px body with a two-line 14px semibold title, two-line 12px Smoke summary, a metadata row (author, version, endorsements with 12px icons) and a footer separated by a 50% Hairline holding the action button and overflow menu. Hover turns the border 40% indigo; a flagged card (with a badge) carries a 40% amber border at rest. Compact tiles repeat the pattern at 16:9, 8px padding and 11px metadata. Cards and clickable rows join the Tab order and open with Enter or Space.

### Inputs / Fields
- **Style:** Panel fill, 1px Hairline, 8px radius, 8px 12px padding, 14px text, Smoke placeholder; label above in 14px medium Ash with a 6px gap.
- **Focus:** 2px accent ring and the border goes transparent.
- **Error:** red border and a 12px red message below.
- **Search variant:** Raised fill, 6px vertical padding, 14px search icon inset left, clear button right; focus only recolors the border to accent (no ring).
- **Checkbox / Radio:** custom 16px, Raised fill, 1.5px Hairline Bright outline, solid accent when checked with a white check or dot.
- **Switch:** 36x20 pill, Lifted track off, accent on, 14px Bone thumb, 200ms slide.

### Navigation
- **Sidebar items:** 14px, 18px Lucide icons, 8px 12px padding, 8px radius, 12px icon gap. Default Ash; hover Raised fill and Bone; active 10% indigo tint with indigo text and icon. Collapsed mode hides labels.
- **Tabs:** underline tabs, 14px medium, 8px 16px; active has a 2px indigo bottom border and Indigo Text, inactive is Smoke and hovers to Ash. Counts follow the label at 12px and 60% opacity; a 6px amber dot flags conflicts and pending updates, red or amber flags health. The game tabs and the Matched sub-tabs are WAI-ARIA tabs (`hooks/use-roving-tabs.ts`): `role="tablist"`, `role="tab"` with `aria-selected` and `aria-controls`, a `role="tabpanel"`; only the active tab is in the Tab order, the arrow keys move focus (wrapping), Home and End jump to the ends, Enter or Space selects, and the active tab scrolls into view. Overflowing edges show a Void gradient; focus shows a 2px accent ring.

### Game status strip
`components/GameStatusStrip.tsx`, the game page's one-line summary in place of the old seven stat cards. A Panel row with a Hairline border and 12px radius holding seven buttons in a fixed order: Scanned, Managed, Nexus Matched, Updates, Conflicts, Frameworks and Health. Each item is a 32px-tall button with a 13px icon (`shrink-0`), a 13px semibold tabular value and an 11px Smoke label, and jumps to the same tab its card did. Tone colors the value and icon: amber for pending updates and for conflicts, the worst-case green, amber or red for the Frameworks and Health verdicts (`useFrameworksVerdict`, `useHealthVerdict`), whose titles list what needs attention. The row wraps to a second line in narrow windows and never truncates; at 1280x800 it fits in one line. Drift stays in the titlebar, not in the strip.

### Labels
`frontend/src/lib/labels.ts` is the one place that turns backend enum values into words; the UI never prints a raw key.
- **Match method** (`matchMethodLabel`): `filename_id` Filename ID, `exact` Exact name, `substring` Name contains, `fuzzy` Name similarity, `file_content` File contents, `file_list` File list, `endorsed_name` Endorsed (name), `requirement` Requirement of another mod, `collection` Collection, `manual` Set by you, `installed` Installed, `fomod` FOMOD. Used by the match badges and the Matched filter chips.
- **Activity** (`activityLabel`): Installed, Uninstalled, Enabled, Disabled, Deployed, Undeployed, Downloaded, Undid, Adopted.
- **Unknown values** show in Title Case (`web_search_v2` reads Web Search V2) and log one `console.warn` per value; an empty value reads Unknown.

Counts use `plural(n, singular, plural?)` from `lib/format.ts`, so "1 file" and "0 files" read correctly.

### Toasts
320px, Panel, Hairline border, 8px radius, Float shadow, 12px 16px padding, a 2px status-colored strip on the left edge and an 18px status icon. Slides in from the right over 300ms and pauses its timer on hover.

### Dialogs
Every modal renders through `components/ui/Dialog.tsx`, the only component that sets `role="dialog"` and `aria-modal="true"` (a guard test enforces it).
- **Portal and focus:** it renders in a portal on `document.body`. On open, focus moves to the caller's `initialFocusRef`, else the first focusable control, else the panel itself. Tab and Shift+Tab cycle inside. On close, focus returns to the element that opened it.
- **Escape and backdrop:** Escape closes (or runs `onEscape`, e.g. step back in the mod detail) unless the caller passes `closeOnEscape={false}` while an operation runs; a control that handles Escape itself calls `preventDefault` and the dialog stays. Backdrop click closes unless `closeOnBackdrop={false}`. Clicks inside never bubble to the row or card that rendered the dialog.
- **Inert background:** while any dialog is open, every `[data-inert-scope]` element gets `inert`: the sidebar, `<main>` and the titlebar's app actions (drift notice and Redeploy). The window buttons, the drag region and the toasts stay usable.
- **Stacking:** with dialogs stacked, only the top one is active; the ones below are `inert` until it closes, and focus goes back to the control in the lower dialog that opened it.
- **Look:** centered over a 50% black scrim (layer 50 or 60, set by the caller's `backdropClassName`), Panel, 12px radius, 24px padding, title row with a 20px status icon, actions right-aligned (secondary Cancel, then the action). The title element is linked with `aria-labelledby`.

## Do's and Don'ts

### Do:
- **Do** take every color from the `@theme` tokens in `frontend/src/index.css`; the palette is 16 tokens and nothing else.
- **Do** build buttons, inputs, cards and badges from `components/ui` (`Button`, `Input`, `Card`, `Badge`) so radius, focus ring and hover stay consistent.
- **Do** show status with the tinted treatment (10 to 15% fill, 20 to 40% border, full text color) and keep solid status fills for prominent counts.
- **Do** raise hover and nesting by one surface step (Void to Panel to Raised to Lifted) with a Hairline border instead of adding a shadow.
- **Do** keep body text at 14px and dense data at 12px; one 24px bold `h1` per page.
- **Do** give every interactive element a 2px accent `focus-visible` ring (with a Void or Panel offset on filled controls). Clickable rows and cards spread `activationProps` from `lib/activation.ts` (Tab stop, Enter and Space open them); sort headers put a `<button>` inside the `<th>`.
- **Do** open every modal with `Dialog` and confirm every action that deletes or resets configuration with `ConfirmDialog`.
- **Do** virtualize lists that can reach hundreds of rows (`VirtualTable`, `VirtualCardGrid`).

### Don't:
- **Don't** use utility classes for tokens that do not exist. The 2026-11-02 pass defined `--color-info` and replaced `bg-surface-secondary` with `bg-surface-1`; a guard test fails on `bg-surface-secondary`.
- **Don't** hand-roll buttons. Shipped drift: 111 raw `<button>` elements against 132 `<Button>` uses; the install and update split buttons in `components/mods/ModCardAction.tsx` and `components/mods/ArchivesList.tsx` use a 6px radius and `hover:opacity-80` instead of the primary button's 8px radius and Indigo Lift hover.
- **Don't** ship a second input treatment. Shipped drift: 19 raw `<input>` against 5 `<Input>`; `SearchInput` uses a Raised fill and a border-only focus while `Input` uses Panel and a ring.
- **Don't** hard-code colors outside the tokens. Shipped drift: `#1a1a2e` and `#555` in the image placeholder SVG of `NexusModCard.tsx`, `NexusModRow.tsx` and `NexusModTile.tsx` (`#1a1a2e` is an off-palette near-twin of Raised `#1a1a25`); `text-white` (17), `text-black` (6), `border-white/20` (3) and the `bg-black/50` scrim (23) bypass the palette.
- **Don't** add arbitrary type sizes, and never one below the 11px floor. `text-[11px]` is the de facto Micro and Label size (the 18 former sub-11px uses moved to it, and the repeated Health source badge to 12px); promote it to an `@theme` font-size token rather than adding new literals.
- **Don't** reach for arbitrary z-index values. Shipped drift: `z-[60]` (16 uses) is the de facto dialog layer and `focus:z-[100]` the skip link; define named layers instead of repeating literals.
- **Don't** use `text-accent` for text: the fill indigo `#5b5ee8` measures 3.4 to 4.4:1 as text on the surfaces. Use `text-accent-text`.
- **Don't** put white text on solid green (2.28:1) or white on solid amber (2.15:1). Use Void on green and black on amber.
- **Don't** dim a row with `opacity` to mean "inactive": Load Order's unmanaged rows once measured 1.45:1. Use Smoke text and a label ("Unmanaged").
- **Don't** add keyframes without a consumer. `slide-in-right`, `pulse-ring`, `orbit-spin` and `slide-down` in `index.css` have no users.
- **Don't** let Ash and Smoke collapse into one level. Shipped today, `#9ca3af` and `#8b8fa0` are close in lightness and Smoke is used almost three times as often (311 vs 108). Decision (2026-10-29), shipped 2026-11-02: Ash is now `#b8bdc9` (9.16:1 on Raised) while Smoke stays `#8b8fa0`, the darkest value that still passes 4.5:1 on every surface (4.77:1 on Lifted). Darkening Smoke instead (to about `#6b7080`) was rejected: it measures 4.0:1 on Void and fails AA.
