"""Pure render functions for plan-record.json artifact.

Provides content-hash computation and JSON serialization for plan
version entries.  No I/O -- callers handle persistence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_content_hash(version_data: dict[str, Any]) -> str:
    """Compute SHA-256 content hash for a PlanVersion entry.

    The hash covers the full version object *excluding* the
    ``content_hash`` field itself, producing a deterministic
    fingerprint for integrity verification and diff detection.

    Args:
        version_data: The PlanVersion dict (content_hash may be present
            but is stripped before hashing).

    Returns:
        ``"sha256:<64-hex>"`` string.
    """
    payload = {k: v for k, v in version_data.items() if k != "content_hash"}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def render_plan_record(document: dict[str, Any], *, indent: int = 2) -> str:
    """Serialize a plan-record document to a JSON string.

    Args:
        document: The full plan-record dict (with schema_version,
            repo_fingerprint, status, versions, etc.).
        indent: JSON indentation level.

    Returns:
        JSON string with trailing newline.
    """
    return json.dumps(document, indent=indent, ensure_ascii=True) + "\n"


def new_plan_record_document(repo_fingerprint: str) -> dict[str, Any]:
    """Create an empty, active plan-record document.

    Args:
        repo_fingerprint: The canonical 24-hex repo fingerprint.

    Returns:
        A dict ready for serialization with ``versions: []``.
    """
    return {
        "schema_version": "1.0.0",
        "repo_fingerprint": repo_fingerprint,
        "status": "active",
        "finalized_at": None,
        "finalized_by_session": None,
        "finalized_phase": None,
        "outcome": None,
        "versions": [],
    }


def stamp_version(version_data: dict[str, Any]) -> dict[str, Any]:
    """Add the content_hash to a PlanVersion dict.

    Args:
        version_data: PlanVersion dict without content_hash (or with a
            stale one that will be recomputed).

    Returns:
        A *new* dict with ``content_hash`` set.
    """
    result = dict(version_data)
    result["content_hash"] = compute_content_hash(result)
    return result
