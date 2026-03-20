from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

import pytest

from .util import REPO_ROOT, get_master_path, git_ls_files, read_text, get_profiles_path, get_docs_path
from pathlib import Path

# Helpers to resolve paths via SSOT for tests that touch templates/docs
def _resolve_rel(rel: str) -> Path:
    if rel.startswith("profiles/"):
        return get_profiles_path() / rel[len("profiles/"):]
    if rel.startswith("docs/"):
        return get_docs_path() / rel[len("docs/"):]
    return REPO_ROOT / rel


@pytest.mark.spec
def test_no_case_only_filename_collisions_windows_safe():
    files = git_ls_files()
    buckets: dict[str, list[str]] = defaultdict(list)
    for f in files:
        p = PurePosixPath(f)
        buckets[str(p).lower()].append(str(p))

    collisions = {k: v for k, v in buckets.items() if len(v) > 1}
    assert not collisions, "Case-only filename/path collisions detected:\n" + "\n".join(
        [f"- {k}: {sorted(v)}" for k, v in sorted(collisions.items())]
    )


@pytest.mark.spec
def test_master_md_no_resolved_path_placeholder_and_variable_paths():
    p = get_master_path()
    assert p.exists(), "master.md not found"

    lines = read_text(p).splitlines()

    placeholder = "<" + "resolved path expression" + ">"
    bad = [i for i, l in enumerate(lines, start=1) if placeholder in l]
    assert not bad, "Unresolved placeholder found in master.md at lines: " + ", ".join(map(str, bad[:50]))

    pat = re.compile(r"^\s*(SourcePath|TargetPath):\s*(.+?)\s*$")
    violations = []
    for i, l in enumerate(lines, start=1):
        m = pat.match(l)
        if not m:
            continue
        val = m.group(2).strip()
        if not val or "${" not in val:
            violations.append((i, l))

    assert not violations, "Non-variable SourcePath/TargetPath entries:\n" + "\n".join(
        [f"- line {i}: {l}" for i, l in violations[:50]]
    )


@pytest.mark.spec
def test_governance_version_present_in_version_file():
    version_file = REPO_ROOT / "governance_runtime" / "VERSION"
    assert version_file.exists(), "governance_runtime/VERSION not found"

    version = version_file.read_text(encoding="utf-8").strip()
    assert version, "governance_runtime/VERSION is empty"

    semver_pattern = r"^[0-9]+\.[0-9]+\.[0-9]+"
    assert re.match(semver_pattern, version), f"Invalid semver in governance_runtime/VERSION: {version}"


@pytest.mark.spec
def test_readme_consistency_no_obsolete_opencode_refs():
    # Check both README.md and README-OPENCODE.md if present
    readmes = [REPO_ROOT / "README.md", REPO_ROOT / "README-OPENCODE.md"]
    texts = []
    for rp in readmes:
        if rp.exists():
            texts.append(read_text(rp))
    assert texts, "No README files found"

    text = "\n\n".join(texts)

    forbidden = [
        r"opencode\.template\.json",
        r"`opencode\.json`",
        r"--remove-opencode-json",
        r"--skip-opencode-json",
        r"Template \(checked in\)",
        r"optional\s+`?governanceVersion`?",
    ]
    for pat in forbidden:
        assert re.search(pat, text, flags=re.IGNORECASE) is None, f"Forbidden README reference found: {pat}"

    required = [
        r"governance\.paths\.json",
    ]
    for pat in required:
        assert re.search(pat, text, flags=re.IGNORECASE), f"README missing required reference: {pat}"


@pytest.mark.spec
def test_bootstrap_binding_payload_contains_required_keys():
    helper = REPO_ROOT / "governance_runtime" / "entrypoints" / "bootstrap_binding_evidence.py"
    text_parts = []
    if helper.exists():
        text_parts.append(read_text(helper))
    text = "\n".join(text_parts)
    required = ["configRoot", "commandsHome", "profilesHome", "governanceHome", "workspacesHome"]
    missing = [k for k in required if (f"'{k}'" not in text and f'"{k}"' not in text)]
    assert not missing, f"bootstrap binding payload missing keys: {missing}"


@pytest.mark.spec
def test_markdown_local_links_resolve_offline():
    """
    Deterministic offline check:
    - validates only relative local links in markdown: ](./foo.md) or ](docs/foo.md)
    - ignores http(s), mailto, and anchor-only links (#...)
    """
    md_files = git_ls_files("*.md")
    link_re = re.compile(r"\]\(([^)]+)\)")

    for rel in md_files:
        md = REPO_ROOT / rel
        if not md.exists():
            continue
        t = read_text(md)
        for raw in link_re.findall(t):
            raw = raw.strip()
            if not raw:
                continue
            if raw.startswith(("http://", "https://", "mailto:")):
                continue
            if raw.startswith("#"):
                continue

            target = raw.split("#", 1)[0].strip()
            if not target:
                continue

            tp = (md.parent / target).resolve()
            # only enforce in-repo targets
            try:
                tp.relative_to(REPO_ROOT.resolve())
            except ValueError:
                continue

            assert tp.exists(), f"Broken local link in {rel}: ({raw}) -> {tp}"


@pytest.mark.spec
def test_entrypoint_surface_removed_repo_wide():
    violations: list[str] = []
    for rel in git_ls_files():
        if rel.startswith("tests/"):
            continue
        path = REPO_ROOT / rel
        try:
            text = read_text(path)
        except Exception:
            continue
        if "--entrypoint" in text:
            violations.append(rel)

    assert not violations, (
        "--entrypoint surface must be fully removed outside tests:\n"
        + "\n".join(f"- {v}" for v in sorted(violations))
    )


@pytest.mark.spec
def test_launcher_contract_declares_final_surface_only():
    text = read_text(REPO_ROOT / "docs/contracts/python-binding-contract.v1.md")
    assert "--session-reader" in text
    assert "--ticket-persist" in text
    assert "--plan-persist" in text
    assert "--review-decision-persist" in text
    assert "--implement-start" in text
    assert "--entrypoint" not in text
