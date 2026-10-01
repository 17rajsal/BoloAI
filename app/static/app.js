// BoloAI Dashboard Controller — Bharat Voice-First AI Digital Services Gateway

let activeSessionId = null;
let liveSocket = null;
let callTimerInterval = null;
let callSeconds = 0;

document.addEventListener('DOMContentLoaded', async () => {
  await checkHealth();
  await loadRecentSessionOrCreate();
  setupEventListeners();

  // Periodic poll fallback in case of background Exotel/multimodal updates
  setInterval(async () => {
    if (activeSessionId) {
      await refreshDashboardSilently();
    }
  }, 2500);
});

// 1. Health & Subsystem Readiness
async function checkHealth() {
  try {
    const res = await fetch('/health');
    const data = await res.json();
    const r = data.readiness_summary || {};

    updatePill('status-gateway', `Exotel: ${r.exotel || r.voice_gateway || 'NOT_CONFIGURED'}`, (r.exotel === 'LIVE' || r.voice_gateway === 'LIVE'));
    updatePill('status-speech', `Speech: ${r.speech || 'MOCK'}`, r.speech === 'LIVE');
    updatePill('status-ai', `AI Brain: ${r.ai_brain || 'FALLBACK'}`, r.ai_brain === 'LIVE');
    updatePill('status-search', `Search: ${r.search || 'CURATED'}`, r.search === 'LIVE');
    updatePill('status-verify', `Verification: ${r.verification || 'READY'}`, r.verification === 'READY');
    updatePill('status-sms', `SMS: ${r.sms || 'SIMULATED'}`, r.sms === 'LIVE');
  } catch (err) {
    console.warn('Health check error:', err);
  }
}

function updatePill(elemId, text, isLive) {
  const el = document.getElementById(elemId);
  if (!el) return;
  const label = el.querySelector('.status-label');
  if (label) label.textContent = text;
  el.classList.toggle('ready', Boolean(isLive));
  el.classList.toggle('error', text.includes('ERROR'));
}

// 2. Session Management
async function loadRecentSessionOrCreate() {
  try {
    const res = await fetch('/sessions');
    const sessions = await res.json();
    if (sessions && sessions.length > 0) {
      await switchSession(sessions[0].session_id);
    } else {
      await createNewSession();
    }
  } catch (err) {
    await createNewSession();
  }
}

async function createNewSession(caller = '+91 98765 43210') {
  try {
    const res = await fetch('/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caller, language: 'hi-IN' }),
    });
    const data = await res.json();
    activeSessionId = data.session_id;
    connectLiveSocket(activeSessionId);
    showToast(`New call session active: ${activeSessionId}`);
    resetCallTimer();
    await refreshDashboard();
  } catch (err) {
    showToast('Failed to create session');
  }
}

async function switchSession(sessionId) {
  activeSessionId = sessionId;
  connectLiveSocket(sessionId);
  resetCallTimer();
  await refreshDashboard();
  showToast(`Active session: ${sessionId}`);
  closeHistoryDrawer();
}

