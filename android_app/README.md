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
  from `platform_app` in a WebView, with pull-to-refresh and a "Live
  tracking" switch that auto-reloads every 20s, so KPIs/statuses can be
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
  "Live tracking" auto-refreshes that page, standing in for what a native
  screen's push/poll loop would do.
- Honest next step for a full rebuild: replace each `DetailActivity` page
  with a real native screen calling a small FastAPI layer directly (faster,
  works offline-ish, real push notifications) - this app is the fast,
  low-risk way to prove the mobile concept today.
