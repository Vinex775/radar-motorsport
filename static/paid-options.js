/* Adds official free, subscription and PPV destinations to today's/future events. */
(() => {
  if (typeof window.renderLiveNow !== 'function' || typeof window.renderEvents !== 'function') return;

  const style = document.createElement('style');
  style.textContent = `
    .paid-watch-options{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
    .paid-watch-option{display:inline-flex;align-items:center;flex-wrap:wrap;gap:7px;max-width:100%;padding:7px 9px;border:1px solid rgba(255,255,255,.12);border-radius:8px;background:rgba(255,255,255,.035);font-size:12px}
    .paid-watch-option strong{font-weight:700}
    .paid-watch-option a{color:var(--accent,#ff5a36);font-weight:700;text-decoration:none;white-space:nowrap}
    .paid-watch-option a:hover{text-decoration:underline}
    .paid-watch-option small{color:var(--muted,#9aa0aa);font-size:10px}
    .schedule-watch-options{margin-top:12px}
  `;
  document.head.appendChild(style);

  const safeText = value => typeof escapeHtml === 'function'
    ? escapeHtml(value == null ? '' : String(value))
    : String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[ch]));
  const safeLink = value => typeof safeUrl === 'function' ? safeUrl(value) : /^https?:\/\//i.test(String(value || '')) ? String(value) : '';
  const accessLabel = value => (typeof accessText !== 'undefined' && accessText[value]) || 'Unknown';

  function optionMarkup(options) {
    return (options || []).filter(option => safeLink(option.url)).map(option => {
      const access = ['free','subscription','ppv','unknown'].includes(option.access) ? option.access : 'unknown';
      const label = option.link_type === 'event_info' ? 'Official info ↗' : 'Open ↗';
      return `<span class="paid-watch-option" title="${safeText(option.note || option.region || '')}"><strong>${safeText(option.platform || 'Official watch option')}</strong><span class="access-tag ${access}">${safeText(accessLabel(access))}</span><small>${safeText(option.region || '')}</small><a href="${safeText(safeLink(option.url))}" target="_blank" rel="noopener noreferrer">${label}</a></span>`;
    }).join('');
  }

  function statusPresentation(item) {
    switch (item.status) {
      case 'live_now': return {label:'LIVE NOW · PLATFORM API', cls:'live'};
      case 'schedule_window': return {label:'SCHEDULE WINDOW · VERIFY', cls:'upcoming'};
      case 'scheduled_today': return {label:'SCHEDULED TODAY', cls:'upcoming'};
      case 'start_time_passed': return {label:'TIME PASSED · VERIFY', cls:'upcoming'};
      case 'ended_today': return {label:'SESSION ENDED TODAY', cls:'upcoming'};
      case 'date_only_today': return {label:'EVENT TODAY · TIMES TBC', cls:'upcoming'};
      default: return {label:'TODAY · CHECK OFFICIAL SOURCE', cls:'upcoming'};
    }
  }

  const originalRenderLiveNow = window.renderLiveNow;
  window.renderLiveNow = function(data) {
    const displayData = {
      ...data,
      note: 'Live Now & Today combines platform-confirmed live streams with source-checked official sessions scheduled for the local day. Free, subscription and pay-per-view destinations are included. A session time is not proof that a video is live; verify coverage, price and territory at the provider.'
    };
    const result = originalRenderLiveNow(displayData);
    const rows = document.querySelectorAll('#platform-results .live-result');
    const items = data.items || [];

    items.forEach((item, index) => {
      const row = rows[index];
      if (!row) return;
      const presentation = statusPresentation(item);
      const badge = row.querySelector('.status-tag');
      if (badge) {
        badge.classList.remove('live','upcoming');
        badge.classList.add(presentation.cls);
        badge.textContent = presentation.label;
      }

      const meta = row.querySelector('.live-result-copy span');
      if (meta && item.scheduled_start_at) {
        const start = new Date(item.scheduled_start_at);
        const end = item.scheduled_end_at ? new Date(item.scheduled_end_at) : null;
        const format = value => Number.isNaN(value.getTime()) ? '' : new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',timeZoneName:'short'}).format(value);
        const timeText = ` · ${format(start)}${end ? `–${format(end)}` : ''}`;
        if (!meta.textContent.includes(format(start))) meta.textContent += timeText;
      }

      const options = optionMarkup(item.watch_options);
      if (options) {
        row.querySelector('.access-tag')?.remove();
        const box = document.createElement('div');
        box.className = 'paid-watch-options';
        box.innerHTML = options;
        row.appendChild(box);
      } else {
        const access = ['free','subscription','ppv','unknown'].includes(item.access) ? item.access : 'unknown';
        const current = row.querySelector('.access-tag');
        if (current) {
          current.className = `access-tag ${access}`;
          current.textContent = accessLabel(access);
        }
      }
    });

    const active = Number(data.active_count || 0);
    const windows = Number(data.schedule_window_count || 0);
    const scheduled = Number(data.scheduled_today_count || 0);
    const passed = Number(data.start_time_passed_count || 0);
    const ended = Number(data.ended_today_count || 0);
    const tbc = Number(data.date_only_today_count || 0);
    const heading = document.querySelector('#platform-results .platform-results-heading');
    if (heading) heading.textContent = `${active} VERIFIED LIVE · ${windows} SCHEDULE WINDOWS · ${scheduled} STARTING LATER · ${passed} TIMES PASSED / VERIFY · ${ended} ENDED · ${tbc} TIMES TBC`;

    const eyebrow = document.querySelector('#panel-live .section-heading .eyebrow');
    const title = document.querySelector('#panel-live .section-heading h2');
    const description = document.querySelector('#panel-live .section-heading p');
    const notice = document.querySelector('#panel-live .notice-strip div');
    const statLabel = document.querySelector('.stat-live .stat-label');
    const statDescription = document.querySelector('.stat-live small');
    if (eyebrow) eyebrow.textContent = "TODAY'S BROADCAST & WATCH OPTIONS / 00";
    if (title) title.textContent = 'LIVE NOW & TODAY';
    if (description) description.textContent = 'Verified active streams plus official sessions scheduled for today, including free, subscription and pay-per-view destinations. Tomorrow and later belong in Schedule & Events.';
    if (notice) notice.innerHTML = '<strong>Paid options are included:</strong> APEX shows official watch destinations even when they require a subscription or pay-per-view. A scheduled session window is not proof that a provider has started its live feed; check the destination, event, session and country.';
    if (statLabel) statLabel.innerHTML = '<i></i> BROADCASTS & SESSIONS TODAY';
    if (statDescription) statDescription.textContent = 'Verified live streams + official sessions and watch options';
    const empty = document.querySelector('#platform-results .platform-empty');
    if (empty && !items.length) empty.textContent = 'No verified live streams or source-checked official sessions were found for today. Tomorrow and later remain in Schedule & Events.';
    const scanNote = document.querySelector('#live-last-scan');
    if (scanNote) scanNote.textContent = 'Automatic platform re-check every 5 minutes. Today’s official schedule and broadcaster directory are also included; provider availability and territorial rights must be verified at the destination.';
    return result;
  };

  // A future event matches an access filter if any of its official watch choices does.
  const originalRenderEvents = window.renderEvents;
  window.renderEvents = function() {
    const result = originalRenderEvents();
    const query = document.querySelector('#event-search')?.value.trim().toLocaleLowerCase('en-US') || '';
    const statusFilter = document.querySelector('#status-filter')?.value || 'all';
    const accessFilter = document.querySelector('#access-filter')?.value || 'all';
    const filtered = state.events.filter(event => {
      const optionText = (event.watch_options || []).map(option => `${option.platform || ''} ${option.region || ''}`).join(' ');
      const searchable = `${event.name || ''} ${event.series || ''} ${event.category || ''} ${event.region || ''} ${event.platform || ''} ${optionText}`.toLocaleLowerCase('en-US');
      const accesses = [event.access, ...(event.watch_options || []).map(option => option.access)];
      return (!query || searchable.includes(query)) &&
        (statusFilter === 'all' || event.status === statusFilter) &&
        (accessFilter === 'all' || accesses.includes(accessFilter));
    });
    const cards = document.querySelectorAll('#event-grid .event-card');
    cards.forEach((card, index) => {
      const html = optionMarkup(filtered[index]?.watch_options);
      if (!html) return;
      const box = document.createElement('div');
      box.className = 'paid-watch-options schedule-watch-options';
      box.innerHTML = html;
      card.querySelector('.access-row')?.insertAdjacentElement('afterend', box);
    });
    return result;
  };

  const originalScanLiveNow = window.scanLiveNow;
  if (typeof originalScanLiveNow === 'function') {
    window.scanLiveNow = async function(showToastOnComplete = true) {
      const data = await originalScanLiveNow(false);
      if (showToastOnComplete && data && typeof showToast === 'function') {
        showToast(`${Number(data.active_count || 0)} verified live · ${Number(data.official_schedule_today_count || 0)} official sessions today · ${Number(data.scheduled_today_count || 0)} starting later. Paid and free watch options are included.`);
      }
      return data;
    };
  }
})();
