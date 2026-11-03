const state = { events: [], discoveries: [], sources: [], searchPresets: [], notificationPermission: false };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value='') => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
const accessText = {free:'Grátis', subscription:'Assinatura', ppv:'Pay-per-view', unknown:'Não confirmado'};
const statusText = {live:'Janela em andamento', upcoming:'Próximo', unknown:'Horário não confirmado'};

function safeUrl(value) {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
}
function formatDate(value) {
  if (!value) return 'Horário não informado';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Horário não informado';
  return new Intl.DateTimeFormat('pt-BR', { timeZone:'America/Sao_Paulo', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' }).format(date).replace(',', ' ·');
}
function formatLastRefresh(value) {
  if (!value) return 'Ainda não executada';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? 'Não disponível' : new Intl.DateTimeFormat('pt-BR', {timeZone:'America/Sao_Paulo', day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}).format(d);
}
function showToast(message, error=false) {
  const toast = $('#toast'); toast.textContent = message; toast.classList.toggle('error', error); toast.classList.add('show');
  window.clearTimeout(showToast.timer); showToast.timer = window.setTimeout(() => toast.classList.remove('show'), 3600);
}
function setLoading(loading) {
  const button = $('#refresh-button'); button.disabled = loading; button.innerHTML = loading ? '<span class="refresh-icon">↻</span> Buscando...' : '<span class="refresh-icon">↻</span> Atualizar radar';
}
function renderStats(data) {
  $('#stat-live').textContent = data.stats?.live ?? 0;
  $('#stat-upcoming').textContent = data.stats?.upcoming ?? 0;
  $('#stat-leads').textContent = data.stats?.leads ?? data.discoveries.length;
  $('#last-refresh').textContent = formatLastRefresh(data.last_refresh);
  $('#events-count').textContent = data.events.length;
  $('#discover-count').textContent = data.discoveries.length;
}
function renderEvents() {
  const query = $('#event-search').value.trim().toLocaleLowerCase('pt-BR');
  const statusFilter = $('#status-filter').value;
  const accessFilter = $('#access-filter').value;
  const filtered = state.events.filter(event => {
    const text = `${event.name} ${event.series} ${event.category} ${event.region} ${event.platform}`.toLocaleLowerCase('pt-BR');
    return (!query || text.includes(query)) && (statusFilter === 'all' || event.status === statusFilter) && (accessFilter === 'all' || event.access === accessFilter);
  });
  const grid = $('#event-grid');
  if (!filtered.length) {
    grid.innerHTML = `<div class="empty-state"><div class="empty-icon">⌁</div><strong>${state.events.length ? 'Nenhum evento corresponde aos filtros.' : 'Nenhum evento no radar ainda.'}</strong><p>${state.events.length ? 'Tente retirar um filtro ou buscar outro termo.' : 'Atualize os coletores ou cadastre uma transmissão manualmente.'}</p></div>`;
    return;
  }
  grid.innerHTML = filtered.map(event => {
    const status = statusText[event.status] || statusText.unknown;
    const access = accessText[event.access] || accessText.unknown;
    const actionUrl = safeUrl(event.stream_url) || safeUrl(event.watch_url) || safeUrl(event.source_url);
    const secondaryUrl = safeUrl(event.source_url);
    return `<article class="event-card ${event.status === 'live' ? 'is-live' : ''}">
      <div class="card-top"><span class="status-tag ${escapeHtml(event.status)}">${escapeHtml(status)}</span><span class="series-tag">${escapeHtml(event.series || 'Motorsport')}</span></div>
      <h3>${escapeHtml(event.name)}</h3><div class="event-kind">${escapeHtml(event.kind || event.category || 'Evento')}</div>
      <div class="event-meta"><div class="meta-cell"><small>Horário de Brasília</small><strong>${escapeHtml(formatDate(event.start_utc))}</strong></div><div class="meta-cell"><small>Região</small><strong>${escapeHtml(event.region || 'Global')}</strong></div></div>
      <div class="access-row"><span class="access-tag ${escapeHtml(event.access || 'unknown')}">${escapeHtml(access)}</span><span class="platform-text">${escapeHtml(event.platform || 'Plataforma não identificada')}</span></div>
      <div class="card-actions">${actionUrl ? `<a class="primary-link" href="${escapeHtml(actionUrl)}" target="_blank" rel="noopener noreferrer">${event.stream_url ? 'Abrir transmissão ↗' : 'Onde assistir ↗'}</a>` : '<a class="primary-link" href="https://www.google.com/search?q='+encodeURIComponent(`${event.series} ${event.name} live stream`)+'" target="_blank" rel="noopener noreferrer">Procurar transmissão ↗</a>'}${secondaryUrl && secondaryUrl !== actionUrl ? `<a href="${escapeHtml(secondaryUrl)}" target="_blank" rel="noopener noreferrer">Fonte ↗</a>` : ''}</div>
    </article>`;
  }).join('');
}
function renderDiscoveries() {
  const list = $('#discover-list');
  if (!state.discoveries.length) {
    list.innerHTML = '<div class="empty-state"><strong>Nenhuma pista carregada.</strong><p>Execute uma varredura para procurar anúncios de transmissões ao vivo.</p></div>'; return;
  }
  list.innerHTML = state.discoveries.map(item => {
    const url = safeUrl(item.url);
    return `<article class="discovery-card"><div><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.summary || item.note || 'Sem resumo disponível.')}</p><div class="discovery-meta"><span>${escapeHtml(item.source_name || 'Fonte externa')}</span><span>${escapeHtml(item.series || 'Motorsport')}</span><span>${escapeHtml(formatDate(item.published_utc || item.published))}</span></div></div><div class="discovery-side"><span class="access-tag ${escapeHtml(item.access || 'unknown')}">${escapeHtml(accessText[item.access] || accessText.unknown)}</span><span class="platform-text">${escapeHtml(item.platform || 'Plataforma não identificada')}</span>${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Abrir fonte ↗</a>` : ''}</div></article>`;
  }).join('');
}
function renderSearchPresets() {
  const select = $("#category-preset");
  if (!select) return;
  const current = select.value;
  select.innerHTML = '<option value="">Escolha uma modalidade para preencher a busca</option>' + state.searchPresets.map(preset => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`).join('');
  if (state.searchPresets.some(preset => preset.id === current)) select.value = current;
}
function renderSources() {
  $('#source-grid').innerHTML = state.sources.map(source => {
    const url = safeUrl(source.url); const evidence = safeUrl(source.official_info);
    return `<article class="source-card"><div class="source-card-top"><h3>${escapeHtml(source.platform)}</h3><span class="access-tag ${escapeHtml(source.access)}">${escapeHtml(accessText[source.access] || accessText.unknown)}</span></div><div class="source-series">${escapeHtml(source.series)}</div><div class="source-region">${escapeHtml(source.region)}</div><p>${escapeHtml(source.note)}</p><div class="source-evidence">${source.confidence === "official" ? "REFERÊNCIA OFICIAL" : source.confidence === "regional" ? "GUIA REGIONAL" : "FONTE / COMUNIDADE"} · atualizado em ${escapeHtml(source.last_checked || "não informado")}</div><div class="source-actions">${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Abrir plataforma ↗</a>` : ''}${evidence ? `<a href="${escapeHtml(evidence)}" target="_blank" rel="noopener noreferrer">Ver referência</a>` : ''}</div></article>`;
  }).join('') || '<div class="empty-state">Nenhuma fonte cadastrada.</div>';
}
function renderDashboard(data) {
  state.events = data.events || []; state.discoveries = data.discoveries || []; state.sources = data.sources || []; state.searchPresets = data.search_presets || [];
  renderStats(data); renderEvents(); renderDiscoveries(); renderSources(); renderSearchPresets(); checkUpcomingAlerts();
}
async function fetchDashboard() {
  const response = await fetch('/api/dashboard'); if (!response.ok) throw new Error('Não foi possível carregar o painel.');
  renderDashboard(await response.json());
}
async function refreshRadar() {
  setLoading(true);
  try {
    const response = await fetch('/api/refresh', {method:'POST'}); const result = await response.json();
    await fetchDashboard();
    if (result.errors?.length) showToast(`Varredura parcial. ${result.errors.join(' | ')}`, true);
    else showToast(`Radar atualizado: ${result.events_updated} eventos e ${result.discoveries_updated} pistas novas.`);
  } catch (error) { showToast(error.message || 'Falha na atualização.', true); }
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
  const message = $('#form-message'); message.textContent = 'Salvando...';
  try {
    const response = await fetch('/api/events', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Não foi possível salvar.');
    closeDialog(); event.currentTarget.reset(); await fetchDashboard(); showToast('Evento adicionado ao radar.'); activateTab('events');
  } catch (error) { message.textContent = error.message; }
}
async function requestNotifications() {
  if (!('Notification' in window)) { showToast('Este navegador não oferece notificações.', true); return; }
  const permission = await Notification.requestPermission();
  if (permission === 'granted') { state.notificationPermission = true; $('#notify-button').textContent = 'Alertas ativados'; showToast('Alertas ativados enquanto o radar estiver aberto.'); checkUpcomingAlerts(); }
  else showToast('Permissão de notificação não concedida.', true);
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
        new Notification(`Começa em breve: ${event.name}`, {body:`${event.series} · ${formatDate(event.start_utc)} · ${event.platform || 'plataforma a confirmar'}`});
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
async function searchYoutubeLive() {
  const term = currentSearchTerm();
  const button = $('#youtube-search'); const original = button.textContent;
  // Abre a aba no clique para evitar bloqueio de popup após a chamada à API.
  const fallbackTab = window.open('about:blank', '_blank');
  button.disabled = true; button.textContent = 'Buscando...';
  try {
    const response = await fetch(`/api/youtube-live?q=${encodeURIComponent(term)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Falha na busca do YouTube.');
    if (!data.configured) {
      showToast('API do YouTube não configurada. Abrindo a busca pública.');
      const fallbackUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${term} live stream`)}`;
      if (fallbackTab) fallbackTab.location.href = fallbackUrl;
      else showToast('O navegador bloqueou a nova aba. Permita pop-ups para abrir a busca.', true);
      return;
    }
    if (fallbackTab) fallbackTab.close();
    const target = $('#platform-results');
    if (!data.items.length) {
      target.innerHTML = '<div class="platform-empty">Nenhuma live correspondente foi retornada pelo YouTube agora.</div>';
      return;
    }
    target.innerHTML = `<div class="platform-results-heading">${data.items.length} TRANSMISSÃO(ÕES) MARCADA(S) COMO AO VIVO PELO YOUTUBE</div>` + data.items.map(item => `<article class="platform-result"><div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.channel)}</span></div><span class="status-tag live">YouTube ao vivo</span><span class="access-tag unknown">Preço não confirmado</span><a href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">Assistir ↗</a></article>`).join('');
  } catch (error) {
    if (fallbackTab) fallbackTab.close();
    showToast(error.message || 'Erro ao procurar no YouTube.', true);
  }
  finally { button.disabled = false; button.textContent = original; }
}

async function searchNewsRadar() {
  const term = currentSearchTerm();
  const button = $("#news-search"); const original = button.textContent;
  button.disabled = true; button.textContent = "Pesquisando...";
  try {
    const response = await fetch(`/api/discover-search?q=${encodeURIComponent(term)}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "A busca no radar falhou.");
    await fetchDashboard();
    activateTab("discover");
    showToast(data.count ? `${data.count} pistas encontradas para: ${term}` : `Nenhuma notícia recente encontrada para: ${term}`);
  } catch (error) {
    showToast(error.message || "Não foi possível pesquisar essa modalidade.", true);
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
$('#youtube-search').addEventListener('click', searchYoutubeLive);
$('#twitch-search').addEventListener('click', () => openLiveSearch('twitch'));
$('#web-search').addEventListener('click', () => openLiveSearch('web'));
$('#local-clock').textContent = `HORÁRIO DE BRASÍLIA · ${new Intl.DateTimeFormat('pt-BR',{timeZone:'America/Sao_Paulo',hour:'2-digit',minute:'2-digit'}).format(new Date())}`;
fetchDashboard().catch(error => showToast(error.message, true));
window.setInterval(checkUpcomingAlerts, 60_000);
