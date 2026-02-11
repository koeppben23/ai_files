"""Deterministic governance pack lock builder for Wave C.

This module provides a fail-closed, side-effect-free resolver for pack metadata
and a deterministic lock payload writer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

LOCK_SCHEMA = "governance-lock.v1"


@dataclass(frozen=True)
class PackManifest:
    """Minimal normalized pack manifest model for Wave C locking."""

    id: str
    version: str
    compat_engine_min: str
    compat_engine_max: str
    requires: tuple[str, ...]
    conflicts_with: tuple[str, ...]
    owns_surfaces: tuple[str, ...]
    touches_surfaces: tuple[str, ...]


def _parse_semver(version: str) -> tuple[int, int, int]:
    """Parse strict semantic version `x.y.z` into sortable integer tuple."""

    parts = version.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"invalid semver: {version!r}")
    try:
        major, minor, patch = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError as exc:
        raise ValueError(f"invalid semver: {version!r}") from exc
    return major, minor, patch


def _ensure_string_list(value: Any, field_name: str) -> tuple[str, ...]:
    """Normalize list field to tuple while validating item types."""

    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"manifest field {field_name!r} must be a list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"manifest field {field_name!r} contains invalid item")
        out.append(item.strip())
    return tuple(out)


def normalize_manifest(manifest: dict[str, Any]) -> PackManifest:
    """Validate and normalize one manifest dict into `PackManifest`."""

    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")

    pack_id = manifest.get("id")
    version = manifest.get("version")
    compat = manifest.get("compat")

    if not isinstance(pack_id, str) or not pack_id.strip():
        raise ValueError("manifest id is required")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"manifest version is required for {pack_id!r}")
    _parse_semver(version)

    if not isinstance(compat, dict):
        raise ValueError(f"manifest compat block is required for {pack_id!r}")
    engine_min = compat.get("engine_min")
    engine_max = compat.get("engine_max")
    if not isinstance(engine_min, str) or not engine_min.strip():
        raise ValueError(f"manifest compat.engine_min is required for {pack_id!r}")
    if not isinstance(engine_max, str) or not engine_max.strip():
        raise ValueError(f"manifest compat.engine_max is required for {pack_id!r}")
    _parse_semver(engine_min)
    _parse_semver(engine_max)

    requires = _ensure_string_list(manifest.get("requires"), "requires")
    conflicts_with = _ensure_string_list(manifest.get("conflicts_with"), "conflicts_with")
    owns_surfaces = _ensure_string_list(manifest.get("owns_surfaces"), "owns_surfaces")
    touches_surfaces = _ensure_string_list(manifest.get("touches_surfaces"), "touches_surfaces")

    return PackManifest(
        id=pack_id.strip(),
        version=version.strip(),
        compat_engine_min=engine_min.strip(),
        compat_engine_max=engine_max.strip(),
        requires=tuple(sorted(set(requires))),
        conflicts_with=tuple(sorted(set(conflicts_with))),
        owns_surfaces=tuple(sorted(set(owns_surfaces))),
        touches_surfaces=tuple(sorted(set(touches_surfaces))),
    )


def _is_engine_compatible(manifest: PackManifest, engine_version: str) -> bool:
    """Return True when engine version falls within manifest compat range."""

    current = _parse_semver(engine_version)
    lower = _parse_semver(manifest.compat_engine_min)
    upper = _parse_semver(manifest.compat_engine_max)
    return lower <= current <= upper


def _manifest_sha256(manifest: PackManifest) -> str:
    """Compute deterministic sha256 digest for normalized manifest payload."""

    payload = {
        "id": manifest.id,
        "version": manifest.version,
        "compat": {
            "engine_min": manifest.compat_engine_min,
            "engine_max": manifest.compat_engine_max,
        },
        "requires": list(manifest.requires),
        "conflicts_with": list(manifest.conflicts_with),
        "owns_surfaces": list(manifest.owns_surfaces),
        "touches_surfaces": list(manifest.touches_surfaces),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def resolve_pack_lock(
    *,
    manifests_by_id: dict[str, dict[str, Any]],
    selected_pack_ids: list[str],
    engine_version: str,
) -> dict[str, Any]:
    """Resolve selected packs into deterministic governance lock payload.

    Fails closed for:
    - missing required dependencies
    - explicit conflicts
    - engine incompatibility
    - dependency cycles
    """

    normalized: dict[str, PackManifest] = {}
    for key in sorted(manifests_by_id):
        manifest = normalize_manifest(manifests_by_id[key])
        normalized[manifest.id] = manifest

    to_process = sorted({pack_id.strip() for pack_id in selected_pack_ids if pack_id.strip()})
    if not to_process:
        raise ValueError("selected_pack_ids must contain at least one pack")

    closure: set[str] = set()
    queue = list(to_process)
    while queue:
        current = queue.pop(0)
        if current in closure:
            continue
        manifest = normalized.get(current)
        if manifest is None:
            raise ValueError(f"missing manifest for selected pack: {current}")
        closure.add(current)
        for dep in manifest.requires:
            if dep not in normalized:
                raise ValueError(f"missing required dependency {dep!r} for pack {current!r}")
            queue.append(dep)

    resolved_ids = sorted(closure)
    for pack_id in resolved_ids:
        manifest = normalized[pack_id]
        if not _is_engine_compatible(manifest, engine_version):
            raise ValueError(f"engine version {engine_version!r} is incompatible with pack {pack_id!r}")
        for conflict in manifest.conflicts_with:
            if conflict in closure:
                raise ValueError(f"pack conflict detected: {pack_id!r} conflicts with {conflict!r}")

    surface_owner: dict[str, str] = {}
    for pack_id in resolved_ids:
        manifest = normalized[pack_id]
        for surface in manifest.owns_surfaces:
            existing_owner = surface_owner.get(surface)
            if existing_owner is not None and existing_owner != pack_id:
                raise ValueError(
                    f"surface conflict detected: {pack_id!r} and {existing_owner!r} both own {surface!r}"
                )
            surface_owner[surface] = pack_id

    for pack_id in resolved_ids:
        manifest = normalized[pack_id]
        for surface in manifest.touches_surfaces:
            owner = surface_owner.get(surface)
            if owner is None or owner == pack_id:
                continue
            if owner not in manifest.requires:
                raise ValueError(
                    f"surface conflict detected: {pack_id!r} touches {surface!r} but does not require owner {owner!r}"
                )

    indegree: dict[str, int] = {pack_id: 0 for pack_id in resolved_ids}
    adjacency: dict[str, set[str]] = {pack_id: set() for pack_id in resolved_ids}
    for pack_id in resolved_ids:
        for dep in normalized[pack_id].requires:
            if dep in adjacency:
                adjacency[dep].add(pack_id)
                indegree[pack_id] += 1

    ordered: list[str] = []
    frontier = sorted([pack_id for pack_id in resolved_ids if indegree[pack_id] == 0])
    while frontier:
        current = frontier.pop(0)
        ordered.append(current)
        for nxt in sorted(adjacency[current]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                frontier.append(nxt)
        frontier.sort()

    if len(ordered) != len(resolved_ids):
        raise ValueError("dependency cycle detected in selected pack set")

    lock_packs: list[dict[str, Any]] = []
    for pack_id in ordered:
        manifest = normalized[pack_id]
        lock_packs.append(
            {
                "id": manifest.id,
                "version": manifest.version,
                "sha256": _manifest_sha256(manifest),
                "compat": {
                    "engine_min": manifest.compat_engine_min,
                    "engine_max": manifest.compat_engine_max,
                },
                "requires": list(manifest.requires),
                "conflicts_with": list(manifest.conflicts_with),
                "owns_surfaces": list(manifest.owns_surfaces),
                "touches_surfaces": list(manifest.touches_surfaces),
            }
        )

    canonical = {
        "schema": LOCK_SCHEMA,
        "engine_version": engine_version,
        "selected": sorted(to_process),
        "resolved_order": ordered,
        "packs": lock_packs,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    canonical["lock_hash"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return canonical


def write_pack_lock(path: Path, payload: dict[str, Any]) -> None:
    """Persist governance lock payload with deterministic JSON formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
