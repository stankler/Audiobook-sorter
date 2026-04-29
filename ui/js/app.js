function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s ?? '');
  return d.innerHTML;
}

const API = (action, opts = {}) => {
  const url = `/plugins/audiobook-organizer/api.php?action=${action}`;
  if (opts.body) {
    const form = new URLSearchParams();
    if (typeof csrf_token !== 'undefined') form.set('csrf_token', csrf_token);
    form.set('payload', opts.body);
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form.toString(),
    });
  }
  return fetch(url, { method: 'GET' });
};

document.querySelectorAll('.ao-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.ao-tab, .ao-tabcontent').forEach(el => el.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'review') { loadReview(); updateQueuedCount(); }
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

let _destPath = '';

API('config_get').then(r => r.json()).then(cfg => {
  if (cfg.stt_engine && sttSelect) { sttSelect.value = cfg.stt_engine; updateSttVisibility(); }
  if (cfg.whisper_model) document.getElementById('cfg-whisper-model').value = cfg.whisper_model;
  if (cfg.confidence_threshold && threshold) {
    threshold.value = Math.round(cfg.confidence_threshold * 100);
    thresholdVal.textContent = cfg.confidence_threshold.toFixed(2);
  }
  _destPath = cfg.dest_path || '';
});

function sanitizePath(s) {
  return (s || '').replace(/[<>:"/\\|?*]/g, '').replace(/\s+/g, ' ').trim();
}

function buildProposedPath(author, title, series, seriesNum) {
  const root = _destPath.replace(/\/$/, '');
  const a = sanitizePath(author);
  const t = sanitizePath(title);
  if (!a || !t) return '';
  if (series && seriesNum != null && seriesNum !== '' && !isNaN(seriesNum)) {
    const s = sanitizePath(series);
    const n = Number(seriesNum);
    const numStr = Number.isInteger(n) ? String(n) : String(n);
    return `${root}/${a}/${s}/${numStr} - ${t}`;
  }
  return `${root}/${a}/${t}`;
}

document.getElementById('cfg-save-btn')?.addEventListener('click', async () => {
  const payload = {
    source_path: document.getElementById('cfg-source').value,
    dest_path: document.getElementById('cfg-dest').value,
    google_books_api_key: document.getElementById('cfg-gbkey').value,
    anthropic_api_key: document.getElementById('cfg-anthropickey').value,
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
  document.getElementById('scan-results').style.display = 'none';
  document.getElementById('scan-complete-msg').textContent = '';
  document.getElementById('go-to-review-btn').style.display = 'none';
  await API('scan_start', { body: '{}' });
  startPolling();
});

document.getElementById('scan-cancel-btn')?.addEventListener('click', async () => {
  await API('scan_cancel', { body: '{}' });
});

document.getElementById('scan-undo-btn')?.addEventListener('click', async () => {
  if (!confirm('Undo the last scan? This will move files back to their original locations.')) return;
  const r = await API('scan_undo', { body: '{}' });
  const data = await r.json();
  alert(data.error ? 'Error: ' + data.error : `Undone ${data.reversed} file(s).`);
});

document.getElementById('go-to-review-btn')?.addEventListener('click', () => {
  document.querySelector('[data-tab=review]').click();
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
  const cancelBtn = document.getElementById('scan-cancel-btn');

  if (state.status === 'scanning') {
    progress.style.display = '';
    results.style.display = 'none';
    current.textContent = state.current_book || '...';
    if (state.total_books > 0) bar.value = Math.round((state.processed_books / state.total_books) * 100);
    if (cancelBtn) cancelBtn.style.display = '';
  } else {
    if (cancelBtn) cancelBtn.style.display = 'none';
  }

  if (state.status === 'complete') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    results.style.display = '';
    const count = (state.manual_review || []).length;
    document.getElementById('scan-complete-msg').textContent =
      `Scan complete. ${count} book(s) ready for review.`;
    document.getElementById('go-to-review-btn').style.display = '';
  } else if (state.status === 'cancelled') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    results.style.display = '';
    document.getElementById('scan-complete-msg').textContent = 'Scan cancelled.';
  } else if (state.status === 'error') {
    clearInterval(pollInterval);
    progress.style.display = 'none';
    if (state.error) alert('Scan error: ' + state.error);
  }
}

async function loadReview() {
  const r = await API('manual_review');
  const items = await r.json();
  const container = document.getElementById('review-container');
  container.innerHTML = '';
  if (!Array.isArray(items) || !items.length) {
    container.innerHTML = '<p>No items pending review.</p>';
    return;
  }
  // Build author → known series map across all scan items
  const authorSeriesMap = {};
  items.forEach(item => {
    (item.candidates || []).forEach(c => {
      if (c.series) {
        const key = (c.author || '').toLowerCase().trim();
        if (key) {
          if (!authorSeriesMap[key]) authorSeriesMap[key] = new Set();
          authorSeriesMap[key].add(c.series);
        }
      }
    });
  });
  items.forEach(item => renderReviewItem(container, item, authorSeriesMap));
}

let _openDropdown = null;
function attachDropdown(input, options, onChange) {
  if (!input || !options.length) return;
  const drop = document.createElement('div');
  drop.className = 'rv-dropdown';
  drop.style.display = 'none';
  options.forEach(val => {
    const item = document.createElement('div');
    item.className = 'rv-dropdown-item';
    item.textContent = val;
    item.addEventListener('mousedown', e => {
      e.preventDefault();
      input.value = val;
      drop.style.display = 'none';
      _openDropdown = null;
      if (onChange) onChange();
    });
    drop.appendChild(item);
  });
  input.parentNode.style.position = 'relative';
  input.parentNode.appendChild(drop);
  input.addEventListener('focus', () => {
    if (_openDropdown && _openDropdown !== drop) _openDropdown.style.display = 'none';
    drop.style.display = '';
    _openDropdown = drop;
  });
  input.addEventListener('blur', () => {
    setTimeout(() => { drop.style.display = 'none'; if (_openDropdown === drop) _openDropdown = null; }, 150);
  });
}

function renderReviewItem(container, item, authorSeriesMap = {}) {
  const id = item.id;
  const candidates = item.candidates || [];
  const div = document.createElement('div');
  div.className = 'review-card';
  div.id = `review-${id}`;

  const uniq = (arr) => [...new Set(arr.filter(Boolean))];
  const titles  = uniq(candidates.map(c => c.title));
  const authors = uniq(candidates.map(c => c.author));
  const nums    = uniq(candidates.map(c => c.series_number != null ? String(c.series_number) : null));

  // Series from this book's candidates + all series known for same authors across scan
  const seriesSet = new Set(candidates.map(c => c.series).filter(Boolean));
  authors.forEach(a => {
    const known = authorSeriesMap[(a || '').toLowerCase().trim()];
    if (known) known.forEach(s => seriesSet.add(s));
  });
  const seriesOpts = [...seriesSet];

  div.innerHTML = `
    <div class="review-folder">${esc(item.book_group.folder)} <span class="review-filecount">(${item.book_group.files.length} file(s))</span></div>
    ${candidates.length
      ? `<button class="btn-toggle-cands" data-id="${esc(id)}">▶ Show ${candidates.length} candidate(s)</button><ul class="review-gb-results" id="rv-cands-${esc(id)}" style="display:none"></ul>`
      : '<p class="review-no-match">No candidates found automatically.</p>'}
    <div class="review-fields">
      <label>Author <input id="rv-author-${esc(id)}" type="text" placeholder="Author" autocomplete="off"></label>
      <label>Series <input id="rv-series-${esc(id)}" type="text" placeholder="Series (optional)" autocomplete="off"></label>
      <label>Title <input id="rv-title-${esc(id)}" type="text" placeholder="Title" autocomplete="off"></label>
      <label>Series # <input id="rv-num-${esc(id)}" type="number" step="0.5" placeholder="0"></label>
    </div>
    <div class="review-path-preview" id="rv-path-${esc(id)}"></div>
    <div class="review-actions">
      <button class="btn-primary" data-action="apply">Apply</button>
      <button class="btn-secondary" data-action="stt">Transcribe (1 min)</button>
      <button class="btn-secondary" data-action="skip">Skip</button>
    </div>
    <pre id="rv-stt-${esc(id)}" class="review-stt-log" style="display:none"></pre>
  `;

  const updatePath = () => {
    const preview = div.querySelector(`#rv-path-${id}`);
    if (!preview) return;
    const p = buildProposedPath(
      div.querySelector(`#rv-author-${id}`).value,
      div.querySelector(`#rv-title-${id}`).value,
      div.querySelector(`#rv-series-${id}`).value,
      div.querySelector(`#rv-num-${id}`).value,
    );
    preview.textContent = p || '';
    preview.style.display = p ? '' : 'none';
  };

  ['rv-title', 'rv-author', 'rv-series', 'rv-num'].forEach(prefix => {
    div.querySelector(`#${prefix}-${id}`)?.addEventListener('input', updatePath);
  });

  attachDropdown(div.querySelector(`#rv-title-${id}`), titles, updatePath);
  attachDropdown(div.querySelector(`#rv-author-${id}`), authors, updatePath);
  attachDropdown(div.querySelector(`#rv-series-${id}`), seriesOpts, updatePath);

  // Auto-fill from best non-parsed candidate
  const best = candidates.find(c => c.confidence > 0);
  if (best) {
    div.querySelector(`#rv-title-${id}`).value = best.title;
    div.querySelector(`#rv-author-${id}`).value = best.author;
    div.querySelector(`#rv-series-${id}`).value = best.series || '';
    div.querySelector(`#rv-num-${id}`).value = best.series_number != null ? best.series_number : '';
  }
  updatePath();

  if (candidates.length) {
    const ul = div.querySelector(`#rv-cands-${id}`);
    const toggleBtn = div.querySelector('.btn-toggle-cands');
    toggleBtn?.addEventListener('click', () => {
      const open = ul.style.display !== 'none';
      ul.style.display = open ? 'none' : '';
      toggleBtn.textContent = (open ? '▶ Show ' : '▼ Hide ') + `${candidates.length} candidate(s)`;
    });
    candidates.forEach(c => {
      const li = document.createElement('li');
      const btn = document.createElement('button');
      btn.className = 'btn-result';
      const seriesStr = c.series ? ` (${c.series}${c.series_number != null ? ' #' + c.series_number : ''})` : '';
      const pct = c.confidence ? ` [${Math.round(c.confidence * 100)}%]` : '';
      btn.textContent = `[${c.source}]${pct} ${c.title} — ${c.author}${seriesStr}`;
      btn.addEventListener('click', () => {
        div.querySelector(`#rv-title-${id}`).value = c.title;
        div.querySelector(`#rv-author-${id}`).value = c.author;
        div.querySelector(`#rv-series-${id}`).value = c.series || '';
        div.querySelector(`#rv-num-${id}`).value = c.series_number != null ? c.series_number : '';
        updatePath();
      });
      li.appendChild(btn);
      ul.appendChild(li);
    });
  }

  div.querySelector('[data-action=apply]').addEventListener('click', () => reviewApply(id));
  div.querySelector('[data-action=skip]').addEventListener('click', () => moveUnidentified(id));
  div.querySelector('[data-action=stt]').addEventListener('click', async () => {
    const btn = div.querySelector('[data-action=stt]');
    const log = div.querySelector(`#rv-stt-${id}`);
    btn.disabled = true;
    btn.textContent = 'Transcribing…';
    log.style.display = '';
    log.textContent = 'Running STT on first 60 seconds…';
    const r = await API(`transcribe&id=${id}`, { body: '{}' });
    const data = await r.json();
    btn.disabled = false;
    btn.textContent = 'Transcribe (1 min)';
    const errMsg = data.error || data.detail;
    log.textContent = errMsg ? 'Error: ' + errMsg : (data.transcript || '(no transcript)');
  });

  container.appendChild(div);
}

async function reviewApply(id) {
  const title = document.getElementById(`rv-title-${id}`).value.trim();
  const author = document.getElementById(`rv-author-${id}`).value.trim();
  const series = document.getElementById(`rv-series-${id}`).value.trim();
  const series_number = parseFloat(document.getElementById(`rv-num-${id}`).value) || null;
  if (!title || !author) { alert('Title and author are required.'); return; }
  const payload = { title, author, series: series || null, series_number };
  const r = await API(`review_identify&id=${id}`, { body: JSON.stringify(payload) });
  const data = await r.json();
  if (data.error) { alert('Error: ' + data.error); return; }
  document.getElementById(`review-${id}`)?.remove();
  if (!document.querySelector('#review-container .review-card')) {
    document.getElementById('review-container').innerHTML = '<p>No items pending review.</p>';
  }
  updateQueuedCount();
}

let _queuedMoves = [];

async function updateQueuedCount() {
  const r = await API('scan_status');
  const state = await r.json();
  _queuedMoves = state.proposed_moves || [];
  const count = _queuedMoves.length;
  const btn = document.getElementById('review-apply-btn');
  const countEl = document.getElementById('review-queued-count');
  if (btn && countEl) {
    countEl.textContent = count;
    btn.style.display = count > 0 ? '' : 'none';
  }
  renderQueuedList();
}

function renderQueuedList() {
  const list = document.getElementById('review-queued-list');
  if (!list) return;
  list.innerHTML = '';
  if (!_queuedMoves.length) { list.style.display = 'none'; return; }
  list.style.display = '';
  _queuedMoves.forEach(m => {
    const div = document.createElement('div');
    div.className = 'queued-move-item';
    div.id = `qm-${m.id}`;
    div.innerHTML = `<span class="qm-src">${esc(m.book_group.folder)}</span><span class="qm-arrow"> → </span><span class="qm-dst">${esc(m.proposed_path || '?')}</span><span class="qm-status"></span>`;
    list.appendChild(div);
  });
}

document.getElementById('review-apply-btn')?.addEventListener('click', async () => {
  if (!_queuedMoves.length) { alert('No queued moves.'); return; }
  const write_tags = document.getElementById('write-tags-toggle')?.checked || false;
  const btn = document.getElementById('review-apply-btn');
  const progress = document.getElementById('review-move-progress');
  const bar = document.getElementById('review-progress-bar');
  const label = document.getElementById('review-progress-label');
  btn.disabled = true;
  progress.style.display = '';

  const totalFiles = _queuedMoves.reduce((sum, m) => sum + (m.book_group.files || []).length, 0);
  bar.max = totalFiles;
  bar.value = 0;

  let movedBooks = 0, errorBooks = 0, filesDone = 0;
  for (const m of [..._queuedMoves]) {
    const itemEl = document.getElementById(`qm-${m.id}`);
    if (itemEl) itemEl.classList.add('qm-moving');
    const files = m.book_group.files || [];
    let bookFailed = false;

    for (let i = 0; i < files.length; i++) {
      const fname = files[i].split('/').pop();
      label.textContent = `File ${filesDone + 1}/${totalFiles}: ${fname}`;
      const isLast = i === files.length - 1;
      const r = await API('move_file', { body: JSON.stringify({ move_id: m.id, file_path: files[i], cleanup: isLast }) });
      const data = await r.json();
      if (data.error || data.detail) bookFailed = true;
      filesDone++;
      bar.value = filesDone;
    }

    // Finalize: write tags + update DB/state
    const finalR = await API('scan_approve', { body: JSON.stringify({ approved_ids: [m.id], write_tags, already_moved: true }) });
    const finalData = await finalR.json();
    if (finalData.error || (finalData.errors && finalData.errors.length)) bookFailed = true;

    if (itemEl) {
      itemEl.classList.remove('qm-moving');
      itemEl.classList.add(bookFailed ? 'qm-error' : 'qm-done');
      itemEl.querySelector('.qm-status').textContent = bookFailed ? ' ✗' : ' ✓';
    }
    if (bookFailed) errorBooks++; else movedBooks++;
  }

  btn.disabled = false;
  progress.style.display = 'none';
  label.textContent = '';
  alert(`Done. Moved: ${movedBooks} book(s). Errors: ${errorBooks}`);
  updateQueuedCount();
});

async function moveUnidentified(id) {
  if (!confirm('Move this book to _unidentified folder?')) return;
  const r = await API(`move_unidentified&id=${id}`, { body: '{}' });
  const data = await r.json();
  if (data.error) { alert('Error: ' + data.error); return; }
  document.getElementById(`review-${id}`)?.remove();
  if (!document.getElementById('review-container').children.length) {
    document.getElementById('review-container').innerHTML = '<p>No items pending review.</p>';
  }
}

async function loadLogs() {
  const r = await API('logs');
  const data = await r.json();
  document.getElementById('logs-content').textContent = (data.lines || []).join('\n');
}
document.getElementById('logs-refresh-btn')?.addEventListener('click', loadLogs);

// Folder browser
let _browseTarget = null;

async function openBrowser(targetId, startPath) {
  _browseTarget = targetId;
  document.getElementById('browse-modal').style.display = '';
  await browseLoad(startPath || document.getElementById(targetId).value || '/mnt');
}

async function browseLoad(path) {
  const r = await API(`browse&path=${encodeURIComponent(path)}`);
  const data = await r.json();
  if (data.detail || data.error) {
    if (path !== '/mnt') { await browseLoad('/mnt'); return; }
    alert('Browse error: ' + (data.detail || data.error));
    return;
  }

  document.getElementById('browse-path').textContent = data.path;
  document.getElementById('browse-select').onclick = () => {
    document.getElementById(_browseTarget).value = data.path;
    closeBrowser();
  };

  const list = document.getElementById('browse-list');
  list.innerHTML = '';
  if (data.path !== data.parent) {
    const up = document.createElement('li');
    up.className = 'up';
    up.textContent = '↑ ..';
    up.onclick = () => browseLoad(data.parent);
    list.appendChild(up);
  }
  data.entries.forEach(e => {
    const li = document.createElement('li');
    li.textContent = '📁 ' + e.name;
    li.onclick = () => browseLoad(e.path);
    list.appendChild(li);
  });
}

function closeBrowser() {
  document.getElementById('browse-modal').style.display = 'none';
}

document.getElementById('browse-cancel')?.addEventListener('click', closeBrowser);
document.getElementById('browse-backdrop')?.addEventListener('click', closeBrowser);
document.querySelectorAll('.btn-browse').forEach(btn => {
  btn.addEventListener('click', () => openBrowser(btn.dataset.target));
});
