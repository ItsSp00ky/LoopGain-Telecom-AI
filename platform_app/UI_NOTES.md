# Platform UI checks

The shared visual helpers in `_shared.py` keep the six existing pages and their
navigation intact. Metric cards grow with their content. Overview cards use two
columns on phones; forms and tower charts stack. Tables and tabs scroll sideways.

Pages use a visible loading indicator, a retryable service-unavailable state, and
explicit empty results. Retry clears the 30-second HTTP cache. No scoring, forecasts,
API payloads, or Android summary formulas change. The overview labels the traffic
forecast with its actual date, since a saved run may be older than today.

Run from `platform_app` using an environment with its requirements installed:

```powershell
python -m unittest test_smoke test_ui_states -v
```

`test_ui_states` mocks responses only inside Streamlit AppTest. It does not serve
test data or change any service URL. Browser checks should use real services and
an isolated session at desktop and phone widths. Check the overview, GIS map,
network heatmaps, tower charts, and embedded workspaces. Embedded workspaces retain
their own themes and loading behavior; the shell offers an Open full screen link.

Restart the Streamlit shell after changing shared imports if a long-running process
still has the previous module loaded. Backend services do not need a restart.
