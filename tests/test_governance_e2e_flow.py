from __future__ import annotations

import re
from fnmatch import fnmatch
from dataclasses import dataclass
from pathlib import Path

import pytest

from .util import read_text, run_install


@dataclass(frozen=True)
class AddonManifest:
    addon_key: str
    addon_class: str
    rulebook: str
    file_globs: tuple[str, ...]


def _commands_dir(config_root: Path) -> Path:
    return config_root / "commands"


def _parse_addon_manifest(path: Path) -> AddonManifest:
    text = read_text(path)

    def get_scalar(key: str) -> str:
        m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        assert m, f"Missing '{key}' in {path.name}"
        return m.group(1).strip().strip('"').strip("'")

    addon_key = get_scalar("addon_key")
    addon_class = get_scalar("addon_class")
    rulebook = get_scalar("rulebook")
    file_globs = tuple(m.group(1).strip() for m in re.finditer(r"^\s*-\s*file_glob:\s*\"?([^\"\n]+)\"?\s*$", text, flags=re.MULTILINE))
    return AddonManifest(
        addon_key=addon_key,
        addon_class=addon_class,
        rulebook=rulebook,
        file_globs=file_globs,
    )


def _repo_relpaths(repo_root: Path) -> list[str]:
    rels = []
    for p in repo_root.rglob("*"):
        if p.is_file():
            rels.append(p.relative_to(repo_root).as_posix())
    return rels


def _matches_file_globs(globs: tuple[str, ...], repo_relpaths: list[str]) -> bool:
    if not globs:
        return False
    for rel in repo_relpaths:
        for g in globs:
            candidates = [g]
            if g.startswith("**/"):
                # Pathlib/fnmatch treat this as requiring at least one directory segment;
                # signals like "**/nx.json" should also match repo-root files.
                candidates.append(g[3:])

            if any(fnmatch(rel, c) for c in candidates):
                return True
    return False


def _evaluate_addons(commands_dir: Path, repo_root: Path) -> tuple[dict[str, str], list[str], list[str]]:
    """Returns (status_by_addon, blocked_next_codes, warnings)."""
    manifests_dir = commands_dir / "profiles" / "addons"
    manifests = sorted(manifests_dir.glob("*.addon.yml"))
    assert manifests, f"No addon manifests found in {manifests_dir}"

    statuses: dict[str, str] = {}
    blocked: list[str] = []
    warnings: list[str] = []

    relpaths = _repo_relpaths(repo_root)
    for mf in manifests:
        addon = _parse_addon_manifest(mf)
        required = _matches_file_globs(addon.file_globs, relpaths)
        if not required:
            statuses[addon.addon_key] = "skipped"
            continue

        rb_path = commands_dir / "profiles" / addon.rulebook
        if rb_path.exists():
            statuses[addon.addon_key] = "loaded"
            continue

        statuses[addon.addon_key] = "missing-rulebook"
        if addon.addon_class == "required":
            blocked.append(f"BLOCKED-MISSING-ADDON:{addon.addon_key}")
        else:
            warnings.append(f"WARN-MISSING-ADDON:{addon.addon_key}")

    return statuses, blocked, warnings


@pytest.mark.e2e_governance
def test_e2e_governance_flow_required_block_then_reload_and_advisory_warn(tmp_path: Path):
    """
    End-to-end governance flow simulation:
    1) required addon missing -> BLOCKED
    2) rulebook re-added (nachladen) -> loaded and unblocked
    3) advisory addon missing -> WARN and non-blocking
    """
    config_root = tmp_path / "opencode-config-e2e"
    r = run_install(["--force", "--no-backup", "--config-root", str(config_root)])
    assert r.returncode == 0, f"install failed:\n{r.stderr}\n{r.stdout}"

    commands = _commands_dir(config_root)
    repo = tmp_path / "fake-repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Signals: Angular/Nx + Cypress
    (repo / "nx.json").write_text("{}\n", encoding="utf-8")
    (repo / "apps" / "web").mkdir(parents=True, exist_ok=True)
    (repo / "apps" / "web" / "cypress.config.ts").write_text("export default {}\n", encoding="utf-8")

    required_rb = commands / "profiles" / "rules.frontend-angular-nx-templates.md"
    advisory_rb = commands / "profiles" / "rules.frontend-cypress-testing.md"
    assert required_rb.exists(), f"Missing installed required rulebook: {required_rb}"
    assert advisory_rb.exists(), f"Missing installed advisory rulebook: {advisory_rb}"

    # Step 1: required missing -> BLOCKED
    required_backup = required_rb.with_suffix(required_rb.suffix + ".bak")
    required_rb.rename(required_backup)
    try:
        statuses, blocked, warnings = _evaluate_addons(commands, repo)
        assert statuses.get("angularNxTemplates") == "missing-rulebook"
        assert "BLOCKED-MISSING-ADDON:angularNxTemplates" in blocked
        assert not any(w.endswith(":angularNxTemplates") for w in warnings)
    finally:
        required_backup.rename(required_rb)

    # Step 2: re-evaluation after reload -> loaded + no required-block
    statuses, blocked, _warnings = _evaluate_addons(commands, repo)
    assert statuses.get("angularNxTemplates") == "loaded"
    assert "BLOCKED-MISSING-ADDON:angularNxTemplates" not in blocked

    # Step 3: advisory missing -> WARN (non-blocking)
    advisory_backup = advisory_rb.with_suffix(advisory_rb.suffix + ".bak")
    advisory_rb.rename(advisory_backup)
    try:
        statuses, blocked, warnings = _evaluate_addons(commands, repo)
        assert statuses.get("frontendCypress") == "missing-rulebook"
        assert "WARN-MISSING-ADDON:frontendCypress" in warnings
        assert "BLOCKED-MISSING-ADDON:frontendCypress" not in blocked
    finally:
        advisory_backup.rename(advisory_rb)
