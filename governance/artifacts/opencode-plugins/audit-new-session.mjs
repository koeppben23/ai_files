import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, existsSync, statSync } from "node:fs";
import { dirname, join } from "node:path";

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

function resolvePython() {
  const override = asString(process.env.OPENCODE_PYTHON);
  if (override) {
    return {
      command: override,
      argvPrefix: [],
      source: "OPENCODE_PYTHON",
      platform: process.platform,
      usedOverride: true,
    };
  }

  if (process.platform === "win32") {
    if (canRun("py", ["-3", "-V"])) {
      return {
        command: "py",
        argvPrefix: ["-3"],
        source: "py -3",
        platform: "win32",
        usedOverride: false,
      };
    }
    if (canRun("python", ["-V"])) {
      return {
        command: "python",
        argvPrefix: [],
        source: "python",
        platform: "win32",
        usedOverride: false,
      };
    }
    return null;
  }

  if (canRun("python3", ["-V"])) {
    return {
      command: "python3",
      argvPrefix: [],
      source: "python3",
      platform: process.platform,
      usedOverride: false,
    };
  }
  if (canRun("python", ["-V"])) {
    return {
      command: "python",
      argvPrefix: [],
      source: "python",
      platform: process.platform,
      usedOverride: false,
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
    "governance.entrypoints.new_work_session",
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
