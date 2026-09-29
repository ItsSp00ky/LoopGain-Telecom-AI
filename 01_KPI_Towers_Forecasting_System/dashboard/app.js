// 4G LTE KPI Forecasting Interactive Dashboard Engine
let currentMode = 'network'; // 'network' or 'tower'
let currentKPI = 'connected_users';
let currentTower = 'TWR_0001';
let forecastChart = null;
let residualChart = null;
let appData = null;

const KPI_CONFIG = {
  connected_users: {
    title: 'Connected Users (Traffic Load & Capacity)',
    unit: 'users',
    actualLabel: 'Actual Users',
    predLabel: 'Predicted Users',
    colorActual: '#06b6d4', // Cyan
    colorPred: '#f43f5e',   // Coral
    icon: '👥'
  },
  dl_throughput: {
    title: 'Downlink Throughput (User Speed & QoE)',
    unit: 'Mbps',
    actualLabel: 'Actual Speed (Mbps)',
    predLabel: 'Predicted Speed (Mbps)',
    colorActual: '#10b981', // Emerald
    colorPred: '#8b5cf6',   // Violet
    icon: '🚀'
  },
  cell_availability: {
    title: 'Cell Availability (Uptime & Hardware Health)',
    unit: '%',
    actualLabel: 'Actual Uptime (%)',
    predLabel: 'Predicted Uptime (%)',
    colorActual: '#3b82f6', // Blue
    colorPred: '#f59e0b',   // Amber
    icon: '📶'
  },
  drop_rate: {
    title: 'E-RAB Drop Rate (Session Retention)',
    unit: '%',
    actualLabel: 'Actual Drop Rate (%)',
    predLabel: 'Predicted Drop Rate (%)',
    colorActual: '#a855f7', // Purple
    colorPred: '#ef4444',   // Red
    icon: '⚠️'
  }
};

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', async () => {
  // Load data from embedded JS fallback or JSON
  if (window.FORECAST_DASHBOARD_DATA) {
    appData = window.FORECAST_DASHBOARD_DATA;
    console.log("Loaded embedded forecast data successfully.");
  } else {
    try {
      const resp = await fetch('data/forecast_dashboard_data.json');
      appData = await resp.json();
    } catch (e) {
      console.warn("Could not fetch JSON, waiting for dynamic server:", e);
    }
  }

  setupAutocomplete();
  renderDashboard();
});

// Setup Autocomplete for 1,060 Towers
function setupAutocomplete() {
  const input = document.getElementById('tower-search-input');
  const dropdown = document.getElementById('tower-dropdown');
  if (!input || !dropdown || !appData) return;

  const allTowers = appData.all_towers || [];

  input.addEventListener('input', (e) => {
    const val = e.target.value.trim().toUpperCase();
    if (!val) {
      dropdown.style.display = 'none';
      return;
    }

    const matches = allTowers.filter(t => t.id.includes(val)).slice(0, 15);
    if (matches.length === 0) {
      dropdown.innerHTML = `<div class="autocomplete-item" style="cursor: default;">No towers matching "${val}"</div>`;
    } else {
      dropdown.innerHTML = matches.map(t => `
        <div class="autocomplete-item ${t.id === currentTower ? 'selected' : ''}" onclick="selectTower('${t.id}')">
          <span><strong>${t.id}</strong> ${t.is_featured ? '⭐ Featured' : ''}</span>
          <span style="font-size: 11px; opacity: 0.7;">Avg: ${t.avg_users} users</span>
        </div>
      `).join('');
    }
    dropdown.style.display = 'block';
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = input.value.trim().toUpperCase();
      if (val) {
        selectTower(val);
        dropdown.style.display = 'none';
      }
    }
  });

  document.addEventListener('click', (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = 'none';
    }
  });
}

