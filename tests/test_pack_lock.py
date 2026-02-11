from __future__ import annotations

from pathlib import Path

import pytest

from governance.packs.pack_lock import LOCK_SCHEMA, resolve_pack_lock, write_pack_lock


def _manifest(
    *,
    pack_id: str,
    version: str = "1.0.0",
    engine_min: str = "1.0.0",
    engine_max: str = "9.9.9",
    requires: list[str] | None = None,
    conflicts_with: list[str] | None = None,
) -> dict:
    """Build a minimal valid manifest dict for lock resolver tests."""

    return {
        "id": pack_id,
        "version": version,
        "compat": {
            "engine_min": engine_min,
            "engine_max": engine_max,
        },
        "requires": requires or [],
        "conflicts_with": conflicts_with or [],
    }


@pytest.mark.governance
def test_pack_lock_resolves_dependencies_deterministically():
    """Resolver should return deterministic closure and topological order."""

    manifests = {
        "core": _manifest(pack_id="core"),
        "addon-a": _manifest(pack_id="addon-a", requires=["core"]),
        "addon-b": _manifest(pack_id="addon-b", requires=["core"]),
    }
    lock = resolve_pack_lock(
        manifests_by_id=manifests,
        selected_pack_ids=["addon-b", "addon-a"],
        engine_version="2.0.0",
    )
    assert lock["schema"] == LOCK_SCHEMA
    assert lock["selected"] == ["addon-a", "addon-b"]
    assert lock["resolved_order"] == ["core", "addon-a", "addon-b"]
    assert len(lock["packs"]) == 3
    assert isinstance(lock["lock_hash"], str) and len(lock["lock_hash"]) == 64


@pytest.mark.governance
def test_pack_lock_fails_closed_on_missing_dependency():
    """Resolver should block when required dependency manifest is missing."""

    manifests = {
        "addon-a": _manifest(pack_id="addon-a", requires=["core"]),
    }
    with pytest.raises(ValueError, match="missing required dependency"):
        resolve_pack_lock(
            manifests_by_id=manifests,
            selected_pack_ids=["addon-a"],
            engine_version="2.0.0",
        )


@pytest.mark.governance
def test_pack_lock_fails_closed_on_conflict():
    """Resolver should block pack sets with explicit conflicts."""

    manifests = {
        "core": _manifest(pack_id="core"),
        "a": _manifest(pack_id="a", requires=["core"], conflicts_with=["b"]),
        "b": _manifest(pack_id="b", requires=["core"]),
    }
    with pytest.raises(ValueError, match="pack conflict detected"):
        resolve_pack_lock(
            manifests_by_id=manifests,
            selected_pack_ids=["a", "b"],
            engine_version="2.0.0",
        )


@pytest.mark.governance
def test_pack_lock_fails_closed_on_engine_incompatibility():
    """Resolver should block when engine version is outside compat range."""

    manifests = {
        "core": _manifest(pack_id="core", engine_min="3.0.0", engine_max="4.0.0"),
    }
    with pytest.raises(ValueError, match="is incompatible"):
        resolve_pack_lock(
            manifests_by_id=manifests,
            selected_pack_ids=["core"],
            engine_version="2.0.0",
        )


@pytest.mark.governance
def test_pack_lock_write_is_deterministic(tmp_path: Path):
    """Lock writer should persist stable bytes for same payload."""

    manifests = {
        "core": _manifest(pack_id="core"),
    }
    lock = resolve_pack_lock(
        manifests_by_id=manifests,
        selected_pack_ids=["core"],
        engine_version="2.0.0",
    )
    path = tmp_path / "governance.lock"
    write_pack_lock(path, lock)
    first = path.read_text(encoding="utf-8")
    write_pack_lock(path, lock)
    second = path.read_text(encoding="utf-8")
    assert first == second
