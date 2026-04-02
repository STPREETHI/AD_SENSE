/* ─── Config ─────────────────────────────────────────────────────────── */
const API = 'http://localhost:8000';

let revenueChart = null;
let spendChart   = null;
let metricsCache = null;

/* ─── Init ───────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  checkBackend();
  setupFileLabels();
});

async function checkBackend() {
  const el = document.getElementById('backend-status');
  try {
    const r = await fetch(`${API}/`);
    const d = await r.json();
    el.textContent = '● API Online';
    el.className = 'status-pill status-ok';
    if (d.data_loaded) {
      document.getElementById('data-status').textContent = 'Data loaded ✓';
      document.getElementById('data-status').className = 'status-pill status-ok';
      loadMetrics();
    }
  } catch {
    el.textContent = '● API Offline';
    el.className = 'status-pill status-error';
  }
}

function setupFileLabels() {
  document.getElementById('salesFile').addEventListener('change', function() {
    const lbl = document.getElementById('salesLabel');
    lbl.textContent = this.files[0]?.name || 'Sales CSV';
    this.closest('label').classList.toggle('selected', !!this.files[0]);
  });
  document.getElementById('adsFile').addEventListener('change', function() {
    const lbl = document.getElementById('adsLabel');
    lbl.textContent = this.files[0]?.name || 'Ads CSV';
    this.closest('label').classList.toggle('selected', !!this.files[0]);
  });
}

/* ─── Upload ─────────────────────────────────────────────────────────── */
async function uploadFiles() {
  const sales = document.getElementById('salesFile').files[0];
  const ads   = document.getElementById('adsFile').files[0];
  const msg   = document.getElementById('upload-msg');
  const btn   = document.getElementById('uploadBtn');

  if (!sales || !ads) {
    showMsg(msg, 'Select both CSV files first.', 'err');
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Uploading…';
  showMsg(msg, 'Processing…', '');

  const fd = new FormData();
  fd.append('sales_file', sales);
  fd.append('ads_file', ads);

  try {
    const r = await fetch(`${API}/upload`, { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Upload failed');

    showMsg(msg, `✓ ${d.sales_rows} sales rows · ${d.ads_rows} ad rows loaded`, 'ok');
    document.getElementById('data-status').textContent = 'Data loaded ✓';
    document.getElementById('data-status').className = 'status-pill status-ok';
    loadMetrics();
  } catch(e) {
    showMsg(msg, `✗ ${e.message}`, 'err');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Upload & Analyze';
  }
}

/* ─── Metrics ────────────────────────────────────────────────────────── */
async function loadMetrics() {
  try {
    const r = await fetch(`${API}/metrics`);
    const d = await r.json();
    metricsCache = d;
    renderKPIs(d);
    renderCharts(d);
    renderTopProducts(d.top_asins);
  } catch(e) {
    console.error('Metrics error:', e);
  }
}

function renderKPIs(d) {
  setText('kpi-rev-val',    '₹' + fmt(d.total_revenue));
  setText('kpi-spend-val',  '₹' + fmt(d.total_ad_spend));
  setText('kpi-profit-val', '₹' + fmt(d.total_profit));
  setText('kpi-units-val',  d.total_units_sold.toLocaleString());
  setText('kpi-organic-val','₹' + fmt(d.organic_revenue));
  setText('kpi-ad-contrib', `Ad: ${d.ad_contribution_pct.toFixed(1)}% | Organic: ${(100-d.ad_contribution_pct).toFixed(1)}%`);

  const acosEl = document.getElementById('kpi-acos-val');
  acosEl.textContent = d.overall_acos > 900 ? 'N/A' : d.overall_acos.toFixed(1) + '%';
  acosEl.className = 'kpi-value ' + (d.overall_acos > 50 ? 'kpi-bad' : d.overall_acos > 30 ? 'kpi-warn' : 'kpi-good');

  document.getElementById('kpi-spend-sub').textContent = `${d.ad_contribution_pct.toFixed(1)}% of revenue`;
  document.getElementById('kpi-profit-sub').textContent = `Attributed: ₹${fmt(d.total_attributed_sales)}`;
}

function renderCharts(d) {
  const labels = d.daily_trend.map(r => r.date.slice(5)); // MM-DD
  const revData = d.daily_trend.map(r => r.revenue);
  const spendData  = d.spend_trend.map(r => r.spend);
  const attrData   = d.spend_trend.map(r => r.attributed);
  const spendLabels = d.spend_trend.map(r => r.date.slice(5));

  if (revenueChart) revenueChart.destroy();
  revenueChart = new Chart(document.getElementById('revenueChart'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Revenue',
        data: revData,
        borderColor: '#00e5ff',
        backgroundColor: 'rgba(0,229,255,0.06)',
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        borderWidth: 2,
      }]
    },
    options: chartOptions('Revenue (₹)')
  });

  if (spendChart) spendChart.destroy();
  spendChart = new Chart(document.getElementById('spendChart'), {
    type: 'bar',
    data: {
      labels: spendLabels,
      datasets: [
        { label: 'Ad Spend', data: spendData, backgroundColor: 'rgba(255,61,87,0.6)', borderRadius: 2 },
        { label: 'Attributed Sales', data: attrData, backgroundColor: 'rgba(0,230,118,0.6)', borderRadius: 2 },
      ]
    },
    options: chartOptions('')
  });
}