// Switch between Network Macro and Tower Micro
function setDashboardMode(mode) {
  currentMode = mode;
  document.getElementById('btn-mode-network').classList.toggle('active', mode === 'network');
  document.getElementById('btn-mode-tower').classList.toggle('active', mode === 'tower');

  const towerControls = document.getElementById('tower-controls');
  const bannerTitle = document.getElementById('banner-title');
  const bannerDesc = document.getElementById('banner-desc');

  if (mode === 'network') {
    towerControls.style.display = 'none';
    bannerTitle.textContent = "High-Fidelity Countrywide Demand Tracking";
    bannerDesc.innerHTML = "Showing nationwide aggregate load across all 1,067 base stations. Countrywide connected user volume achieves an extraordinary <strong>1.38% MAPE</strong> (Mean Absolute Percentage Error) through hierarchical variance cancellation.";
  } else {
    towerControls.style.display = 'flex';
    bannerTitle.textContent = `Individual Base Station Tracking: ${currentTower}`;
    bannerDesc.innerHTML = `Exploring micro-level time series dynamics for site <strong>${currentTower}</strong>. Evaluating daily actual measurements against 23-feature XGBoost multi-lag forecasts.`;
  }

  renderDashboard();
}

// Switch Active KPI Tab
function switchActiveKPI(kpiKey) {
  currentKPI = kpiKey;
  document.querySelectorAll('.kpi-tab').forEach(tab => {
    tab.classList.toggle('active', tab.id === `tab-${kpiKey}`);
  });
  renderDashboard();
}

// Select Tower
async function selectTower(towerId) {
  currentTower = towerId;
  const input = document.getElementById('tower-search-input');
  if (input) input.value = towerId;

  const dropdown = document.getElementById('tower-dropdown');
  if (dropdown) dropdown.style.display = 'none';

  document.querySelectorAll('.quick-chip').forEach(chip => {
    chip.classList.toggle('active', chip.textContent.trim() === towerId);
  });

  const bannerTitle = document.getElementById('banner-title');
  if (bannerTitle && currentMode === 'tower') {
    bannerTitle.textContent = `Individual Base Station Tracking: ${currentTower}`;
  }

  // If tower is not in featured pre-bundled data, try fetching from local server
  if (appData && (!appData.featured_towers || !appData.featured_towers[towerId])) {
    try {
      const res = await fetch(`/api/tower/${towerId}`);
      if (res.ok) {
        const dynamicTower = await res.json();
        if (!appData.featured_towers) appData.featured_towers = {};
        appData.featured_towers[towerId] = dynamicTower;
      }
    } catch (e) {
      console.warn("Could not query dynamic API for tower", towerId);
    }
  }

  renderDashboard();
}

// Main Render Function
function renderDashboard() {
  if (!appData) return;

  const dates = appData.dates;
  let actualSeries = [];
  let predSeries = [];
  let kpiStats = null;

  const kpiInfo = KPI_CONFIG[currentKPI];

  if (currentMode === 'network') {
    const netKPI = appData.network[currentKPI];
    actualSeries = netKPI.actual;
    predSeries = netKPI.pred;
    kpiStats = netKPI.metrics;

    document.getElementById('chart-heading-text').textContent = `Countrywide Network Aggregate: ${kpiInfo.title}`;
    document.getElementById('chart-subtitle').textContent = `Nationwide Total / Average across 1,067 Base Stations • 109 Chronological Out-of-Time Days`;

    updateOverviewCards(appData.network);
  } else {
    const towerData = appData.featured_towers ? appData.featured_towers[currentTower] : null;
    if (towerData && towerData.kpis && towerData.kpis[currentKPI]) {
      const tKPI = towerData.kpis[currentKPI];
      actualSeries = tKPI.actual;
      predSeries = tKPI.pred;
      kpiStats = tKPI.metrics;
      updateTowerCards(towerData);
    } else {
      // Fallback if data pending
      actualSeries = [];
      predSeries = [];
      kpiStats = { r2: 0, mae: 0, rmse: 0, mape: 0 };
    }

    document.getElementById('chart-heading-text').textContent = `Cell Tower [${currentTower}]: ${kpiInfo.title}`;
    document.getElementById('chart-subtitle').textContent = `Site-Level Precision (R² = ${kpiStats.r2}, MAE = ${kpiStats.mae} ${kpiInfo.unit}) • 109 Chronological Days`;
  }

  renderMainChart(dates, actualSeries, predSeries, kpiInfo);
  renderResidualChart(dates, actualSeries, predSeries, kpiInfo);
}

