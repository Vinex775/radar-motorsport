const state = { events: [], discoveries: [], sources: [], searchPresets: [], notificationPermission: false, liveScanInProgress: false };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value='') => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
const accessText = {free:'Free', subscription:'Subscription', ppv:'Pay-per-view', unknown:'Unknown'};
const statusText = {live:'Scheduled window active', upcoming:'Upcoming', unknown:'Time unknown'};
const leadStatusText = {historical_reference:'Historical reference', unverified_lead:'Unverified lead'};

function safeUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
}
function formatDate(value) {
  if (!value) return 'Time not provided';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Time not provided';
  return new Intl.DateTimeFormat('en-GB', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', timeZoneName:'short' }).format(date).replace(',', ' ·');
}
function formatLastRefresh(value) {
  if (!value) return 'Not run yet';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? 'Unavailable' : new Intl.DateTimeFormat('en-GB', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}).format(d);
}
function showToast(message, error=false) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.toggle('error', error); toast.classList.add('show');
  window.clearTimeout(showToast.timer); showToast.timer = window.setTimeout(() => toast.classList.remove('show'), 3600);
}
function setLoading(loading) {
  const button = $('#refresh-button'); button.disabled = loading; button.innerHTML = loading ? '<span class="refresh-icon">↻</span> Scanning...' : '<span class="refresh-icon">↻</span> Refresh radar';
}
function renderStats(data) {
  $('#stat-live').textContent = '—';
  $('#stat-upcoming').textContent = data.stats?.upcoming ?? 0;
  $('#stat-leads').textContent = data.stats?.leads ?? data.discoveries.length;
  $('#last-refresh').textContent = formatLastRefresh(data.last_refresh);
  $('#events-count').textContent = data.events.length;
  $('#discover-count').textContent = data.discoveries.length;
}
function renderEvents() {
  const query = $('#event-search').value.trim().toLocaleLowerCase('en-US');
  const statusFilter = $('#status-filter').value;
  const accessFilter = $('#access-filter').value;
  const filtered = state.events.filter(event => {
    const text = `${event.name} ${event.series} ${event.category} ${event.region} ${event.platform}`.toLocaleLowerCase('en-US');
    return (!query || text.includes(query)) && (statusFilter === 'all' || event.status === statusFilter) && (accessFilter === 'all' || event.access === accessFilter);
  });
  const grid = $('#event-grid');
  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">⌁</div><strong>${state.events.length ? 'No events match these filters.' : 'No events in APEX yet.'}</strong><p>${state.events.length ? 'Try removing a filter or searching for another term.' : 'Refresh the collectors or add an event manually.'}</p></div>`;
    return;
  }
  grid.innerHTML = filtered.map(event => {
    const status = statusText[event.status] || statusText.unknown;
    const access = accessText[event.access] || accessText.unknown;
    const actionUrl = safeUrl(event.stream_url) || safeUrl(event.watch_url) || safeUrl(event.source_url);
    const secondaryUrl = safeUrl(event.source_url);
    return `<article class="event-card ${event.status === 'live' ? 'is-live' : ''}">
      <div class="card-top"><span class="status-tag ${escapeHtml(event.status)}">${escapeHtml(status)}</span><span class="series-tag">${escapeHtml(event.series || 'Motorsport')}</span></div>
      <h3>${escapeHtml(event.name)}</h3><div class="event-kind">${escapeHtml(event.kind || event.category || 'Event')}</div>
      <div class="event-meta"><div class="meta-cell"><small>Local time</small><strong>${escapeHtml(formatDate(event.start_utc))}</strong></div><div class="meta-cell"><small>Region</small><strong>${escapeHtml(event.region || 'Global')}</strong></div></div>
      <div class="access-row"><span class="access-tag ${escapeHtml(event.access || 'unknown')}">${escapeHtml(access)}</span><span class="platform-text">${escapeHtml(event.platform || 'Platform unidentified')}</span></div>
      <div class="card-actions">${actionUrl ? `<a class="primary-link" href="${escapeHtml(actionUrl)}" target="_blank" rel="noopener noreferrer">${event.stream_url ? 'Open stream ↗' : 'Where to watch ↗'}</a>` : '<a class="primary-link" href="https://www.google.com/search?q='+encodeURIComponent(`${event.series} ${event.name} live stream`)+'" target="_blank" rel="noopener noreferrer">Find a stream ↗</a>'}${secondaryUrl && secondaryUrl !== actionUrl ? `<a href="${escapeHtml(secondaryUrl)}" target="_blank" rel="noopener noreferrer">Source ↗</a>` : ''}</div>
    </article>`;
  }).join('');
}
function renderDiscoveries() {
  const list = $('#discover-list');
  if (!state.discoveries.length) {
    list.innerHTML = '<div class="empty-state"><strong>No discovery leads loaded.</strong><p>Run a scan to find live-stream announcements.</p></div>'; return;
  }
  list.innerHTML = state.discoveries.map(item => {
    const url = safeUrl(item.url);
    const leadStatus = leadStatusText[item.lead_status] || 'Unverified lead';
    const historicalClass = item.lead_status === 'historical_reference' ? ' historical-reference' : '';
    return `<article class="discovery-card${historicalClass}"><div><div class="discovery-badges"><span class="status-tag ${item.lead_status === 'historical_reference' ? 'past' : 'unknown'}">${escapeHtml(leadStatus)}</span><span class="access-tag ${escapeHtml(item.access || 'unknown')}">${escapeHtml(accessText[item.access] || accessText.unknown)}</span></div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary || item.note || 'No summary available.')}</p><div class="discovery-meta"><span>${escapeHtml(item.source_name || 'External source')}</span><span>${escapeHtml(item.series || 'Motorsport')}</span><span>${escapeHtml(formatDate(item.published_utc || item.published))}</span></div><small>${escapeHtml(item.note || 'Editorial lead only — not a verified live stream.')}</small></div><div class="discovery-side"><span class="platform-text">${escapeHtml(item.platform || 'Platform unidentified')}</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>` : ''}</div></article>`;
  }).join('');
}
function renderSearchPresets() {
  const select = $("#category-preset");
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">Choose a discipline to fill the search</option>' + state.searchPresets.map(preset => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`).join('');
  if (state.searchPresets.some(preset => preset.id === current)) select.value = current;
}
function renderSources() {
  $('#source-grid').innerHTML = state.sources.map(source => {
    const url = safeUrl(source.url); const evidence = safeUrl(source.official_info);
    return `<article class="source-card"><div class="source-card-top"><h3>${escapeHtml(source.platform)}</h3><span class="access-tag ${escapeHtml(source.access)}">${escapeHtml(accessText[source.access] || accessText.unknown)}</span></div><div class="source-series">${escapeHtml(source.series)}</div><div class="source-region">${escapeHtml(source.region)}</div><p>${escapeHtml(source.note)}</p><div class="source-evidence">${source.confidence === "official" ? "OFFICIAL REFERENCE" : source.confidence === "regional" ? "REGIONAL GUIDE" : "SOURCE / COMMUNITY"} · checked on ${escapeHtml(source.last_checked || "not provided")}</div><div class="source-actions">${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open platform ↗</a>` : ''}${evidence ? `<a href="${escapeHtml(evidence)}" target="_blank" rel="noopener noreferrer">View reference</a>` : ''}</div></article>`;
  }).join('') || '<div class="empty-state">No sources added.</div>';
}
function renderDashboard(data) {
  state.events = data.events || []; state.discoveries = data.discoveries || []; state.sources = data.sources || []; state.searchPresets = data.search_presets || [];
  renderStats(data); renderEvents(); renderDiscoveries(); renderSources(); renderSearchPresets(); checkUpcomingAlerts();
}
async function fetchDashboard() {
  const response = await fetch('/api/dashboard'); if (!response.ok) throw new Error('Could not load the dashboard.');
  renderDashboard(await response.json());
}
async function refreshRadar() {
  setLoading(true);
  try {
    // Live broadcasts are the primary purpose of APEX: scan them first so a
    // slower calendar/news refresh never delays the answer to "what is live now?".
    const live = await scanLiveNow(false);
    const response = await fetch('/api/refresh', {method:'POST'});
    const result = await response.json();
    await fetchDashboard();
    // Dashboard rendering resets summary counters; repaint Live Now from the
    // just-populated provider cache without spending additional API quota.
    await scanLiveNow(false);
    if (result.errors?.length) showToast(`Live scan complete (${live?.count ?? 0} active streams). Schedule/news warnings: ${result.errors.join(' | ')}`, true);
    else showToast(`Radar refreshed: ${live?.count ?? 0} active broadcasts now, ${result.events_updated} scheduled events, ${result.discoveries_updated} discovery leads.`);
  } catch (error) { showToast(error.message || 'Refresh failed.', true); }
  finally { setLoading(false); }
}
function activateTab(tab) {
  document.querySelectorAll('.tab-button').forEach(btn => btn.classList.toggle('active', btn.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === `panel-${tab}`));
}
function openDialog() { $('#form-message').textContent = ''; $('#event-dialog').showModal(); }
function closeDialog() { $('#event-dialog').close(); }
async function submitManualEvent(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget); const payload = Object.fromEntries(form.entries());
  for (const key of ['end','stream_url','watch_url','category','region','kind']) if (!payload[key]) payload[key] = null;
  const message = $('#form-message'); message.textContent = 'Saving...';
  try {
    const response = await fetch('/api/events', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Could not save the event.');
    closeDialog(); event.currentTarget.reset(); await fetchDashboard(); showToast('Event added to APEX.'); activateTab('events');
  } catch (error) { message.textContent = error.message; }
}
async function requestNotifications() {
  if (!('Notification' in window)) { showToast('This browser does not support notifications.', true); return; }
  const permission = await Notification.requestPermission();
  if (permission === 'granted') { state.notificationPermission = true; $('#notify-button').textContent = 'Alerts enabled'; showToast('Alerts are enabled while APEX remains open.'); checkUpcomingAlerts(); }
  else showToast('Notification permission was not granted.', true);
}
function checkUpcomingAlerts() {
  if (!('Notification' in window) || Notification.permission !== 'granted') return;
  const now = Date.now();
  state.events.forEach(event => {
    if (!event.start_utc || event.status !== 'upcoming') return;
    const start = new Date(event.start_utc).getTime(); const diff = start - now;
    if (diff > 0 && diff <= 15*60*1000) {
      const key = `radar-alert-${event.id || event.external_id}-${event.start_utc}`;
      if (!sessionStorage.getItem(key)) {
        new Notification(`Starts soon: ${event.name}`, {body:`${event.series} · ${formatDate(event.start_utc)} · ${event.platform || 'platform TBC'}`});
        sessionStorage.setItem(key, '1');
      }
    }
  });
}
$('#refresh-button').addEventListener('click', refreshRadar);
$('#notify-button').addEventListener('click', requestNotifications);
$('#event-search').addEventListener('input', renderEvents);
$('#status-filter').addEventListener('change', renderEvents);
$('#access-filter').addEventListener('change', renderEvents);
document.querySelectorAll('.tab-button').forEach(button => button.addEventListener('click', () => activateTab(button.dataset.tab)));
$('#add-event-button').addEventListener('click', openDialog); $('#add-event-button-bottom').addEventListener('click', openDialog);
$('#close-dialog').addEventListener('click', closeDialog); $('#cancel-dialog').addEventListener('click', closeDialog);
$('#event-form').addEventListener('submit', submitManualEvent);
function currentSearchTerm() {
  const category = $("#live-search").value.trim() || "motorsport";
  const region = $("#region-search").value.trim();
  return [category, region].filter(Boolean).join(" ").slice(0, 220);
}
function openLiveSearch(target) {
  const term = currentSearchTerm();
  const encoded = encodeURIComponent(`${term} live stream`);
  const urls = {
    youtube: `https://www.youtube.com/results?search_query=${encoded}`,
    twitch: `https://www.twitch.tv/search?term=${encodeURIComponent(term)}`,
    web: `https://www.google.com/search?q=${encodeURIComponent(`\"${term}\" (live OR livestream OR \"watch live\")`)}`
  };
  const url = urls[target]; if (url) window.open(url, '_blank', 'noopener,noreferrer');
}
function renderLiveNow(data) {
  const target = $('#platform-results');
  const items = data.items || [];
  const platforms = data.platforms || {};
  const platformSummary = Object.entries(platforms).map(([name, status]) => {
    const stateLabel = status.ok ? 'CONNECTED' : status.configured ? 'ERROR' : 'NOT CONFIGURED';
    const stateClass = status.ok ? 'connected' : status.configured ? 'failed' : 'disabled';
    const cached = status.cached ? ' · cached' : '';
    return `<span class="platform-source ${stateClass}" title="${escapeHtml(status.message || stateLabel)}"><strong>${escapeHtml(name)}</strong> ${escapeHtml(stateLabel)} · ${Number(status.count || 0)} found${cached}</span>`;
  }).join('');

  $('#stat-live').textContent = Number(data.count ?? items.length);
  $('#live-count').textContent = Number(data.count ?? items.length);

  const sourceHtml = platformSummary ? `<div class="platform-source-list">${platformSummary}</div>` : '';
  const heading = `<div class="platform-results-heading">${Number(data.count ?? items.length)} ACTIVE BROADCAST(S) FOUND</div>${sourceHtml}`;
  const explanation = `<p class="data-note">${escapeHtml(data.note || 'Platform APIs report these channels as live. Open the stream to verify the actual race feed and access conditions.')}</p>`;

  if (!items.length) {
    const configured = Number(data.configured_sources || 0);
    const hasErrors = Object.values(platforms).some(status => status.configured && !status.ok);
    const emptyMessage = hasErrors
      ? 'One or more connected platforms returned an error. Check the provider status above and verify the API credentials in your .env file.'
      : configured
        ? 'No matching motorsport streams are being reported live right now. Try another scan shortly; small local streams may not be indexed by platform search.'
        : 'No live platform API is configured yet. Add your API credentials to the .env file to enable automatic discovery across YouTube, Twitch, and Kick.';
    target.innerHTML = `${heading}${explanation}<div class="platform-empty">${escapeHtml(emptyMessage)}</div>`;
  } else {
    const rows = items.map(item => {
      const meta = [item.platform, item.category || 'Motorsport', item.started_at ? `Started ${formatDate(item.started_at)}` : '', item.viewers ? `${Number(item.viewers).toLocaleString('en-US')} viewers` : ''].filter(Boolean).join(' · ');
      const link = safeUrl(item.url);
      return `<article class="platform-result live-result"><div class="live-result-copy"><strong>${escapeHtml(item.title || 'Live motorsport stream')}</strong><span>${escapeHtml(item.channel || 'Unknown channel')} · ${escapeHtml(meta)}</span></div><span class="status-tag live">LIVE NOW · API</span><span class="access-tag unknown">Access unknown</span>${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">Watch ↗</a>` : ''}</article>`;
    }).join('');
    target.innerHTML = `${heading}${explanation}${rows}`;
  }

  const scannedAt = data.scanned_at ? new Date(Number(data.scanned_at) * 1000) : new Date();
  $('#last-refresh').textContent = formatLastRefresh(scannedAt.toISOString());
  $('#live-last-scan').textContent = `Last live scan: ${new Intl.DateTimeFormat('en-GB', {hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(scannedAt)} · Auto-check every 5 minutes · YouTube cache: 20 minutes to respect its daily API limit.`;
}

async function scanLiveNow(showToastOnComplete = true) {
  if (state.liveScanInProgress) return null;
  state.liveScanInProgress = true;
  const button = $('#scan-live-button');
  const original = button?.textContent || 'Scan all platforms';
  if (button) { button.disabled = true; button.textContent = 'Scanning platforms...'; }
  try {
    const term = currentSearchTerm();
    const response = await fetch(`/api/live-now?q=${encodeURIComponent(term)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Live scan failed.');
    renderLiveNow(data);
    if (showToastOnComplete) {
      if (data.count) showToast(`Found ${data.count} active broadcasts across connected platforms.`);
      else if (!data.configured_sources) showToast('No live platform APIs configured yet. See .env.example and README.');
      else showToast('No matching motorsport streams are live right now.');
    }
    return data;
  } catch (error) {
    $('#platform-results').innerHTML = `<div class="platform-empty">${escapeHtml(error.message || 'Could not scan live platforms.')}</div>`;
    if (showToastOnComplete) showToast(error.message || 'Live scan failed.', true);
    return null;
  } finally {
    state.liveScanInProgress = false;
    if (button) { button.disabled = false; button.textContent = original; }
  }
}

async function searchNewsRadar() {
  const term = currentSearchTerm();
  const button = $("#news-search"); const original = button.textContent;
  button.disabled = true; button.textContent = "Searching...";
  try {
    const response = await fetch(`/api/discover-search?q=${encodeURIComponent(term)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "APEX search failed.");
    await fetchDashboard();
    activateTab("discover");
    showToast(data.count ? `${data.count} leads found for: ${term}` : `No recent news found for: ${term}`);
  } catch (error) {
    showToast(error.message || "Could not search this discipline.", true);
  } finally {
    button.disabled = false; button.textContent = original;
  }
}
function applySearchPreset() {
  const selected = $("#category-preset").value;
  const preset = state.searchPresets.find(item => item.id === selected);
  if (preset) {
    $("#live-search").value = preset.query;
    $("#live-search").focus();
  }
}

$('#news-search').addEventListener('click', searchNewsRadar);
$('#category-preset').addEventListener('change', applySearchPreset);
$('#youtube-search').addEventListener('click', () => openLiveSearch('youtube'));
$('#scan-live-button').addEventListener('click', () => scanLiveNow(true));
$('#twitch-search').addEventListener('click', () => openLiveSearch('twitch'));
$('#web-search').addEventListener('click', () => openLiveSearch('web'));
$('#local-clock').textContent = `LOCAL TIME · ${new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit'}).format(new Date())}`;
fetchDashboard().then(() => scanLiveNow(false)).catch(error => showToast(error.message, true));
window.setInterval(checkUpcomingAlerts, 60_000);
window.setInterval(() => scanLiveNow(false), 5 * 60_000);
