# LoopGain KPI Monitor (Android demo)

A thin native Android shell around the existing `platform_app` Streamlit shell,
opened straight to the Network KPI page. It does not reimplement any ML - it
just makes the already-running web platform reachable and refreshable from a
phone, for the demo of "tracking from your phone."

Features:
- Loads `platform_app`'s Network KPI page in a WebView.
- Pull-to-refresh, plus a "Live tracking" switch that auto-reloads every 20s.
- Editable server address (saved on device) - no rebuild needed to switch
  between the emulator and a real phone. Hidden by default for a clean demo;
  long-press the status bar (where "Last updated" and "Live tracking" are) to
  show or hide it.

## 1. Start the backend on your laptop

From the `LoopGain-Telecom-AI` folder:

```
python run_platform.py
```

This starts the GIS API (8001), KPI API (8002) and the Streamlit shell (8510)
unconditionally - churn/assistants are skipped unless their API keys are set,
which is fine, the KPI page doesn't need them. Confirm
`http://127.0.0.1:8510/network` opens in your browser before moving to Android.

## 2. Open the Android project

Open the `android_app` folder (this folder) directly in Android Studio as an
existing project. If Android Studio reports the Gradle wrapper jar is missing,
accept its offer to regenerate it (or run `gradle wrapper` once from its
Terminal) - the wrapper version is already pinned in
`gradle/wrapper/gradle-wrapper.properties`.

## 3. Run it

- **Emulator** (default, no changes needed): the app defaults to
  `http://10.0.2.2:8510/network` - `10.0.2.2` is the emulator's alias for your
  laptop's `localhost`. Just click Run in Android Studio.
- **Physical phone**: connect the phone to the same WiFi as your laptop, find
  your laptop's LAN IP (`ipconfig` on Windows, look for IPv4 address), and type
  e.g. `http://192.168.1.23:8510/network` into the address bar at the top of
  the app, then tap "Go". It's saved automatically for next launch.

## Talking points for the demo

- The ML models (LightGBM/XGBoost/Random Forest for GIS, similar for KPI
  forecasting) are unchanged - this shows the *same* trained models and the
  *same* dashboard, just delivered through a phone shell instead of a laptop
  browser, which is the fast path to a mobile presence.
- "Live tracking" auto-refreshes the page, standing in for what a native app's
  push/poll loop would do so ops staff can check KPIs without a laptop.
- Mention the honest next step: a production app would replace this WebView
  wrapper with a small native UI calling a FastAPI layer directly (faster,
  works offline-ish, real push notifications) - this wrapper is the
  fastest way to prove the concept on a phone today.
