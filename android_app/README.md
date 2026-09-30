# LoopGain Telecom AI (Android demo)

A native Android app shell around the existing `platform_app` Streamlit shell.
It does not reimplement any ML - it gives the already-running web platform a
real phone-app dashboard: a home screen of module cards, each opening its own
screen, instead of one flat webpage. This is the fast path to a mobile
presence; see "Talking points" below for the honest framing of what's native
vs. wrapped.

## Structure

- **DashboardActivity** (launcher) - a native grid of cards (Overview,
  Network KPIs, Congestion & Steering, Site Planning/GIS, Churn & Retention,
  AI Assistants). Fully native UI, no WebView here.
- **DetailActivity** - opened when a card is tapped. Loads that module's page
  from `platform_app` in a WebView, with pull-to-refresh and a "Auto-refresh" switch that auto-reloads every 20s, so KPIs/statuses can be
  checked from a phone without a laptop.
- Server address is set once via the gear icon (top-right of the dashboard),
  not per-screen - saved on device, no rebuild needed to switch between the
  emulator and a real phone.

## 1. Start the backend on your laptop

From the `LoopGain-Telecom-AI` folder:

```
python run_platform.py
```

This starts the GIS API (8001), KPI API (8002) and the Streamlit shell (8510)
unconditionally - churn/assistants are skipped unless their API keys are set.
Confirm `http://127.0.0.1:8510` opens in your browser before moving to
Android.

## 2. Open the Android project

Open the `android_app` folder (this folder) directly in Android Studio as an
existing project. If Android Studio reports the Gradle wrapper jar is
missing, accept its offer to regenerate it - the wrapper version is already
pinned in `gradle/wrapper/gradle-wrapper.properties`.

## 3. Run it

- **Emulator** (default, no changes needed): the app defaults to
  `http://10.0.2.2:8510` - `10.0.2.2` is the emulator's alias for your
  laptop's `localhost`. Just click Run in Android Studio.
- **Physical phone**: connect the phone to the same WiFi as your laptop, find
  your laptop's LAN IP (`ipconfig` on Windows, look for IPv4 address), tap the
  gear icon on the dashboard, and enter e.g. `http://192.168.1.23:8510`. It's
  saved automatically for next launch.

## Talking points for the demo

- The ML models (LightGBM/XGBoost/Random Forest for GIS, similar for KPI
  forecasting) are unchanged - this shows the *same* trained models and the
  *same* dashboards, just delivered through a native phone app shell instead
  of a laptop browser.
- The dashboard/navigation (home screen, cards, back stack, toolbar) is real
  native Android UI - that part is a genuine phone app, not a wrapped
  website.
- Each module screen still renders through the existing Streamlit page inside
  a WebView - so no model or backend work had to be redone to get here.
  "Auto-refresh" auto-refreshes that page, standing in for what a native
  screen's push/poll loop would do.
- Honest next step for a full rebuild: replace each `DetailActivity` page
  with a real native screen calling a small FastAPI layer directly (faster,
  works offline-ish, real push notifications) - this app is the fast,
  low-risk way to prove the mobile concept today.


## Native operations dashboard (September 30 UI update)

The home screen now contains five native summary cards from the same sources as
the web Overview: KPI SLA breaches, critical towers, dated 4G traffic forecasts,
candidate planning sites, and revenue at risk. Tapping a card or attention note
opens the corresponding existing module. All six original navigation cards remain directly below the summaries, including
Overview and AI Assistants; Needs attention follows the navigation grid.
"Ask AI" stays visible below the scrollable content on home and module screens;
it opens the existing Assistants page, and Back returns to the previous screen.
The button is hidden inside Assistants to avoid stacking copies of that screen.
The server address appears only in Settings.

### Enable the summary feed

The launcher starts it, in its own uv environment built from `platform_app/requirements.txt`:

```powershell
python run_platform.py
```

The launcher now starts `platform_app/mobile_summary.py` on port **8511**, alongside
the existing web shell on **8510**. To start only the new feed from the repo root, with
the platform requirements installed (`python -m pip install -r platform_app/requirements.txt`):

```powershell
python -m uvicorn mobile_summary:app --app-dir platform_app --host 0.0.0.0 --port 8511
```

Android requests `GET /dashboard/summary` from the configured platform computer
on port 8511. Server settings has an optional **Summary API address** override for
different ports or proxy prefixes; enter the base address, without the endpoint.
The phone must be able to reach that port on the computer.

The summary service uses `PLATFORM_KPI_API_URL`, `PLATFORM_GIS_API_URL`,
`PLATFORM_CHURN_API_URL`, and `PREPAID_CHURN_COPILOT_KEY` on the server, following
the shell's environment / `assistants/.env` lookup. It exposes aggregates and
review notes only. The Android app never receives or stores service API keys.
Missing services, missing authorization and malformed results show unavailable
values, not zeroes. "Checked" is fetch time; source dates remain on the cards.
The traffic card says **4G traffic forecast**, rather than implying an old export
predicts tomorrow. Congestion is labeled a backtest; GIS results require review.

Refresh fetches the summaries again; returning home refreshes after 30 seconds.
The module WebView keeps the original page routes, back behavior and pull-to-refresh.
Its loading overlay has a 30-second timeout. Connection errors and main-frame HTTP
errors show a native retry screen; a failed image does not hide the whole page.
Auto-refresh runs every 20 seconds on a successfully loaded, foreground page and
pauses during loading/errors. "Page loaded" does not claim all embedded services
are healthy. Streamlit's own in-page/WebSocket errors retain their web UI.

### Validation

- Java 17: `gradlew.bat :app:assembleDebug :app:lintDebug`.
- Summary service: from `platform_app`, run `python -m unittest test_mobile_summary -v`
  (test environment also needs `httpx`). Eight tests cover valid data, partial and
  full outages, missing/nonfinite values, source dates and credential redaction.
- Emulator checks should cover summary loading/unavailable/data states, card links,
  attention notes, Ask AI and Back, WebView retry/recovery, refresh controls, dark
  mode, larger text, and rotation. UI fixtures are test data, not project results.