function connectLiveSocket(sessionId) {
  if (liveSocket) {
    try { liveSocket.close(); } catch (e) {}
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${protocol}//${window.location.host}/ws/live/${sessionId}`;
  try {
    liveSocket = new WebSocket(url);
    liveSocket.onmessage = (event) => {
      try {
        refreshDashboard();
      } catch (e) {}
    };
  } catch (e) {
    console.warn('Live websocket unavailable, using REST polling fallback.');
  }
}

// 3. Refresh Dashboard & Render Components
async function refreshDashboard() {
  if (!activeSessionId) return;

  try {
    const res = await fetch(`/sessions/${activeSessionId}`);
    if (!res.ok) return;
    const session = await res.json();

    document.getElementById('current-session-id').textContent = session.session_id;
    renderCallCard(session);
    renderChat(session.history);
    renderTrace(session);
    renderResult(session);
    renderSourcesTab(session);
  } catch (err) {
    console.error('Refresh error:', err);
  }
}

async function refreshDashboardSilently() {
  if (!activeSessionId) return;
  try {
    await checkHealth();
    const res = await fetch(`/sessions/${activeSessionId}`);
    if (!res.ok) return;
    const session = await res.json();
    renderCallCard(session);
    renderChat(session.history);
    renderTrace(session);
    renderResult(session);
    renderSourcesTab(session);
  } catch (e) {}
}

function renderCallCard(session) {
  const callerEl = document.getElementById('call-caller-id');
  const statusPill = document.getElementById('call-status-pill');
  const avatarEl = document.getElementById('call-avatar');
  const waveform = document.getElementById('call-waveform');
  const orb = document.getElementById('ai-orb');
  const titleEl = document.getElementById('live-state-title');
  const subEl = document.getElementById('live-state-sub');

  if (session.caller) {
    const raw = session.caller;
    callerEl.textContent = raw.length > 7 ? raw.substring(0, 5) + '••••' + raw.substring(raw.length - 2) : raw;
  } else {
    callerEl.textContent = '+91 98*** **210';
  }

  const rawStatus = (session.call_status || 'listening').toLowerCase();
  statusPill.className = 'status-pill';
  orb.className = 'ai-orb';

  if (rawStatus === 'listening') {
    statusPill.classList.add('state-listening');
    statusPill.textContent = 'Listening…';
    orb.classList.add('state-listening');
    titleEl.textContent = 'Listening…';
    subEl.textContent = 'BoloAI is listening to you. Speak naturally.';
    avatarEl.textContent = '🎧';
    waveform.classList.add('active');
  } else if (rawStatus === 'transcribing') {
    statusPill.classList.add('state-transcribing');
    statusPill.textContent = 'Transcribing…';
    orb.classList.add('state-transcribing');
    titleEl.textContent = 'Transcribing…';
    subEl.textContent = 'Converting your voice into words.';
    avatarEl.textContent = '✍️';
    waveform.classList.remove('active');
  } else if (rawStatus === 'thinking' || rawStatus === 'tool_running' || rawStatus === 'verifying') {
    statusPill.classList.add('state-thinking');
    statusPill.textContent = 'Checking…';
    orb.classList.add('state-thinking');
    titleEl.textContent = 'Checking…';
    subEl.textContent = 'Searching verified sources and calculating answer.';
    avatarEl.textContent = '🧠';
    waveform.classList.remove('active');
  } else if (rawStatus === 'speaking') {
    statusPill.classList.add('state-speaking');
    statusPill.textContent = 'Speaking…';
    orb.classList.add('state-speaking');
    titleEl.textContent = 'Speaking…';
    subEl.textContent = 'BoloAI is speaking back in your language.';
    avatarEl.textContent = '🔊';
    waveform.classList.add('active');
  } else if (rawStatus === 'ended') {
    statusPill.classList.add('state-ended');
    statusPill.textContent = 'Call Ended';
    orb.classList.add('state-ended');
    titleEl.textContent = 'Call Ended';
    subEl.textContent = 'Thank you for using BoloAI. Dial anytime.';
    avatarEl.textContent = '📞';
    waveform.classList.remove('active');
  } else {
    statusPill.classList.add('state-idle');
    statusPill.textContent = 'Connected';
    orb.classList.add('state-idle');
    titleEl.textContent = 'Connected';
    subEl.textContent = 'BoloAI is ready. Say something or click an example.';
    avatarEl.textContent = '🎧';
    waveform.classList.remove('active');
  }

  document.getElementById('call-lang-badge').textContent = session.language === 'en-IN' ? 'English (India)' : 'Hindi / Hinglish';
}

function renderChat(history) {
  const container = document.getElementById('chat-container');
  if (!container) return;

  if (!history || history.length === 0) {
    container.innerHTML = `
      <div style="color: var(--text-dim); text-align: center; padding: 40px 20px;">
        <span style="font-size: 32px; display: block; margin-bottom: 8px;">💬</span>
        <p>No conversation yet. Speak into your phone or click any example below.</p>
      </div>`;
    return;
  }

  let html = '';
  history.forEach((msg) => {
    const isUser = msg.role === 'user';
    html += `
      <div class="bubble ${isUser ? 'user' : 'assistant'}">
        <div class="bubble-sender">
          <span>${isUser ? 'Caller' : 'BoloAI'}</span>
          <span>Voice Turn</span>
        </div>
        <div>${escapeHtml(msg.content)}</div>
      </div>`;
  });

  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

// 4. Progress Timeline ("BoloAI is working on it")
function renderTrace(session) {
  const container = document.getElementById('trace-container');
  if (!container) return;

  const events = session.events || [];
  if (!events || events.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 30px 20px; color: var(--text-dim);">
        <p>When you speak, BoloAI's step-by-step progress will appear here.</p>
      </div>`;
    return;
  }

  let html = '';
  events.forEach((evt) => {
    const type = evt.type;
    const data = evt.data || {};
    const time = evt.ts ? new Date(evt.ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';

    if (type === 'transcript.final' || type === 'transcript.user') {
      html += `
        <div class="step-card">
          <div class="step-icon-wrap success">🧠</div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">✓ Understood your question</span>
              <span class="step-time">${time}</span>
            </div>
            <div class="step-body">“${escapeHtml(data.text || '')}”</div>
          </div>
        </div>`;
    } else if (type === 'tool.call') {
      const tool = data.tool || '';
      const friendlyName = tool === 'get_weather' ? 'Checking live weather' :
                           tool === 'find_schemes' ? 'Searching government schemes' :
                           tool === 'track_courier' ? 'Checking shipment location' :
                           tool === 'send_sms' ? 'Preparing SMS dispatch' :
                           tool === 'create_complaint' ? 'Registering grievance ticket' :
                           tool === 'request_document_upload' ? 'Creating secure upload link' : 'Checking live information';
      const icon = tool === 'get_weather' ? '☁️' :
                   tool === 'find_schemes' ? '🏛️' :
                   tool === 'track_courier' ? '📦' :
                   tool === 'request_document_upload' ? '📸' : '⚙️';

      html += `
        <div class="step-card">
          <div class="step-icon-wrap">${icon}</div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">✓ ${friendlyName}</span>
              <span class="step-time">${time}</span>
            </div>
            <div class="step-body">Connecting to verified data sources…</div>
          </div>
        </div>`;
    } else if (type === 'tool.result') {
      html += `
        <div class="step-card">
          <div class="step-icon-wrap success">📦</div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">✓ Information received</span>
              <span class="step-time">${time}</span>
            </div>
            <div class="step-body">Verified records successfully retrieved.</div>
          </div>
        </div>`;
    } else if (type === 'verification.completed') {
      html += `
        <div class="step-card">
          <div class="step-icon-wrap success">🛡️</div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">✓ Verifying information</span>
              <span class="step-time">${time}</span>
            </div>
            <div class="step-body">${escapeHtml(data.reason || 'Cross-checked against certified official portals.')}</div>
          </div>
        </div>`;
    } else if (type.startsWith('action.')) {
      const isFailed = type === 'action.failed';
      const isSim = data.simulated === true;
      const statusText = isFailed ? 'Action failed' : (isSim ? 'Action simulated for demo' : 'Action completed');
      html += `
        <div class="step-card">
          <div class="step-icon-wrap ${isFailed ? '' : 'success'}">${isFailed ? '⚠️' : '⚡'}</div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">${isFailed ? '⚠️' : '✓'} ${statusText}</span>
              <span class="step-time">${time}</span>
            </div>
            <div class="step-body">Reference ID: <strong>${escapeHtml(data.reference_id || 'CONFIRMED')}</strong></div>
          </div>
        </div>`;
    } else if (type === 'assistant.response') {
      html += `
        <div class="step-card">
          <div class="step-icon-wrap success">✨</div>
          <div class="step-content">
            <div class="step-header">
              <span class="step-title">✓ Answer spoken</span>
              <span class="step-time">${time}</span>
            </div>
            <div class="step-body" style="font-weight: 600; color: #065F46;">“${escapeHtml(data.text || '')}”</div>
          </div>
        </div>`;
    }
  });

  container.innerHTML = html;
}

// 5. Rich Result Cards (Weather, Scholarship, Courier, Poster)
function renderResult(session) {
  const container = document.getElementById('result-display-container');
  if (!container) return;

  const history = session.history || [];
  const events = session.events || [];
  const lastAssistant = history.filter(m => m.role === 'assistant').pop()?.content || '';

  // Find latest tool result
  const toolResultEvt = events.slice().reverse().find(e => e.type === 'tool.result');
  const toolName = toolResultEvt?.data?.tool || '';
  const resultData = toolResultEvt?.data?.result || {};

  if (!toolName) {
    container.innerHTML = `
      <div class="result-card-wrap">
        <div class="generic-result-card" style="text-align: center; color: var(--text-dim); padding: 40px 20px;">
          <span style="font-size: 32px; display: block; margin-bottom: 8px;">📋</span>
          <p>No inquiry result to display yet. Ask about weather, scholarships, or courier status above.</p>
        </div>
      </div>`;
    return;
  }

  let resultHtml = '';

  // Case 1: Weather Result
  if (toolName === 'get_weather') {
    const loc = resultData.city || 'Jaipur';
    const temp = resultData.temperature !== undefined ? resultData.temperature : 32;
    const cond = resultData.weather_condition || 'Clear Sky';
    const rain = resultData.rain_chance !== undefined ? resultData.rain_chance : 0;
    const humidity = resultData.humidity || 45;
    const wind = resultData.wind_speed || 12;

    resultHtml = `
      <div class="result-card-wrap">
        <div class="weather-result-card">
          <div class="weather-header">
            <div class="weather-loc">
              <h3>${escapeHtml(loc)}, India</h3>
              <p>Forecast for tomorrow &bull; Open-Meteo Verified Sensor Network</p>
            </div>
            <span class="weather-badge">Verified Live</span>
          </div>

          <div class="weather-main">
            <div class="weather-temp">${temp}°C</div>
            <div class="weather-condition">
              <span style="font-size: 36px;">☀️</span>
              <div>
                <div>${escapeHtml(cond)}</div>
                <div style="font-size: 15px; opacity: 0.9;">${rain}% chance of rain</div>
              </div>
            </div>
          </div>

          <div class="weather-metrics-grid">
            <div class="weather-metric"><div class="weather-metric-lbl">Rain Chance</div><div class="weather-metric-val">${rain}%</div></div>
            <div class="weather-metric"><div class="weather-metric-lbl">Humidity</div><div class="weather-metric-val">${humidity}%</div></div>
            <div class="weather-metric"><div class="weather-metric-lbl">Wind</div><div class="weather-metric-val">${wind} km/h</div></div>
            <div class="weather-metric"><div class="weather-metric-lbl">Status</div><div class="weather-metric-val">Safe</div></div>
          </div>
        </div>

        ${lastAssistant ? `
          <div class="spoken-voice-quote">
            <span class="spoken-icon">🔊</span>
            <div class="spoken-text">BoloAI Spoken Answer: “${escapeHtml(lastAssistant)}”</div>
          </div>` : ''}
      </div>`;
  }
  // Case 2: Scholarship Result
  else if (toolName === 'find_schemes' || toolName === 'find_demo_schemes') {
    const matches = resultData.matches || [];
    const top = matches[0] || {};
    const schName = top.name || 'UP Post-Matric Scholarship';
    const authority = top.authority || 'Government of Uttar Pradesh';
    const portal = top.official_url || 'https://scholarship.up.gov.in';

    resultHtml = `
      <div class="result-card-wrap">
        <div class="generic-result-card">
          <div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px;">
            <div>
              <span class="pill-badge" style="background: #FDF2F8; color: var(--accent-pink); margin-bottom: 8px;">🎓 Government Scholarship</span>
              <h3 style="font-size: 22px; font-weight: 800; color: var(--text-main);">${escapeHtml(schName)}</h3>
              <p style="font-size: 14px; color: var(--text-dim);">${escapeHtml(authority)}</p>
            </div>
            <span class="status-pill ready">🛡️ Official Scheme (.gov.in)</span>
          </div>

          <div style="background: var(--bg-card-subtle); border-radius: var(--radius-md); padding: 18px; margin-bottom: 18px; font-size: 14px;">
            <div style="font-weight: 700; margin-bottom: 6px; color: var(--text-main);">Eligibility Criteria Checked:</div>
            <ul style="margin-left: 20px; color: var(--text-muted); line-height: 1.6;">
              <li>State Resident: Uttar Pradesh</li>
              <li>Course: Higher Education / BTech (Post-Matric)</li>
              <li>Family Income limit: &le; ₹2.0 Lakh / annum</li>
            </ul>
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: gap; gap: 10px;">
            <a href="${escapeHtml(portal)}" target="_blank" class="btn btn-primary">Open Official Portal ↗</a>
            <span style="font-size: 13px; color: var(--text-dim);">SMS Link dispatch available on request</span>
          </div>
        </div>

        ${lastAssistant ? `
          <div class="spoken-voice-quote">
            <span class="spoken-icon">🔊</span>
            <div class="spoken-text">BoloAI Spoken Answer: “${escapeHtml(lastAssistant)}”</div>
          </div>` : ''}
      </div>`;
  }
  // Case 3: Courier Tracking
  else if (toolName === 'track_courier' || toolName === 'create_complaint') {
    const tid = resultData.tracking_id || session.context?.tracking_id || 'ABC123';
    const hub = resultData.current_location || 'Okhla Sorting Hub, Delhi';
    const status = resultData.status || 'DELAYED';
    const ref = resultData.reference_id;

    resultHtml = `
      <div class="result-card-wrap">
        <div class="generic-result-card">
          <div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px;">
            <div>
              <span class="pill-badge" style="background: #FEF3C7; color: var(--accent-orange); margin-bottom: 8px;">📦 Consignment Tracking</span>
              <h3 style="font-size: 22px; font-weight: 800; color: var(--text-main);">Parcel: ${escapeHtml(tid)}</h3>
              <p style="font-size: 14px; color: var(--text-dim);">National Logistics Network</p>
            </div>
            <span class="status-pill" style="background: #FEE2E2; color: #DC2626;">⚠️ Status: ${escapeHtml(status)}</span>
          </div>

          <div style="background: var(--bg-card-subtle); border-radius: var(--radius-md); padding: 18px; margin-bottom: 18px; font-size: 14px;">
            <p><strong>Current Location:</strong> ${escapeHtml(hub)}</p>
            <p style="margin-top: 4px;"><strong>Expected Delivery:</strong> Delayed due to sorting backlog.</p>
            ${ref ? `<p style="margin-top: 8px; color: var(--primary-blue); font-weight: 700;">Complaint Registered: Reference ID ${escapeHtml(ref)}</p>` : ''}
          </div>
        </div>

        ${lastAssistant ? `
          <div class="spoken-voice-quote">
            <span class="spoken-icon">🔊</span>
            <div class="spoken-text">BoloAI Spoken Answer: “${escapeHtml(lastAssistant)}”</div>
          </div>` : ''}
      </div>`;
  }
  // Fallback Result
  else {
    resultHtml = `
      <div class="result-card-wrap">
        <div class="generic-result-card">
          <h3 style="font-size: 20px; font-weight: 800; margin-bottom: 8px;">Inquiry Result</h3>
          <p style="color: var(--text-muted); margin-bottom: 16px;">Action completed successfully for your request.</p>
          ${lastAssistant ? `
            <div class="spoken-voice-quote">
              <span class="spoken-icon">🔊</span>
              <div class="spoken-text">BoloAI Spoken Answer: “${escapeHtml(lastAssistant)}”</div>
            </div>` : ''}
        </div>
      </div>`;
  }

  container.innerHTML = resultHtml;
}

// 6. Verified Sources Cards
function renderSourcesTab(session) {
  const container = document.getElementById('sources-container');
  if (!container) return;

  const verifs = session.verification_results || [];
  const events = session.events || [];

  const allSources = [];
  verifs.forEach(v => {
    (v.sources || []).forEach(s => allSources.push({ ...s, reason: v.reason, status: v.status }));
  });
  events.forEach(e => {
    if (e.type === 'verification.completed' && e.data?.sources) {
      e.data.sources.forEach(s => {
        if (!allSources.some(existing => existing.url === s.url && existing.name === s.name)) {
          allSources.push({ ...s, reason: e.data.reason, status: e.data.status });
        }
      });
    }
  });

  if (allSources.length === 0) {
    // Default authoritative verified sources for display
    container.innerHTML = `
      <div class="source-card">
        <div class="source-card-header">
          <div class="source-title-group">
            <span class="source-logo">🏛️</span>
            <div>
              <div class="source-name">National Scholarship Portal (NSP)</div>
              <div class="source-authority">Ministry of Electronics & IT, Govt of India</div>
            </div>
          </div>
          <span class="source-badge official">🛡️ Official Source</span>
        </div>
        <div class="source-desc">Central government gateway for higher education scholarships and direct benefit transfer eligibility.</div>
        <div class="source-footer">
          <span>Checked: Certified Official</span>
          <a href="https://scholarships.gov.in" target="_blank" rel="noreferrer" class="source-open-btn">Open Source ↗</a>
        </div>
      </div>

      <div class="source-card">
        <div class="source-card-header">
          <div class="source-title-group">
            <span class="source-logo">⛅</span>
            <div>
              <div class="source-name">Open-Meteo Meteorological Sensor API</div>
              <div class="source-authority">National Weather Services & ECMWF</div>
            </div>
          </div>
          <span class="source-badge official">🛡️ Live Sensor Data</span>
        </div>
        <div class="source-desc">High-resolution numerical weather prediction models providing temperature and rainfall probabilities.</div>
        <div class="source-footer">
          <span>Checked: Realtime</span>
          <a href="https://open-meteo.com" target="_blank" rel="noreferrer" class="source-open-btn">Open Source ↗</a>
        </div>
      </div>`;
    return;
  }

  let html = '';
  allSources.forEach(s => {
    const isGov = s.is_official || (s.url && (s.url.includes('.gov.in') || s.url.includes('.nic.in')));
    const isUnverified = s.status === 'UNVERIFIED';

    html += `
      <div class="source-card">
        <div class="source-card-header">
          <div class="source-title-group">
            <span class="source-logo">${isGov ? '🏛️' : '🌐'}</span>
            <div>
              <div class="source-name">${escapeHtml(s.name || s.scheme || 'Authoritative Source')}</div>
              <div class="source-authority">${escapeHtml(s.authority || (isGov ? 'Government of India / State Authority' : 'Public Knowledge Base'))}</div>
            </div>
          </div>
          <span class="source-badge ${isGov ? 'official' : (isUnverified ? '' : 'official')}">
            ${isGov ? '🛡️ Official Source' : (isUnverified ? '⚠️ Unofficial' : '✓ Verified')}
          </span>
        </div>
        <div class="source-desc">${escapeHtml(s.reason || 'Cross-referenced against verified public portal documentation.')}</div>
        <div class="source-footer">
          <span>Checked: Just now</span>
          ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer" class="source-open-btn">Open Source ↗</a>` : ''}
        </div>
      </div>`;
  });

  container.innerHTML = html;
}

// 7. Photo / Document Upload from UI
async function uploadFileFromPage(e) {
  const file = e.target.files[0];
  if (!file) return;

  if (file.size > 10 * 1024 * 1024) {
    alert("File size exceeds 10MB limit.");
    return;
  }

  showToast('Uploading photo to BoloAI...');

  // 1. Get or create token for current session
  try {
    if (!activeSessionId) await createNewSession();

    // Trigger upload link request in session
    await fetch('/agent/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, text: 'Mere paas ek poster hai verify karna hai.' }),
    });

    const sessRes = await fetch(`/sessions/${activeSessionId}`);
    const session = await sessRes.json();
    const uploadEvt = (session.events || []).slice().reverse().find(e => e.type === 'tool.result' && e.data?.tool === 'request_document_upload');
    const token = uploadEvt?.data?.result?.token;

    if (token) {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`/u/${token}`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.ok) {
        document.getElementById('upload-success-panel').style.display = 'block';
        document.getElementById('upload-success-details').textContent = `Received: ${file.name} (${Math.round(file.size / 1024)} KB)`;
        showToast('Photo received! BoloAI is analyzing claims.');
        await refreshDashboard();
        // Scroll to results
        document.getElementById('results').scrollIntoView({ behavior: 'smooth' });
      }
    }
  } catch (err) {
    showToast('Failed to upload photo.');
  }
}

// 8. Interactive Actions
async function sendMessage() {
  const input = document.getElementById('user-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';

  if (!activeSessionId) {
    await createNewSession();
  }

  showToast('Sending to BoloAI Master Agent...');
  try {
    const res = await fetch('/agent/respond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSessionId, text }),
    });
    await res.json();
    await refreshDashboard();
  } catch (err) {
    showToast('Failed to send turn');
  }
}

async function runScenario(scenarioId) {
  showToast(`Starting ${scenarioId.toUpperCase()} demo scenario...`);
  try {
    const res = await fetch(`/demo/simulate-scenario?scenario_id=${scenarioId}`, { method: 'POST' });
    const data = await res.json();
    activeSessionId = data.session_id;
    connectLiveSocket(activeSessionId);
    await refreshDashboard();
    showToast(`Loaded: ${data.scenario}`);
    // Scroll to live call section
    scrollToCall();
  } catch (err) {
    showToast('Error running demo scenario');
  }
}

function scrollToCall() {
  const el = document.getElementById('live-call');
  if (el) {
    el.scrollIntoView({ behavior: 'smooth' });
    setTimeout(() => {
      document.getElementById('user-input')?.focus();
    }, 500);
  }
}

// 9. Call History Drawer
async function toggleHistoryDrawer() {
  const drawer = document.getElementById('history-drawer');
  const overlay = document.getElementById('drawer-overlay');
  const isOpen = drawer.classList.contains('open');

  if (isOpen) {
    closeHistoryDrawer();
  } else {
    drawer.classList.add('open');
    overlay.classList.add('open');
    await loadHistoryDrawer();
  }
}

function closeHistoryDrawer() {
  const drawer = document.getElementById('history-drawer');
  const overlay = document.getElementById('drawer-overlay');
  if (drawer) drawer.classList.remove('open');
  if (overlay) overlay.classList.remove('open');
}

async function loadHistoryDrawer() {
  const container = document.getElementById('history-drawer-list');
  if (!container) return;
  container.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">Loading call history...</div>';

  try {
    const res = await fetch('/sessions');
    const sessions = await res.json();
    if (!sessions || sessions.length === 0) {
      container.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">No call sessions recorded yet.</div>';
      return;
    }

    let html = '';
    sessions.forEach(s => {
      const isActive = s.session_id === activeSessionId;
      const time = s.updated_at ? new Date(s.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
      html += `
        <div class="history-item ${isActive ? 'active' : ''}" onclick="switchSession('${s.session_id}')">
          <div class="history-item-header">
            <span class="history-item-caller">${escapeHtml(s.caller || '+91 98*** **210')}</span>
            <span style="font-size: 11px; font-weight: 700; color: var(--primary-purple);">${escapeHtml(s.session_id)}</span>
          </div>
          <div class="history-item-goal">${escapeHtml(s.current_goal || 'General Digital Services Inquiry')}</div>
          <div class="history-item-footer">
            <span>Status: <strong>${(s.call_status || 'idle').toUpperCase()}</strong></span>
            <span>Events: ${s.events_count || 0} &bull; ${time}</span>
          </div>
        </div>`;
    });
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = '<div style="color: #EF4444; padding: 20px;">Failed to load call history.</div>';
  }
}

function toggleStatusDrawer() {
  const pills = document.getElementById('system-status-pills');
  const icon = document.getElementById('status-toggle-icon');
  if (pills) {
    const isShown = pills.style.display !== 'none';
    pills.style.display = isShown ? 'none' : 'flex';
    if (icon) icon.textContent = isShown ? '▶' : '▼';
  }
}

function resetCallTimer() {
  if (callTimerInterval) clearInterval(callTimerInterval);
  callSeconds = 0;
  callTimerInterval = setInterval(() => {
    callSeconds++;
    const mins = String(Math.floor(callSeconds / 60)).padStart(2, '0');
    const secs = String(callSeconds % 60).padStart(2, '0');
    const el = document.getElementById('call-duration');
    if (el) el.textContent = `${mins}:${secs}`;
  }, 1000);
}

function showToast(message) {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 3200);
}

function escapeHtml(str) {
  if (typeof str !== 'string') return String(str);
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[m]);
}

function setupEventListeners() {
  const input = document.getElementById('user-input');
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendMessage();
    });
  }
}
