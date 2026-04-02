from __future__ import annotations

import base64
import enum
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar


class OpenCodeServerError(Exception):
    pass


class ServerNotAvailableError(OpenCodeServerError):
    pass


class ServerTargetUnreachableError(ServerNotAvailableError):
    """Raised when target server is not reachable."""

    def __init__(self, message: str, target_url: str | None = None):
        super().__init__(message)
        self.target_url = target_url


class ServerTargetUnhealthyError(ServerNotAvailableError):
    """Raised when target server is reachable but unhealthy."""

    def __init__(self, message: str, target_url: str | None = None, health_response: dict | None = None):
        super().__init__(message)
        self.target_url = target_url
        self.health_response = health_response


class ServerStartFailedError(ServerNotAvailableError):
    """Raised when server auto-start fails."""

    def __init__(self, message: str, target_url: str | None = None):
        super().__init__(message)
        self.target_url = target_url


class ServerStartTimeoutError(ServerNotAvailableError):
    """Raised when server does not become healthy within timeout."""

    def __init__(self, message: str, target_url: str | None = None, timeout_seconds: int | None = None):
        super().__init__(message)
        self.target_url = target_url
        self.timeout_seconds = timeout_seconds


class ServerBindingMismatchError(ServerNotAvailableError):
    """Raised when server is found on different port/hostname than configured."""

    def __init__(
        self,
        message: str,
        target_url: str | None = None,
        found_url: str | None = None,
    ):
        super().__init__(message)
        self.target_url = target_url
        self.found_url = found_url


class AuthenticationError(OpenCodeServerError):
    pass


class APIError(OpenCodeServerError):
    pass


class ProjectNotFoundError(APIError):
    """Raised when no OpenCode project matches the given worktree path."""

    def __init__(self, message: str, project_path: str | None = None):
        super().__init__(message)
        self.project_path = project_path


class ProjectSessionNotFoundError(APIError):
    """Raised when the project exists but has no sessions."""

    def __init__(self, message: str, project_id: str | None = None, project_path: str | None = None):
        super().__init__(message)
        self.project_id = project_id
        self.project_path = project_path


# ---------------------------------------------------------------------------
# Server discovery exceptions (attach_existing mode)
# ---------------------------------------------------------------------------


class ServerDiscoveryNotFoundError(ServerNotAvailableError):
    """Raised when attach_existing discovery finds zero healthy OpenCode servers."""

    def __init__(self, message: str, candidates_scanned: int = 0):
        super().__init__(message)
        self.candidates_scanned = candidates_scanned


class ServerDiscoveryAmbiguousError(ServerNotAvailableError):
    """Raised when attach_existing discovery finds multiple healthy OpenCode servers."""

    def __init__(self, message: str, healthy_endpoints: list[str] | None = None):
        super().__init__(message)
        self.healthy_endpoints = healthy_endpoints or []


class ServerAuthRequiredError(ServerNotAvailableError):
    """Raised when a candidate returns HTTP 401 and no credentials are configured."""

    def __init__(self, message: str, target_url: str | None = None):
        super().__init__(message)
        self.target_url = target_url


class ServerDiscoveryUnsupportedPlatformError(ServerNotAvailableError):
    """Raised when attach_existing discovery is requested on an unsupported platform."""

    def __init__(self, message: str, platform: str | None = None):
        super().__init__(message)
        self.platform = platform


# ---------------------------------------------------------------------------
# Server mode enum
# ---------------------------------------------------------------------------


class ServerMode(enum.Enum):
    """Server discovery/lifecycle mode for governance runtime.

    ATTACH_EXISTING (default): Discover and attach to an already-running
        local OpenCode server. Never auto-start. Block if none or multiple found.
    MANAGED: Start and manage a server with a fixed port via
        ``opencode serve --port X --hostname Y``. Start-if-absent is allowed.
    """

    ATTACH_EXISTING = "attach_existing"
    MANAGED = "managed"


T = TypeVar("T")


def _retry_with_backoff(
    func: Callable[[], T],
    max_attempts: int = 3,
    backoff_ms: int = 100,
    retryable_exceptions: tuple[type[Exception], ...] = (ServerNotAvailableError, TimeoutError),
) -> T:
    """Execute a function with linear backoff retry for transient failures.

    Args:
        func: Function to execute
        max_attempts: Maximum number of attempts (default: 3)
        backoff_ms: Initial backoff delay in milliseconds (default: 100)
        retryable_exceptions: Exceptions that trigger retry (default: ServerNotAvailableError, TimeoutError)

    Returns:
        Result of func()

    Raises:
        Last exception if all attempts fail (fail-closed)
    """
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return func()
        except retryable_exceptions as e:
            last_error = e
            if attempt < max_attempts - 1:
                sleep_time = backoff_ms * (attempt + 1) / 1000.0
                time.sleep(sleep_time)
    raise last_error