function chartOptions(ylabel) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#5a6680', font: { family: 'Space Mono', size: 10 } } } },
    scales: {
      x: { ticks: { color: '#5a6680', font: { family: 'Space Mono', size: 9 } }, grid: { color: 'rgba(30,37,53,0.8)' } },
      y: { ticks: { color: '#5a6680', font: { family: 'Space Mono', size: 9 } }, grid: { color: 'rgba(30,37,53,0.8)' } },
    }
  };
}

function renderTopProducts(products) {
  if (!products || !products.length) return;
  const container = document.getElementById('top-products-table');
  container.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>#</th><th>ASIN</th><th>Product</th><th>Revenue</th><th>Units</th>
        </tr>
      </thead>
      <tbody>
        ${products.map((p, i) => `
          <tr>
            <td>${i+1}</td>
            <td class="asin-cell">${p.asin}</td>
            <td title="${p.product_title}">${truncate(p.product_title, 50)}</td>
            <td class="rev-cell">₹${fmt(p.revenue)}</td>
            <td>${(p.units || 0).toLocaleString()}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

/* ─── Agent Query ─────────────────────────────────────────────────────── */
function setQuery(text) {
  document.getElementById('queryInput').value = text;
}

async function runQuery() {
  const query = document.getElementById('queryInput').value.trim();
  if (!query) return;

  const btn = document.getElementById('analyzeBtn');
  btn.disabled = true;
  document.getElementById('agent-response').classList.add('hidden');
  document.getElementById('agent-error').classList.add('hidden');
  document.getElementById('agent-loading').classList.remove('hidden');

  // Animate loading steps
  const steps = document.querySelectorAll('.loading-step');
  steps.forEach(s => s.className = 'loading-step');
  let stepIdx = 0;
  const stepInterval = setInterval(() => {
    if (stepIdx > 0) steps[stepIdx-1].className = 'loading-step done';
    if (stepIdx < steps.length) {
      steps[stepIdx].className = 'loading-step active';
      stepIdx++;
    } else {
      clearInterval(stepInterval);
    }
  }, 1200);

  try {
    const r = await fetch(`${API}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    clearInterval(stepInterval);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Query failed');
    renderAgentResponse(d);
  } catch(e) {
    clearInterval(stepInterval);
    const errEl = document.getElementById('agent-error');
    errEl.textContent = '✗ ' + e.message + ' — Is the backend running? (uvicorn main:app --reload)';
    errEl.classList.remove('hidden');
  } finally {
    document.getElementById('agent-loading').classList.add('hidden');
    btn.disabled = false;
  }
}

function renderAgentResponse(d) {
  setText('res-understanding', d.query_understanding || '');

  const stepsEl = document.getElementById('res-steps');
  stepsEl.innerHTML = (d.analysis_steps || []).map(s => `<li>${s}</li>`).join('');

  const findingsEl = document.getElementById('res-findings');
  findingsEl.innerHTML = (d.key_findings || []).map(f => `<div class="finding-item">${f}</div>`).join('');

  setText('res-insight', d.cross_dataset_insight || '');

  const recsEl = document.getElementById('res-recommendations');
  recsEl.innerHTML = (d.recommendations || []).map((rec, i) => `
    <div class="rec-card ${(rec.confidence||'').toLowerCase()}" style="animation-delay:${i*0.08}s">
      <div class="rec-action">→ ${rec.action}</div>
      <div class="rec-reason">${rec.reason}</div>
      <div class="rec-meta">
        <span class="rec-badge badge-confidence-${(rec.confidence||'medium').toLowerCase()}">${rec.confidence} Confidence</span>
        <span class="rec-badge badge-impact">${rec.expected_impact}</span>
      </div>
    </div>
  `).join('');

  const risks = d.risk_warnings || [];
  const riskSection = document.getElementById('risk-section');
  if (risks.length) {
    riskSection.classList.remove('hidden');
    document.getElementById('res-risks').innerHTML = risks.map(r => `<div class="risk-item">${r}</div>`).join('');
  } else {
    riskSection.classList.add('hidden');
  }

  document.getElementById('agent-response').classList.remove('hidden');
  document.getElementById('agent-response').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

/* ─── What-If Simulator ──────────────────────────────────────────────── */
function updateSimLabel(val) {
  document.getElementById('sim-pct-val').textContent = val;
}

async function runWhatIf() {
  const pct = document.getElementById('sim-slider').value;
  const out = document.getElementById('sim-result');
  out.style.display = 'block';
  out.textContent = 'Calculating…';

  if (metricsCache) {
    const spend = metricsCache.total_ad_spend;
    const attrSales = metricsCache.total_attributed_sales;
    const organic = metricsCache.organic_revenue;

    const savings = spend * (pct / 100);
    const newSpend = spend - savings;
    const attrDrop = attrSales * (pct / 100) * 0.75; // assumes 75% of cut = proportional attr drop
    const newTotal = organic + (attrSales - attrDrop);
    const revImpact = metricsCache.total_revenue - newTotal;

    out.innerHTML = `
━━ What-If: -${pct}% Ad Spend ━━
Current spend:  ₹${fmt(spend)}
New spend:      ₹${fmt(newSpend)}
Savings:        ₹${fmt(savings)}

Est. rev impact: -₹${fmt(revImpact)}
Net gain:       ₹${fmt(savings - revImpact)}
Verdict: ${savings > revImpact ? '✓ PROFITABLE CUT' : '✗ NOT RECOMMENDED'}
    `;
  } else {
    // Use API if available
    try {
      const r = await fetch(`${API}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: `What happens if I reduce ad spend by ${pct}%?` }),
      });
      const d = await r.json();
      const svr = d.raw_tool_outputs?.spend_vs_revenue?.what_if_20pct_cut;
      if (svr) {
        out.innerHTML = `
Savings: ₹${fmt(svr.estimated_savings)}
New spend: ₹${fmt(svr.reduced_spend)}
Est. revenue: ₹${fmt(svr.estimated_revenue_impact)}
        `;
      } else {
        out.textContent = 'Upload data first to run simulation.';
      }
    } catch {
      out.textContent = 'Backend not available. Upload data first.';
    }
  }
}

/* ─── Helpers ────────────────────────────────────────────────────────── */
function fmt(n) {
  if (n === undefined || n === null) return '—';
  return Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function showMsg(el, text, type) {
  el.textContent = text;
  el.className = 'msg ' + type;
}
function truncate(str, n) {
  return str && str.length > n ? str.slice(0, n) + '…' : str;
}

// Allow Enter key to submit query
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.ctrlKey) runQuery();
});
