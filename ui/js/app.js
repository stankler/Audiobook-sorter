function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s ?? '');
  return d.innerHTML;
}

const API = (action, opts = {}) =>
  fetch(`/plugins/audiobook-organizer/api.php?action=${action}`, { method: opts.body ? 'POST' : 'GET', ...opts });

document.querySelectorAll('.ao-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ao-tab, .ao-tabcontent').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'review') loadReview();
    if (btn.dataset.tab === 'logs') loadLogs();
  });
});

const threshold = document.getElementById('cfg-threshold');
const thresholdVal = document.getElementById('cfg-threshold-val');
if (threshold) {
  thresholdVal.textContent = (threshold.value / 100).toFixed(2);
  threshold.addEventListener('input', () => {
    thresholdVal.textContent = (threshold.value / 100).toFixed(2);
  });
}

const sttSelect = document.getElementById('cfg-stt');
function updateSttVisibility() {
  const val = sttSelect.value;
  document.getElementById('cfg-whisper-row').style.display = val === 'local_whisper' ? '' : 'none';
  document.getElementById('cfg-apikey-row').style.display = ['openai_api', 'google_speech'].includes(val) ? '' : 'none';
}
if (sttSelect) { sttSelect.addEventListener('change', updateSttVisibility); updateSttVisibility(); }

fetch('?action=config_get').then(r => r.json()).then(cfg => {
  if (cfg.stt_engine && sttSelect) { sttSelect.value = cfg.stt_engine; updateSttVisibility(); }
  if (cfg.whisper_model) document.getElementById('cfg-whisper-model').value = cfg.whisper_model;
  if (cfg.confidence_threshold && threshold) {
    threshold.value = Math.round(cfg.confidence_threshold * 100);
    thresholdVal.textContent = cfg.confidence_threshold.toFixed(2);
  }
});

document.getElementById('cfg-save-btn')?.addEventListener('click', async () => {
  const payload = {
    source_path: document.getElementById('cfg-source').value,
    dest_path: document.getElementById('cfg-dest').value,
    google_books_api_key: document.getElementById('cfg-gbkey').value,
    stt_engine: sttSelect.value,
    whisper_model: document.getElementById('cfg-whisper-model').value,
    stt_api_key: document.getElementById('cfg-sttkey').value,
    confidence_threshold: parseFloat(threshold.value) / 100,
  };
  const r = await API('config_save', { body: JSON.stringify(payload) });
  const data = await r.json();
  document.getElementById('cfg-status').textContent = data.error ? 'Error: ' + data.error : 'Saved.';
});

let pollInterval = null;

document.getElementById('scan-start-btn')?.addEventListener('click', async () => {
  await API('scan_start', { body: '{}' });
  startPolling();
});

document.getElementById('scan-undo-btn')?.addEventListener('click', async () => {
  if (!confirm('Undo the last scan? This will move files back to their original locations.')) return;
  const r = await API('scan_undo', { body: '{}' });
  const data = await r.json();
  alert(data.error ? 'Error: ' + data.error : `Undone ${data.reversed} file(s).`);
});

function startPolling() {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(pollScanStatus, 2000);
  pollScanStatus();
}

async function pollScanStatus() {
  const r = await API('scan_status');
  const state = await r.json();

  const progress = document.getElementById('scan-progress');
  const results = document.getElementById('scan-results');
  const bar = document.getElementById('scan-bar');
  const current = document.getElementById('scan-current');

  if (state.status === 'scanning') {
    progress.style.display = '';
    results.style.display = 'none';
    current.textContent = state.current_book || '...';
    if (state.total_books > 0) bar.value = Math.round((state.processed_books / state.total_books) * 100);
  } else if (state.status === 'awaiting_approval') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    results.style.display = '';
    renderResults(state.proposed_moves);
  } else if (state.status === 'complete' || state.status === 'error') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    if (state.error) alert('Scan error: ' + state.error);
  }
}

function renderResults(moves) {
  const tbody = document.getElementById('results-body');
  tbody.innerHTML = '';
  moves.forEach(move => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><input type="checkbox" class="approve-cb" data-id="${esc(move.id)}" checked></td>
      <td style="font-size:12px">${esc(move.book_group.folder)}</td>
      <td style="font-size:12px">${esc(move.proposed_path || '—')}</td>
      <td>${move.match ? Math.round(move.match.confidence * 100) + '%' : '—'}</td>
      <td>${move.match ? esc(move.match.source) : '—'}</td>
    `;
    tbody.appendChild(tr);
  });
}

document.getElementById('apply-btn')?.addEventListener('click', async () => {
  const approved_ids = [...document.querySelectorAll('.approve-cb:checked')].map(cb => cb.dataset.id);
  const write_tags = document.getElementById('write-tags-toggle').checked;
  const r = await API('scan_approve', { body: JSON.stringify({ approved_ids, write_tags }) });
  const data = await r.json();
  if (data.error) { alert('Error: ' + data.error); return; }
  alert(`Done. Moved: ${data.moved}. Errors: ${(data.errors || []).length}`);
  document.getElementById('scan-results').style.display = 'none';
});

async function loadReview() {
  const r = await API('manual_review');
  const items = await r.json();
  const tbody = document.getElementById('review-body');
  tbody.innerHTML = '';
  if (!items.length) { tbody.innerHTML = '<tr><td colspan="3">No items pending review.</td></tr>'; return; }
  items.forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${esc(item.book_group.folder)}</td>
      <td>${item.book_group.files.length} file(s)</td>
      <td><button onclick="moveUnidentified('${esc(item.id)}')">Move to _unidentified</button></td>
    `;
    tbody.appendChild(tr);
  });
}

async function moveUnidentified(id) {
  if (!confirm('Move this book to _unidentified folder?')) return;
  const r = await fetch(`?action=move_unidentified&id=${id}`, { method: 'POST', body: '{}' });
  const data = await r.json();
  if (data.error) { alert('Error: ' + data.error); return; }
  loadReview();
}

async function loadLogs() {
  const r = await API('logs');
  const data = await r.json();
  document.getElementById('logs-content').textContent = (data.lines || []).join('\n');
}
document.getElementById('logs-refresh-btn')?.addEventListener('click', loadLogs);
