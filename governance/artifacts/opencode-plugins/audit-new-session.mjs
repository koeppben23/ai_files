import { spawn, spawnSync } from "node:child_process";

const seen = new Set();
const MAX_LOG_BYTES = 64 * 1024;

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
  return asString(event.session_id) ?? asString(event.sessionId) ?? asString(event.id);
}

function extractRepoRoot(event, client) {
  if (event && typeof event === "object") {
    const fromEvent = asString(event.repo_root) ?? asString(event.repoRoot);
    if (fromEvent) {
      return fromEvent;
    }
  }
  if (client && typeof client === "object") {
    const fromClient = asString(client.repo_root) ?? asString(client.repoRoot) ?? asString(client.cwd);
    if (fromClient) {
      return fromClient;
    }
  }
  return process.cwd();
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
    return { cmd: override, args: [] };
  }

  if (process.platform === "win32") {
    if (canRun("py", ["-3", "-V"])) {
      return { cmd: "py", args: ["-3"] };
    }
    if (canRun("python", ["-V"])) {
      return { cmd: "python", args: [] };
    }
    return null;
  }

  if (canRun("python3", ["-V"])) {
    return { cmd: "python3", args: [] };
  }
  if (canRun("python", ["-V"])) {
    return { cmd: "python", args: [] };
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
    ...python.args,
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

  const child = spawn(python.cmd, args, {
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
      if (!event || event.type !== "session.created") {
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

      const cwd = extractRepoRoot(event, client);
      if (!asString(event?.repo_root) && !asString(event?.repoRoot)) {
        log(client, `[audit] session.created missing repo_root; fallback cwd=${cwd}`);
      }

      const python = resolvePython();
      if (!python) {
        log(client, "[audit] no python interpreter found (set OPENCODE_PYTHON); skipping new_work_session");
        return;
      }

      const reason = asString(event.reason);

      runInitializer({
        cwd,
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
