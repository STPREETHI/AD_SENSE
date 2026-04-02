/* =========================================================
   AdSense AI — Frontend Script
   Architecture: Frontend -> FastAPI backend -> AI provider
   API keys live in .env on the server. Never in the browser.
   ========================================================= */

const API = 'http://localhost:8000';

let revenueChart = null;
let spendChart   = null;
let salesData    = [];
let adsData      = [];

/* ── Init ─────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  checkBackend();
  setupFileLabels();
});

async function checkBackend() {
  const statusEl  = document.getElementById('backend-status');
  const dataEl    = document.getElementById('data-status');
  try {
    const r = await fetch(`${API}/`);
    const d = await r.json();
    statusEl.textContent = 'API Online';
    statusEl.className   = 'status-pill status-ok';

    // Show AI config from backend
    loadAIConfig();

    if (d.data_loaded) {
      dataEl.textContent = 'Data loaded';
      dataEl.className   = 'status-pill status-ok';
      loadMetrics();
    }
  } catch {
    statusEl.textContent = 'API Offline';
    statusEl.className   = 'status-pill status-error';
  }
}

async function loadAIConfig() {
  try {
    const r = await fetch(`${API}/config`);
    const d = await r.json();
    setText('ai-provider-val', d.ai_provider || '—');
    setText('ai-model-val',    d.model        || '—');
    const keyEl = document.getElementById('ai-key-val');
    if (keyEl) {
      keyEl.textContent = d.api_key_set ? 'Configured' : 'NOT SET';
      keyEl.style.color = d.api_key_set ? 'var(--green)' : 'var(--red)';
    }
    // Update agent badge
    const badge = document.getElementById('agent-model-badge');
    if (badge && d.model) badge.textContent = `${d.ai_provider} / ${d.model}`;
  } catch {
    // Backend may not have /config yet — ignore
  }
}

function setupFileLabels() {
  document.getElementById('salesFile').addEventListener('change', function () {
    document.getElementById('salesLabel').textContent = this.files[0]?.name || 'Sales CSV';
    this.closest('label').classList.toggle('selected', !!this.files[0]);
  });
  document.getElementById('adsFile').addEventListener('change', function () {
    document.getElementById('adsLabel').textContent = this.files[0]?.name || 'Ads CSV';
    this.closest('label').classList.toggle('selected', !!this.files[0]);
  });
}

/* ── CSV Parser (client-side for charts & simulator) ─────────────────── */
function parseCSV(text) {
  const lines   = text.trim().split('\n');
  const headers = lines[0].split(',').map(h => h.trim().replace(/"/g, ''));
  return lines.slice(1).map(line => {
    const vals = [];
    let cur = '', inQ = false;
    for (const ch of line) {
      if (ch === '"') { inQ = !inQ; }
      else if (ch === ',' && !inQ) { vals.push(cur.trim()); cur = ''; }
      else { cur += ch; }
    }
    vals.push(cur.trim());
    const obj = {};
    headers.forEach((h, i) => {
      const v = (vals[i] || '').replace(/"/g, '');
      obj[h] = v !== '' && !isNaN(v) ? Number(v) : v;
    });
    return obj;
  });
}

function numSum(arr, key) {
  return arr.reduce((a, r) => a + (Number(r[key]) || 0), 0);
}

/* ── Upload ───────────────────────────────────────────────────────────── */
async function uploadFiles() {
  const salesFile = document.getElementById('salesFile').files[0];
  const adsFile   = document.getElementById('adsFile').files[0];
  const msg       = document.getElementById('upload-msg');
  const btn       = document.getElementById('uploadBtn');

  if (!salesFile || !adsFile) { showMsg(msg, 'Select both CSV files first.', 'err'); return; }

  btn.disabled    = true;
  btn.textContent = 'Processing...';
  showMsg(msg, 'Uploading...', '');

  try {
    // Parse locally for charts and simulator
    const [salesText, adsText] = await Promise.all([salesFile.text(), adsFile.text()]);
    salesData = parseCSV(salesText);
    adsData   = parseCSV(adsText);

    // Send to backend (which holds the data for AI queries)
    const fd = new FormData();
    fd.append('sales_file', salesFile);
    fd.append('ads_file',   adsFile);
    const r = await fetch(`${API}/upload`, { method: 'POST', body: fd });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Upload failed');

    showMsg(msg, `${d.sales_rows} sales rows and ${d.ads_rows} ad rows loaded`, 'ok');
    document.getElementById('data-status').textContent = 'Data loaded';
    document.getElementById('data-status').className   = 'status-pill status-ok';

    computeAndRenderAll();
  } catch (e) {
    showMsg(msg, `Error: ${e.message}`, 'err');
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Upload & Analyze';
  }
}

/* ── Metrics ─────────────────────────────────────────────────────────── */
async function loadMetrics() {
  try {
    const r = await fetch(`${API}/metrics`);
    const d = await r.json();
    if (d.total_revenue) renderKPIsFromBackend(d);
  } catch { /* ignore — will render from client-side parse on upload */ }
}

function computeAndRenderAll() {
  if (!salesData.length || !adsData.length) return;

  const totalRevenue    = numSum(salesData, 'revenue');
  const totalUnits      = numSum(salesData, 'units_sold');
  const totalSpend      = numSum(adsData,   'ad_spend');
  const totalAttr       = numSum(adsData,   'attributed_sales');
  const totalClicks     = numSum(adsData,   'clicks');
  const totalImpr       = numSum(adsData,   'impressions');
  const totalAttrUnits  = numSum(adsData,   'attributed_units');
  const organicRev      = Math.max(0, totalRevenue - totalAttr);
  const overallAcos     = totalAttr  > 0 ? totalSpend / totalAttr * 100 : 999;
  const overallRoas     = totalSpend > 0 ? totalAttr / totalSpend : 0;
  const adContribPct    = totalRevenue > 0 ? totalAttr / totalRevenue * 100 : 0;
  const ctr             = totalImpr   > 0 ? totalClicks / totalImpr * 100 : 0;
  const cvr             = totalClicks > 0 ? totalAttrUnits / totalClicks * 100 : 0;
  const avgCpc          = totalClicks > 0 ? totalSpend / totalClicks : 0;
  const wastedSpend     = adsData
    .filter(r => r.clicks > 0 && r.attributed_units === 0)
    .reduce((a, r) => a + (Number(r.ad_spend) || 0), 0);

  const profitRows  = salesData.filter(r => r.profit_margin_pct > 0);
  const avgMargin   = profitRows.length > 0
    ? profitRows.reduce((a, r) => a + r.profit_margin_pct, 0) / profitRows.length / 100
    : 0.20;
  const totalProfit = totalRevenue * avgMargin - totalSpend;

  renderKPIs({ totalRevenue, totalUnits, totalSpend, totalAttr, organicRev,
    overallAcos, overallRoas, adContribPct, totalProfit,
    totalClicks, totalImpr, ctr, cvr, avgCpc, wastedSpend });
  renderCharts();
  renderTopProducts();
}

function renderKPIs(m) {
  const asinCount = [...new Set(salesData.map(r => r.asin))].length;
  setText('kpi-rev-val',     fmtINR(m.totalRevenue));
  setText('kpi-spend-val',   fmtINR(m.totalSpend));
  setText('kpi-units-val',   Math.round(m.totalUnits).toLocaleString('en-IN'));
  setText('kpi-organic-val', fmtINR(m.organicRev));
  setText('kpi-rev-sub',     `${asinCount} products`);
  setText('kpi-spend-sub',   `${(m.adContribPct||0).toFixed(1)}% of revenue`);
  setText('kpi-ad-contrib',  `Ad ${(m.adContribPct||0).toFixed(1)}% | Organic ${(100-(m.adContribPct||0)).toFixed(1)}%`);
  setText('kpi-profit-val',  fmtINR(m.totalProfit));
  setText('kpi-attr-val',    fmtINR(m.totalAttr));
  setText('kpi-ctr-val',     `${(m.ctr||0).toFixed(2)}%`);
  setText('kpi-cpc-val',     `Rs.${(m.avgCpc||0).toFixed(2)}`);
  setText('kpi-clicks-val',  Math.round(m.totalClicks||0).toLocaleString('en-IN'));
  setText('kpi-impr-val',    Math.round(m.totalImpr||0).toLocaleString('en-IN'));
  setText('kpi-cvr-val',     `${(m.cvr||0).toFixed(2)}%`);
  setText('kpi-waste-val',   fmtINR(m.wastedSpend||0));

  const acosEl = document.getElementById('kpi-acos-val');
  const acos   = m.overallAcos || 0;
  acosEl.textContent = acos > 900 ? 'N/A' : `${acos.toFixed(1)}%`;
  acosEl.className   = `kpi-value ${acos > 50 ? 'kpi-bad' : acos > 30 ? 'kpi-warn' : 'kpi-good'}`;

  const roasEl = document.getElementById('kpi-roas-val');
  const roas   = m.overallRoas || 0;
  roasEl.textContent = `${roas.toFixed(2)}x`;
  roasEl.className   = `kpi-value ${roas >= 3 ? 'kpi-good' : roas >= 1.5 ? 'kpi-warn' : 'kpi-bad'}`;
}

function renderKPIsFromBackend(d) {
  renderKPIs({
    totalRevenue:  d.total_revenue,
    totalSpend:    d.total_ad_spend,
    totalAttr:     d.total_attributed_sales,
    totalUnits:    d.total_units_sold,
    organicRev:    d.organic_revenue,
    overallAcos:   d.overall_acos,
    overallRoas:   d.overall_roas || (d.total_attributed_sales / d.total_ad_spend),
    adContribPct:  d.ad_contribution_pct,
    totalProfit:   d.total_profit,
    totalClicks:   d.total_clicks   || 0,
    totalImpr:     d.total_impressions || 0,
    ctr:           d.avg_ctr        || 0,
    cvr:           d.avg_cvr        || 0,
    avgCpc:        d.avg_cpc        || 0,
    wastedSpend:   d.wasted_spend   || 0,
  });
}

/* ── Charts ──────────────────────────────────────────────────────────── */
function renderCharts() {
  // Daily revenue
  const salesByDate = {};
  salesData.forEach(r => {
    const d = (r.date || '').slice(0, 10);
    if (d) salesByDate[d] = (salesByDate[d] || 0) + (Number(r.revenue) || 0);
  });
  const revDates = Object.keys(salesByDate).sort().slice(-30);
  const revVals  = revDates.map(d => salesByDate[d]);

  // Daily spend & attributed
  const spendByDate = {};
  const attrByDate  = {};
  adsData.forEach(r => {
    const d = (r.date || '').slice(0, 10);
    if (!d) return;
    spendByDate[d] = (spendByDate[d] || 0) + (Number(r.ad_spend)         || 0);
    attrByDate[d]  = (attrByDate[d]  || 0) + (Number(r.attributed_sales) || 0);
  });
  const spendDates = Object.keys(spendByDate).sort().slice(-30);

  const CHART_OPTS = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#6b7280', font: { family: 'DM Sans', size: 11 } } } },
    scales: {
      x: { ticks: { color: '#9ca3af', font: { family: 'DM Mono', size: 9 } }, grid: { color: 'rgba(226,230,240,0.8)' } },
      y: { ticks: { color: '#9ca3af', font: { family: 'DM Mono', size: 9 } }, grid: { color: 'rgba(226,230,240,0.8)' } },
    },
  };

  if (revenueChart) revenueChart.destroy();
  revenueChart = new Chart(document.getElementById('revenueChart'), {
    type: 'line',
    data: {
      labels: revDates.map(d => d.slice(5)),
      datasets: [{
        label: 'Revenue (Rs.)',
        data: revVals,
        borderColor: '#1a56db',
        backgroundColor: 'rgba(26,86,219,0.07)',
        fill: true, tension: 0.4, pointRadius: 2, borderWidth: 2.2,
      }],
    },
    options: CHART_OPTS,
  });

  if (spendChart) spendChart.destroy();
  spendChart = new Chart(document.getElementById('spendChart'), {
    type: 'bar',
    data: {
      labels: spendDates.map(d => d.slice(5)),
      datasets: [
        { label: 'Ad Spend',         data: spendDates.map(d => spendByDate[d] || 0), backgroundColor: 'rgba(217,119,6,0.55)',  borderRadius: 2 },
        { label: 'Attributed Sales', data: spendDates.map(d => attrByDate[d]  || 0), backgroundColor: 'rgba(14,159,110,0.55)', borderRadius: 2 },
      ],
    },
    options: CHART_OPTS,
  });
}

function renderTopProducts() {
  if (!salesData.length) return;
  const byAsin = {};
  salesData.forEach(r => {
    const k = r.asin;
    if (!byAsin[k]) byAsin[k] = { asin: k, title: r.product_title || k, rev: 0, units: 0 };
    byAsin[k].rev   += Number(r.revenue)    || 0;
    byAsin[k].units += Number(r.units_sold) || 0;
  });
  const top = Object.values(byAsin).sort((a, b) => b.rev - a.rev).slice(0, 10);
  document.getElementById('top-products-table').innerHTML = `
    <table class="data-table">
      <thead><tr><th>#</th><th>ASIN</th><th>Product</th><th>Revenue</th><th>Units</th></tr></thead>
      <tbody>
        ${top.map((p, i) => `
          <tr>
            <td>${i + 1}</td>
            <td class="asin-cell">${p.asin}</td>
            <td title="${escHtml(p.title)}">${escHtml(trunc(p.title, 55))}</td>
            <td class="rev-cell">${fmtINR(p.rev)}</td>
            <td>${Math.round(p.units).toLocaleString('en-IN')}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;
}

/* ── Agent Query — calls backend, backend calls AI ────────────────────── */
function setQuery(text) { document.getElementById('queryInput').value = text; }

async function runQuery() {
  const query = document.getElementById('queryInput').value.trim();
  if (!query) return;

  const btn = document.getElementById('analyzeBtn');
  btn.disabled = true;
  document.getElementById('agent-response').classList.add('hidden');
  document.getElementById('agent-error').classList.add('hidden');
  document.getElementById('agent-loading').classList.remove('hidden');

  // Animate loading steps
  const steps = [...document.querySelectorAll('.loading-step')];
  steps.forEach(s => s.className = 'loading-step');
  let idx = 0;
  const ticker = setInterval(() => {
    if (idx > 0) steps[idx - 1].className = 'loading-step done';
    if (idx < steps.length) { steps[idx].className = 'loading-step active'; idx++; }
    else clearInterval(ticker);
  }, 900);

  try {
    // Just send the text query — backend handles all AI API calls
    const r = await fetch(`${API}/query`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query }),
    });
    clearInterval(ticker);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || 'Query failed');
    renderAgentResponse(d);
  } catch (e) {
    clearInterval(ticker);
    showAgentError(`${e.message} — Make sure the backend is running: uvicorn main:app --reload`);
  } finally {
    document.getElementById('agent-loading').classList.add('hidden');
    btn.disabled = false;
  }
}

