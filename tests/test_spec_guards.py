from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

import pytest

from .util import REPO_ROOT, git_ls_files, read_text


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
    p = REPO_ROOT / "master.md"
    assert p.exists(), "master.md not found at repo root"

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
def test_governance_version_present_in_master_md():
    p = REPO_ROOT / "master.md"
    assert p.exists(), "master.md not found"
    head = "\n".join(read_text(p).splitlines()[:60])

    patterns = [
        r"Governance-Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)",
        r"^\s*governanceVersion:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)\s*$",
        r"^\s*governance_version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)\s*$",
    ]

    ver = None
    for pat in patterns:
        m = re.search(pat, head, flags=re.IGNORECASE | re.MULTILINE)
        if m:
            ver = m.group(1)
            break

    assert ver, "Missing governance version in master.md. Add e.g. '# Governance-Version: 1.0.0' near the top."


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
def test_start_md_fallback_paths_payload_contains_required_keys():
    p = REPO_ROOT / "start.md"
    assert p.exists(), "start.md not found at repo root"
    helper = REPO_ROOT / "diagnostics" / "start_binding_evidence.py"
    text_parts = [read_text(p)]
    if helper.exists():
        text_parts.append(read_text(helper))
    text = "\n".join(text_parts)
    required = ["configRoot", "commandsHome", "profilesHome", "diagnosticsHome", "workspacesHome"]
    missing = [k for k in required if (f"'{k}'" not in text and f'"{k}"' not in text)]
    assert not missing, f"start bootstrap fallback payload missing keys: {missing}"


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
