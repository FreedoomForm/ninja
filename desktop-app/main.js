const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const http = require('http');

let mainWindow = null;
let pythonProcess = null;
const PYTHON_PORT = 58765;

// Path to Python backend
const isDev = !app.isPackaged;
const getPythonPath = () => {
  if (isDev) {
    return path.join(__dirname, '..', 'ninja', 'app', 'main.py');
  }
  return path.join(process.resourcesPath, 'python', 'main.py');
};

// Check if Python backend is running
const isBackendRunning = () => {
  return new Promise((resolve) => {
    const req = http.request({
      hostname: '127.0.0.1',
      port: PYTHON_PORT,
      path: '/api/status',
      method: 'GET',
      timeout: 1000
    }, (res) => {
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
};

// Start Python backend
const startPythonBackend = () => {
  return new Promise(async (resolve, reject) => {
    const running = await isBackendRunning();
    if (running) {
      resolve(true);
      return;
    }

    const pythonPath = getPythonPath();
    const pythonExe = 'python'; // or 'python3' depending on system
    
    pythonProcess = spawn(pythonExe, [pythonPath], {
      cwd: path.dirname(pythonPath),
      env: { ...process.env }
    });

    pythonProcess.stdout.on('data', (data) => {
      console.log(`Python: ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      console.error(`Python Error: ${data}`);
    });

    // Wait for backend to start
    let attempts = 0;
    const maxAttempts = 30;
    const checkInterval = setInterval(async () => {
      attempts++;
      const running = await isBackendRunning();
      if (running) {
        clearInterval(checkInterval);
        resolve(true);
      } else if (attempts >= maxAttempts) {
        clearInterval(checkInterval);
        reject(new Error('Backend failed to start'));
      }
    }, 500);
  });
};

// Create main window
const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    minWidth: 800,
    minHeight: 600,
    title: '🥷 Ninja Bot',
    icon: path.join(__dirname, 'icon.ico'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    backgroundColor: '#1a1a2e',
    show: false
  });

  mainWindow.loadFile('index.html');

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Open DevTools in development
  if (isDev) {
    mainWindow.webContents.openDevTools();
  }
};

// App ready
app.whenReady().then(async () => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Quit when all windows are closed
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (pythonProcess) {
      pythonProcess.kill();
    }
    app.quit();
  }
});

// IPC: Get backend status
ipcMain.handle('get-status', async () => {
  try {
    const running = await isBackendRunning();
    if (!running) return { running: false, username: null, message_count: 0 };

    return new Promise((resolve) => {
      http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/status',
        method: 'GET'
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve(JSON.parse(data)));
      }).on('error', () => resolve({ running: false, username: null, message_count: 0 })).end();
    });
  } catch {
    return { running: false, username: null, message_count: 0 };
  }
});

// IPC: Get config
ipcMain.handle('get-config', async () => {
  try {
    return new Promise((resolve) => {
      http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/config',
        method: 'GET'
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve(JSON.parse(data)));
      }).on('error', () => resolve({})).end();
    });
  } catch {
    return {};
  }
});

// IPC: Save config
ipcMain.handle('save-config', async (event, config) => {
  try {
    return new Promise((resolve) => {
      const req = http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/config',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve({ success: true }));
      }).on('error', () => resolve({ success: false }));
      req.write(JSON.stringify(config));
      req.end();
    });
  } catch {
    return { success: false };
  }
});

// IPC: Start bot
ipcMain.handle('start-bot', async () => {
  try {
    await startPythonBackend();
    return new Promise((resolve) => {
      http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/start',
        method: 'POST'
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve({ success: true }));
      }).on('error', () => resolve({ success: false })).end();
    });
  } catch {
    return { success: false };
  }
});

// IPC: Stop bot
ipcMain.handle('stop-bot', async () => {
  try {
    return new Promise((resolve) => {
      http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/stop',
        method: 'POST'
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve({ success: true }));
      }).on('error', () => resolve({ success: false })).end();
    });
  } catch {
    return { success: false };
  }
});

// IPC: Get logs
ipcMain.handle('get-logs', async () => {
  try {
    return new Promise((resolve) => {
      http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/logs',
        method: 'GET'
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve(JSON.parse(data)));
      }).on('error', () => resolve([])).end();
    });
  } catch {
    return [];
  }
});

// IPC: Clear logs
ipcMain.handle('clear-logs', async () => {
  try {
    return new Promise((resolve) => {
      http.request({
        hostname: '127.0.0.1',
        port: PYTHON_PORT,
        path: '/api/logs/clear',
        method: 'POST'
      }, (res) => {
        let data = '';
        res.on('data', chunk => data += chunk);
        res.on('end', () => resolve({ success: true }));
      }).on('error', () => resolve({ success: false })).end();
    });
  } catch {
    return { success: false };
  }
});

// IPC: Start backend manually
ipcMain.handle('start-backend', async () => {
  try {
    await startPythonBackend();
    return { success: true };
  } catch (e) {
    return { success: false, error: e.message };
  }
});

// IPC: Check backend
ipcMain.handle('check-backend', async () => {
  return await isBackendRunning();
});
