const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

// ESM modules (loaded dynamically)
let TelegramClient, StringSession, NewMessage, Mistral;

let mainWindow = null;
let telegramClient = null;
let mistralClient = null;
let isRunning = false;
let username = null;
let messageCount = 0;

// Data paths
const dataDir = path.join(app.getPath('userData'), 'ninja-data');
const sessionFile = path.join(dataDir, 'session.txt');
const configFile = path.join(dataDir, 'config.json');
const logsFile = path.join(dataDir, 'logs.json');

// Ensure data directory exists
if (!fs.existsSync(dataDir)) {
  fs.mkdirSync(dataDir, { recursive: true });
}

// Default config
const defaultConfig = {
  apiId: 36244324,
  apiHash: '15657d847ab4b8ae111ade8e2cbca51f',
  mistralKey: 'bz2Mp9E67ep1QfmaHzXBSJaRVOfIkx8v',
  mistralModel: 'mistral-medium-latest',
  systemPrompt: 'You are the personal AI assistant replying on behalf of the account owner in Telegram private chats. Be friendly, concise, and natural. Reply in the same language the user wrote in.'
};

// Conversation history
const history = {};
const HISTORY_LIMIT = 12;

// Logs
let logs = [];

// Load ESM modules dynamically
async function loadModules() {
  const telegram = await import('telegram');
  const sessions = await import('telegram/sessions');
  const events = await import('telegram/events');
  const mistral = await import('@mistralai/mistralai');
  
  TelegramClient = telegram.TelegramClient;
  StringSession = sessions.StringSession;
  NewMessage = events.NewMessage;
  Mistral = mistral.Mistral;
}

// Load config
function loadConfig() {
  try {
    if (fs.existsSync(configFile)) {
      return { ...defaultConfig, ...JSON.parse(fs.readFileSync(configFile, 'utf8')) };
    }
  } catch (e) {
    console.error('Load config error:', e);
  }
  return defaultConfig;
}

// Save config
function saveConfig(config) {
  try {
    fs.writeFileSync(configFile, JSON.stringify(config, null, 2));
  } catch (e) {
    console.error('Save config error:', e);
  }
}

// Load logs
function loadLogs() {
  try {
    if (fs.existsSync(logsFile)) {
      logs = JSON.parse(fs.readFileSync(logsFile, 'utf8'));
    }
  } catch (e) {
    logs = [];
  }
}

// Save logs
function saveLogsToFile() {
  try {
    fs.writeFileSync(logsFile, JSON.stringify(logs.slice(-500), null, 2));
  } catch (e) {}
}

// Add log entry
function addLog(message, sender = 'System', direction = 'system') {
  const entry = {
    id: Date.now().toString(),
    timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
    sender,
    message: message.substring(0, 200),
    direction
  };
  logs.push(entry);
  saveLogsToFile();
  
  // Send to window if exists
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('new-log', entry);
  }
}

// Build messages for Mistral
function buildMessages(chatId, systemPrompt) {
  const msgs = [{ role: 'system', content: systemPrompt }];
  if (history[chatId]) {
    msgs.push(...history[chatId]);
  }
  return msgs;
}

// Push to history
function pushHistory(chatId, role, content) {
  if (!history[chatId]) history[chatId] = [];
  history[chatId].push({ role, content });
  if (history[chatId].length > HISTORY_LIMIT) {
    history[chatId] = history[chatId].slice(-HISTORY_LIMIT);
  }
}

// Get Mistral response
async function getMistralResponse(messages, config) {
  const response = await mistralClient.chat({
    model: config.mistralModel,
    messages: messages,
    temperature: 0.7,
    maxTokens: 400
  });
  return response.choices[0].message.content.trim();
}

// Reply to message
async function replyToMessage(chatId, sender, text, config) {
  const senderName = sender.firstName || sender.lastName || sender.id.toString();
  addLog(text, senderName, 'incoming');
  
  pushHistory(chatId, 'user', text);
  
  try {
    addLog('Getting AI response...', 'System', 'system');
    const messages = buildMessages(chatId, config.systemPrompt);
    const reply = await getMistralResponse(messages, config);
    
    pushHistory(chatId, 'assistant', reply);
    addLog('Sending to Telegram...', 'System', 'system');
    
    await telegramClient.sendMessage(chatId, { message: reply });
    messageCount++;
    
    addLog(reply, senderName, 'outgoing');
  } catch (e) {
    addLog(`Error: ${e.message}`, 'System', 'error');
    console.error('Reply error:', e);
  }
}

// Process unread messages
async function processUnreadMessages(config) {
  try {
    const dialogs = await telegramClient.getDialogs({ limit: 100 });
    
    for (const dialog of dialogs) {
      const entity = dialog.entity;
      
      // Skip non-users, self, bots
      if (!entity || entity.className !== 'User' || entity.self || entity.bot) continue;
      
      const senderName = entity.firstName || entity.lastName || entity.id.toString();
      
      if (dialog.unreadCount > 0) {
        addLog(`Found ${dialog.unreadCount} unread from ${senderName}`, 'System', 'system');
        
        const messages = await telegramClient.getMessages(entity, { limit: dialog.unreadCount });
        
        for (const msg of messages.reverse()) {
          if (!msg.out && msg.text) {
            await replyToMessage(dialog.id, entity, msg.text, config);
          }
        }
        
        // Mark as read
        await telegramClient.readHistory(entity);
      } else {
        // Check last message
        const messages = await telegramClient.getMessages(entity, { limit: 1 });
        if (messages.length > 0 && messages[0] && !messages[0].out && messages[0].text) {
          const msgTime = new Date(messages[0].date * 1000);
          const hoursAgo = (Date.now() - msgTime.getTime()) / (1000 * 60 * 60);
          
          if (hoursAgo < 24) {
            addLog(`Replying to last message from ${senderName}`, 'System', 'system');
            await replyToMessage(dialog.id, entity, messages[0].text, config);
          }
        }
      }
    }
  } catch (e) {
    addLog(`Process error: ${e.message}`, 'System', 'error');
  }
}

