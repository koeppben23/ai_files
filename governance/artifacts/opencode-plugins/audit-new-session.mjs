import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const seen = new Set();
const MAX_LOG_BYTES = 64 * 1024;
const DEBUG_ENABLED = process.env.OPENCODE_AUDIT_DEBUG === "1";

function debugLog(message) {
  if (!DEBUG_ENABLED) {
    return;
  }
  const configured = asString(process.env.OPENCODE_AUDIT_DEBUG_LOG);
  const home = asString(process.env.HOME) ?? asString(process.env.USERPROFILE);
  const fallback = home ? join(home, ".config", "opencode", "logs", "audit-new-session.debug.log") : null;
  const target = configured ?? fallback;
  if (!target) {
    return;
  }
  try {
    appendFileSync(target, `${new Date().toISOString()} ${message}\n`, "utf8");
  } catch {
    // debug-only best effort
  }
}

function asString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function capAppend(buffer, chunk) {
  if (buffer.length >= MAX_LOG_BYTES) {
    return buffer;
  }
  const next = buffer + String(chunk);
  if (next.length <= MAX_LOG_BYTES) {
    return next;
  }
  return next.slice(0, MAX_LOG_BYTES);
}

function extractSessionId(event) {
  if (!event || typeof event !== "object") {
    return null;
  }
  const props = event.properties && typeof event.properties === "object" ? event.properties : null;
  const info = props && typeof props.info === "object" ? props.info : null;
  return (
    asString(info?.id) ??
    asString(event.sessionId) ??
    asString(event.session_id) ??
    asString(event.id)
  );
}

function isExistingDir(pathValue) {
  const value = asString(pathValue);
  if (!value) {
    return false;
  }
  try {
    if (!existsSync(value)) {
      return false;
    }
    return statSync(value).isDirectory();
  } catch {
    return false;
  }
}

function looksRepoPlausible(pathValue) {
  if (!isExistingDir(pathValue)) {
    return false;
  }
  const markers = [".git", "governance", "governance.paths.json", "pyproject.toml", "package.json"];
  for (const marker of markers) {
    try {
      if (existsSync(join(pathValue, marker))) {
        return true;
      }
    } catch {
      // continue
    }
  }
  return false;
}

function extractRepoRoot(event, client) {
  const props = event && typeof event === "object" && event.properties && typeof event.properties === "object"
    ? event.properties
    : null;
  const info = props && typeof props.info === "object" ? props.info : null;
  const candidates = [
    { source: "event.properties.info.directory", value: asString(info?.directory), fallback: false },
    { source: "event.properties.directory", value: asString(props?.directory), fallback: false },
    { source: "client.repo_root", value: asString(client?.repo_root) ?? asString(client?.repoRoot) ?? asString(client?.cwd), fallback: false },
    { source: "process.cwd", value: process.cwd(), fallback: true },
  ];

  for (const candidate of candidates) {
    const value = asString(candidate.value);
    if (!value || !isExistingDir(value)) {
      continue;
    }
    if (!candidate.fallback) {
      if (!looksRepoPlausible(value)) {
        debugLog(`[audit] cwd warning source=${candidate.source} path=${value} repo_plausible=false`);
      }
      return { cwd: value, source: candidate.source, usedFallback: false };
    }
    if (looksRepoPlausible(value)) {
      return { cwd: value, source: candidate.source, usedFallback: true };
    }
    return { cwd: null, source: candidate.source, usedFallback: true };
  }
  return { cwd: null, source: "none", usedFallback: false };
}

function canRun(cmd, args = []) {
  try {
    const result = spawnSync(cmd, args, { stdio: "ignore" });
    return result.status === 0;
  } catch {
    return false;
  }
}

/**
 * Attempt to locate the PYTHON_BINDING file written by the installer.
 *
 * Discovery order:
 * 1. Derive config_root from the plugin's own installed location
 *    (plugin lives at <config_root>/plugins/audit-new-session.mjs,
 *     so config_root = dirname(dirname(thisFile))).
 * 2. Well-known default: ~/.config/opencode/bin/PYTHON_BINDING
 *
 * Returns the absolute interpreter path string, or null.
 */
function resolveBindingFile() {
  const candidates = [];

  // 1. Derive from own installed location
  try {
    const thisFile = fileURLToPath(import.meta.url);
    const pluginsDir = dirname(thisFile);           // <config_root>/plugins
    const configRoot = dirname(pluginsDir);          // <config_root>
    candidates.push(join(configRoot, "bin", "PYTHON_BINDING"));
  } catch {
    // import.meta.url not usable (e.g., bundled or eval context)
  }

  // 2. Well-known default location
  const home = asString(process.env.HOME) ?? asString(process.env.USERPROFILE);
  if (home) {
    candidates.push(join(home, ".config", "opencode", "bin", "PYTHON_BINDING"));
  }

  for (const candidatePath of candidates) {
    try {
      if (!existsSync(candidatePath)) {
        continue;
      }
      const raw = readFileSync(candidatePath, "utf8").trim();
      if (!raw) {
        debugLog(`[audit] PYTHON_BINDING empty at ${candidatePath}`);
        continue;
      }
      // Contract: single line, absolute path
      if (raw.includes("\n")) {
        debugLog(`[audit] PYTHON_BINDING malformed (multi-line) at ${candidatePath}`);
        continue;
      }
      debugLog(`[audit] PYTHON_BINDING resolved from ${candidatePath}: ${raw}`);
      return raw;
    } catch (err) {
      debugLog(`[audit] PYTHON_BINDING read error at ${candidatePath}: ${err}`);
    }
  }
  return null;
}

