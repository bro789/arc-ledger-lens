'use strict';
const $ = (id) => document.getElementById(id);
let activeEvidence = null;
let busy = false;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const short = (value) => value ? `${value.slice(0, 8)}…${value.slice(-6)}` : 'Contract creation';
const row = (name, value) => `<div class="raw-row"><span>${esc(name)}</span><code>${esc(value)}</code></div>`;
const metric = (label, value, note, unit = 'USDC') => `<article class="metric"><div class="metric-label">${esc(label)}</div><div class="metric-value">${esc(value)}<small>${esc(unit)}</small></div><div class="metric-note">${esc(note)}</div></article>`;
function panel(name) {
  ['account', 'transaction', 'verify'].forEach((key) => {
    $(`panel-${key}`).hidden = key !== name;
    $(`tab-${key}`).classList.toggle('active', key === name);
    $(`tab-${key}`).setAttribute('aria-selected', String(key === name));
  });
}
document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => panel(tab.dataset.panel)));
['account-address','amount','gas-limit','fee-cap','transaction-hash'].forEach((id) => $(id).addEventListener('input', () => {
  // A changed query must not retain a green result for the previous identifier.
  activeEvidence = null;
  $('results').hidden = true;
  $('results').replaceChildren();
  status('');
}));
function status(message, error = false) {
  $('status').hidden = !message;
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
async function request(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request did not complete.');
  return data;
}
async function run(task) {
  if (busy) return;
  busy = true;
  activeEvidence = null;
  $('results').hidden = true;
  $('results').replaceChildren();
  document.querySelectorAll('button').forEach((x) => x.disabled = true);
  status('Reading evidence. No wallet, signature or on-chain transaction is involved…');
  try { await task(); status(''); }
  catch (error) { status(error.message, true); }
  finally { busy = false; document.querySelectorAll('button').forEach((x) => x.disabled = false); }
}
function evidenceFooter(doc) {
  return `<div class="evidence-card"><div class="card-head"><h3>Evidence trail</h3><span class="badge">${doc.rpc_trace.length} read calls</span></div><div class="card-body">${row('Endpoint', doc.endpoint)}${row('Captured (UTC)', doc.captured_at_utc)}${row('SHA-256', doc.sha256)}<p class="note">File integrity and arithmetic can be verified offline with the exported JSON. The digest is not a cryptographic chain or validator proof.</p></div><details><summary>Inspect recorded JSON-RPC requests & responses</summary><pre>${esc(JSON.stringify(doc.rpc_trace, null, 2))}</pre></details></div>`;
}
function resultHeader(doc, recorded) {
  const block = doc.payload.block;
  return `<div class="result-head"><div><h2>${doc.kind === 'account' ? 'Balance evidence' : 'Transaction evidence'}</h2><p><span class="badge ${recorded ? 'recorded' : 'live'}">${recorded ? 'Recorded mainnet · not live' : 'Fresh mainnet read'}</span>${block ? `Block ${block.number.toLocaleString('en-US')} · ${esc(block.timestamp_utc)}` : 'Receipt unavailable'}</p></div><button id="export-button" class="button primary">Export evidence ↓</button></div>`;
}
function render(doc, recorded = false) {
  activeEvidence = doc;
  const p = doc.payload;
  let html = resultHeader(doc, recorded);
  if (doc.kind === 'account') {
    const b = p.balance, budget = p.budget;
    html += `<div class="metrics">${metric('One displayed balance', b.display_usdc, 'ERC-20 view · 6 decimal places')}${metric('Hypothetical gas budget cap', budget.gas_budget_cap_usdc, `${budget.gas_limit.toLocaleString('en-US')} gas × ${budget.max_fee_gwei} Gwei`)}${metric('Budget shortfall', budget.shortfall_usdc, budget.can_cover_budget_cap ? 'Balance covers the arithmetic reserve' : 'Transfer + gas reserve exceeds balance')}</div>`;
    html += `<div class="evidence-card"><div class="card-head"><h3>18 / 6 decimal reconciliation</h3><span class="badge ${b.views_reconcile ? 'live' : 'warning'}">${b.views_reconcile ? 'Views reconcile' : 'Mismatch — investigate'}</span></div><div class="card-body"><div class="comparison"><div class="compare-row"><span class="tiny">CORRECT · COUNT THE FUNDS ONCE</span><strong>${esc(b.display_usdc)} <small>USDC</small></strong></div><div class="compare-row wrong"><span class="tiny">WRONG · ADD BOTH INTERFACES</span><strong>${esc(b.double_counted_display_usdc)} <small>USDC</small></strong></div></div>${row('Account', p.address)}${row('Native raw (18 decimals)', b.native_raw_18)}${row('ERC-20 raw (6 decimals)', b.erc20_raw_6)}${row('Native precision for gas', `${b.native_gas_precision_usdc} USDC`)}${row('Residual below 1 micro-USDC', `${b.residual_usdc} USDC`)}<p class="note">${esc(b.explanation)}</p></div></div>`;
    html += `<div class="evidence-card"><div class="card-head"><h3>Transfer + gas arithmetic</h3><span class="badge">No execution</span></div><div class="card-body">${row('Hypothetical transfer', `${budget.amount_usdc} USDC`)}${row('Maximum gas reserve', `${budget.gas_budget_cap_usdc} USDC`)}${row('Required budget ceiling', `${budget.total_budget_cap_usdc} USDC`)}${budget.cap_below_observed_block_base_fee || budget.cap_below_20_gwei_submission_floor ? '<p class="warning-note">The fee cap is below the observed base fee or the documented 20 Gwei submission floor. Affordability alone does not make this fee setting usable.</p>' : ''}<p class="note">${esc(budget.note)}</p></div></div>`;
  } else if (p.state !== 'receipt_observed') {
    html += `<div class="evidence-card"><div class="card-body"><span class="badge warning">${esc(p.state.replaceAll('_', ' '))}</span>${row('Hash', p.hash)}<p class="warning-note">${esc(p.note)}</p></div></div>`;
  } else {
    const fee = p.fee, t = p.transfers;
    html += `<div class="metrics">${metric('Exact receipt gas charge', fee.fee_usdc, `${fee.gas_used.toLocaleString('en-US')} gas × ${fee.effective_gas_price_gwei} Gwei`)}${metric('Canonical gross movement', t.canonical_gross_usdc, `${t.system_count} system events · not a balance delta`)}${metric('Duplicate overcount avoided', t.duplicate_overcount_usdc, `${t.paired_count} ERC-20 mirrors matched`)}</div>`;
    html += `<div class="evidence-card"><div class="card-head"><h3>Receipt & gas cost</h3><span class="badge ${fee.status === 'succeeded' ? 'live' : 'warning'}">${esc(fee.status)}</span></div><div class="card-body">${row('Transaction', p.hash)}${row('From', p.from)}${row('To', p.to || 'Contract creation')}${row('Gas used / limit', `${fee.gas_used} / ${fee.gas_limit}`)}${row('Base fee component', fee.base_fee_component_usdc === null ? 'Unavailable' : `${fee.base_fee_component_usdc} USDC`)}${row('Tip component', fee.tip_component_usdc === null ? 'Unavailable' : `${fee.tip_component_usdc} USDC`)}<p class="note">Gas has no Transfer event. It must be calculated separately from gasUsed × effectiveGasPrice. No failure cause is guessed from a receipt alone.</p></div></div>`;
    html += `<div class="evidence-card"><div class="card-head"><h3>Canonical USDC movements</h3><span class="badge">${t.system_count} system / ${t.erc20_count} ERC-20</span></div><div class="card-body"><div class="comparison"><div class="compare-row"><span class="tiny">CANONICAL SYSTEM STREAM</span><strong>${esc(t.canonical_gross_usdc)} <small>USDC</small></strong></div><div class="compare-row wrong"><span class="tiny">NAIVE SUM OF BOTH STREAMS</span><strong>${esc(t.naive_two_stream_gross_usdc)} <small>USDC</small></strong></div></div><div class="table-scroll">${t.system_count ? `<table class="movements"><thead><tr><th>From → To</th><th>Amount (USDC)</th><th>System / ERC-20 log</th><th>Kind</th></tr></thead><tbody>${t.canonical_system_movements.map((m) => `<tr><td title="${esc(m.from)} → ${esc(m.to)}">${esc(short(m.from))}<br>→ ${esc(short(m.to))}</td><td class="amount">${esc(m.amount_usdc)}</td><td>#${m.system_log_index} / ${m.erc20_log_index === null ? '—' : `#${m.erc20_log_index}`}</td><td>${esc(m.kind)}</td></tr>`).join('')}</tbody></table>` : '<p class="empty">This receipt has no explicit USDC system Transfer events. That does not imply its gas cost was zero.</p>'}</div><p class="note">${esc(t.note)}</p></div></div>`;
  }
  (p.warnings || []).forEach((warning) => html += `<p class="warning-note">${esc(warning)}</p>`);
  html += evidenceFooter(doc);
  $('results').innerHTML = html;
  $('results').hidden = false;
  $('export-button').addEventListener('click', () => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([JSON.stringify(activeEvidence, null, 2) + '\n'], {type:'application/json'}));
    link.download = `arc-ledger-lens-${activeEvidence.kind}-${activeEvidence.sha256.slice(0, 12)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  });
  $('results').scrollIntoView({behavior:'smooth', block:'start'});
}
$('account-form').addEventListener('submit', (event) => {
  event.preventDefault();
  run(async () => render(await ArcLens.account($('account-address').value.trim(), $('amount').value.trim(), Number($('gas-limit').value), $('fee-cap').value.trim() || null)));
});
$('transaction-form').addEventListener('submit', (event) => {
  event.preventDefault(); run(async () => render(await ArcLens.transaction($('transaction-hash').value.trim())));
});
$('demo-button').addEventListener('click', () => run(async () => {
  const bundle = await request('./evidence/demo-bundle.json');
  await ArcLens.verify(bundle.transaction);
  await ArcLens.verify(bundle.account);
  panel('transaction');
  $('account-address').value = bundle.account.payload.address;
  $('transaction-hash').value = bundle.transaction.payload.hash;
  render(bundle.transaction, true);
}));
$('verify-form').addEventListener('submit', (event) => {
  event.preventDefault(); run(async () => {
    const file = $('evidence-file').files[0];
    if (!file || file.size > 2 * 1024 * 1024) throw new Error('Select an evidence JSON file smaller than 2 MB.');
    let doc;
    try { doc = JSON.parse(await file.text()); } catch { throw new Error('This file is not valid JSON.'); }
    const result = await ArcLens.verify(doc);
    activeEvidence = null;
    $('results').innerHTML = `<div class="evidence-card verify-grid"><span class="badge live">Integrity & arithmetic verified</span><h2>Evidence checks passed.</h2><p class="note">${esc(result.scope)}</p>${row('SHA-256', result.sha256)}</div>`;
    $('results').hidden = false;
    $('results').scrollIntoView({behavior:'smooth'});
  });
});
