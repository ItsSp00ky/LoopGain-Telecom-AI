# 4G/LTE KPI Forecast Visualizations Gallery

This document showcases all 12 forecast evaluation charts comparing **Actual vs Predicted** network performance across frequency bands.

---

## 1. E-RAB Drop Rate ($R^2 = 0.980$ — Excellent)
*Predicts voice/data session drop percentage (customer satisfaction / QoS).*

### Full Year Timeline (Train 70% + Test 30%)
![Drop Rate - Full Timeline](forecast_results/plots/forecast_E-RAB_Drop_Rate_timeline.png)

### Daily Actual vs Predicted (Test Period)
![Drop Rate - Daily](forecast_results/plots/forecast_E-RAB_Drop_Rate_daily.png)

### Weekly Aggregated View
![Drop Rate - Weekly](forecast_results/plots/forecast_E-RAB_Drop_Rate_weekly.png)

### Per Frequency Band Breakdown (`earfcndl`)
![Drop Rate - Per Band](forecast_results/plots/forecast_E-RAB_Drop_Rate_bands.png)

---

## 2. Avg RRC Connected Users ($R^2 = 0.989$ — Excellent)
*Predicts active user demand and capacity congestion.*

### Full Year Timeline (Train 70% + Test 30%)
![Users - Full Timeline](forecast_results/plots/forecast_Avg_RRC_Connected_users_timeline.png)

### Daily Actual vs Predicted (Test Period)
![Users - Daily](forecast_results/plots/forecast_Avg_RRC_Connected_users_daily.png)

### Weekly Aggregated View
![Users - Weekly](forecast_results/plots/forecast_Avg_RRC_Connected_users_weekly.png)

### Per Frequency Band Breakdown (`earfcndl`)
![Users - Per Band](forecast_results/plots/forecast_Avg_RRC_Connected_users_bands.png)

---

## 3. 4G Cell Availability ($R^2 = 0.344$ — Event-Driven)
*Predicts cell uptime percentage.*

### Full Year Timeline (Train 70% + Test 30%)
![Availability - Full Timeline](forecast_results/plots/forecast_4G_Cell_Av._pct_timeline.png)

### Daily Actual vs Predicted (Test Period)
![Availability - Daily](forecast_results/plots/forecast_4G_Cell_Av._pct_daily.png)

### Weekly Aggregated View
![Availability - Weekly](forecast_results/plots/forecast_4G_Cell_Av._pct_weekly.png)

### Per Frequency Band Breakdown (`earfcndl`)
![Availability - Per Band](forecast_results/plots/forecast_4G_Cell_Av._pct_bands.png)