// Update 4 Summary Stat Cards
function updateOverviewCards(networkObj) {
  // Users
  const u = networkObj.connected_users;
  const lastUsers = Math.round(u.actual[u.actual.length - 1]);
  document.getElementById('val-users').innerHTML = `${lastUsers.toLocaleString()} <span class="card-unit">users</span>`;
  document.getElementById('badge-users-r2').textContent = `R²: ${u.metrics.r2}`;
  document.getElementById('badge-users-mae').textContent = `MAPE: ${u.metrics.mape}%`;

  // Throughput
  const t = networkObj.dl_throughput;
  const lastThroughput = t.actual[t.actual.length - 1].toFixed(2);
  document.getElementById('val-throughput').innerHTML = `${lastThroughput} <span class="card-unit">Mbps</span>`;
  document.getElementById('badge-dl-r2').textContent = `R²: ${t.metrics.r2}`;
  document.getElementById('badge-dl-mae').textContent = `MAE: ${t.metrics.mae} Mbps`;

  // Availability
  const a = networkObj.cell_availability;
  const lastAvail = a.actual[a.actual.length - 1].toFixed(2);
  document.getElementById('val-avail').innerHTML = `${lastAvail} <span class="card-unit">%</span>`;
  document.getElementById('badge-avail-mape').textContent = `Uptime: ${lastAvail}%`;
  document.getElementById('badge-avail-mae').textContent = `MAE: ${a.metrics.mae}%`;

  // Drop Rate
  const d = networkObj.drop_rate;
  const lastDrop = d.actual[d.actual.length - 1].toFixed(3);
  document.getElementById('val-drop').innerHTML = `${lastDrop} <span class="card-unit">%</span>`;
  document.getElementById('badge-drop-mae').textContent = `MAE: ${d.metrics.mae}%`;
  document.getElementById('badge-drop-mape').textContent = `MAPE: ${d.metrics.mape}%`;
}

function updateTowerCards(towerObj) {
  const kpis = towerObj.kpis;
  // Users
  if (kpis.connected_users) {
    const u = kpis.connected_users;
    const last = u.actual[u.actual.length - 1];
    document.getElementById('val-users').innerHTML = `${last} <span class="card-unit">users</span>`;
    document.getElementById('badge-users-r2').textContent = `R²: ${u.metrics.r2}`;
    document.getElementById('badge-users-mae').textContent = `MAE: ${u.metrics.mae}`;
  }

  // DL Throughput
  if (kpis.dl_throughput) {
    const t = kpis.dl_throughput;
    const last = t.actual[t.actual.length - 1];
    document.getElementById('val-throughput').innerHTML = `${last} <span class="card-unit">Mbps</span>`;
    document.getElementById('badge-dl-r2').textContent = `R²: ${t.metrics.r2}`;
    document.getElementById('badge-dl-mae').textContent = `MAE: ${t.metrics.mae} Mbps`;
  }

  // Cell Availability
  if (kpis.cell_availability) {
    const a = kpis.cell_availability;
    const last = a.actual[a.actual.length - 1];
    document.getElementById('val-avail').innerHTML = `${last} <span class="card-unit">%</span>`;
    document.getElementById('badge-avail-mape').textContent = `R²: ${a.metrics.r2}`;
    document.getElementById('badge-avail-mae').textContent = `MAE: ${a.metrics.mae}%`;
  }

  // Drop Rate
  if (kpis.drop_rate) {
    const d = kpis.drop_rate;
    const last = d.actual[d.actual.length - 1];
    document.getElementById('val-drop').innerHTML = `${last} <span class="card-unit">%</span>`;
    document.getElementById('badge-drop-mae').textContent = `MAE: ${d.metrics.mae}%`;
    document.getElementById('badge-drop-mape').textContent = `R²: ${d.metrics.r2}`;
  }
}

