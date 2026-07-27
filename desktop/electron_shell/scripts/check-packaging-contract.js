const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const packageJsonPath = path.join(root, "package.json");
const packageLockPath = path.join(root, "package-lock.json");
const mainJsPath = path.join(root, "src", "main.js");
const windowsBuildPath = path.resolve(root, "..", "build", "build-electron-windows.bat");
const sidecarSpecPath = path.resolve(root, "..", "python_sidecar", "warehouse-sidecar.spec");
const appVersionPath = path.resolve(root, "..", "..", "warehouse_app", "version.py");

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exitCode = 1;
}

function requireIncludes(source, needle, label) {
  if (!source.includes(needle)) {
    fail(`${label} is missing required text: ${needle}`);
  }
}

function requireNotIncludes(source, needle, label) {
  if (source.includes(needle)) {
    fail(`${label} contains forbidden text: ${needle}`);
  }
}

const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
const mainJs = fs.readFileSync(mainJsPath, "utf8");
const windowsBuild = fs.readFileSync(windowsBuildPath, "utf8");
const sidecarSpec = fs.readFileSync(sidecarSpecPath, "utf8");
const appVersionSource = fs.readFileSync(appVersionPath, "utf8");

if (!fs.existsSync(packageLockPath)) {
  fail("package-lock.json must be committed for reproducible Electron builds.");
}

if (packageJson.main !== "src/main.js") {
  fail("package.json main must be src/main.js");
}

if (!packageJson.build || packageJson.build.productName !== "Warehouse Control Desk") {
  fail("Electron productName must remain Warehouse Control Desk until a deliberate rename pass.");
}

const appVersionMatch = appVersionSource.match(/APP_VERSION\s*=\s*"([^"]+)"/);
if (!appVersionMatch || appVersionMatch[1] !== packageJson.version) {
  fail("Electron package version must match warehouse_app/version.py.");
}

for (const dependencyName of ["electron", "electron-builder"]) {
  const version = packageJson.devDependencies?.[dependencyName];
  if (!version || /^[~^*]/.test(version)) {
    fail(`${dependencyName} must use an exact version in package.json.`);
  }
}

const extraResources = packageJson.build?.extraResources || [];
const hasBackendResource = extraResources.some((entry) => entry.from === "resources/backend" && entry.to === "backend");
if (!hasBackendResource) {
  fail("Electron build.extraResources must copy resources/backend to backend.");
}

const nsis = packageJson.build?.nsis || {};
if (nsis.perMachine !== false || nsis.allowElevation !== false) {
  fail("NSIS installer must stay per-user and must not require elevation.");
}

requireIncludes(mainJs, "findFreePort()", "src/main.js");
requireIncludes(mainJs, "process.resourcesPath", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_DATA_DIR", "src/main.js");
requireIncludes(mainJs, "DJANGO_DB_PATH", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_LOCAL_TRUSTED_MODE", "src/main.js");
requireIncludes(mainJs, "DJANGO_SECRET_KEY", "src/main.js");
requireIncludes(mainJs, "django-secret.key", "src/main.js");
requireIncludes(mainJs, "crypto.randomBytes", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_ENABLE_SHUTDOWN", "src/main.js");
requireIncludes(mainJs, "WAREHOUSE_SHUTDOWN_TOKEN", "src/main.js");
requireIncludes(mainJs, "X-Warehouse-Shutdown-Token", "src/main.js");
requireIncludes(mainJs, "requestSingleInstanceLock", "src/main.js");
requireIncludes(mainJs, "waitForHealthz", "src/main.js");
requireIncludes(mainJs, "processToStop.kill(\"SIGKILL\")", "src/main.js");
requireNotIncludes(mainJs, "localhost:8000", "src/main.js");
requireNotIncludes(mainJs, "127.0.0.1:8000", "src/main.js");
requireIncludes(windowsBuild, "call npm ci", "build-electron-windows.bat");
requireNotIncludes(windowsBuild, "call npm install", "build-electron-windows.bat");
requireIncludes(sidecarSpec, "upx=False", "warehouse-sidecar.spec");
requireNotIncludes(sidecarSpec, "upx=True", "warehouse-sidecar.spec");

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log("Electron packaging contract OK");