function resolvePython() {
  // Priority 1: Explicit environment override (contract §4.3, priority 1)
  const override = asString(process.env.OPENCODE_PYTHON);
  if (override) {
    return {
      command: override,
      argvPrefix: [],
      source: "OPENCODE_PYTHON",
      platform: process.platform,
      usedOverride: true,
      degraded: false,
    };
  }

  // Priority 2: PYTHON_BINDING file (contract §4.3, priority 2)
  const boundPath = resolveBindingFile();
  if (boundPath) {
    // PYTHON_BINDING uses POSIX paths; on Windows convert forward slashes
    // to native backslashes for spawn compatibility.
    const nativePath = process.platform === "win32"
      ? boundPath.replace(/\//g, "\\")
      : boundPath;
    return {
      command: nativePath,
      argvPrefix: [],
      source: "PYTHON_BINDING",
      platform: process.platform,
      usedOverride: false,
      degraded: false,
    };
  }

  // Priority 3: Degraded PATH probing fallback (contract §4.3, priority 3)
  // WARNING: This path is only used when no installation binding exists
  // (e.g., fresh clone without install). The resolved interpreter may differ
  // from the installed binding.
  debugLog("[audit] PYTHON_BINDING not found; falling back to degraded PATH probing");

  if (process.platform === "win32") {
    if (canRun("py", ["-3", "-V"])) {
      return {
        command: "py",
        argvPrefix: ["-3"],
        source: "py -3 (degraded)",
        platform: "win32",
        usedOverride: false,
        degraded: true,
      };
    }
    if (canRun("python", ["-V"])) {
      return {
        command: "python",
        argvPrefix: [],
        source: "python (degraded)",
        platform: "win32",
        usedOverride: false,
        degraded: true,
      };
    }
    return null;
  }

  if (canRun("python3", ["-V"])) {
    return {
      command: "python3",
      argvPrefix: [],
      source: "python3 (degraded)",
      platform: process.platform,
      usedOverride: false,
      degraded: true,
    };
  }
  if (canRun("python", ["-V"])) {
    return {
      command: "python",
      argvPrefix: [],
      source: "python (degraded)",
      platform: process.platform,
      usedOverride: false,
      degraded: true,
    };
  }
  return null;
}

function log(client, message) {
  try {
    client?.app?.log?.(message);
  } catch {
    // Non-blocking log best-effort.
  }
}

function runInitializer({ cwd, python, sessionId, reason, onExit, onError }) {
  const args = [
    ...python.argvPrefix,
    "-m",
    "governance_runtime.entrypoints.new_work_session",
    "--trigger-source",
    "desktop-plugin",
    "--quiet",
  ];

  if (sessionId) {
    args.push("--session-id", sessionId);
  }
  if (reason) {
    args.push("--reason", reason);
  }

  const child = spawn(python.command, args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";
  child.stdout?.on("data", (chunk) => {
    stdout = capAppend(stdout, chunk);
  });
  child.stderr?.on("data", (chunk) => {
    stderr = capAppend(stderr, chunk);
  });
  child.on("error", onError);
  child.on("close", (code) => {
    onExit(code ?? 1, stdout.trim(), stderr.trim());
  });
}

export const AuditNewSession = async ({ client }) => {
  return {
    event: async ({ event }) => {
      if (!event) {
        return;
      }
      if (event.type === "file.watcher.updated") {
        return;
      }
      if (event.type !== "session.created") {
        return;
      }

      const sessionId = extractSessionId(event);
      if (!sessionId) {
        log(client, "[audit] session.created missing session_id; proceeding without dedupe");
      } else {
        if (seen.has(sessionId)) {
          return;
        }
        seen.add(sessionId);
      }

      const cwdResolution = extractRepoRoot(event, client);
      if (!cwdResolution.cwd) {
        log(client, "[audit] no plausible cwd resolved; skipping new_work_session");
        return;
      }
      if (cwdResolution.usedFallback) {
        log(client, `[audit] cwd fallback source=${cwdResolution.source} cwd=${cwdResolution.cwd}`);
      }

      const python = resolvePython();
      if (!python) {
        log(client, "[audit] no python interpreter found (set OPENCODE_PYTHON); skipping new_work_session");
        return;
      }
      if (python.degraded) {
        log(client, `[audit] WARNING: using degraded PATH fallback (source=${python.source}); interpreter may differ from installed binding`);
      }
      debugLog(`[audit] resolver source=${python.source} command=${python.command} cwd_source=${cwdResolution.source}`);

      const reason = asString(event.reason) ?? asString(event?.properties?.info?.reason);

      runInitializer({
        cwd: cwdResolution.cwd,
        python,
        sessionId,
        reason,
        onExit: (code, out, err) => {
          if (code === 0) {
            log(client, `[audit] new_work_session ok session=${sessionId ?? "unknown"} ${out}`);
            return;
          }
          log(client, `[audit] new_work_session failed session=${sessionId ?? "unknown"} rc=${code} stderr=${err}`);
        },
        onError: (error) => {
          log(client, `[audit] new_work_session spawn failed session=${sessionId ?? "unknown"} err=${String(error)}`);
        },
      });
    },
  };
};

export default AuditNewSession;
