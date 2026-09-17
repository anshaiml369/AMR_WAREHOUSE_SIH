# AMR Simulator Baseline Checklist

Date: 2026-09-17
Application: `http://127.0.0.1:8004/`
WebSocket: `ws://127.0.0.1:8765`

## Verified Before Extension

- [x] Backend server is running.
- [x] Dashboard page loads in Chromium through Playwright.
- [x] Warehouse map renders 324 cells for the 18x18 backend warehouse.
- [x] Five backend robots render in the fleet panel.
- [x] Three-robot fleet creation produces exactly three backend/UI robots.
- [x] Robot positions are received through WebSocket state.
- [x] Simulation tick advances while running.
- [x] Pause stops the displayed simulation tick.
- [x] Start/resume advances the displayed simulation tick again.
- [x] Reset restores the default five-robot fleet.
- [x] Task creation produces four backend tasks in the control probe.
- [x] Dynamic obstacle insertion appears in backend state.
- [x] Speed `0.1x` reaches the backend state.
- [x] Speed `2x` reaches the backend state.
- [x] Existing metrics and event stream render without browser errors.
- [x] Existing Python regression suite passes: `7 passed`.

## Evidence Commands

```text
node tests/e2e_dashboard_recovery.js
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q
```

## Known Baseline Gaps

- Package lifecycle is present in backend state but only minimally represented in the current UI.
- Task allocation is distance-based and does not yet expose a structured allocation reason.
- Scenario builder, robot/task inspection views, richer P2P inspection, and full deadlock scenario controls are not yet exposed in the UI.
- Persistence/database and deployment packaging are not yet present.
- ML/DL production inference is intentionally not part of this baseline.
- The browser baseline currently verifies three robots and the default five-robot reset; ten-robot and long-run browser workflows remain to be added.

Any later phase must rerun this checklist and preserve every checked item.
