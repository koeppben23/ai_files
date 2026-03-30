from __future__ import annotations

import base64
import json
import os
import urllib.request
from pathlib import Path
from typing import Mapping


class OpenCodeServerError(Exception):
    pass


class ServerNotAvailableError(OpenCodeServerError):
    pass


class AuthenticationError(OpenCodeServerError):
    pass


class APIError(OpenCodeServerError):
    pass


def is_server_required_mode() -> bool:
    """Check if server is required (fail-closed) mode.

    When AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER=1 is set:
    - Server MUST be available or call will fail
    - No fallback to legacy CLI bridge

    Returns:
        True if server is required, False for opportunistic mode (default)
    """
    return os.environ.get("AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER", "").strip().lower() in {"1", "true", "yes", "on"}


def _resolve_base_url_from_opencode_json() -> str | None:
    """Resolve base_url from opencode.json (SSOT for server config).

    Reads ~/.config/opencode/opencode.json or opencode.jsonc for:
    - server.hostname
    - server.port

    Returns:
        base_url if found in config, None otherwise
    """
    import json
    import re
    import os

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
            hostname = server.get("hostname", "").strip() or "127.0.0.1"
            port = server.get("port")
            if port:
                return f"http://{hostname}:{port}"
        except Exception:
            continue
    return None


def resolve_opencode_server_base_url() -> str:
    """Resolve OpenCode server base URL.

    Resolution order:
    1. opencode.json (server.hostname + server.port) - SSOT
    2. OPENCODE_PORT (fallback for explicit port)
    3. fail-closed with clear error

    Returns:
        Base URL like "http://127.0.0.1:4096"

    Raises:
        ServerNotAvailableError: If no server URL can be resolved
    """
    config_url = _resolve_base_url_from_opencode_json()
    if config_url:
        return config_url

    port = os.environ.get("OPENCODE_PORT", "").strip()
    if port:
        return f"http://127.0.0.1:{port}"

    raise ServerNotAvailableError(
        "OpenCode server URL not resolvable. "
        "Set server.hostname/server.port in ~/.config/opencode/opencode.json "
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
) -> dict:
    """Send JSON POST request to OpenCode server.

    Args:
        path: API path (e.g., "/session/abc/message")
        body: JSON body to send
        base_url: Base URL override (default: resolved from environment)

    Returns:
        Parsed JSON response

    Raises:
        ServerNotAvailableError: If server is not reachable
        AuthenticationError: If auth fails
        APIError: For other API errors
    """
    if base_url is None:
        base_url = resolve_opencode_server_base_url()

    url = f"{base_url}{path}"
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
            f"Cannot connect to OpenCode server at {base_url}: {e.reason}"
        ) from e
    except TimeoutError as e:
        raise ServerNotAvailableError(f"Request timeout to {url}") from e


def send_session_prompt(
    session_id: str,
    text: str,
    *,
    model: dict[str, str] | None = None,
    output_schema: dict | None = None,
    required: bool = False,
) -> dict:
    """Send a prompt to a session and get LLM response.

    This is the documented programmatic way to access the OpenCode session LLM,
    replacing the legacy subprocess("opencode run --session ...") approach.

    Note: The server API documentation is inconsistent between format (SDK examples)
    and outputFormat (API overview). Default uses "format" per SDK examples.
    Set AI_GOVERNANCE_USE_OUTPUTFORMAT=1 to use "outputFormat" instead.

    Args:
        session_id: Session ID to continue
        text: Prompt text to send
        model: Optional model specification (e.g., {"providerID": "openai", "modelID": "gpt-5"})
               If None, uses the session's default model
        output_schema: Optional JSON schema for structured output
                      Uses "format" by default; set AI_GOVERNANCE_USE_OUTPUTFORMAT=1 for outputFormat
        required: If True, fail-closed when server not available (respects AI_GOVERNANCE_REQUIRE_OPENCODE_SERVER)

    Returns:
        Session response dict with info and parts

    Raises:
        ServerNotAvailableError: If server is not reachable (or in required mode)
        AuthenticationError: If auth fails
        APIError: For API errors
    """
    if not session_id:
        raise APIError("session_id is required")

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

    return post_json(f"/session/{session_id}/message", body, base_url=server_url)


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


def check_server_health(*, base_url: str | None = None) -> bool:
    """Check if OpenCode server is available and healthy.

    Uses GET /global/health per official server API documentation.

    Args:
        base_url: Base URL override

    Returns:
        True if server is healthy, False otherwise
    """
    import urllib.request

    try:
        if base_url is None:
            base_url = resolve_opencode_server_base_url()

        url = f"{base_url}/global/health"
        headers = {}
        auth_headers = _resolve_auth()
        if auth_headers:
            headers.update(auth_headers)

        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("healthy", False) is True
    except Exception:
        return False


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
    except Exception as e:
        return False, f"Health check error: {e}"


def is_bootstrap_server_health_check_skipped() -> bool:
    """Check if server health check should be skipped (for testing).

    Returns:
        True if health check should be skipped
    """
    return os.environ.get("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "").strip().lower() in {"1", "true", "yes"}
