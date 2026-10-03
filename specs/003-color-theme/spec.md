# Color theme

Status: Implemented

## Scope and requirements

- **003-R1**: Login and all dashboard states expose a labeled, keyboard-accessible selector for System, Light, and Dark. Shared surfaces, inputs, dialogs, and text adapt to the selected palette.
- **003-R2**: Persist explicit preference in browser local storage. With no valid preference, follow the operating-system color scheme, including live changes. Apply the palette before first paint.
- **003-R3**: Unavailable storage must not break rendering or in-session selection. Theme changes do not affect campaign data or authorization.

## Acceptance scenarios

1. Given a new browser, when its OS uses light/dark mode, then the initial palette matches; changing the OS updates System mode.
2. Given an explicit selection, when reloading or navigating between login and dashboard, then the selection remains; OS changes do not override it.
3. Given invalid or inaccessible storage, when opening the app, then it renders using the system palette and the selector still works.
4. Given desktop or mobile layout, when switching themes, then login, workspace selection, campaign cards, and creation dialogs use readable themed surfaces without horizontal overflow.

## Plan and assumptions

Use CSS semantic color variables, a shared client selector, and an inline pre-paint initializer in the root layout. System is the default; preference is browser-local, not an account setting. No dependencies, API, backend, or database changes. Keep decorative brand colors where appropriate. No unresolved decisions.

## Tasks

- [x] Implement shared theme initialization and selector (003-R1/R2/R3).
- [x] Replace fixed surface/text colors with palette tokens (003-R1).
- [x] Run focused browser checks, frontend tests, lint, and build; record evidence (003-R1/R2/R3).

## Evidence

Validated 2026-09-29. Commands below run from `00_frontend/` unless noted.

| Requirements | Check | Result |
| --- | --- | --- |
| 003-R1/R2/R3 | `bun run test:browser` | 34 passed across desktop Chromium and mobile emulation. Includes palettes, system updates, explicit selection/reload, invalid and blocked storage, keyboard focus, navigation, pre-hydration initialization, and existing authorization/lifecycle flows. |
| 003-R3 | `bun run test` | 42 passed. Existing dashboard tests now supply jsdom's missing matchMedia API. |
| 003-R1/R2/R3 | `bun run lint` | Passed. |
| 003-R1/R2/R3 | `bun run build` | Passed, including TypeScript. Existing outdated Browserslist data warning remains. |
| 003-R1 | Visual review | Inspected desktop light and mobile dark campaign-dialog screenshots generated under `00_frontend/test-results/`; themed surfaces and layout are readable. |
| All | `git diff --check` (repository root) | Passed. |

An initial browser assertion assumed platform-independent native-select arrow behavior; changed to verify keyboard focus/tab navigation and explicit option selection separately. Final run passes. Browser coverage uses deterministic HTTP fixtures; no live Firebase/model services. Safari/Firefox and exhaustive contrast auditing were not run.
