// BoloAI Dashboard Controller — Bharat Voice-First AI Digital Services Gateway

let activeSessionId = null;
let liveSocket = null;
let callTimerInterval = null;
let callSeconds = 0;
let currentTab = 'conversation';

document.addEventListener('DOMContentLoaded', async () => {
  await checkHealth();
  await loadRecentSessionOrCreate();
  setupEventListeners();

  // Periodic poll fallback in case of background Exotel/multimodal updates
  setInterval(async () => {
    if (activeSessionId) {
      await refreshDashboardSilently();
    }
  }, 3000);
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
    showToast(`New session active: ${activeSessionId}`);
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
  showToast(`Switched to session: ${sessionId}`);
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
    renderTrace(session);
    renderChat(session.history);
    renderSourcesTab(session);
    renderContext(session.context, session.current_goal);
    renderToolsPanel(session);
    renderRawEvents(session);
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
    renderTrace(session);
    renderChat(session.history);
    renderSourcesTab(session);
    renderContext(session.context, session.current_goal);
    renderRawEvents(session);
  } catch (e) {}
}

function renderCallCard(session) {
  const callerEl = document.getElementById('call-caller-id');
  const statusPill = document.getElementById('call-status-pill');
  const avatarEl = document.getElementById('call-avatar');
  const waveform = document.getElementById('call-waveform');

  if (session.caller) {
    const raw = session.caller;
    callerEl.textContent = raw.length > 7 ? raw.substring(0, 5) + '••••' + raw.substring(raw.length - 2) : raw;
  } else {
    callerEl.textContent = '+91 98*** **210';
  }

  const rawStatus = (session.call_status || 'idle').toLowerCase();
  statusPill.className = 'status-pill';

  if (rawStatus === 'listening') {
    statusPill.classList.add('state-listening');
    statusPill.textContent = '🎧 LISTENING...';
    avatarEl.textContent = '🎧';
    waveform.classList.add('active');
  } else if (rawStatus === 'transcribing') {
    statusPill.classList.add('state-transcribing');
    statusPill.textContent = '✍️ TRANSCRIBING...';
    avatarEl.textContent = '✍️';
    waveform.classList.remove('active');
  } else if (rawStatus === 'thinking' || rawStatus === 'tool_running' || rawStatus === 'verifying') {
    statusPill.classList.add('state-thinking');
    statusPill.textContent = '🧠 THINKING...';
    avatarEl.textContent = '🧠';
    waveform.classList.remove('active');
  } else if (rawStatus === 'speaking') {
    statusPill.classList.add('state-speaking');
    statusPill.textContent = '🔊 SPEAKING...';
    avatarEl.textContent = '🔊';
    waveform.classList.add('active');
  } else if (rawStatus === 'ended') {
    statusPill.classList.add('state-ended');
    statusPill.textContent = '⏹️ ENDED';
    avatarEl.textContent = '📞';
    waveform.classList.remove('active');
  } else {
    statusPill.classList.add('state-idle');
    statusPill.textContent = '⚪ IDLE';
    avatarEl.textContent = '📞';
    waveform.classList.remove('active');
  }

  document.getElementById('call-lang-badge').textContent = session.language === 'en-IN' ? 'English (India)' : 'Hindi / Hinglish';
}