// Chart.js Main Forecast Chart
function renderMainChart(dates, actualData, predData, kpiInfo) {
  const ctx = document.getElementById('forecastCanvas').getContext('2d');

  if (forecastChart) {
    forecastChart.destroy();
  }

  // Format short date strings (e.g., "Jun 03")
  const shortLabels = dates.map(d => {
    const dt = new Date(d);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });

  // Gradient fill for actual series
  const gradient = ctx.createLinearGradient(0, 0, 0, 400);
  gradient.addColorStop(0, `${kpiInfo.colorActual}33`);
  gradient.addColorStop(1, `${kpiInfo.colorActual}00`);

  forecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: shortLabels,
      datasets: [
        {
          label: 'Actual Ground Truth',
          data: actualData,
          borderColor: kpiInfo.colorActual,
          backgroundColor: gradient,
          fill: true,
          borderWidth: 2.2,
          pointRadius: 1.5,
          pointHoverRadius: 6,
          pointBackgroundColor: kpiInfo.colorActual,
          tension: 0.25
        },
        {
          label: 'XGBoost ML Forecast',
          data: predData,
          borderColor: kpiInfo.colorPred,
          borderWidth: 2.2,
          borderDash: [5, 4],
          pointRadius: 0,
          pointHoverRadius: 5,
          pointBackgroundColor: kpiInfo.colorPred,
          tension: 0.25
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(17, 24, 39, 0.95)',
          titleColor: '#ffffff',
          bodyColor: '#e5e7eb',
          borderColor: 'rgba(255, 255, 255, 0.15)',
          borderWidth: 1,
          padding: 12,
          boxPadding: 6,
          usePointStyle: true,
          callbacks: {
            title: (items) => {
              const idx = items[0].dataIndex;
              const rawDate = dates[idx];
              const dt = new Date(rawDate);
              const dayName = dt.toLocaleDateString('en-US', { weekday: 'long' });
              return `${rawDate} (${dayName})`;
            },
            afterBody: (items) => {
              const act = items[0].raw;
              const prd = items[1].raw;
              const delta = (act - prd).toFixed(3);
              const pct = act !== 0 ? Math.abs((act - prd) / act * 100).toFixed(1) : 0;
              return `\nDelta (Error): ${delta > 0 ? '+' : ''}${delta} ${kpiInfo.unit}\nDeviation: ${pct}%`;
            }
          }
        }
      },
      scales: {
        x: {
          grid: {
            color: 'rgba(255, 255, 255, 0.05)',
            borderColor: 'rgba(255, 255, 255, 0.1)'
          },
          ticks: {
            color: '#9ca3af',
            maxTicksLimit: 12,
            font: { family: 'Inter', size: 11 }
          }
        },
        y: {
          grid: {
            color: 'rgba(255, 255, 255, 0.05)',
            borderColor: 'rgba(255, 255, 255, 0.1)'
          },
          ticks: {
            color: '#9ca3af',
            font: { family: 'Inter', size: 11 }
          }
        }
      }
    }
  });
}

// Chart.js Residual Chart
function renderResidualChart(dates, actualData, predData, kpiInfo) {
  const ctx = document.getElementById('residualCanvas').getContext('2d');

  if (residualChart) {
    residualChart.destroy();
  }

  const shortLabels = dates.map(d => {
    const dt = new Date(d);
    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  });

  const residuals = actualData.map((act, i) => {
    const prd = predData[i];
    return Number((act - prd).toFixed(3));
  });

  const barColors = residuals.map(r => r >= 0 ? 'rgba(6, 182, 212, 0.65)' : 'rgba(244, 63, 94, 0.65)');

  residualChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: shortLabels,
      datasets: [{
        label: 'Residual Error (Actual - Predicted)',
        data: residuals,
        backgroundColor: barColors,
        borderRadius: 2
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(17, 24, 39, 0.95)',
          padding: 10,
          callbacks: {
            label: (item) => `Residual: ${item.raw > 0 ? '+' : ''}${item.raw} ${kpiInfo.unit}`
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: '#6b7280',
            maxTicksLimit: 12,
            font: { family: 'Inter', size: 10 }
          }
        },
        y: {
          grid: {
            color: 'rgba(255, 255, 255, 0.05)',
            borderColor: 'rgba(255, 255, 255, 0.1)'
          },
          ticks: {
            color: '#9ca3af',
            font: { family: 'Inter', size: 10 }
          }
        }
      }
    }
  });
}