def is_server_required_mode() -> bool:
    """Check if server is required (fail-closed) mode.

    When AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER=1 is set:
    - Server MUST be available or call will fail
    - No fallback to legacy CLI bridge

    Returns:
        True if server is required, False for opportunistic mode (default)
    """
    return os.environ.get("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "").strip().lower() in {"1", "true", "yes", "on"}


_VALID_SERVER_MODES: frozenset[str] = frozenset(m.value for m in ServerMode)


def resolve_server_mode(cli_value: str | None = None) -> ServerMode:
    """Resolve the server discovery/lifecycle mode.

    Resolution order (first non-None wins):
      1. ``cli_value`` (from ``--server-mode`` CLI arg)
      2. ``OPENCODE_SERVER_MODE`` environment variable
      3. Default: ``attach_existing``

    Args:
        cli_value: Explicit mode string from CLI argument, or None.

    Returns:
        Resolved ``ServerMode`` enum member.

    Raises:
        ValueError: If the resolved value is not a valid server mode.
    """
    raw: str | None = None

    if cli_value is not None:
        raw = cli_value.strip().lower()
    else:
        env = os.environ.get("OPENCODE_SERVER_MODE", "").strip().lower()
        if env:
            raw = env

    if raw is None:
        return ServerMode.ATTACH_EXISTING

    if raw not in _VALID_SERVER_MODES:
        raise ValueError(
            f"Invalid server mode '{raw}'. "
            f"Valid modes: {', '.join(sorted(_VALID_SERVER_MODES))}"
        )

    return ServerMode(raw)


def _parse_port(raw: object, *, purpose: str) -> int:
    token = str(raw).strip()
    if not token:
        raise ValueError(f"{purpose}: empty port")
    try:
        value = int(token)
    except ValueError as exc:
        raise ValueError(f"{purpose}: port must be an integer") from exc
    if value < 1 or value > 65535:
        raise ValueError(f"{purpose}: port must be between 1 and 65535")
    return value


def _resolve_server_endpoint_from_opencode_json() -> tuple[str, int] | None:
    """Resolve (hostname, port) from opencode.json/opencode.jsonc.

    Invalid/malformed files are ignored (best-effort config discovery).
    """
    import re


    home = os.path.expanduser("~")
    config_root = Path(home) / ".config" / "opencode"

    for filename in ("opencode.json", "opencode.jsonc"):
        config_path = config_root / filename
        if not config_path.is_file():
            continue

        try:
            content = config_path.read_text(encoding="utf-8")
            if filename.endswith(".jsonc"):
                content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)
            config = json.loads(content)
            server = config.get("server", {})
            if not isinstance(server, dict):
                continue
            hostname = str(server.get("hostname", "")).strip() or "127.0.0.1"
            raw_port = server.get("port")
            if raw_port is None:
                continue
            port = _parse_port(raw_port, purpose="opencode.json server.port")
            return hostname, port
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return None


def _resolve_base_url_from_opencode_json() -> str | None:
    """Resolve base_url from opencode.json (SSOT for server config).

    Reads ~/.config/opencode/opencode.json or opencode.jsonc for:
    - server.hostname
    - server.port

    Returns:
        base_url if found in config, None otherwise
    """
    endpoint = _resolve_server_endpoint_from_opencode_json()
    if endpoint is None:
        return None
    hostname, port = endpoint
    return f"http://{hostname}:{port}"


