import { spawn } from "node:child_process";

const seen = new Set();

function asString(value) {
  return typeof value === "string" && value.trim() ? value.trim() : null;
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

function log(client, message) {
  try {
    client?.app?.log?.(message);
  } catch {
    // Non-blocking log best-effort.
  }
}

function runInitializer({ cwd, sessionId, reason, onExit, onError }) {
  const args = [
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

  const child = spawn("python3", args, {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";
  child.stdout?.on("data", (chunk) => {
    stdout += String(chunk);
  });
  child.stderr?.on("data", (chunk) => {
    stderr += String(chunk);
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
      if (sessionId && seen.has(sessionId)) {
        return;
      }
      if (sessionId) {
        seen.add(sessionId);
      }

      const cwd = extractRepoRoot(event, client);
      const reason = asString(event.reason);

      runInitializer({
        cwd,
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
