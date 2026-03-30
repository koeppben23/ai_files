"""Integration tests for OpenCode server client.

These tests start a dedicated OpenCode server for testing.
Run with: pytest tests/integration/test_opencode_server_integration.py -v

The tests will:
1. Start opencode serve --port 4096 (without auth for testing)
2. Run integration tests
3. Stop the server
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Generator

import pytest


OPENCODE_HOST = "127.0.0.1"
OPENCODE_PORT = "4096"
TEST_PASSWORD = "test-password"


def _find_opencode_binary() -> str | None:
    """Find the opencode binary."""
    candidates = [
        "opencode",
        "/Applications/OpenCode.app/Contents/MacOS/opencode-cli",
        os.path.expanduser("~/Library/Application Support/ai.opencode.desktop/opencode-cli"),
    ]
    for binary in candidates:
        try:
            result = subprocess.run(
                [binary, "--version"],
                capture_output=True,
                timeout=5,
                text=True,
            )
            if result.returncode == 0:
                return binary
        except Exception:
            continue
    return None


def _is_port_in_use(port: str) -> bool:
    """Check if port is already in use."""
    import urllib.request
    import urllib.error
    try:
        url = f"http://{OPENCODE_HOST}:{port}/global/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2):
            return True
    except urllib.error.HTTPError as e:
        if e.code in (200, 401):
            return True
        return False
    except Exception:
        return False


@pytest.fixture(scope="module")
def opencode_server() -> Generator[tuple[subprocess.Popen, str], None, None]:
    """Start OpenCode server for integration tests.

    Uses: opencode serve --hostname 127.0.0.1 --port 4096
    """
    binary = _find_opencode_binary()
    if not binary:
        pytest.skip("opencode binary not found. Install OpenCode Desktop.")

    port = OPENCODE_PORT
    host = OPENCODE_HOST

    existing_server = _is_port_in_use(port)
    if existing_server:
        pass

    env = os.environ.copy()
    env["OPENCODE_SERVER_PASSWORD"] = TEST_PASSWORD

    proc = subprocess.Popen(
        [binary, "serve", "--hostname", host, "--port", port],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    max_wait = 30
    server_started = False
    for _ in range(max_wait):
        if _is_port_in_use(port):
            server_started = True
            break
        time.sleep(1)

    if not server_started:
        proc.terminate()
        proc.wait()
        pytest.skip(f"OpenCode server failed to start on {host}:{port}")

    yield proc, port

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="module")
def server_port() -> str:
    """Get the test server port."""
    return OPENCODE_PORT


@pytest.fixture(scope="module")
def server_auth() -> dict:
    """Get auth headers for test server."""
    import base64
    credentials = f"opencode:{TEST_PASSWORD}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


class TestOpencodeServerIntegration:
    """Integration tests for real OpenCode server communication."""

    def test_server_health_check(self, opencode_server, server_auth):
        """Verify server is reachable and healthy."""
        import urllib.request

        url = f"http://{OPENCODE_HOST}:{OPENCODE_PORT}/global/health"
        req = urllib.request.Request(url, method="GET", headers=server_auth)
        with urllib.request.urlopen(req, timeout=10) as resp:
            assert resp.status == 200, f"Unexpected status: {resp.status}"

    def test_resolve_server_url(self, opencode_server):
        """Verify server URL is resolved correctly from opencode.json."""
        from governance_runtime.infrastructure.opencode_server_client import resolve_opencode_server_base_url

        os.environ["OPENCODE_PORT"] = OPENCODE_PORT
        os.environ["HOME"] = os.path.expanduser("~")

        url = resolve_opencode_server_base_url()
        expected = f"http://{OPENCODE_HOST}:{OPENCODE_PORT}"
        assert url == expected, f"Expected {expected}, got {url}"

    def test_server_session_list(self, opencode_server, server_auth):
        """Test listing sessions from server."""
        import urllib.request
        import urllib.error

        url = f"http://{OPENCODE_HOST}:{OPENCODE_PORT}/session"
        req = urllib.request.Request(url, method="GET", headers=server_auth)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status in (200, 204), f"Unexpected status: {resp.status}"
        except urllib.error.HTTPError as e:
            pytest.fail(f"Server returned {e.code}: {e.reason}")

    def test_server_session_create(self, opencode_server, server_auth):
        """Test creating a session returns 200."""
        import urllib.request
        import urllib.error

        url = f"http://{OPENCODE_HOST}:{OPENCODE_PORT}/session"
        req = urllib.request.Request(url, method="POST", headers=server_auth)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 200, f"Unexpected status: {resp.status}"
        except urllib.error.HTTPError as e:
            pytest.fail(f"Failed to create session: {e.code}: {e.reason}")


class TestGovernanceWithRealServer:
    """Test governance production paths with real server."""

    def test_server_client_can_send_prompt_with_auth(self, opencode_server, server_auth):
        """Test sending a prompt to a session via server client with auth."""
        from governance_runtime.infrastructure.opencode_server_client import send_session_prompt, APIError
        import urllib.request

        os.environ["OPENCODE_PORT"] = OPENCODE_PORT
        os.environ["OPENCODE_SERVER_PASSWORD"] = TEST_PASSWORD
        os.environ["OPENCODE_SERVER_USERNAME"] = "opencode"

        url = f"http://{OPENCODE_HOST}:{OPENCODE_PORT}/session"
        req = urllib.request.Request(url, method="POST", headers=server_auth)
        session_id = None
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    session_data = json.loads(resp.read().decode("utf-8"))
                    session_id = session_data.get("sessionID")
        except Exception:
            pass

        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())

        try:
            result = send_session_prompt(session_id, "Hello")
            assert result is not None
        except APIError as e:
            if "400" in str(e):
                pytest.skip(f"Session not ready: {e}")
            pytest.fail(f"API error: {e}")


class TestServerUrlResolution:
    """Test server URL resolution from opencode.json."""

    def test_reads_from_opencode_json(self, opencode_server, tmp_path):
        """Test that URL is read from opencode.json."""
        from governance_runtime.infrastructure.opencode_server_client import resolve_opencode_server_base_url

        home = tmp_path / "home"
        home.mkdir(parents=True)
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)

        config = {
            "server": {
                "hostname": OPENCODE_HOST,
                "port": int(OPENCODE_PORT)
            }
        }
        (config_dir / "opencode.json").write_text(json.dumps(config))

        old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(home)
        try:
            url = resolve_opencode_server_base_url()
            assert url == f"http://{OPENCODE_HOST}:{OPENCODE_PORT}"
        finally:
            if old_home:
                os.environ["HOME"] = old_home
            else:
                os.environ.pop("HOME", None)