function renderTrace(session) {
  const container = document.getElementById('trace-container');
  if (!container) return;

  const events = session.events || [];
  if (!events || events.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 40px 20px; color: var(--text-dim);">
        <p>No operational trace events recorded yet.</p>
        <p style="font-size: 13px; margin-top: 6px;">Speak into phone, type below, or run a 1-click Demo Scenario.</p>
      </div>`;
    return;
  }

  let html = '';
  events.forEach((evt) => {
    const type = evt.type;
    const data = evt.data || {};
    const time = evt.ts ? new Date(evt.ts).toLocaleTimeString() : '';

    if (type === 'transcript.final' || type === 'transcript.user') {
      html += `
        <div class="trace-item">
          <div class="trace-icon user">🗣️</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge user">Caller Utterance</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">"${escapeHtml(data.text || '')}"</div>
          </div>
        </div>`;
    } else if (type === 'agent.intent') {
      html += `
        <div class="trace-item">
          <div class="trace-icon intent">🎯</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge intent">Intent Detected</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">Goal: ${escapeHtml(data.goal || data.intent || 'Service Inquiry')}</div>
            <div class="trace-meta-grid">
              <div><span class="meta-field-label">Category</span><div class="meta-field-value">${escapeHtml(data.intent || 'GENERAL')}</div></div>
              <div><span class="meta-field-label">Language</span><div class="meta-field-value">${escapeHtml(data.detected_language || 'hi-IN')}</div></div>
            </div>
          </div>
        </div>`;
    } else if (type === 'agent.plan') {
      html += `
        <div class="trace-item">
          <div class="trace-icon plan">📋</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge plan">Agent Decision & Plan</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-body">${escapeHtml(data.reason || 'Evaluating user requirements and tool eligibility.')}</div>
            ${data.tool ? `<div style="margin-top: 8px; font-size: 12px; font-weight: 600; color: var(--primary);">Planned Tool: ${escapeHtml(data.tool)}</div>` : ''}
            ${data.missing_slots ? `<div style="margin-top: 8px; font-size: 12px; color: var(--accent-amber); font-weight: 600;">Clarification Required: ${escapeHtml(data.missing_slots.join(', '))}</div>` : ''}
          </div>
        </div>`;
    } else if (type === 'attachment.received') {
      html += `
        <div class="trace-item">
          <div class="trace-icon tool">📸</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge tool">Photo Received</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">Caller uploaded document: ${escapeHtml(data.filename || 'poster.jpg')}</div>
            <div class="trace-meta-grid">
              <div><span class="meta-field-label">File Type</span><div class="meta-field-value">${escapeHtml(data.content_type || 'image/jpeg')}</div></div>
              <div><span class="meta-field-label">Size</span><div class="meta-field-value">${Math.round((data.size_bytes || 0) / 1024)} KB</div></div>
            </div>
          </div>
        </div>`;
    } else if (type === 'attachment.analyzed') {
      html += `
        <div class="trace-item">
          <div class="trace-icon plan">🔬</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge plan">Multimodal Analysis</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">Extracted Scheme: ${escapeHtml(data.scheme_name || 'Document')}</div>
            <div class="trace-body" style="margin-top: 6px;">${escapeHtml(data.extracted_text || '')}</div>
            ${data.red_flags ? `
              <div style="margin-top: 8px; padding: 8px 10px; background: #FEF2F2; border-left: 3px solid #EF4444; border-radius: 6px; font-size: 12px; color: #991B1B;">
                <strong>⚠️ Suspicious Red Flags:</strong>
                <ul style="margin-left: 16px; margin-top: 4px;">
                  ${data.red_flags.map(f => `<li>${escapeHtml(f)}</li>`).join('')}
                </ul>
              </div>` : ''}
          </div>
        </div>`;
    } else if (type === 'tool.call') {
      html += `
        <div class="trace-item">
          <div class="trace-icon tool">⚙️</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge tool">${data.action ? 'Running' : 'Tool Selected'}</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">Invoking: ${escapeHtml(data.tool || '')}</div>
            <div class="trace-meta-grid">
              <div><span class="meta-field-label">Arguments</span><div class="meta-field-value">${escapeHtml(JSON.stringify(data.args || {}))}</div></div>
            </div>
          </div>
        </div>`;
    } else if (type === 'verification.completed') {
      const isOfficial = data.status === 'VERIFIED_OFFICIAL';
      const isMultiple = data.status === 'VERIFIED_MULTIPLE_SOURCES';
      const isUnverified = data.status === 'UNVERIFIED';
      const badgeClass = isOfficial ? 'verify' : (isMultiple ? 'plan' : 'action');
      const badgeText = isOfficial ? 'VERIFIED OFFICIAL (.GOV.IN)' : (isUnverified ? 'UNVERIFIED / SUSPICIOUS' : data.status);

      html += `
        <div class="trace-item">
          <div class="trace-icon verify">🛡️</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge ${badgeClass}">${badgeText}</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">${escapeHtml(data.reason || 'Verification completed against authoritative source.')}</div>

            <!-- Dedicated Embedded Source Card -->
            ${data.sources && data.sources.length ? `
              <div class="source-card ${isOfficial ? 'official' : (isUnverified ? 'unverified' : 'curated')}" style="margin-top: 10px; margin-bottom: 0;">
                <div class="source-card-header">
                  <div class="source-card-title">
                    <span>${isOfficial ? '🏛️' : '🌐'}</span> ${escapeHtml(data.sources[0].name || data.sources[0].scheme || 'Authoritative Source')}
                  </div>
                  <span class="source-badge ${isOfficial ? 'official' : (isUnverified ? 'unverified' : 'curated')}">
                    ${isOfficial ? '🛡️ Official Govt Portal' : (isUnverified ? '⚠️ Unofficial Source' : 'Curated Dataset')}
                  </span>
                </div>
                ${data.sources[0].url ? `<a href="${escapeHtml(data.sources[0].url)}" target="_blank" rel="noreferrer" class="source-card-url">${escapeHtml(data.sources[0].url)} ↗</a>` : ''}
                <div class="source-card-claims">${escapeHtml(data.reason)}</div>
              </div>` : ''}
          </div>
        </div>`;
    } else if (type.startsWith('action.')) {
      const simulated = data.simulated === true;
      const state = type === 'action.failed' ? 'Failed' :
        type === 'action.completed' ? (simulated ? 'Simulated' : 'Completed') :
        type === 'action.confirmed' ? 'Confirmed' :
        type === 'action.requested' ? 'Pending' :
        type === 'action.reused' ? (simulated ? 'Simulated' : data.state === 'FAILED' ? 'Failed' : 'Completed') : 'Running';
      const style = state === 'Failed' ? 'action-failed' : state === 'Simulated' ? 'action-simulated' :
        state === 'Completed' ? 'action-completed' : 'action-pending';
      const icon = state === 'Failed' ? '!' : state === 'Simulated' ? '◌' : state === 'Completed' ? '✓' : '…';
      const actionNames = {send_sms: 'SMS', create_complaint: 'Complaint', request_document_upload: 'Upload link'};
      const name = actionNames[data.action] || 'Action';
      html += `
        <div class="trace-item">
          <div class="trace-icon ${style}">${icon}</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge ${style}">${state}</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title">${escapeHtml(`${name}: ${state.toLowerCase()}`)}</div>
            ${state === 'Failed' ? `<div class="trace-body">${escapeHtml(data.error || 'Provider did not confirm success.')}</div>` : ''}
            ${state === 'Simulated' ? '<div class="trace-body">Demo only. No real provider action occurred.</div>' : ''}
            <div class="trace-meta-grid">
              <div><span class="meta-field-label">Reference ID</span><div class="meta-field-value">${escapeHtml(data.reference_id || 'Not supplied')}</div></div>
              <div><span class="meta-field-label">Status</span><div class="meta-field-value">${escapeHtml(state)}</div></div>
            </div>
          </div>
        </div>`;
    } else if (type === 'assistant.response') {
      html += `
        <div class="trace-item">
          <div class="trace-icon response">🔊</div>
          <div class="trace-content">
            <div class="trace-header">
              <span class="trace-badge response">Spoken Spurt to Caller</span>
              <span style="font-size: 11px; color: var(--text-dim);">${time}</span>
            </div>
            <div class="trace-title" style="color: #065F46;">"${escapeHtml(data.text || '')}"</div>
          </div>
        </div>`;
    }
  });

  container.innerHTML = html;
}

function renderChat(history) {
  const container = document.getElementById('chat-container');
  if (!container) return;

  if (!history || history.length === 0) {
    container.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">No conversation messages yet.</div>';
    return;
  }

  let html = '';
  history.forEach((msg) => {
    const isUser = msg.role === 'user';
    html += `
      <div class="bubble ${isUser ? 'user' : 'assistant'}">
        <div class="bubble-sender">
          <span>${isUser ? 'Caller' : 'BoloAI'}</span>
          <span style="font-size: 10px; font-weight: normal; opacity: 0.7;">Voice Turn</span>
        </div>
        <div>${escapeHtml(msg.content)}</div>
      </div>`;
  });

  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

function renderSourcesTab(session) {
  const container = document.getElementById('sources-container');
  if (!container) return;

  const verifs = session.verification_results || [];
  const events = session.events || [];

  // Collect all verified sources from verification_results and events
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
    container.innerHTML = `
      <div style="text-align: center; padding: 40px 20px; color: var(--text-dim);">
        <p>No verified sources referenced in this call yet.</p>
        <p style="font-size: 13px; margin-top: 6px;">When the caller inquires about government schemes, weather, or claims, authoritative official sources (.gov.in) will appear here.</p>
      </div>`;
    return;
  }

  let html = '';
  allSources.forEach(s => {
    const isGov = s.is_official || (s.url && (s.url.includes('.gov.in') || s.url.includes('.nic.in')));
    const isUnverified = s.status === 'UNVERIFIED';

    html += `
      <div class="source-card ${isGov ? 'official' : (isUnverified ? 'unverified' : 'curated')}">
        <div class="source-card-header">
          <div class="source-card-title">
            <span>${isGov ? '🏛️' : '🌐'}</span> ${escapeHtml(s.name || s.scheme || 'Verified Source')}
          </div>
          <span class="source-badge ${isGov ? 'official' : (isUnverified ? 'unverified' : 'curated')}">
            ${isGov ? '🛡️ Official Govt Portal' : (isUnverified ? '⚠️ Unofficial Source' : 'Curated Dataset')}
          </span>
        </div>
        ${s.url ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noreferrer" class="source-card-url">${escapeHtml(s.url)} ↗</a>` : ''}
        <div class="source-card-claims">${escapeHtml(s.reason || 'Verified against authoritative documentation.')}</div>
        <div class="source-card-footer">
          <span>Authority: ${escapeHtml(s.authority || (isGov ? 'Govt of India / State Portal' : 'Public Reference'))}</span>
          <span>Security: ${isGov ? 'Certified Portal' : 'Inspection Required'}</span>
        </div>
      </div>`;
  });

  container.innerHTML = html;
}

function renderContext(ctx, goal) {
  const container = document.getElementById('context-container');
  if (!container) return;

  const state = ctx?.state || 'Not specified';
  const course = ctx?.course || 'Not specified';
  const year = ctx?.year || 'Not specified';
  const income = ctx?.income ? `₹${(ctx.income / 100000).toFixed(1)} Lakh/yr` : 'Not specified';
  const trackingId = ctx?.tracking_id || 'None';
  const phone = ctx?.phone || '+91 98765 43210';

  container.innerHTML = `
    <div style="margin-bottom: 14px;">
      <div class="context-card-label">Active Goal</div>
      <div style="font-size: 14.5px; font-weight: 700; color: var(--primary);">${escapeHtml(goal || 'Digital Services Gateway Assistance')}</div>
    </div>
    <div class="context-grid">
      <div class="context-card"><div class="context-card-label">State</div><div class="context-card-val">${escapeHtml(state)}</div></div>
      <div class="context-card"><div class="context-card-label">Education</div><div class="context-card-val">${escapeHtml(course)}</div></div>
      <div class="context-card"><div class="context-card-label">Year of Study</div><div class="context-card-val">${escapeHtml(year)}</div></div>
      <div class="context-card"><div class="context-card-label">Family Income</div><div class="context-card-val">${escapeHtml(income)}</div></div>
      <div class="context-card"><div class="context-card-label">Tracking Consignment</div><div class="context-card-val">${escapeHtml(trackingId)}</div></div>
      <div class="context-card"><div class="context-card-label">Caller Phone</div><div class="context-card-val">${escapeHtml(phone)}</div></div>
    </div>`;
}

function renderToolsPanel(session) {
  const container = document.getElementById('tools-container');
  if (!container) return;

  const toolsList = [
    { title: 'Open-Meteo Live Weather', icon: '☀️', type: 'Live Sensor API', desc: 'Realtime temperature, rain forecast and weather codes.' },
    { title: 'Government Schemes Engine', icon: '🏛️', type: 'Verified Official (.gov.in)', desc: 'Pre/Post-Matric, NSP, PM-Kisan with eligibility matching.' },
    { title: 'Consignment Tracking', icon: '📦', type: 'Logistics Gateway', desc: 'Live transit hub status and estimated delivery time.' },
    { title: 'Grievance Redressal Action', icon: '📝', type: 'Action Dispatcher', desc: 'Generates formal complaint reference IDs.' },
    { title: 'SMS Portal Dispatch', icon: '💬', type: 'Cellular Dispatcher', desc: 'Sends authoritative web portal links to caller phone.' },
    { title: 'Multimodal Document Handoff', icon: '📸', type: 'Document Inspection', desc: 'Generates secure /u/{token} upload links for posters.' },
    { title: 'Verification Engine', icon: '🛡️', type: 'Trust Classifier', desc: 'Inspects claims, ranks official sources, stops hallucinations.' },
  ];

  let html = '';
  toolsList.forEach(t => {
    html += `
      <div class="tool-box">
        <div class="tool-box-header">
          <span style="font-size: 20px;">${t.icon}</span>
          <span class="tool-badge-pill">${t.type}</span>
        </div>
        <div class="tool-box-title">${t.title}</div>
        <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">${t.desc}</div>
      </div>`;
  });

  container.innerHTML = html;
}

function renderRawEvents(session) {
  const tbody = document.getElementById('events-tbody');
  if (!tbody) return;

  const events = session.events || [];
  let html = '';
  events.slice().reverse().forEach(evt => {
    const time = evt.ts ? new Date(evt.ts).toLocaleTimeString() : '';
    html += `
      <tr>
        <td style="color: var(--text-dim);">${time}</td>
        <td><strong>${escapeHtml(evt.type)}</strong></td>
        <td><code>${escapeHtml(JSON.stringify(evt.data || {}))}</code></td>
      </tr>`;
  });
  tbody.innerHTML = html;
}

// 4. Interactive Actions
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
    const data = await res.json();
    await refreshDashboard();
  } catch (err) {
    showToast('Failed to send message');
  }
}

async function runScenario(scenarioId) {
  showToast(`Simulating ${scenarioId.toUpperCase()} flow...`);
  try {
    const res = await fetch(`/demo/simulate-scenario?scenario_id=${scenarioId}`, { method: 'POST' });
    const data = await res.json();
    activeSessionId = data.session_id;
    connectLiveSocket(activeSessionId);
    await refreshDashboard();
    showToast(`Loaded scenario: ${data.scenario}`);
  } catch (err) {
    showToast('Error running scenario');
  }
}

// 5. History Drawer
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
  container.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">Loading sessions...</div>';

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
            <span style="font-size: 11px; font-weight: 600; color: var(--primary);">${escapeHtml(s.session_id)}</span>
          </div>
          <div class="history-item-goal">${escapeHtml(s.current_goal || 'General Voice Digital Service Inquiry')}</div>
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

// 6. Navigation Tabs
function switchTab(tabName) {
  currentTab = tabName;
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-content').forEach(pane => {
    pane.style.display = pane.id === `tab-${tabName}` ? 'block' : 'none';
  });
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
