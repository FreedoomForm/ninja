// DOM Elements
const elements = {
  connectionStatus: document.getElementById('connectionStatus'),
  botStatus: document.getElementById('botStatus'),
  statStatus: document.getElementById('statStatus'),
  statMessages: document.getElementById('statMessages'),
  statUser: document.getElementById('statUser'),
  startBtn: document.getElementById('startBtn'),
  stopBtn: document.getElementById('stopBtn'),
  refreshBtn: document.getElementById('refreshBtn'),
  startBackendBtn: document.getElementById('startBackendBtn'),
  backendStatus: document.getElementById('backendStatus'),
  controlLogs: document.getElementById('controlLogs'),
  logsList: document.getElementById('logsList'),
  clearLogsBtn: document.getElementById('clearLogsBtn'),
  saveConfigBtn: document.getElementById('saveConfigBtn'),
  apiId: document.getElementById('apiId'),
  apiHash: document.getElementById('apiHash'),
  mistralKey: document.getElementById('mistralKey'),
  mistralModel: document.getElementById('mistralModel'),
  systemPrompt: document.getElementById('systemPrompt')
};

let isConnected = false;
let isBotRunning = false;

// Tab switching
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

// Update UI
function updateConnectionStatus(connected) {
  isConnected = connected;
  const dot = elements.connectionStatus.querySelector('.status-dot');
  const text = elements.connectionStatus.querySelector('span:last-child');
  
  if (connected) {
    dot.classList.remove('disconnected');
    dot.classList.add('connected');
    text.textContent = 'Connected';
    elements.backendStatus.classList.remove('show');
  } else {
    dot.classList.remove('connected');
    dot.classList.add('disconnected');
    text.textContent = 'Disconnected';
    elements.backendStatus.classList.add('show');
  }
}

function updateBotStatus(running, username, messageCount) {
  isBotRunning = running;
  
  const badge = elements.botStatus.querySelector('.status-badge');
  badge.textContent = running ? 'Online' : 'Offline';
  badge.className = `status-badge ${running ? 'online' : 'offline'}`;
  
  elements.statStatus.textContent = running ? 'Running' : 'Stopped';
  elements.statMessages.textContent = messageCount || 0;
  elements.statUser.textContent = username || '-';
  
  elements.startBtn.disabled = running || !isConnected;
  elements.stopBtn.disabled = !running || !isConnected;
}

function renderLogs(logs) {
  const html = logs.length === 0 
    ? '<div class="empty-state"><span class="empty-icon">💬</span><p>No messages yet</p></div>'
    : logs.slice(0, 50).map(log => `
        <div class="log-entry ${log.direction}">
          <div>
            <span class="time">${log.timestamp}</span>
            <span class="sender">${log.sender}</span>
            <span class="message">${log.message}</span>
          </div>
        </div>
      `).join('');
  
  elements.controlLogs.innerHTML = html;
  elements.logsList.innerHTML = html;
}

function updateConfig(config) {
  elements.apiId.value = config.api_id || '';
  elements.apiHash.value = config.api_hash || '';
  elements.mistralKey.value = config.mistral_key || '';
  elements.mistralModel.value = config.mistral_model || '';
  elements.systemPrompt.value = config.system_prompt || '';
}

// Fetch data
async function fetchStatus() {
  try {
    const status = await window.electronAPI.getStatus();
    updateConnectionStatus(true);
    updateBotStatus(status.running, status.username, status.message_count);
    return true;
  } catch {
    updateConnectionStatus(false);
    updateBotStatus(false);
    return false;
  }
}

async function fetchLogs() {
  try {
    const logs = await window.electronAPI.getLogs();
    renderLogs(logs.reverse());
  } catch {
    renderLogs([]);
  }
}

async function fetchConfig() {
  try {
    const config = await window.electronAPI.getConfig();
    updateConfig(config);
  } catch {}
}

// Event handlers
elements.startBtn.addEventListener('click', async () => {
  elements.startBtn.disabled = true;
  elements.startBtn.innerHTML = '<span class="btn-icon loading">⏳</span> Starting...';
  
  try {
    await window.electronAPI.startBot();
    await fetchStatus();
  } catch (e) {
    console.error(e);
  }
  
  elements.startBtn.innerHTML = '<span class="btn-icon">▶️</span> Start Bot';
});

elements.stopBtn.addEventListener('click', async () => {
  elements.stopBtn.disabled = true;
  elements.stopBtn.innerHTML = '<span class="btn-icon loading">⏳</span> Stopping...';
  
  try {
    await window.electronAPI.stopBot();
    await fetchStatus();
  } catch (e) {
    console.error(e);
  }
  
  elements.stopBtn.innerHTML = '<span class="btn-icon">⏹️</span> Stop Bot';
});

elements.refreshBtn.addEventListener('click', async () => {
  elements.refreshBtn.disabled = true;
  elements.refreshBtn.innerHTML = '<span class="btn-icon loading">⏳</span> Refreshing...';
  
  await fetchStatus();
  await fetchLogs();
  
  elements.refreshBtn.innerHTML = '<span class="btn-icon">🔄</span> Refresh';
  elements.refreshBtn.disabled = false;
});

elements.startBackendBtn.addEventListener('click', async () => {
  elements.startBackendBtn.disabled = true;
  elements.startBackendBtn.innerHTML = '<span class="loading">⏳</span> Starting...';
  
  try {
    const result = await window.electronAPI.startBackend();
    if (result.success) {
      await fetchStatus();
      await fetchConfig();
    }
  } catch (e) {
    console.error(e);
  }
  
  elements.startBackendBtn.innerHTML = '🚀 Start Backend';
  elements.startBackendBtn.disabled = false;
});

elements.saveConfigBtn.addEventListener('click', async () => {
  const config = {
    api_id: elements.apiId.value,
    api_hash: elements.apiHash.value,
    mistral_key: elements.mistralKey.value,
    mistral_model: elements.mistralModel.value,
    system_prompt: elements.systemPrompt.value
  };
  
  elements.saveConfigBtn.disabled = true;
  elements.saveConfigBtn.innerHTML = '<span class="btn-icon loading">⏳</span> Saving...';
  
  try {
    await window.electronAPI.saveConfig(config);
    elements.saveConfigBtn.innerHTML = '<span class="btn-icon">✅</span> Saved!';
    setTimeout(() => {
      elements.saveConfigBtn.innerHTML = '<span class="btn-icon">💾</span> Save Settings';
      elements.saveConfigBtn.disabled = false;
    }, 1500);
  } catch (e) {
    elements.saveConfigBtn.innerHTML = '<span class="btn-icon">💾</span> Save Settings';
    elements.saveConfigBtn.disabled = false;
  }
});

elements.clearLogsBtn.addEventListener('click', async () => {
  try {
    await window.electronAPI.clearLogs();
    renderLogs([]);
  } catch (e) {
    console.error(e);
  }
});

// Initialize
async function init() {
  await fetchStatus();
  await fetchConfig();
  await fetchLogs();
  
  // Poll for updates
  setInterval(async () => {
    await fetchStatus();
    await fetchLogs();
  }, 3000);
}

init();