def resolve_opencode_server_base_url() -> str:
    """Resolve OpenCode server base URL.

    Resolution order:
    1. SESSION_STATE.SessionHydration.resolved_server_url (hydration discovery)
       — This is checked FIRST because it reflects the ACTUAL running server
       discovered by lsof.  OpenCode Desktop starts on random ports, so the
       installer-written opencode.json port is stale after each restart.
    2. opencode.json (server.hostname + server.port)
       — Authoritative when hydration has not yet run (e.g., managed mode
       with a fixed port).
    3. OPENCODE_PORT env var (explicit user override)
    4. fail-closed with clear error

    Returns:
        Base URL like "http://127.0.0.1:4096"

    Raises:
        ServerNotAvailableError: If no server URL can be resolved
    """
    # ── Source 1: hydrated server URL from SESSION_STATE ──────────────
    # Written by /hydrate when server discovery (lsof) succeeds.
    # Survives bootstrap cycles via hydration preservation guards in
    # bootstrap_persistence.py, bootstrap_preflight_readonly.py, and
    # new_work_session.py.
    hydrated_url = _read_server_url_from_state()
    if hydrated_url:
        return hydrated_url

    # ── Source 2: opencode.json ───────────────────────────────────────
    endpoint = _resolve_server_endpoint_from_opencode_json()
    env_port_token = os.environ.get("OPENCODE_PORT", "").strip()

    if endpoint is not None:
        hostname, json_port = endpoint
        if env_port_token:
            try:
                env_port = _parse_port(env_port_token, purpose="OPENCODE_PORT")
                if env_port != json_port:
                    warnings.warn(
                        (
                            "Server port drift detected: opencode.json server.port "
                            f"({json_port}) != OPENCODE_PORT ({env_port}). "
                            "Using opencode.json as authoritative source."
                        ),
                        RuntimeWarning,
                        stacklevel=2,
                    )
            except ValueError:
                warnings.warn(
                    "OPENCODE_PORT is invalid and ignored because opencode.json is authoritative.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        return f"http://{hostname}:{json_port}"

    # ── Source 3: OPENCODE_PORT env var ───────────────────────────────
    if env_port_token:
        try:
            env_port = _parse_port(env_port_token, purpose="OPENCODE_PORT")
        except ValueError as exc:
            raise ServerNotAvailableError(
                f"OpenCode server URL not resolvable: {exc}"
            ) from exc
        return f"http://127.0.0.1:{env_port}"

    # ── Source 4: fail-closed ─────────────────────────────────────────
    raise ServerNotAvailableError(
        "OpenCode server URL not resolvable. "
        "Run /hydrate to discover the server, "
        "set server.hostname/server.port in ~/.config/opencode/opencode.json, "
        "or set OPENCODE_PORT."
    )


def _resolve_auth() -> dict[str, str] | None:
    """Resolve Basic Auth headers if configured.

    Environment:
    - OPENCODE_SERVER_PASSWORD: enables Basic Auth
    - OPENCODE_SERVER_USERNAME: override username (default: opencode)

    Returns:
        Dict with Authorization header, or None if not configured
    """
    password = os.environ.get("OPENCODE_SERVER_PASSWORD", "").strip()
    if not password:
        return None

    username = os.environ.get("OPENCODE_SERVER_USERNAME", "opencode").strip()
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


def post_json(
    path: str,
    body: dict,
    *,
    base_url: str | None = None,
    retry: bool = False,
    max_attempts: int = 3,
    backoff_ms: int = 100,
) -> dict:
    """Send JSON POST request to OpenCode server.

    Args:
        path: API path (e.g., "/session/abc/message")
        body: JSON body to send
        base_url: Base URL override (default: resolved from environment)
        retry: If True, retry on transient failures (connection/timeout)
        max_attempts: Maximum retry attempts (default: 3)
        backoff_ms: Initial backoff delay in ms (default: 100)

    Returns:
        Parsed JSON response

    Raises:
        ServerNotAvailableError: If server is not reachable (or in required mode)
        AuthenticationError: If auth fails
        APIError: For other API errors
    """

    def _do_request() -> dict:
        _base_url = base_url
        if _base_url is None:
            _base_url = resolve_opencode_server_base_url()

        url = f"{_base_url}{path}"
        headers = {"Content-Type": "application/json"}

        auth_headers = _resolve_auth()
        if auth_headers:
            headers.update(auth_headers)

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                response_body = resp.read().decode("utf-8")
                if response_body:
                    return json.loads(response_body)
                return {}
        except urllib.request.HTTPError as e:
            if e.code == 401:
                raise AuthenticationError(
                    f"Authentication failed for {url}. Check OPENCODE_SERVER_PASSWORD."
                ) from e
            raise APIError(f"API error {e.code}: {e.reason}") from e
        except urllib.request.URLError as e:
            raise ServerNotAvailableError(
                f"Cannot connect to OpenCode server at {_base_url}: {e.reason}"
            ) from e
        except TimeoutError as e:
            raise ServerNotAvailableError(f"Request timeout to {url}") from e

    if retry:
        return _retry_with_backoff(
            _do_request,
            max_attempts=max_attempts,
            backoff_ms=backoff_ms,
        )
    return _do_request()


def _read_hydrated_session_id_from_state() -> str | None:
    """Read SessionHydration.hydrated_session_id from SESSION_STATE.

    Returns the hydrated session ID string, or None when unavailable.
    This is intentionally fail-safe: any error → None (caller decides
    whether to raise).

    Performance: uses a lazy import of session_locator + json_store to
    avoid circular imports and keep the common path (env var set) fast.
    The file read is a single JSON parse of the already-on-disk
    SESSION_STATE.json — no network I/O.
    """
    try:
        from governance_runtime.infrastructure.session_locator import (
            resolve_active_session_paths,
        )
        from governance_runtime.infrastructure.json_store import load_json

        session_path, _fp, _wh, _wd = resolve_active_session_paths()
        document = load_json(session_path)
        state = document.get("SESSION_STATE")
        if not isinstance(state, dict):
            return None
        hydration = state.get("SessionHydration")
        if not isinstance(hydration, dict):
            return None
        if str(hydration.get("status") or "").strip().lower() != "hydrated":
            return None
        sid = str(hydration.get("hydrated_session_id") or "").strip()
        return sid if sid else None
    except Exception:  # noqa: BLE001 — fail-safe; caller decides policy
        return None


def _read_server_url_from_state() -> str | None:
    """Read SessionHydration.resolved_server_url from SESSION_STATE.

    Returns the server URL string, or None when unavailable.
    This is intentionally fail-safe: any error → None (caller falls
    through to the next resolution source).

    The URL is written during /hydrate when server discovery succeeds.
    It survives bootstrap cycles via the hydration preservation guard.

    Performance: same lazy-import pattern as _read_hydrated_session_id_from_state.
    """
    try:
        from governance_runtime.infrastructure.session_locator import (
            resolve_active_session_paths,
        )
        from governance_runtime.infrastructure.json_store import load_json

        session_path, _fp, _wh, _wd = resolve_active_session_paths()
        document = load_json(session_path)
        state = document.get("SESSION_STATE")
        if not isinstance(state, dict):
            return None
        hydration = state.get("SessionHydration")
        if not isinstance(hydration, dict):
            return None
        if str(hydration.get("status") or "").strip().lower() != "hydrated":
            return None
        url = str(hydration.get("resolved_server_url") or "").strip()
        return url if url else None
    except Exception:  # noqa: BLE001 — fail-safe; caller decides policy
        return None


def resolve_session_id() -> tuple[str, dict]:
    """Resolve OpenCode session ID.

    Resolution chain (first match wins):
        1. OPENCODE_SESSION_ID environment variable  (explicit, pipeline mode)
        2. SESSION_STATE.SessionHydration.hydrated_session_id  (direct/chat mode)
        3. Fail-closed with APIError

    Returns:
        Tuple of (session_id, evidence_dict with session_id_source)

    Raises:
        APIError: If no session ID can be resolved from any source
    """
    # ── Source 1: explicit env var (fast path, no I/O) ────────────────
    session_id = os.environ.get("OPENCODE_SESSION_ID", "").strip()
    if session_id:
        return session_id, {"session_id_source": "OPENCODE_SESSION_ID"}

    # ── Source 2: hydrated session from SESSION_STATE (file read) ─────
    hydrated_id = _read_hydrated_session_id_from_state()
    if hydrated_id:
        return hydrated_id, {"session_id_source": "SESSION_STATE.SessionHydration"}

    # ── Source 3: fail-closed ─────────────────────────────────────────
    raise APIError(
        "No OpenCode session ID available. "
        "Set OPENCODE_SESSION_ID or run /hydrate to bind a session. "
        "Resolution chain: OPENCODE_SESSION_ID env → SESSION_STATE.SessionHydration → fail."
    )


def send_session_prompt(
    text: str,
    *,
    session_id: str | None = None,
    model: dict[str, str] | None = None,
    output_schema: dict | None = None,
    required: bool = False,
    retry: bool = False,
    max_attempts: int = 3,
    backoff_ms: int = 100,
) -> dict:
    """Send a prompt to a session and get LLM response.

    This is the documented programmatic way to access the OpenCode session LLM,
    replacing the legacy subprocess("opencode run --session ...") approach.

    Session ID resolution (first match wins):
        1. Explicit ``session_id`` parameter  (caller-provided, highest priority)
        2. ``resolve_session_id()`` chain:
           a. OPENCODE_SESSION_ID env var
           b. SESSION_STATE.SessionHydration.hydrated_session_id
           c. Fail-closed with APIError

    Note: The server API documentation is inconsistent between format (SDK examples)
    and outputFormat (API overview). Default uses "format" per SDK examples.
    Set AI_GOVERNANCE_USE_OUTPUTFORMAT=1 to use "outputFormat" instead.

    Args:
        text: Prompt text to send
        session_id: Optional explicit session ID.  When provided, skips
                    resolve_session_id() entirely (avoids env + file I/O).
        model: Optional model specification (e.g., {"providerID": "openai", "modelID": "gpt-5"})
               If None, uses the session's default model
        output_schema: Optional JSON schema for structured output
                      Uses "format" by default; set AI_GOVERNANCE_USE_OUTPUTFORMAT=1 for outputFormat
        required: If True, fail-closed when server not available (respects AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER)
        retry: If True, retry on transient failures (connection/timeout)
        max_attempts: Maximum retry attempts (default: 3)
        backoff_ms: Initial backoff delay in ms (default: 100)

    Returns:
        Session response dict with info and parts, plus resolved_session_id in response

    Raises:
        ServerNotAvailableError: If server is not reachable (or in required mode)
        AuthenticationError: If auth fails
        APIError: For API errors or missing OPENCODE_SESSION_ID
    """
    if session_id:
        resolved_session_id = session_id
        session_evidence: dict = {"session_id_source": "explicit_parameter"}
    else:
        resolved_session_id, session_evidence = resolve_session_id()

    server_required = required or is_server_required_mode()

    try:
        server_url = resolve_opencode_server_base_url()
    except ServerNotAvailableError as exc:
        if server_required:
            raise ServerNotAvailableError(
                f"OpenCode server required but not available: {exc}"
            ) from exc
        raise

    body: dict = {
        "noReply": False,
        "parts": [{"type": "text", "text": text}],
    }

    if model:
        body["model"] = model

    if output_schema:
        use_outputformat = os.environ.get("AI_GOVERNANCE_USE_OUTPUTFORMAT", "").strip().lower() == "1"
        if use_outputformat:
            body["outputFormat"] = {
                "type": "json_schema",
                "schema": output_schema,
            }
        else:
            body["format"] = {
                "type": "json_schema",
                "schema": output_schema,
            }

    response = post_json(
        f"/session/{resolved_session_id}/message",
        body,
        base_url=server_url,
        retry=retry,
        max_attempts=max_attempts,
        backoff_ms=backoff_ms,
    )

    response["resolved_session_id"] = resolved_session_id
    response["session_evidence"] = session_evidence

    return response


def extract_session_response(payload: dict) -> str:
    """Extract text from session response.

    Priority:
    1. info.structured_output (JSON)
    2. Text parts from info.parts
    3. Empty string if nothing found

    Args:
        payload: Response from send_session_prompt

    Returns:
        Extracted text or JSON string
    """
    if not isinstance(payload, dict):
        return ""

    info = payload.get("info", {})
    if not isinstance(info, dict):
        info = {}

    structured = info.get("structured_output")
    if structured is not None:
        if isinstance(structured, dict):
            return json.dumps(structured, ensure_ascii=False)
        return str(structured)

    parts = info.get("parts", [])
    if not isinstance(parts, list):
        parts = []

    if not parts:
        parts = payload.get("parts", [])
        if not isinstance(parts, list):
            parts = []

    text_parts = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type", "")
        if part_type == "text":
            content = part.get("text", "")
            if content:
                text_parts.append(content)

    if text_parts:
        return "\n".join(text_parts)

    return ""


def send_session_command(
    session_id: str,
    command: str,
) -> dict:
    """Execute a command in a session.

    Args:
        session_id: Session ID
        command: Command to execute (e.g., "/plan")

    Returns:
        Command response dict

    Raises:
        ServerNotAvailableError: If server is not reachable
        AuthenticationError: If auth fails
        APIError: For API errors
    """
    if not session_id:
        raise APIError("session_id is required")

    if not command:
        raise APIError("command is required")

    body = {
        "command": command,
        "arguments": [],
    }

    return post_json(f"/session/{session_id}/command", body)


def bootstrap_check_server_reachable(config_root: Path | None = None) -> tuple[bool, str]:
    """Check if configured OpenCode server is reachable.

    Reads server.hostname/server.port from opencode.json and performs health check.

    Args:
        config_root: Path to config root (optional, for future use)

    Returns:
        (is_reachable, error_message) tuple
    """
    base_url = _resolve_base_url_from_opencode_json()

    if not base_url:
        return True, ""

    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme: {parsed.scheme}"
    if not parsed.netloc:
        return False, "Missing netloc"

    url = f"{base_url}/global/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, ""
            return False, f"Health check returned status {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Connection failed: {e.reason}"
    except (OSError, ValueError) as e:
        return False, f"Health check error: {e}"


def is_bootstrap_server_health_check_skipped() -> bool:
    """Check if server health check should be skipped (for testing).

    Returns:
        True if health check should be skipped
    """
    return os.environ.get("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "").strip().lower() in {"1", "true", "yes"}


def get_session_messages(session_id: str | None = None) -> dict:
    """Get message history for a session.

    Uses GET /session/:id/message per official server API documentation.
    This can be used to verify session continuity.

    Args:
        session_id: Session ID (optional, uses OPENCODE_SESSION_ID if not provided)

    Returns:
        Dict with info and parts arrays

    Raises:
        ServerNotAvailableError: If server is not reachable
        APIError: For API errors or missing session ID
    """
    if session_id is None:
        session_id, _ = resolve_session_id()

    try:
        server_url = resolve_opencode_server_base_url()
    except ServerNotAvailableError as exc:
        raise APIError(f"Server not available: {exc}") from exc

    headers = {}
    auth_headers = _resolve_auth()
    if auth_headers:
        headers.update(auth_headers)

    url = f"{server_url}/session/{session_id}/message"
    import urllib.request
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            import json
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise APIError(f"HTTP {e.code}: {e.reason}") from e
    except (OSError, ValueError) as e:
        raise APIError(f"Failed to get session messages: {e}") from e


def check_server_health() -> dict:
    """Check if OpenCode server is reachable.

    Uses GET /global/health per official server API documentation.

    Returns:
        Dict with "healthy" (bool) and "version" (str) keys

    Raises:
        ServerNotAvailableError: If server is not reachable
    """
    try:
        server_url = resolve_opencode_server_base_url()
    except ServerNotAvailableError as exc:
        raise ServerNotAvailableError(
            f"OpenCode server not reachable: {exc}. "
            "Ensure OpenCode Desktop is running or start with: opencode serve"
        ) from exc

    headers = {}
    auth_headers = _resolve_auth()
    if auth_headers:
        headers.update(auth_headers)

    url = f"{server_url}/global/health"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise ServerNotAvailableError(f"Server health check failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise ServerNotAvailableError(f"Cannot connect to server: {e.reason}") from e
    except (OSError, ValueError) as e:
        raise ServerNotAvailableError(f"Cannot connect to server: {e}") from e
    except Exception as e:
        raise ServerNotAvailableError(f"Server health check failed: {e}") from e


def ensure_opencode_server_running(
    *,
    hostname: str | None = None,
    port: int | None = None,
    startup_timeout_seconds: int = 30,
    health_check_timeout: int = 10,
) -> dict:
    """Ensure OpenCode server is running on target (hostname, port).

    This is the server lifecycle manager for governance. It implements:
    - Adopt if matching: healthy server on target -> use it
    - Start if absent: server not running -> start and wait for health
    - Block if mismatched: server running but not healthy -> fail closed

    Priority:
      1) Use provided hostname/port if given
      2) Resolve from opencode.json (SSOT)

    Args:
        hostname: Target hostname (optional, overrides config)
        port: Target port (optional, overrides config)
        startup_timeout_seconds: Max time to wait for server startup (default: 30)
        health_check_timeout: HTTP timeout for health check (default: 10)

    Returns:
        Dict with "healthy" (bool), "version" (str), "started" (bool) keys

    Raises:
        ServerNotAvailableError: If server cannot be started or is unhealthy
    """
    if hostname is None or port is None:
        from governance_runtime.install.install import resolve_effective_opencode_port
        resolved = _resolve_server_endpoint_from_opencode_json()
        resolved_port = resolved[1] if resolved else None
        resolved_hostname = resolved[0] if resolved else None

        if port is None:
            port = resolved_port
        if port is None:
            from governance_runtime.install.install import DEFAULT_OPENCODE_PORT
            port = DEFAULT_OPENCODE_PORT

        if hostname is None:
            if resolved_hostname:
                hostname = resolved_hostname
            else:
                from governance_runtime.install.install import DEFAULT_OPENCODE_HOSTNAME
                hostname = DEFAULT_OPENCODE_HOSTNAME

    if port is None:
        raise ServerNotAvailableError(
            "OpenCode server port not resolvable. "
            "Set server.port in opencode.json or provide port explicitly."
        )

    target_url = f"http://{hostname}:{port}"

    health = None
    try:
        health = _check_target_server_health(
            hostname=hostname,
            port=port,
            timeout=health_check_timeout,
        )
        if health.get("healthy") is True:
            return {
                "healthy": True,
                "version": health.get("version", "unknown"),
                "started": False,
                "target_url": target_url,
            }
    except ServerNotAvailableError:
        pass

    if health is not None and health.get("healthy") is not True:
        raise ServerTargetUnhealthyError(
            f"Target server at {target_url} is reachable but unhealthy. "
            f"Health response: {health}. "
            f"Cannot auto-start: a server process appears to be running but not healthy. "
            f"Stop the existing server or fix its health before retrying.",
            target_url=target_url,
            health_response=health,
        )

    mismatch = detect_server_binding_mismatch(hostname, port)
    if mismatch:
        found_hostname, found_port = mismatch
        found_url = f"http://{found_hostname}:{found_port}"
        raise ServerBindingMismatchError(
            f"Server binding mismatch: expected {target_url} but found server at {found_url}. "
            f"Governance will not automatically adopt a server on a different port/hostname. "
            f"Either stop the existing server or update opencode.json to match.",
            target_url=target_url,
            found_url=found_url,
        )

    # Build platform-specific kwargs for process detachment.
    # On Unix, start_new_session=True calls setsid() to detach the child
    # into its own session, preventing parent-exit from killing it.
    # On Windows, start_new_session is not the reliable detachment
    # mechanism — we use explicit creationflags instead:
    # CREATE_NEW_PROCESS_GROUP detaches from the parent's console control
    # group (Ctrl+C), and DETACHED_PROCESS prevents the child from
    # inheriting or creating a console window.
    _popen_detach_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        _create_new_pg = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        _detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        _popen_detach_kwargs["creationflags"] = _create_new_pg | _detached
    else:
        _popen_detach_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(
            ["opencode", "serve", "--port", str(port), "--hostname", hostname],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_popen_detach_kwargs,
        )
    except FileNotFoundError:
        raise ServerStartFailedError(
            f"Cannot start OpenCode server: 'opencode' command not found. "
            f"Ensure OpenCode Desktop is installed and 'opencode serve' is available.",
            target_url=target_url,
        ) from None
    except OSError as e:
        raise ServerStartFailedError(
            f"Failed to start OpenCode server: {e}",
            target_url=target_url,
        ) from e

    poll_interval = 0.5
    elapsed = 0.0
    while elapsed < startup_timeout_seconds:
        time.sleep(poll_interval)
        elapsed += poll_interval
        try:
            health = _check_target_server_health(
                hostname=hostname,
                port=port,
                timeout=health_check_timeout,
            )
            if health.get("healthy") is True:
                return {
                    "healthy": True,
                    "version": health.get("version", "unknown"),
                    "started": True,
                    "target_url": target_url,
                }
        except ServerNotAvailableError:
            continue

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    raise ServerStartTimeoutError(
        f"OpenCode server start timeout: server did not become healthy within "
        f"{startup_timeout_seconds}s on {target_url}. "
        f"Check logs or start manually: opencode serve --port {port} --hostname {hostname}",
        target_url=target_url,
        timeout_seconds=startup_timeout_seconds,
    )


def _check_target_server_health(
    hostname: str,
    port: int,
    timeout: int = 10,
) -> dict:
    """Check health of a specific server endpoint.

    Args:
        hostname: Server hostname
        port: Server port
        timeout: HTTP request timeout

    Returns:
        Dict with health status

    Raises:
        ServerNotAvailableError: If server is not reachable
    """
    url = f"http://{hostname}:{port}/global/health"
    headers = {}
    auth_headers = _resolve_auth()
    if auth_headers:
        headers.update(auth_headers)

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, dict):
                raise ServerNotAvailableError(
                    f"Invalid health response from {url}: expected dict, got {type(data)}"
                )
            return data
    except urllib.error.HTTPError as e:
        raise ServerNotAvailableError(
            f"Server health check failed on {url}: HTTP {e.code}"
        ) from e
    except urllib.error.URLError as e:
        raise ServerNotAvailableError(
            f"Cannot connect to server at {url}: {e.reason}"
        ) from e
    except (OSError, ValueError) as e:
        raise ServerNotAvailableError(
            f"Server health check failed on {url}: {e}"
        ) from e
    except json.JSONDecodeError as e:
        raise ServerNotAvailableError(
            f"Invalid JSON in health response from {url}: {e}"
        ) from e


def detect_server_binding_mismatch(
    target_hostname: str,
    target_port: int,
    scan_ports: list[int] | None = None,
    scan_timeout: int = 2,
) -> tuple[str, int] | None:
    """Detect if OpenCode server is running on a different port/hostname than target.

    This implements drift detection for Phase 4 of the server lifecycle plan:
    - Check if server is running on configured target → OK
    - Check if server is running elsewhere → MISMATCH (block, don't auto-adopt)

    Note: This is diagnostic-only heuristics, not SSOT. The scan_ports list represents
    commonly used OpenCode ports. This will NOT auto-adopt or auto-rebind - it only
    provides diagnostic information for the user.

    Args:
        target_hostname: Expected hostname from config
        target_port: Expected port from config
        scan_ports: Ports to scan for drift detection (default: common ports)
        scan_timeout: Timeout per port check

    Returns:
        Tuple of (found_hostname, found_port) if drift detected, None if no server found
    """
    if scan_ports is None:
        scan_ports = [4096, 4097, 4098, 8192]

    for port in scan_ports:
        if port == target_port:
            continue
        try:
            url = f"http://{target_hostname}:{port}/global/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=scan_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("healthy") is True:
                    return (target_hostname, port)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
            continue

    return None


# ---------------------------------------------------------------------------
# attach_existing discovery (lsof-based)
# ---------------------------------------------------------------------------

_LSOF_TIMEOUT_SECONDS: int = 5
_HEALTH_CHECK_TIMEOUT_SECONDS: int = 5
_OPENCODE_PROCESS_PREFIXES: tuple[str, ...] = ("opencode",)


def _parse_lsof_candidates(lsof_output: str) -> list[tuple[str, int]]:
    """Parse lsof TCP-LISTEN output into (hostname, port) candidate tuples.

    Pre-filters on process name containing an ``opencode`` prefix.
    This is a heuristic pre-filter only — ``/global/health`` is the authority.

    Expected lsof line format (``-nP`` suppresses name resolution)::

        opencode- 53525 koeppben 11u IPv4 0x... TCP 127.0.0.1:52372 (LISTEN)

    Args:
        lsof_output: Raw stdout from ``lsof -iTCP@127.0.0.1 -sTCP:LISTEN -nP``.

    Returns:
        De-duplicated list of ``(hostname, port)`` tuples from opencode-named processes.
    """
    seen: set[tuple[str, int]] = set()
    candidates: list[tuple[str, int]] = []

    for line in lsof_output.splitlines():
        parts = line.split()
        if len(parts) < 9:
            continue

        command_name = parts[0].lower()
        if not any(command_name.startswith(prefix) for prefix in _OPENCODE_PROCESS_PREFIXES):
            continue

        # TCP column is typically parts[8] in format "host:port"
        # But position can shift — scan backwards for the (LISTEN) marker
        tcp_field: str | None = None
        for i in range(len(parts) - 1, -1, -1):
            if parts[i] == "(LISTEN)" and i > 0:
                tcp_field = parts[i - 1]
                break

        if tcp_field is None:
            continue

        # Parse "host:port" — handle IPv6 bracket notation if present
        if tcp_field.startswith("["):
            # IPv6: [::1]:port
            bracket_end = tcp_field.rfind("]")
            if bracket_end < 0:
                continue
            hostname = tcp_field[: bracket_end + 1]
            port_str = tcp_field[bracket_end + 2 :]  # skip ]:
        else:
            colon_pos = tcp_field.rfind(":")
            if colon_pos < 0:
                continue
            hostname = tcp_field[:colon_pos]
            port_str = tcp_field[colon_pos + 1 :]

        try:
            port = int(port_str)
        except ValueError:
            continue

        if port < 1 or port > 65535:
            continue

        key = (hostname, port)
        if key not in seen:
            seen.add(key)
            candidates.append(key)

    return candidates


def discover_local_opencode_server(
    *,
    health_check_timeout: int = _HEALTH_CHECK_TIMEOUT_SECONDS,
    lsof_timeout: int = _LSOF_TIMEOUT_SECONDS,
) -> tuple[str, dict]:
    """Discover a running local OpenCode server via OS-level port scanning.

    Used by ``attach_existing`` mode. Finds opencode-named TCP listeners on
    127.0.0.1, then verifies each candidate via ``/global/health``.

    Platform support:
      - macOS / Linux: ``lsof -iTCP@127.0.0.1 -sTCP:LISTEN -nP``
      - Windows: raises ``ServerDiscoveryUnsupportedPlatformError``

    Args:
        health_check_timeout: HTTP timeout per candidate health check (seconds).
        lsof_timeout: Timeout for the lsof subprocess (seconds).

    Returns:
        Tuple of ``(base_url, health_dict)`` for the single healthy server.

    Raises:
        ServerDiscoveryUnsupportedPlatformError: On unsupported platforms (Windows).
        ServerDiscoveryNotFoundError: If zero healthy OpenCode servers found.
        ServerDiscoveryAmbiguousError: If multiple healthy OpenCode servers found.
        ServerAuthRequiredError: If a candidate returns HTTP 401 and no credentials
            are configured via ``OPENCODE_SERVER_PASSWORD``.
    """
    if sys.platform == "win32":
        raise ServerDiscoveryUnsupportedPlatformError(
            "attach_existing discovery is not implemented on Windows yet; "
            "use --server-mode managed",
            platform="win32",
        )

    # --- Run lsof to find TCP listeners on localhost ---
    try:
        result = subprocess.run(
            ["lsof", "-iTCP@127.0.0.1", "-sTCP:LISTEN", "-nP"],
            capture_output=True,
            text=True,
            timeout=lsof_timeout,
        )
    except FileNotFoundError:
        raise ServerDiscoveryNotFoundError(
            "Cannot discover local servers: 'lsof' command not found. "
            "Install lsof or use --server-mode managed.",
            candidates_scanned=0,
        ) from None
    except subprocess.TimeoutExpired:
        raise ServerDiscoveryNotFoundError(
            f"Cannot discover local servers: lsof timed out after {lsof_timeout}s. "
            "Use --server-mode managed as a workaround.",
            candidates_scanned=0,
        ) from None
    except OSError as exc:
        raise ServerDiscoveryNotFoundError(
            f"Cannot discover local servers: lsof failed: {exc}. "
            "Use --server-mode managed as a workaround.",
            candidates_scanned=0,
        ) from exc

    # lsof returns exit code 1 when no matching files found — that's expected
    candidates = _parse_lsof_candidates(result.stdout)

    if not candidates:
        raise ServerDiscoveryNotFoundError(
            "No OpenCode server found listening on 127.0.0.1. "
            "Start OpenCode Desktop or use --server-mode managed.",
            candidates_scanned=0,
        )

    # --- Health-check each candidate; /global/health is the authority ---
    healthy: list[tuple[str, dict]] = []
    auth_required_url: str | None = None

    for hostname, port in candidates:
        base_url = f"http://{hostname}:{port}"
        url = f"{base_url}/global/health"

        headers: dict[str, str] = {}
        auth_headers = _resolve_auth()
        if auth_headers:
            headers.update(auth_headers)

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=health_check_timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, dict) and data.get("healthy") is True:
                    healthy.append((base_url, data))
        except urllib.error.HTTPError as e:
            if e.code == 401 and not _resolve_auth():
                # Real HTTP 401 from a candidate, and no credentials configured
                auth_required_url = base_url
            # Other HTTP errors: candidate is not a healthy OpenCode server
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            # Connection refused, timeout, malformed response: skip candidate
            continue

    # --- Evaluate results ---
    if len(healthy) == 1:
        return healthy[0]

    if len(healthy) > 1:
        endpoints = [url for url, _ in healthy]
        raise ServerDiscoveryAmbiguousError(
            f"Multiple healthy OpenCode servers found on 127.0.0.1: "
            f"{', '.join(endpoints)}. "
            f"Stop extra servers or use --server-mode managed with an explicit port.",
            healthy_endpoints=endpoints,
        )

    # Zero healthy — check if auth was the blocker
    if auth_required_url is not None:
        raise ServerAuthRequiredError(
            f"OpenCode server at {auth_required_url} requires authentication. "
            f"Set OPENCODE_SERVER_PASSWORD (and optionally OPENCODE_SERVER_USERNAME) "
            f"environment variables.",
            target_url=auth_required_url,
        )

    raise ServerDiscoveryNotFoundError(
        f"Found {len(candidates)} opencode-named listener(s) on 127.0.0.1 "
        f"but none returned healthy on /global/health. "
        f"Start OpenCode Desktop or use --server-mode managed.",
        candidates_scanned=len(candidates),
    )


def get_projects(*, base_url: str | None = None) -> list[dict]:
    """Get all projects from OpenCode server.

    Uses GET /project per official server API documentation.

    Args:
        base_url: Optional server base URL. If provided, uses this URL directly
            instead of resolving via opencode.json / OPENCODE_PORT.

    Returns:
        List of project dicts with id, worktree, vcs, etc.

    Raises:
        ServerNotAvailableError: If server is not reachable
        APIError: For API errors
    """
    if base_url is not None:
        server_url = base_url
    else:
        try:
            server_url = resolve_opencode_server_base_url()
        except ServerNotAvailableError as exc:
            raise ServerNotAvailableError(
                f"OpenCode server not reachable: {exc}. "
                "Ensure OpenCode Desktop is running."
            ) from exc

    headers = {}
    auth_headers = _resolve_auth()
    if auth_headers:
        headers.update(auth_headers)

    url = f"{server_url}/project"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise APIError(f"Failed to get projects: HTTP {e.code}: {e.reason}") from e
    except (OSError, ValueError) as e:
        raise APIError(f"Failed to get projects: {e}") from e


def resolve_project_id(
    project_path: str,
    *,
    base_url: str | None = None,
) -> str:
    """Resolve a filesystem project path to an OpenCode project ID.

    Calls GET /project and matches by canonicalized comparison of
    ``project["worktree"]`` against *project_path*.

    Args:
        project_path: Absolute filesystem path to the repository root.
        base_url: Optional server base URL.

    Returns:
        The ``id`` field of the matching project.

    Raises:
        ProjectNotFoundError: If no project matches the given path.
        ServerNotAvailableError: If server is not reachable.
        APIError: For other API errors.
    """
    projects = get_projects(base_url=base_url)

    # Canonicalize: resolve symlinks, remove trailing slashes, normalize case
    # on case-insensitive filesystems (macOS).
    try:
        canon_target = os.path.realpath(project_path).rstrip(os.sep)
    except (OSError, ValueError):
        canon_target = project_path.rstrip("/").rstrip("\\")

    for project in projects:
        worktree = project.get("worktree", "")
        if not worktree:
            continue
        try:
            canon_worktree = os.path.realpath(worktree).rstrip(os.sep)
        except (OSError, ValueError):
            canon_worktree = worktree.rstrip("/").rstrip("\\")
        if canon_target == canon_worktree:
            return project["id"]

    available = [p.get("worktree", "") for p in projects if p.get("worktree")]
    raise ProjectNotFoundError(
        f"No OpenCode project found for path: {project_path}. "
        f"Available project worktrees: {available}. "
        "Open this repository in OpenCode Desktop first.",
        project_path=project_path,
    )


def get_sessions(*, base_url: str | None = None, directory: str | None = None) -> list[dict]:
    """Get sessions from OpenCode server.

    Uses GET /session per official server API documentation.

    Args:
        base_url: Optional server base URL. If provided, uses this URL directly
            instead of resolving via opencode.json / OPENCODE_PORT. This enables
            attach_existing mode where the server was discovered dynamically.
        directory: Optional directory filter. When provided, appended as
            ``?directory=<path>`` so the server returns only sessions scoped
            to that directory.  Without this parameter the server returns
            only global sessions.

    Returns:
        List of session dicts with id, title, projectID, directory, etc.

    Raises:
        ServerNotAvailableError: If server is not reachable
        APIError: For API errors
    """
    if base_url is not None:
        server_url = base_url
    else:
        try:
            server_url = resolve_opencode_server_base_url()
        except ServerNotAvailableError as exc:
            raise ServerNotAvailableError(
                f"OpenCode server not reachable: {exc}. "
                "Ensure OpenCode Desktop is running."
            ) from exc

    headers = {}
    auth_headers = _resolve_auth()
    if auth_headers:
        headers.update(auth_headers)

    url = f"{server_url}/session"
    if directory:
        url = f"{url}?directory={urllib.parse.quote(directory, safe='')}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise APIError(f"Failed to get sessions: HTTP {e.code}: {e.reason}") from e
    except (OSError, ValueError) as e:
        raise APIError(f"Failed to get sessions: {e}") from e


def get_active_session(
    project_path: str | None = None,
    *,
    base_url: str | None = None,
) -> dict:
    """Get the active session for a project via project-based resolution.

    Resolution when *project_path* is provided:
      1. ``GET /project`` — list all projects.
      2. Resolve *project_path* → ``project_id`` by canonicalized worktree match.
      3. ``GET /session`` — list all sessions.
      4. Filter sessions where ``session["projectID"] == project_id``.
      5. 0 matches → ``ProjectSessionNotFoundError``.
      6. 1 match  → return it.
      7. Multiple → return the most recently created (highest ``createdAt``).

    If *project_path* is not provided, returns the most recently updated session
    (no project resolution).

    Args:
        project_path: Optional project directory path (e.g., "/path/to/repo").
        base_url: Optional server base URL. If provided, uses this URL directly
            instead of resolving via opencode.json / OPENCODE_PORT. This enables
            attach_existing mode where the server was discovered dynamically.

    Returns:
        Session dict with id, title, projectID, directory, etc.

    Raises:
        ServerNotAvailableError: If server is not reachable.
        ProjectNotFoundError: If no OpenCode project matches *project_path*.
        ProjectSessionNotFoundError: If the project exists but has no sessions.
        APIError: If no sessions exist at all.
    """
    sessions = get_sessions(base_url=base_url, directory=project_path)

    if not sessions:
        raise APIError(
            "No OpenCode sessions found. "
            "Start a session in OpenCode Desktop before running /hydrate."
        )

    if project_path:
        # Step 1-2: Resolve project_path → project_id via worktree match.
        # ProjectNotFoundError propagates if no project matches.
        project_id = resolve_project_id(project_path, base_url=base_url)

        # Step 3-4: Filter sessions by projectID (NOT by directory).
        matching_sessions = [
            s for s in sessions
            if s.get("projectID") == project_id
        ]

        if len(matching_sessions) == 0:
            # Diagnostic: include actual projectIDs for debugging.
            actual_ids = sorted({s.get("projectID", "<missing>") for s in sessions})
            raise ProjectSessionNotFoundError(
                f"No session found for project '{project_path}' (projectID={project_id}). "
                f"Sessions returned had projectIDs: {actual_ids}. "
                "Open a new session for this project in OpenCode Desktop.",
                project_id=project_id,
                project_path=project_path,
            )

        if len(matching_sessions) == 1:
            return matching_sessions[0]

        # Multiple matches: return the most recently created session.
        # Session objects have nested time.created (numeric Unix timestamp ms).
        matching_sessions.sort(
            key=lambda s: s.get("time", {}).get("created", 0),
            reverse=True,
        )
        return matching_sessions[0]

    # No project_path: return the first (most recent) session.
    return sessions[0]


def send_session_message(
    text: str,
    session_id: str | None = None,
    *,
    base_url: str | None = None,
    model: dict[str, str] | None = None,
) -> dict:
    """Send a message to a session without waiting for LLM response.

    Uses POST /session/:id/message per official server API documentation.
    This is used by /hydrate to write the hydration brief to the session.

    Args:
        text: Message text to send
        session_id: Session ID (optional, uses OPENCODE_SESSION_ID if not provided)
        base_url: Optional server base URL. If provided, uses this URL directly
            instead of resolving via opencode.json / OPENCODE_PORT. This enables
            attach_existing mode where the server was discovered dynamically.
        model: Optional model specification

    Returns:
        Session response dict with info and parts

    Raises:
        ServerNotAvailableError: If server is not reachable
        APIError: For API errors or missing session ID
    """
    if session_id is None:
        session_id, _ = resolve_session_id()

    if base_url is not None:
        server_url = base_url
    else:
        try:
            server_url = resolve_opencode_server_base_url()
        except ServerNotAvailableError as exc:
            raise APIError(f"Server not available: {exc}") from exc

    body: dict = {
        "noReply": True,
        "parts": [{"type": "text", "text": text}],
    }

    if model:
        body["model"] = model

    headers = {"Content-Type": "application/json"}
    auth_headers = _resolve_auth()
    if auth_headers:
        headers.update(auth_headers)

    url = f"{server_url}/session/{session_id}/message"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8")
            if response_body:
                return json.loads(response_body)
            return {}
    except urllib.error.HTTPError as e:
        raise APIError(f"HTTP {e.code}: {e.reason}") from e
    except (OSError, ValueError) as e:
        raise APIError(f"Failed to send session message: {e}") from e