function renderAgentResponse(d) {
  setText('res-understanding', d.query_understanding || '');

  document.getElementById('res-steps').innerHTML =
    (d.analysis_steps || []).map(s => `<li>${escHtml(s)}</li>`).join('');

  document.getElementById('res-findings').innerHTML =
    (d.key_findings || []).map(f => `<div class="finding-item">${escHtml(f)}</div>`).join('');

  setText('res-insight', d.cross_dataset_insight || '');

  document.getElementById('res-recommendations').innerHTML =
    (d.recommendations || []).map((rec, i) => `
      <div class="rec-card ${(rec.confidence || 'medium').toLowerCase()}" style="animation-delay:${i * 0.07}s">
        <div class="rec-action">--> ${escHtml(rec.action)}</div>
        <div class="rec-reason">${escHtml(rec.reason)}</div>
        <div class="rec-meta">
          <span class="rec-badge badge-confidence-${(rec.confidence || 'medium').toLowerCase()}">${rec.confidence || 'Medium'} Confidence</span>
          <span class="rec-badge badge-impact">${escHtml(rec.expected_impact)}</span>
        </div>
      </div>`).join('');

  const risks = d.risk_warnings || [];
  const riskSec = document.getElementById('risk-section');
  riskSec.classList.toggle('hidden', risks.length === 0);
  document.getElementById('res-risks').innerHTML =
    risks.map(r => `<div class="risk-item">${escHtml(r)}</div>`).join('');

  document.getElementById('agent-response').classList.remove('hidden');
  document.getElementById('agent-response').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function showAgentError(msg) {
  const el = document.getElementById('agent-error');
  el.textContent = msg;
  el.classList.remove('hidden');
  document.getElementById('agent-loading').classList.add('hidden');
}

/* ── What-If Simulator ───────────────────────────────────────────────── */
function updateSimLabel(val) {
  document.getElementById('sim-pct-val').textContent = val;
}

function runWhatIf() {
  const pct = parseInt(document.getElementById('sim-slider').value);
  const out = document.getElementById('sim-result');
  out.style.display = 'block';

  if (!salesData.length || !adsData.length) {
    out.textContent = 'Upload data first to run simulation.';
    return;
  }

  const totalSpend   = numSum(adsData,   'ad_spend');
  const totalAttr    = numSum(adsData,   'attributed_sales');
  const totalRevenue = numSum(salesData, 'revenue');
  const organicRev   = Math.max(0, totalRevenue - totalAttr);

  const savings    = totalSpend * (pct / 100);
  const newSpend   = totalSpend - savings;
  const attrDrop   = totalAttr * (pct / 100) * 0.70;   // 70% proportional drop
  const newTotal   = organicRev + (totalAttr - attrDrop);
  const revImpact  = totalRevenue - newTotal;
  const netGain    = savings - revImpact;
  const newAcos    = newSpend > 0 && (totalAttr - attrDrop) > 0
    ? newSpend / (totalAttr - attrDrop) * 100 : 999;
  const newRoas    = newSpend > 0 ? (totalAttr - attrDrop) / newSpend : 0;

  out.innerHTML = [
    `What-If: -${pct}% Ad Spend`,
    ``,
    `Current spend:   ${fmtINR(totalSpend)}`,
    `New spend:       ${fmtINR(newSpend)}`,
    `Savings:         ${fmtINR(savings)}`,
    ``,
    `Est. rev impact: -${fmtINR(revImpact)}`,
    `Net gain:        ${fmtINR(netGain)}`,
    `New ACoS:        ${newAcos > 900 ? 'N/A' : newAcos.toFixed(1) + '%'}`,
    `New ROAS:        ${newRoas.toFixed(2)}x`,
    ``,
    `Verdict: ${netGain > 0 ? 'PROFITABLE CUT' : 'NOT RECOMMENDED'}`,
    `(Assumes 70% proportional attributed sales drop)`,
  ].join('\n');
}

/* ── Helpers ──────────────────────────────────────────────────────────── */
// Use ASCII Rs. prefix to avoid encoding issues with the Rupee symbol
function fmtINR(n) {
  if (n === undefined || n === null) return '-';
  return 'Rs.' + Math.round(Number(n)).toLocaleString('en-IN');
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function showMsg(el, text, type) {
  el.textContent = text;
  el.className   = 'msg ' + type;
}
function trunc(str, n) {
  return str && str.length > n ? str.slice(0, n) + '...' : (str || '');
}
function escHtml(str) {
  return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && e.ctrlKey) runQuery();
});