// Start bot
async function startBot(config) {
  try {
    addLog('Starting bot...', 'System', 'system');
    
    // Load session
    let sessionString = '';
    if (fs.existsSync(sessionFile)) {
      sessionString = fs.readFileSync(sessionFile, 'utf8');
    }
    
    const stringSession = new StringSession(sessionString);
    
    // Create Telegram client
    telegramClient = new TelegramClient(stringSession, config.apiId, config.apiHash, {
      connectionRetries: 5,
    });
    
    // Initialize Mistral client
    mistralClient = new Mistral(config.mistralKey);
    
    // Connect
    await telegramClient.start({
      phoneNumber: async () => {
        addLog('Please enter phone number in console...', 'System', 'system');
        return await new Promise((resolve) => {
          const readline = require('readline');
          const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout
          });
          rl.question('Enter phone number: ', (answer) => {
            rl.close();
            resolve(answer);
          });
        });
      },
      password: async () => {
        return await new Promise((resolve) => {
          const readline = require('readline');
          const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout
          });
          rl.question('Enter 2FA password: ', (answer) => {
            rl.close();
            resolve(answer);
          });
        });
      },
      phoneCode: async () => {
        return await new Promise((resolve) => {
          const readline = require('readline');
          const rl = readline.createInterface({
            input: process.stdin,
            output: process.stdout
          });
          rl.question('Enter verification code: ', (answer) => {
            rl.close();
            resolve(answer);
          });
        });
      },
      onError: (err) => {
        addLog(`Login error: ${err.message}`, 'System', 'error');
      }
    });
    
    // Save session
    fs.writeFileSync(sessionFile, telegramClient.session.save());
    
    // Get user info
    const me = await telegramClient.getMe();
    username = me.username ? `@${me.username}` : me.firstName;
    isRunning = true;
    
    addLog(`Logged in as ${username}`, 'System', 'success');
    
    // Setup message handler
    telegramClient.addEventHandler(async (event) => {
      const message = event.message;
      
      // Skip outgoing, non-private, empty messages
      if (message.out || !event.isPrivate || !message.text) return;
      
      const sender = await message.getSender();
      
      // Skip self and bots
      if (sender.self || sender.bot) return;
      
      await replyToMessage(message.chatId, sender, message.text, config);
    }, new NewMessage({}));
    
    // Process existing messages
    addLog('Checking messages...', 'System', 'system');
    await processUnreadMessages(config);
    
    addLog('Bot is running! Waiting for new messages...', 'System', 'success');
    
    // Update UI
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('status-update', {
        running: isRunning,
        username,
        messageCount
      });
    }
    
  } catch (e) {
    addLog(`Start error: ${e.message}`, 'System', 'error');
    console.error('Start error:', e);
    isRunning = false;
  }
}

// Stop bot
async function stopBot() {
  if (telegramClient) {
    await telegramClient.disconnect();
    telegramClient = null;
  }
  isRunning = false;
  addLog('Bot stopped', 'System', 'info');
  
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send('status-update', {
      running: false,
      username,
      messageCount
    });
  }
}

// Create window
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 550,
    height: 650,
    minWidth: 450,
    minHeight: 550,
    title: 'Ninja Bot',
    icon: path.join(__dirname, 'icon.ico'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    backgroundColor: '#1a1a2e',
    show: false,
    autoHideMenuBar: true
  });

  mainWindow.loadFile('index.html');

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// App ready
app.whenReady().then(async () => {
  // Load ESM modules first
  await loadModules();
  
  loadLogs();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows closed
app.on('window-all-closed', async () => {
  if (telegramClient) {
    await telegramClient.disconnect();
  }
  app.quit();
});

// IPC handlers
ipcMain.handle('get-status', () => ({
  running: isRunning,
  username,
  messageCount
}));

ipcMain.handle('get-config', () => {
  const config = loadConfig();
  return {
    apiId: config.apiId.toString(),
    apiHash: config.apiHash,
    mistralKey: config.mistralKey,
    mistralModel: config.mistralModel,
    systemPrompt: config.systemPrompt
  };
});

ipcMain.handle('save-config', (event, config) => {
  const current = loadConfig();
  saveConfig({
    ...current,
    apiId: parseInt(config.apiId) || current.apiId,
    apiHash: config.apiHash || current.apiHash,
    mistralKey: config.mistralKey || current.mistralKey,
    mistralModel: config.mistralModel || current.mistralModel,
    systemPrompt: config.systemPrompt || current.systemPrompt
  });
  return { success: true };
});

ipcMain.handle('start-bot', async () => {
  if (isRunning) return { success: true };
  const config = loadConfig();
  await startBot(config);
  return { success: isRunning };
});

ipcMain.handle('stop-bot', async () => {
  await stopBot();
  return { success: true };
});

ipcMain.handle('get-logs', () => logs.slice(-100));

ipcMain.handle('clear-logs', () => {
  logs = [];
  saveLogsToFile();
  return { success: true };
});
