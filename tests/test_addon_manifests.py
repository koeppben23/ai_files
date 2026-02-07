from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, git_ls_files, read_text, run


@pytest.mark.governance
def test_addon_manifests_reference_existing_rulebooks():
    """Addon manifests are declarative; they must not point to missing rulebooks."""
    manifests = list(git_ls_files("profiles/addons/*.addon.yml"))
    assert manifests, "No addon manifests found under profiles/addons/*.addon.yml"

    missing = []
    for rel in manifests:
        p = REPO_ROOT / rel
        t = read_text(p)
        m = re.search(r"^rulebook:\s*([^\s#]+)\s*$", t, flags=re.MULTILINE)
        assert m, f"Missing 'rulebook:' field in addon manifest: {rel}"

        rb = m.group(1).strip()
        rb_path = (REPO_ROOT / "profiles" / rb) if not rb.startswith("profiles/") else (REPO_ROOT / rb)
        if not rb_path.exists():
            missing.append((rel, rb))

    assert not missing, "Addon manifests reference missing rulebooks:\n" + "\n".join(
        [f"- {m}: {rb}" for m, rb in missing]
    )


@pytest.mark.governance
def test_addon_manifests_have_addon_key():
    manifests = list(git_ls_files("profiles/addons/*.addon.yml"))
    assert manifests, "No addon manifests found under profiles/addons/*.addon.yml"

    bad = []
    for rel in manifests:
        t = read_text(REPO_ROOT / rel)
        if re.search(r"^addon_key:\s*\S+\s*$", t, flags=re.MULTILINE) is None:
            bad.append(rel)

    assert not bad, "Addon manifests missing addon_key:\n" + "\n".join([f"- {r}" for r in bad])


@pytest.mark.governance
def test_addon_manifests_have_valid_addon_class():
    manifests = list(git_ls_files("profiles/addons/*.addon.yml"))
    assert manifests, "No addon manifests found under profiles/addons/*.addon.yml"

    bad = []
    for rel in manifests:
        t = read_text(REPO_ROOT / rel)
        m = re.search(r"^addon_class:\s*(\S+)\s*$", t, flags=re.MULTILINE)
        if not m:
            bad.append(f"{rel}: missing addon_class")
            continue
        value = m.group(1).strip().strip('"').strip("'")
        if value not in {"required", "advisory"}:
            bad.append(f"{rel}: invalid addon_class={value}")

    assert not bad, "Addon manifests with invalid addon_class:\n" + "\n".join([f"- {r}" for r in bad])


@pytest.mark.governance
def test_master_addon_policy_includes_required_advisory_and_reload():
    """Pipeline guard: master must define required/advisory semantics and re-evaluation support."""
    master = read_text(REPO_ROOT / "master.md")

    required_snippets = [
        "addon_class` (`required` | `advisory`)",
        "`addon_class = required`  -> `Mode = BLOCKED` with `BLOCKED-MISSING-ADDON:<addon_key>`",
        "`addon_class = advisory` -> continue non-blocking",
        "Addons MAY be re-evaluated and loaded later at any Phase-4 re-entry/resume",
    ]

    missing = [s for s in required_snippets if s not in master]
    assert not missing, "master.md missing addon policy guarantees:\n" + "\n".join([f"- {s}" for s in missing])


@pytest.mark.governance
def test_frontend_addons_exist_and_classification_matches_policy():
    """Pipeline guard: frontend addon set supports required templates + advisory quality addons."""
    expected = {
        "profiles/addons/angularNxTemplates.addon.yml": "required",
        "profiles/addons/frontendCypress.addon.yml": "advisory",
        "profiles/addons/frontendOpenApiTsClient.addon.yml": "advisory",
    }

    problems = []
    for rel, expected_class in expected.items():
        p = REPO_ROOT / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
            continue

        text = read_text(p)
        m = re.search(r"^addon_class:\s*(\S+)\s*$", text, flags=re.MULTILINE)
        if not m:
            problems.append(f"missing addon_class: {rel}")
            continue

        value = m.group(1).strip().strip('"').strip("'")
        if value != expected_class:
            problems.append(f"{rel}: expected addon_class={expected_class}, got {value}")

    assert not problems, "Frontend addon policy mismatch:\n" + "\n".join([f"- {p}" for p in problems])


@pytest.mark.governance
def test_docs_governance_addon_exists_and_is_advisory():
    rel = "profiles/addons/docsGovernance.addon.yml"
    p = REPO_ROOT / rel
    assert p.exists(), f"missing: {rel}"

    text = read_text(p)
    m_class = re.search(r"^addon_class:\s*(\S+)\s*$", text, flags=re.MULTILINE)
    m_rulebook = re.search(r"^rulebook:\s*([^\s#]+)\s*$", text, flags=re.MULTILINE)
    assert m_class, f"missing addon_class: {rel}"
    assert m_rulebook, f"missing rulebook: {rel}"

    value = m_class.group(1).strip().strip('"').strip("'")
    assert value == "advisory", f"{rel}: expected addon_class=advisory, got {value}"

    rb = m_rulebook.group(1).strip()
    rb_path = (REPO_ROOT / "profiles" / rb) if not rb.startswith("profiles/") else (REPO_ROOT / rb)
    assert rb_path.exists(), f"rulebook does not exist: {rb}"


@pytest.mark.governance
def test_shared_principal_governance_addons_exist_and_are_advisory():
    expected = {
        "profiles/addons/principalExcellence.addon.yml": "rules.principal-excellence.md",
        "profiles/addons/riskTiering.addon.yml": "rules.risk-tiering.md",
        "profiles/addons/scorecardCalibration.addon.yml": "rules.scorecard-calibration.md",
    }

    problems = []
    for rel, expected_rulebook in expected.items():
        p = REPO_ROOT / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
            continue

        text = read_text(p)
        m_class = re.search(r"^addon_class:\s*(\S+)\s*$", text, flags=re.MULTILINE)
        m_rulebook = re.search(r"^rulebook:\s*([^\s#]+)\s*$", text, flags=re.MULTILINE)
        if not m_class:
            problems.append(f"missing addon_class: {rel}")
            continue
        if not m_rulebook:
            problems.append(f"missing rulebook: {rel}")
            continue

        value = m_class.group(1).strip().strip('"').strip("'")
        if value != "advisory":
            problems.append(f"{rel}: expected addon_class=advisory, got {value}")

        rb = m_rulebook.group(1).strip()
        if rb != expected_rulebook:
            problems.append(f"{rel}: expected rulebook={expected_rulebook}, got {rb}")
            continue

        rb_path = (REPO_ROOT / "profiles" / rb) if not rb.startswith("profiles/") else (REPO_ROOT / rb)
        if not rb_path.exists():
            problems.append(f"{rel}: missing rulebook file {rb}")

    assert not problems, "Shared principal governance addon validation failed:\n" + "\n".join(
        [f"- {p}" for p in problems]
    )


@pytest.mark.governance
def test_validate_addons_script_passes():
    script = REPO_ROOT / "scripts" / "validate_addons.py"
    assert script.exists(), f"Missing script: {script}"

    r = run([sys.executable, str(script), "--repo-root", str(REPO_ROOT)])
    assert r.returncode == 0, f"validate_addons.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"
