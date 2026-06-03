const { app, BrowserWindow, dialog } = require("electron");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const { spawn } = require("node:child_process");

const APP_NAME = "Warehouse Control Desk";
const DEFAULT_HOST = "127.0.0.1";
const READINESS_TIMEOUT_MS = 60000;
const READINESS_INTERVAL_MS = 400;

let mainWindow = null;
let sidecarProcess = null;
let logStream = null;

function projectRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
  return dirPath;
}

function dataDir() {
  return ensureDir(path.join(app.getPath("userData"), "data"));
}

function logsDir() {
  return ensureDir(path.join(app.getPath("userData"), "logs"));
}

function appendLog(message) {
  if (!logStream) {
    logStream = fs.createWriteStream(path.join(logsDir(), "desktop.log"), { flags: "a" });
  }
  logStream.write(`[${new Date().toISOString()}] ${message}\n`);
}

function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.on("error", reject);
    server.listen(0, DEFAULT_HOST, () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function packagedSidecarPath() {
  const executableName = process.platform === "win32" ? "warehouse-sidecar.exe" : "warehouse-sidecar";
  return path.join(process.resourcesPath, "backend", executableName);
}

function sidecarCommand() {
  if (app.isPackaged) {
    const executable = packagedSidecarPath();
    if (!fs.existsSync(executable)) {
      throw new Error(`Packaged sidecar not found: ${executable}`);
    }
    return { command: executable, args: [] };
  }

  return {
    command: process.env.WAREHOUSE_PYTHON || (process.platform === "win32" ? "python" : "python3"),
    args: [path.join(projectRoot(), "desktop", "python_sidecar", "serve.py")],
  };
}

function startSidecar(port) {
  const { command, args } = sidecarCommand();
  const env = {
    ...process.env,
    WAREHOUSE_APP_HOST: DEFAULT_HOST,
    WAREHOUSE_APP_PORT: String(port),
    WAREHOUSE_DATA_DIR: dataDir(),
    DJANGO_DB_PATH: path.join(dataDir(), "db.sqlite3"),
    DJANGO_DEBUG: "0",
    DJANGO_ALLOWED_HOSTS: "127.0.0.1,localhost",
    WAREHOUSE_AUTO_MIGRATE: process.env.WAREHOUSE_AUTO_MIGRATE || "1",
  };

  appendLog(`Starting sidecar: ${command} ${args.join(" ")} port=${port}`);

  sidecarProcess = spawn(command, args, {
    cwd: app.isPackaged ? path.dirname(command) : projectRoot(),
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  sidecarProcess.stdout.on("data", (chunk) => appendLog(`[sidecar:stdout] ${chunk.toString().trimEnd()}`));
  sidecarProcess.stderr.on("data", (chunk) => appendLog(`[sidecar:stderr] ${chunk.toString().trimEnd()}`));
  sidecarProcess.on("exit", (code, signal) => {
    appendLog(`Sidecar exited: code=${code} signal=${signal}`);
    sidecarProcess = null;
  });
}

function waitForHealthz(port) {
  const startedAt = Date.now();
  const url = `http://${DEFAULT_HOST}:${port}/healthz/`;

  return new Promise((resolve, reject) => {
    const probe = () => {
      fetch(url)
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
          }
          return response.json();
        })
        .then((payload) => {
          if (payload.status !== "ok") {
            throw new Error(`Unexpected health payload: ${JSON.stringify(payload)}`);
          }
          resolve();
        })
        .catch((error) => {
          if (Date.now() - startedAt > READINESS_TIMEOUT_MS) {
            reject(error);
            return;
          }
          setTimeout(probe, READINESS_INTERVAL_MS);
        });
    };

    probe();
  });
}

function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1100,
    minHeight: 760,
    show: false,
    title: APP_NAME,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.removeMenu();
  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.loadURL(`http://${DEFAULT_HOST}:${port}/`);
}

async function stopSidecar() {
  if (!sidecarProcess) {
    return;
  }

  const processToStop = sidecarProcess;
  appendLog("Stopping sidecar");
  processToStop.kill();

  setTimeout(() => {
    if (sidecarProcess === processToStop) {
      appendLog("Force-stopping sidecar");
      processToStop.kill("SIGKILL");
    }
  }, 3000);
}

async function showStartupError(error) {
  appendLog(`Startup failed: ${error.stack || error.message}`);
  await dialog.showMessageBox({
    type: "error",
    title: `${APP_NAME}: ошибка запуска`,
    message: "Не удалось запустить локальный backend приложения.",
    detail: `${error.message}\n\nЛоги: ${logsDir()}`,
  });
}

app.on("second-instance", () => {
  if (mainWindow) {
    if (mainWindow.isMinimized()) {
      mainWindow.restore();
    }
    mainWindow.focus();
  }
});

app.on("before-quit", () => {
  stopSidecar();
});

app.whenReady().then(async () => {
  if (!app.requestSingleInstanceLock()) {
    app.quit();
    return;
  }

  try {
    const port = await findFreePort();
    startSidecar(port);
    await waitForHealthz(port);
    createWindow(port);
  } catch (error) {
    await showStartupError(error);
    app.quit();
  }
});
