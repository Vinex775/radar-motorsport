/* Adds scheduled-for-today broadcasts to Live Now and later broadcasts to Schedule & Events. */
(() => {
  if (typeof window.renderLiveNow !== 'function' || typeof state === 'undefined') return;

  state.todayBroadcasts = [];

  const dayKey = (value) => {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  };
  const clockLabel = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return 'time TBC';
    return new Intl.DateTimeFormat('en-GB', {hour:'2-digit', minute:'2-digit', timeZoneName:'short'}).format(date);
  };
  const seriesKey = (value) => {
    const text = String(value || '').toLowerCase();
    const patterns = [
      ['porsche', /porsche|carrera cup|sprint challenge/],
      ['f1', /\bformula\s*1\b|\bf1\b/],
      ['f4-brasil', /\bf4\s*(?:brasil|brazil)\b/],
      ['wec', /\bwec\b|world endurance championship/],
      ['motogp', /\bmotogp\b/],
      ['moto1000gp', /moto1000gp/],
      ['nascar', /\bnascar\b/],
      ['gb3', /\bgb3\b/],
      ['eurocup3', /eurocup\s*[- ]?3/],
      ['supercars', /supercars championship|\bsandown 500\b/],
      ['world-outlaws', /world of outlaws|\bdirtcar\b/],
      ['nhra', /\bnhra\b/],
      ['iame', /\biame\b/],
    ];
    return patterns.find(([, pattern]) => pattern.test(text))?.[0] || '';
  };

  function mergeFutureBroadcasts(items) {
    const today = dayKey(new Date());

    // A broadcast that rolls into today is no longer a future Schedule entry:
    // it belongs in today's Live Now list (or in the active stream results).
    state.events = state.events.filter(event => {
      const broadcast = event.youtubeScheduledBroadcast;
      if (!broadcast) return true;
      const broadcastDay = dayKey(broadcast.start_utc);
      if (broadcastDay && broadcastDay <= today) {
        if (broadcast.synthetic) return false;
        event.platform = event._apexOriginalPlatform || event.platform;
        event.stream_url = event._apexOriginalStreamUrl || null;
        delete event.youtubeScheduledBroadcast;
        delete event._apexOriginalPlatform;
        delete event._apexOriginalStreamUrl;
      }
      return true;
    });

    for (const item of items || []) {
      if (!item.start_utc || dayKey(item.start_utc) <= today) continue;
      const itemKey = seriesKey(`${item.name || ''} ${item.series || ''}`);
      const itemDay = dayKey(item.start_utc);
      let existing = state.events.find(event => event.external_id === item.external_id);
      if (!existing && itemKey) {
        existing = state.events.find(event =>
          dayKey(event.start_utc) === itemDay &&
          seriesKey(`${event.name || ''} ${event.series || ''}`) === itemKey
        );
      }

      if (existing) {
        if (!existing.youtubeScheduledBroadcast) {
          existing._apexOriginalPlatform = existing.platform;
          existing._apexOriginalStreamUrl = existing.stream_url;
        }
        existing.stream_url = item.stream_url;
        existing.platform = `YouTube · broadcast scheduled ${clockLabel(item.start_utc)}`;
        existing.youtubeScheduledBroadcast = {
          external_id: item.external_id,
          start_utc: item.start_utc,
          url: item.stream_url,
          synthetic: false,
        };
      } else {
        state.events.push({
          ...item,
          status: 'upcoming',
          youtubeScheduledBroadcast: {
            external_id: item.external_id,
            start_utc: item.start_utc,
            url: item.stream_url,
            synthetic: true,
          },
        });
      }
    }

    state.events.sort((a, b) => String(a.start_utc || '').localeCompare(String(b.start_utc || '')));
    const count = document.querySelector('#events-count');
    if (count) count.textContent = String(state.events.length);
    const upcoming = document.querySelector('#stat-upcoming');
    if (upcoming) upcoming.textContent = String(state.events.length);
    if (typeof window.renderEvents === 'function') window.renderEvents();
  }

  const originalRenderLiveNow = window.renderLiveNow;
  window.renderLiveNow = function(data) {
    state.todayBroadcasts = (data.items || []).filter(item =>
      item.status === 'scheduled_today' || item.status === 'start_time_passed'
    );
    const result = originalRenderLiveNow(data);

    const eyebrow = document.querySelector('#panel-live .section-heading .eyebrow');
    const title = document.querySelector('#panel-live .section-heading h2');
    const description = document.querySelector('#panel-live .section-heading p');
    const notice = document.querySelector('#panel-live .notice-strip div');
    const statLabel = document.querySelector('.stat-live .stat-label');
    const statDescription = document.querySelector('.stat-live small');
    const liveTab = document.querySelector('.tab-button[data-tab="live"]');
    if (eyebrow) eyebrow.textContent = "TODAY'S BROADCAST SCANNER / 00";
    if (title) title.textContent = 'LIVE NOW & TODAY';
    if (description) description.textContent = "Active broadcasts plus YouTube livestreams scheduled to start today. Tomorrow and later go to Schedule & Events.";
    if (notice) notice.innerHTML = '<strong>What appears here:</strong> Confirmed live broadcasts first, then YouTube livestreams scheduled later today, followed by today’s broadcasts whose scheduled start time has passed. A passed time is a warning to verify the stream — it is not proof that the broadcast started.';
    if (statLabel) statLabel.innerHTML = '<i></i> BROADCASTS TODAY';
    if (statDescription) statDescription.textContent = 'Active now + official streams scheduled for today';
    if (liveTab && liveTab.firstChild) liveTab.firstChild.textContent = 'Live Now & Today ';

    const rows = document.querySelectorAll('#platform-results .live-result');
    (data.items || []).forEach((item, index) => {
      if (!['scheduled_today', 'start_time_passed'].includes(item.status)) return;
      const row = rows[index];
      if (!row) return;
      const badge = row.querySelector('.status-tag');
      if (badge) {
        badge.classList.remove('live');
        badge.classList.add('upcoming');
        badge.textContent = item.status === 'start_time_passed'
          ? 'TIME PASSED · VERIFY'
          : 'SCHEDULED TODAY';
      }
      const meta = row.querySelector('.live-result-copy span');
      if (meta) meta.textContent += item.status === 'start_time_passed'
        ? ` · Scheduled ${clockLabel(item.scheduled_start_at)} · start time passed`
        : ` · Starts ${clockLabel(item.scheduled_start_at)}`;
    });

    const heading = document.querySelector('#platform-results .platform-results-heading');
    if (heading) {
      const active = Number(data.active_count || 0);
      const scheduled = Number(data.scheduled_today_count || 0);
      const passed = Number(data.start_time_passed_count || 0);
      heading.textContent = `${active} LIVE NOW · ${scheduled} STARTING LATER TODAY · ${passed} START TIMES PASSED / VERIFY`;
    }
    const scheduledStatus = (data.platforms || {})['YouTube scheduled'];
    if (scheduledStatus && Number(scheduledStatus.future_broadcast_count || 0)) {
      const scheduledTag = Array.from(document.querySelectorAll('#platform-results .platform-source'))
        .find(tag => tag.textContent.toLowerCase().includes('youtube scheduled'));
      if (scheduledTag) scheduledTag.textContent += ` · ${Number(scheduledStatus.future_broadcast_count)} later in Schedule`;
    }
    const empty = document.querySelector('#platform-results .platform-empty');
    if (empty && !data.count) empty.textContent = 'No active broadcasts or YouTube livestreams scheduled for today were found. Tomorrow and later are listed in Schedule & Events.';

    mergeFutureBroadcasts(data.future_events || []);
    return result;
  };

  // Extend the existing 15-minute browser alert to same-day scheduled streams.
  const originalCheckUpcomingAlerts = window.checkUpcomingAlerts;
  if (typeof originalCheckUpcomingAlerts === 'function') {
    window.checkUpcomingAlerts = function() {
      originalCheckUpcomingAlerts();
      if (!('Notification' in window) || Notification.permission !== 'granted') return;
      const now = Date.now();
      for (const item of state.todayBroadcasts || []) {
        const start = new Date(item.scheduled_start_at).getTime();
        const difference = start - now;
        if (item.status !== 'scheduled_today' || !Number.isFinite(start) || difference <= 0 || difference > 15 * 60 * 1000) continue;
        const key = `apex-scheduled-broadcast-${item.external_id || item.id}-${item.scheduled_start_at}`;
        if (sessionStorage.getItem(key)) continue;
        new Notification(`Broadcast starts soon: ${item.title}`, {
          body: `${item.channel || 'YouTube'} · ${clockLabel(item.scheduled_start_at)}`,
        });
        sessionStorage.setItem(key, '1');
      }
    };
  }

  // Keep manual scan feedback honest now that the total includes scheduled streams.
  const originalScanLiveNow = window.scanLiveNow;
  if (typeof originalScanLiveNow === 'function') {
    window.scanLiveNow = async function(showToastOnComplete = true) {
      const data = await originalScanLiveNow(showToastOnComplete);
      if (showToastOnComplete && data) {
        showToast(`${Number(data.active_count || 0)} live now · ${Number(data.scheduled_today_count || 0)} starting later today · ${Number(data.start_time_passed_count || 0)} start times passed — verify.`);
      }
      return data;
    };
  }
})();
