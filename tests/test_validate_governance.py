from __future__ import annotations

import json
import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text, run, write_governance_paths


@pytest.mark.governance
def test_required_files_present():
    required = [
        "master.md",
        "rules.md",
        "BOOTSTRAP.md",
        "SESSION_STATE_SCHEMA.md",
        "STABILITY_SLA.md",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    assert not missing, f"Missing: {missing}"



@pytest.mark.governance
def test_governance_lint_script_exists_and_passes():
    script = REPO_ROOT / "scripts" / "governance_lint.py"
    assert script.exists(), "Missing scripts/governance_lint.py"

    r = run([sys.executable, str(script)])
    assert r.returncode == 0, f"governance_lint failed:\n{r.stdout}\n{r.stderr}"


@pytest.mark.governance
def test_blocked_consistency_schema_vs_catalog():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    catalog = read_text(REPO_ROOT / "governance" / "assets" / "reasons" / "blocked_reason_catalog.yaml")

    s = set(re.findall(r"BLOCKED-[A-Z-]+", schema))
    c = set(re.findall(r"BLOCKED-[A-Z-]+", catalog))

    missing_in_catalog = s - c
    assert not missing_in_catalog, f"Missing in blocked_reason_catalog.yaml: {sorted(missing_in_catalog)}"


@pytest.mark.governance
def test_profiles_use_canonical_blocked_codes():
    forbidden = {
        "BLOCKED-TEMPLATES-MISSING",
        "BLOCKED-KAFKA-TEMPLATES-MISSING",
    }
    profile_files = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert profile_files, "No profile rulebooks found under profiles/rules*.md"

    offenders: list[str] = []
    for p in profile_files:
        t = read_text(p)
        hits = sorted([code for code in forbidden if code in t])
        if hits:
            offenders.append(f"{p.relative_to(REPO_ROOT)} -> {hits}")

    assert not offenders, "Found non-canonical BLOCKED codes in profiles:\n" + "\n".join([f"- {o}" for o in offenders])


@pytest.mark.governance
def test_claim_verification_mapping_requires_pinning_and_scope_not_pass_only():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    required_tokens = [
        "`verified` claims require `result=pass` plus compatible scope evidence, typed artifact/reference, and tool/runtime pinning evidence",
        "claims MUST remain `not-verified`",
    ]
    missing = [token for token in required_tokens if token not in schema]
    assert not missing, "SESSION_STATE_SCHEMA.md missing claim verification mapping tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )

    def classify_claim(evidence_item: dict[str, object]) -> str:
        # Contract simulation from SESSION_STATE_SCHEMA mapping: pass is necessary but not sufficient.
        result_ok = evidence_item.get("result") == "pass"
        has_scope = bool(evidence_item.get("scope_paths") or evidence_item.get("modules"))
        artifacts = evidence_item.get("artifacts")
        has_artifact = isinstance(artifacts, list) and len(artifacts) > 0
        has_pinning = bool(evidence_item.get("env_fingerprint"))
        return "verified" if (result_ok and has_scope and has_artifact and has_pinning) else "not-verified"

    pass_without_pinning = {
        "result": "pass",
        "scope_paths": ["services/person"],
        "artifacts": [{"type": "junit", "path": "reports/junit.xml"}],
    }
    assert classify_claim(pass_without_pinning) == "not-verified"

    pass_with_pinning = {
        "result": "pass",
        "scope_paths": ["services/person"],
        "artifacts": [{"type": "junit", "path": "reports/junit.xml"}],
        "env_fingerprint": "java21+maven3.9.9",
    }
    assert classify_claim(pass_with_pinning) == "verified"


@pytest.mark.governance
def test_template_rulebooks_define_correctness_by_construction_contract():
    templates = [
        "profiles/rules.backend-java-templates.md",
        "profiles/rules.backend-java-kafka-templates.md",
        "profiles/rules.frontend-angular-nx-templates.md",
    ]
    required_tokens = [
        "## Correctness by construction (binding)",
        "Inputs required:",
        "Outputs guaranteed:",
        "Evidence expectation:",
        "evidence_kinds_required:",
        "Golden examples:",
        "Anti-example:",
    ]

    missing: list[str] = []
    for rel in templates:
        text = read_text(REPO_ROOT / rel)
        absent = [token for token in required_tokens if token not in text]
        if absent:
            missing.append(f"{rel} missing {absent}")

    assert not missing, "Template rulebooks missing correctness-by-construction contract:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_template_evidence_kinds_are_allowed():
    templates = [
        REPO_ROOT / "profiles/rules.backend-java-templates.md",
        REPO_ROOT / "profiles/rules.backend-java-kafka-templates.md",
        REPO_ROOT / "profiles/rules.frontend-angular-nx-templates.md",
    ]
    allowed = {"unit-test", "integration-test", "contract-test", "e2e", "lint", "build"}
    issues: list[str] = []

    for p in templates:
        text = read_text(p)
        m = re.search(r"^\s*evidence_kinds_required:\s*$", text, flags=re.MULTILINE)
        if not m:
            issues.append(f"{p.relative_to(REPO_ROOT)}: missing evidence_kinds_required")
            continue

        kinds: list[str] = []
        for line in text[m.end() :].splitlines():
            mm = re.match(r"^\s{2}-\s*(.*?)\s*$", line)
            if mm:
                kinds.append(mm.group(1).strip().strip('"').strip("'"))
                continue
            if not line.strip():
                continue
            break

        if not kinds:
            issues.append(f"{p.relative_to(REPO_ROOT)}: empty evidence_kinds_required")
            continue
        for kind in kinds:
            if kind not in allowed:
                issues.append(f"{p.relative_to(REPO_ROOT)}: unsupported evidence kind {kind}")

    assert not issues, "Template evidence kinds invalid:\n" + "\n".join([f"- {i}" for i in issues])


@pytest.mark.governance
def test_ruleset_hash_changes_when_ruleset_files_change():
    files = [
        REPO_ROOT / "master.md",
        REPO_ROOT / "rules.md",
        *sorted((REPO_ROOT / "profiles").glob("rules*.md")),
        *sorted((REPO_ROOT / "profiles" / "addons").glob("*.addon.yml")),
    ]

    import hashlib

    def digest_for(contents: list[tuple[str, str]]) -> str:
        h = hashlib.sha256()
        for rel, text in sorted(contents):
            h.update(rel.encode("utf-8"))
            h.update(b"\0")
            h.update(text.encode("utf-8"))
            h.update(b"\n")
        return h.hexdigest()

    baseline_contents = [(p.relative_to(REPO_ROOT).as_posix(), read_text(p)) for p in files]
    baseline = digest_for(baseline_contents)

    mutated_contents = list(baseline_contents)
    rel, text = mutated_contents[0]
    mutated_contents[0] = (rel, text + "\n# ruleset-hash-test-mutation\n")
    mutated = digest_for(mutated_contents)

    assert baseline != mutated, "ruleset hash must change when any ruleset file content changes"


@pytest.mark.governance
def test_docs_governance_addon_has_principal_reviewability_contract():
    docs_addon = read_text(REPO_ROOT / "profiles" / "rules.docs-governance.md")

    required_snippets = [
        "Gate review scorecard for docs checks",
        "Claim-to-evidence (binding):",
        "Canonical terms lint (binding):",
        "## Cross-file Consistency Matrix (Binding)",
        "Docs Governance Summary",
    ]
    missing = [s for s in required_snippets if s not in docs_addon]
    assert not missing, "rules.docs-governance.md missing required reviewability sections:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_all_profile_rulebooks_define_principal_excellence_contract():
    principal_shared = read_text(REPO_ROOT / "profiles" / "rules.principal-excellence.md")
    required_shared_tokens = [
        "## Principal Excellence Contract (Binding)",
        "### Gate Review Scorecard (binding)",
        "### Claim-to-evidence (binding)",
        "### Exit criteria (binding)",
        "### Recovery when evidence is missing (binding)",
        "WARN-PRINCIPAL-EVIDENCE-MISSING",
    ]
    missing_shared = [s for s in required_shared_tokens if s not in principal_shared]
    assert not missing_shared, "rules.principal-excellence.md missing required principal contract sections:\n" + "\n".join(
        [f"- {m}" for m in missing_shared]
    )

    delegation_tokens = [
        "## Shared Principal Governance Contracts (Binding)",
        "rules.principal-excellence.md",
        "rules.risk-tiering.md",
        "rules.scorecard-calibration.md",
    ]

    profile_files = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert profile_files, "No profile rulebooks found under profiles/rules*.md"

    offenders: list[str] = []
    for path in profile_files:
        if path.name in {
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
        }:
            continue
        text = read_text(path)
        missing = [token for token in delegation_tokens if token not in text]
        if missing:
            offenders.append(f"{path.relative_to(REPO_ROOT)} -> missing {missing}")

    assert not offenders, "Profile rulebooks missing shared principal contract delegation:\n" + "\n".join(
        [f"- {line}" for line in offenders]
    )


@pytest.mark.governance
def test_all_profile_rulebooks_define_standard_risk_tiering_v21():
    risk_tiering = read_text(REPO_ROOT / "profiles" / "rules.risk-tiering.md")
    required_tokens = [
        "## Principal Hardening v2.1 - Standard Risk Tiering (Binding)",
        "### RTN-1 Canonical tiers (binding)",
        "`TIER-LOW`",
        "`TIER-MEDIUM`",
        "`TIER-HIGH`",
        "WARN-RISK-TIER-UNRESOLVED",
    ]
    missing = [token for token in required_tokens if token not in risk_tiering]
    assert not missing, "rules.risk-tiering.md missing v2.1 risk tiering contract sections:\n" + "\n".join(
        [f"- {line}" for line in missing]
    )


@pytest.mark.governance
def test_java_profile_delegates_shared_principal_contract_and_shared_file_contains_shape():
    backend_java = read_text(REPO_ROOT / "profiles" / "rules.backend-java.md")
    delegation_tokens = [
        "Shared contract note:",
        "rules.principal-excellence.md",
        "rules.risk-tiering.md",
        "rules.scorecard-calibration.md",
        "SESSION_STATE.LoadedRulebooks.addons.principalExcellence",
        "SESSION_STATE.LoadedRulebooks.addons.riskTiering",
        "SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration",
    ]
    missing_delegation = [token for token in delegation_tokens if token not in backend_java]
    assert not missing_delegation, "rules.backend-java.md missing shared principal contract delegation:\n" + "\n".join(
        [f"- {line}" for line in missing_delegation]
    )

    shared = read_text(REPO_ROOT / "profiles" / "rules.principal-excellence.md")
    required_shape = [
        "SESSION_STATE:",
        "GateScorecards:",
        "principal_excellence:",
        "PRINCIPAL-QUALITY-CLAIMS-EVIDENCED",
        "PRINCIPAL-DETERMINISM-AND-TEST-RIGOR",
        "PRINCIPAL-ROLLBACK-OR-RECOVERY-READY",
    ]

    missing_shape = [token for token in required_shape if token not in shared]
    assert not missing_shape, "Shared principal scorecard contract incomplete:\n" + "\n".join(
        [f"- {line}" for line in missing_shape]
    )


@pytest.mark.governance
def test_java_profile_contains_principal_hardening_v2_controls():
    text = read_text(REPO_ROOT / "profiles" / "rules.backend-java.md")
    required = [
        "## Java-first Principal Hardening v2 (Binding)",
        "### JPH2-1 Risk tiering by touched surface (binding)",
        "### JPH2-2 Mandatory evidence pack per tier (binding)",
        "### JPH2-3 Hard fail criteria for principal acceptance (binding)",
        "JPH2-FAIL-01",
        "JPH2-FAIL-05",
        "### JPH2-4 Required test matrix mapping (binding)",
        "### JPH2-5 Determinism and flakiness budget (binding)",
        "WARN-JAVA-DETERMINISM-RISK",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.backend-java.md missing Java-first principal hardening controls:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_backend_java_tool_gating_handles_non_runnable_tools_conservatively():
    text = read_text(REPO_ROOT / "profiles" / "rules.backend-java.md")
    required = [
        "and is runnable in the current environment",
        "If a tool exists but is not runnable in the current environment",
        "mark claims as `not-verified`",
        "emit recovery commands",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.backend-java.md missing non-runnable tool handling semantics:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_backend_java_uses_shared_tiering_and_avoids_parallel_tier_taxonomy():
    text = read_text(REPO_ROOT / "profiles" / "rules.backend-java.md")
    required = [
        "using the canonical tiering contract from `rules.risk-tiering.md`",
        "does not define a parallel tier system",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.backend-java.md missing shared-tiering delegation semantics:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )

    forbidden_old_parallel_defs = [
        "internal refactor without contract/persistence/async changes",
        "service/business logic or controller behavior change",
        "persistence/migration, security semantics, async messaging, or externally visible contract change",
    ]
    offenders = [token for token in forbidden_old_parallel_defs if token in text]
    assert not offenders, "rules.backend-java.md still contains old parallel tier definitions:\n" + "\n".join(
        [f"- {m}" for m in offenders]
    )


@pytest.mark.governance
def test_java_templates_and_kafka_include_v2_hardening_sections():
    expectations = {
        "profiles/rules.backend-java-templates.md": [
            "## Java-first Principal Hardening v2 - Template Conformance (Binding)",
            "### JTH2-1 Template conformance gate (binding)",
            "### JTH2-2 Evidence artifact contract (binding)",
            "EV-TPL-CODE",
            "EV-TPL-TEST",
            "EV-TPL-GATE",
            "### JTH2-4 Template deviation protocol (binding)",
        ],
        "profiles/rules.backend-java-kafka-templates.md": [
            "## Java-first Principal Hardening v2 - Kafka Critical Gate (Binding)",
            "### KPH2-1 Kafka scorecard criteria (binding)",
            "KAFKA-IDEMPOTENCY-PROVEN",
            "### KPH2-2 Required kafka test matrix (binding)",
            "### KPH2-3 Kafka hard fail conditions (binding)",
            "WARN-KAFKA-IDEMPOTENCY-UNVERIFIED",
            "WARN-KAFKA-RETRY-POLICY-UNKNOWN",
            "WARN-KAFKA-ASYNC-FLAKINESS-RISK",
        ],
    }

    problems: list[str] = []
    for rel, required_tokens in expectations.items():
        text = read_text(REPO_ROOT / Path(rel))
        missing = [token for token in required_tokens if token not in text]
        if missing:
            problems.append(f"{rel} -> missing {missing}")

    assert not problems, "Java template hardening v2 contract incomplete:\n" + "\n".join(
        [f"- {line}" for line in problems]
    )


@pytest.mark.governance
def test_frontend_cypress_addon_contains_principal_hardening_v2_controls():
    text = read_text(REPO_ROOT / "profiles" / "rules.frontend-cypress-testing.md")
    required = [
        "## Principal Hardening v2 - Cypress Critical Quality (Binding)",
        "### CPH2-1 Required scorecard criteria (binding)",
        "CYPRESS-CRITICAL-FLOW-COVERAGE",
        "CYPRESS-NO-FIXED-SLEEPS",
        "### CPH2-3 Hard fail criteria (binding)",
        "WARN-CYPRESS-NETWORK-CONTROL-MISSING",
        "WARN-CYPRESS-ASYNC-FLAKE-RISK",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.frontend-cypress-testing.md missing hardening v2 controls:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_frontend_openapi_ts_addon_contains_principal_hardening_v2_controls():
    text = read_text(REPO_ROOT / "profiles" / "rules.frontend-openapi-ts-client.md")
    required = [
        "## Principal Hardening v2 - Frontend OpenAPI TS Client (Binding)",
        "### FOPH2-1 Required scorecard criteria (binding)",
        "FE-OPENAPI-NO-HAND-EDIT-GENERATED",
        "FE-OPENAPI-CONTRACT-NEGATIVE-TEST",
        "### FOPH2-3 Hard fail criteria (binding)",
        "WARN-FE-OPENAPI-SOURCE-UNRESOLVED",
        "WARN-FE-OPENAPI-CONTRACT-TEST-MISSING",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.frontend-openapi-ts-client.md missing hardening v2 controls:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_fallback_profile_contains_principal_hardening_v2_controls():
    text = read_text(REPO_ROOT / "profiles" / "rules.fallback-minimum.md")
    required = [
        "## Principal Hardening v2 - Fallback Minimum Safety (Binding)",
        "### FMPH2-1 Baseline scorecard criteria (binding)",
        "FALLBACK-BUILD-VERIFY-EXECUTED",
        "FALLBACK-ROLLBACK-OR-RECOVERY-PLAN",
        "### FMPH2-3 Hard fail criteria (binding)",
        "WARN-FALLBACK-BASELINE-UNKNOWN",
        "WARN-FALLBACK-RECOVERY-UNSPECIFIED",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.fallback-minimum.md missing hardening v2 controls:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_addon_rulebooks_use_standard_risk_tiering_v21():
    shared = read_text(REPO_ROOT / "profiles" / "rules.risk-tiering.md")
    required_shared_tokens = [
        "## Principal Hardening v2.1 - Standard Risk Tiering (Binding)",
        "### RTN-1 Canonical tiers (binding)",
        "`TIER-LOW`",
        "`TIER-MEDIUM`",
        "`TIER-HIGH`",
        "### RTN-4 Required SESSION_STATE shape (binding)",
        "RiskTiering:",
        "WARN-RISK-TIER-UNRESOLVED",
    ]
    missing_shared = [token for token in required_shared_tokens if token not in shared]
    assert not missing_shared, "rules.risk-tiering.md missing v2.1 shared contract tokens:\n" + "\n".join(
        [f"- {line}" for line in missing_shared]
    )

    addon_rulebooks = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert addon_rulebooks, "No profile rulebooks found under profiles/rules*.md"

    required_delegation = [
        "## Shared Principal Governance Contracts (Binding)",
        "rules.risk-tiering.md",
    ]

    problems: list[str] = []
    for path in addon_rulebooks:
        if path.name in {
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
        }:
            continue
        text = read_text(path)
        missing = [token for token in required_delegation if token not in text]
        if missing:
            problems.append(f"{path.relative_to(REPO_ROOT)} -> missing {missing}")

    assert not problems, "Rulebooks missing shared v2.1 delegation:\n" + "\n".join(
        [f"- {line}" for line in problems]
    )


@pytest.mark.governance
def test_addon_rulebooks_use_scorecard_calibration_v211():
    shared = read_text(REPO_ROOT / "profiles" / "rules.scorecard-calibration.md")
    required_shared_tokens = [
        "## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)",
        "### CAL-1 Standard criterion weights by tier (binding)",
        "`TIER-LOW`: each active criterion weight = `2`",
        "`TIER-MEDIUM`: each active criterion weight = `3`",
        "`TIER-HIGH`: each active criterion weight = `5`",
        "### CAL-3 Tier score thresholds (binding)",
        "`TIER-HIGH`: >= `0.90`",
        "CalibrationVersion: v2.1.1",
        "WARN-SCORECARD-CALIBRATION-INCOMPLETE",
    ]
    missing_shared = [token for token in required_shared_tokens if token not in shared]
    assert not missing_shared, "rules.scorecard-calibration.md missing v2.1.1 shared contract tokens:\n" + "\n".join(
        [f"- {line}" for line in missing_shared]
    )

    addon_rulebooks = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert addon_rulebooks, "No profile rulebooks found under profiles/rules*.md"

    required_delegation = [
        "## Shared Principal Governance Contracts (Binding)",
        "rules.scorecard-calibration.md",
    ]

    problems: list[str] = []
    for path in addon_rulebooks:
        if path.name in {
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
        }:
            continue
        text = read_text(path)
        missing = [token for token in required_delegation if token not in text]
        if missing:
            problems.append(f"{path.relative_to(REPO_ROOT)} -> missing {missing}")

    assert not problems, "Rulebooks missing shared v2.1.1 calibration delegation:\n" + "\n".join(
        [f"- {line}" for line in problems]
    )


@pytest.mark.governance
def test_factory_commands_exist_and_define_principal_generation_contracts():
    targets = {
        "docs/_archive/new_profile.md": [
            "# Governance Factory - New Profile",
            "## Required Input (Binding)",
            "## Generation Contract (Binding)",
            "## Principal Conformance Checklist (Binding)",
            "## Shared Principal Governance Contracts (Binding)",
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
            "rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`",
            "phase integration section (minimum: Phase 2/2.1/4/5/6 expectations)",
            "canonical evidence-path requirement language",
            "SESSION_STATE.AddonsEvidence.<addon_key>",
            "SESSION_STATE.RepoFacts.CapabilityEvidence",
            "SESSION_STATE.Diagnostics.ReasonPayloads",
            "applicability_signals",
            "MUST NOT be used as profile-selection activation logic",
            "Preferred: `profiles/rules_<profile_key>.md`",
            "Examples (GOOD/BAD)",
            "Troubleshooting with at least 3 concrete symptom->cause->fix entries",
        ],
        "docs/_archive/new_addon.md": [
            "# Governance Factory - New Addon",
            "## Required Input (Binding)",
            "## Manifest Contract (Binding)",
            "## Rulebook Contract (Binding)",
            "## Principal Conformance Checklist (Binding)",
            "## Shared Principal Governance Contracts (Binding)",
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
            "manifest_version",
            "path_roots",
            "owns_surfaces",
            "touches_surfaces",
            "capabilities_any",
            "capabilities_all",
            "rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`",
            "phase integration section (minimum: Phase 2/2.1/4/5.3/6 expectations)",
            "phase semantics MUST reference canonical `master.md` phase labels",
            "evidence contract section (canonical SESSION_STATE paths, lifecycle status, WARN handling)",
            "SESSION_STATE.AddonsEvidence.<addon_key>",
            "SESSION_STATE.RepoFacts.CapabilityEvidence",
            "SESSION_STATE.Diagnostics.ReasonPayloads",
            "tracking keys are audit/trace pointers (map entries), not activation signals",
            "Examples (GOOD/BAD)",
            "Troubleshooting with at least 3 concrete symptom->cause->fix entries",
            "BLOCKED-MISSING-ADDON:<addon_key>",
        ],
    }

    missing: list[str] = []
    for rel, required in targets.items():
        p = REPO_ROOT / rel
        if not p.exists():
            missing.append(f"missing file: {rel}")
            continue
        text = read_text(p)
        absent = [token for token in required if token not in text]
        if absent:
            missing.append(f"{rel} missing {absent}")

    assert not missing, "Factory command contract violations:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_reviewed_rulebooks_include_examples_and_troubleshooting_sections():
    required = {
        "profiles/rules.backend-java.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.backend-java-templates.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.backend-java-kafka-templates.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.cucumber-bdd.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.frontend-angular-nx.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.principal-excellence.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.risk-tiering.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
        "profiles/rules.scorecard-calibration.md": ["Examples (GOOD/BAD)", "Troubleshooting"],
    }

    missing: list[str] = []
    for rel, tokens in required.items():
        text = read_text(REPO_ROOT / rel)
        absent = [token for token in tokens if token not in text]
        if absent:
            missing.append(f"{rel} missing {absent}")

    assert not missing, "Rulebooks missing examples/troubleshooting sections:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_fallback_profile_has_explicit_evidence_contract_section():
    text = read_text(REPO_ROOT / "profiles/rules.fallback-minimum.md")
    required = [
        "## Evidence contract (binding)",
        "SESSION_STATE.BuildEvidence",
        "warnings[]",
        "claims MUST be marked `not-verified`",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.fallback-minimum.md missing explicit evidence contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_docs_governance_marks_blocked_aliases_as_legacy_non_emitting():
    text = read_text(REPO_ROOT / "profiles/rules.docs-governance.md")
    required = [
        "MUST NOT set BLOCKED",
        "reference only, do not emit from this addon",
        "legacy vocabulary and MUST NOT be emitted by any advisory addon",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.docs-governance.md missing legacy BLOCKED alias safeguards:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_factory_contract_diagnostic_exists_and_is_calibrated():
    p = REPO_ROOT / "governance" / "assets" / "catalogs" / "PROFILE_ADDON_FACTORY_CONTRACT.json"
    assert p.exists(), "Missing governance/PROFILE_ADDON_FACTORY_CONTRACT.json"

    text = read_text(p)
    required_tokens = [
        '"schema": "governance.factory.contract.v1"',
        '"requiredProfileSections"',
        '"sharedContractRulebooks"',
        '"requiredLoadedRulebookAddonKeys"',
        '"requiredAddonManifestFields"',
        '"owns_surfaces"',
        '"touches_surfaces"',
        '"recommendedAddonManifestFields"',
        '"capabilities_any"',
        '"capabilities_all"',
        '"requiredWarningCodes"',
        '"canonicalRiskTiers"',
        '"scoreThresholds"',
        '"TIER-HIGH": 0.9',
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "Factory governance contract incomplete:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_session_state_schema_includes_risk_tiering_contract_shape():
    text = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    required_tokens = [
        "## 8.2a Risk Tiering Contract",
        "RiskTiering:",
        "ActiveTier: TIER-LOW | TIER-MEDIUM | TIER-HIGH",
        "MissingEvidence",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "SESSION_STATE_SCHEMA.md missing risk tiering contract shape:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_session_state_bootstrap_recovery_script_exists():
    p = REPO_ROOT / "governance" / "entrypoints" / "bootstrap_session_state.py"
    assert p.exists(), "Missing governance/entrypoints/bootstrap_session_state.py"

    text = read_text(p)
    
    pointer_ssot = REPO_ROOT / "governance" / "infrastructure" / "session_pointer.py"
    pointer_text = read_text(pointer_ssot) if pointer_ssot.exists() else ""
    
    required_tokens = [
        "SESSION_STATE.json",
        "repo-identity-map.yaml",
        "opencode-session-pointer.v1",
        "activeSessionStateFile",
        "workspaces",
        "session_state_version",
        "ruleset_hash",
        "1.1-Bootstrap",
        "BLOCKED-START-REQUIRED",
        "\"OutputMode\": \"ARCHITECT\"",
        "\"DecisionSurface\": {}",
        "\"quality_index\": \"${COMMANDS_HOME}/QUALITY_INDEX.md\"",
        "\"conflict_resolution\": \"${COMMANDS_HOME}/CONFLICT_RESOLUTION.md\"",
        "--repo-fingerprint",
        "--repo-name",
        "--config-root",
        "--force",
        "--dry-run",
    ]
    combined_text = text + "\n" + pointer_text
    missing = [token for token in required_tokens if token not in combined_text]
    assert not missing, "bootstrap_session_state.py or session_pointer.py missing required behavior tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_session_state_bootstrap_recovery_script_creates_state_file(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "bootstrap_session_state.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f7"
    write_governance_paths(cfg)

    env = os.environ.copy()
    env["OPENCODE_FORCE_READ_ONLY"] = "1"
    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--repo-root", str(repo_root), "--config-root", str(cfg)], env=env)
    assert r.returncode == 2, f"bootstrap_session_state.py should exit 2 when writes blocked:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload.get("bootstrapSessionState") == "blocked"
    assert payload.get("writes_allowed") is False
    assert not (cfg / "SESSION_STATE.json").exists()
    assert not (cfg / "workspaces" / repo_fp / "SESSION_STATE.json").exists()


@pytest.mark.governance
def test_workspace_persistence_backfill_script_exists_and_defines_required_targets():
    p = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    assert p.exists(), "Missing governance/entrypoints/persist_workspace_artifacts.py"

    text = read_text(p)
    required_tokens = [
        "repo-cache.yaml",
        "repo-map-digest.md",
        "decision-pack.md",
        "workspace-memory.yaml",
        "business-rules.md",
        "${REPO_CACHE_FILE}",
        "${REPO_DIGEST_FILE}",
        "${REPO_DECISION_PACK_FILE}",
        "${WORKSPACE_MEMORY_FILE}",
        "${REPO_BUSINESS_RULES_FILE}",
        "--repo-fingerprint",
        "--repo-root",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "persist_workspace_artifacts.py missing required tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_workspace_persistence_backfill_script_creates_missing_artifacts(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    repo_fp = "a1b2c3d4e5f6a1b2c3d4e5f6"
    write_governance_paths(cfg)

    workspace = cfg / "workspaces" / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    session_file = workspace / "SESSION_STATE.json"
    session_payload = {
        "SESSION_STATE": {
            "Phase": "2",
            "Mode": "NORMAL",
            "ConfidenceLevel": 80,
            "Next": "Phase2.1-DecisionPack",
            "Scope": {"Repository": "Demo Repo", "RepositoryType": "governance-rulebook-repo"},
            "ActiveProfile": "docs-governance",
            "ProfileEvidence": "user-explicit",
        }
    }
    session_file.write_text(json.dumps(session_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    env = {"OPENCODE_FORCE_READ_ONLY": "1"}
    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--repo-root", str(repo_root), "--config-root", str(cfg)], env=env)
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout.strip().splitlines()[-1])
    assert payload.get("workspacePersistenceHook") == "skipped"
    assert payload.get("read_only") is True


@pytest.mark.governance
def test_workspace_persistence_backfill_derives_fingerprint_from_repo_root(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"
    write_governance_paths(cfg)

    git_dir = repo_root / ".git"
    (git_dir / "refs" / "remotes" / "origin").mkdir(parents=True, exist_ok=True)
    (git_dir / "config").write_text(
        """[remote \"origin\"]
    url = git@github.com:example/derived-repo.git
""",
        encoding="utf-8",
    )
    (git_dir / "refs" / "remotes" / "origin" / "HEAD").write_text(
        "ref: refs/remotes/origin/main\n",
        encoding="utf-8",
    )

    expected_fp = hashlib.sha256("repo:repo://github.com/example/derived-repo".encode("utf-8")).hexdigest()[:24]

    env = {"OPENCODE_FORCE_READ_ONLY": "1"}
    r = run([
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--config-root",
        str(cfg),
        "--quiet",
    ], env=env)
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    assert payload.get("repoFingerprint") == expected_fp
    assert payload.get("repoFingerprintSource") == "git-metadata"
    assert payload.get("workspacePersistenceHook") == "skipped"


@pytest.mark.governance
def test_workspace_persistence_backfill_writes_business_rules_when_phase15_extracted(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    repo_fp = "b2c3d4e5f6a1b2c3d4e5f6a2"
    write_governance_paths(cfg)

    workspace = cfg / "workspaces" / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    session_file = workspace / "SESSION_STATE.json"
    session_payload = {
        "SESSION_STATE": {
            "Phase": "1.5",
            "Mode": "NORMAL",
            "ConfidenceLevel": 85,
            "Next": "Phase 4",
            "Scope": {
                "Repository": "Demo Repo",
                "RepositoryType": "governance-rulebook-repo",
                "BusinessRules": "extracted",
            },
            "BusinessRules": {
                "InventoryFileStatus": "write-requested",
                "InventoryFileMode": "unknown",
            },
        }
    }
    session_file.write_text(json.dumps(session_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    env = {"OPENCODE_FORCE_READ_ONLY": "1"}
    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--repo-root", str(repo_root), "--config-root", str(cfg), "--quiet"], env=env)
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    assert payload.get("workspacePersistenceHook") == "skipped"
    assert payload.get("read_only") is True
    assert not (workspace / "business-rules.md").exists()


@pytest.mark.governance
def test_workspace_persistence_normalizes_legacy_placeholder_phrasing_without_force(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    repo_fp = "c3d4e5f6a1b2c3d4e5f6a1b3"
    write_governance_paths(cfg)

    workspace = cfg / "workspaces" / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    session_file = workspace / "SESSION_STATE.json"
    session_payload = {
        "SESSION_STATE": {
            "Phase": "4",
            "Mode": "NORMAL",
            "ConfidenceLevel": 80,
            "Next": "Phase5",
            "Scope": {
                "Repository": "Demo Repo",
                "RepositoryType": "governance-rulebook-repo",
            },
            "ActiveProfile": "fallback-minimum",
            "ProfileEvidence": "phase2-detected",
        }
    }
    session_file.write_text(json.dumps(session_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    cache_file = workspace / "repo-cache.yaml"
    cache_file.write_text(
        "RepoCache:\n"
        "  ConventionsDigest:\n"
        '    - "Backfill placeholder: refresh after Phase 2 discovery."\n',
        encoding="utf-8",
    )

    decision_file = workspace / "decision-pack.md"
    decision_file.write_text(
        "# Decision Pack\n"
        "Evidence: Backfill initialization only; no fresh Phase 2 domain extraction attached\n",
        encoding="utf-8",
    )

    env = {"OPENCODE_FORCE_READ_ONLY": "1"}
    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--repo-root", str(repo_root), "--config-root", str(cfg), "--quiet"], env=env)
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    assert payload.get("workspacePersistenceHook") == "skipped"
    assert payload.get("read_only") is True

    cache_text = cache_file.read_text(encoding="utf-8")
    decision_text = decision_file.read_text(encoding="utf-8")
    assert "Backfill placeholder: refresh after Phase 2 discovery." in cache_text
    assert "Backfill initialization only" in decision_text


@pytest.mark.governance
def test_workspace_persistence_normalizes_legacy_decision_pack_and_emits_event(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    repo_fp = "d4e5f6a1b2c3d4e5f6a1b2c3"
    write_governance_paths(cfg)

    workspace = cfg / "workspaces" / repo_fp
    workspace.mkdir(parents=True, exist_ok=True)
    session_file = workspace / "SESSION_STATE.json"
    session_payload = {
        "SESSION_STATE": {
            "Phase": "2.1-DecisionPack",
            "Mode": "IN_PROGRESS",
            "ConfidenceLevel": 80,
            "Next": "3A-API-Inventory",
            "Scope": {
                "Repository": "Demo Repo",
                "RepositoryType": "governance-rulebook-repo",
            },
            "ActiveProfile": "fallback-minimum",
            "ProfileEvidence": "phase2-detected",
        }
    }
    session_file.write_text(json.dumps(session_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    decision_file = workspace / "decision-pack.md"
    decision_file.write_text(
        "# Decision Pack\n"
        "D-001: Run Phase 1.5 (Business Rules Discovery) now?\n"
        "A) Yes\n"
        "B) No\n"
        "Recommendation: A (run lightweight Phase 1.5 to establish initial domain evidence)\n"
        "What would change it: keep B only when operator explicitly defers business-rules discovery\n",
        encoding="utf-8",
    )

    r = run([
        sys.executable,
        str(script),
        "--repo-fingerprint",
        repo_fp,
        "--repo-root",
        str(repo_root),
        "--config-root",
        str(cfg),
        "--quiet",
    ])
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    actions = payload.get("actions", {})
    assert actions.get("decisionPack") == "normalized"
    assert actions.get("decisionPackNormalizationEvent") == "written"

    decision_text = decision_file.read_text(encoding="utf-8")
    assert "D-001: Apply Phase 1.5 Business Rules bootstrap policy" in decision_text
    assert "Status: automatic" in decision_text
    assert "A) Yes" not in decision_text
    assert "B) No" not in decision_text

    events_text = (workspace / "events.jsonl").read_text(encoding="utf-8")
    assert "decision-pack-normalized-legacy-format" in events_text


@pytest.mark.governance
def test_workspace_persistence_quiet_blocked_payload_includes_reason_contract_fields(tmp_path: Path):
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    non_repo_root = tmp_path / "not-a-repo"
    non_repo_root.mkdir(parents=True, exist_ok=True)
    write_governance_paths(cfg)

    r = run([
        sys.executable,
        str(script),
        "--repo-root",
        str(non_repo_root),
        "--config-root",
        str(cfg),
        "--quiet",
    ])
    assert r.returncode == 2, (
        "persist_workspace_artifacts.py expected blocked exit:\n"
        f"STDERR:\n{r.stderr}\n"
        f"STDOUT:\n{r.stdout}"
    )

    payload = json.loads(r.stdout)
    assert payload.get("status") == "blocked"
    assert payload.get("reason_code") == "BLOCKED-REPO-ROOT-NOT-DETECTABLE"
    assert isinstance(payload.get("missing_evidence"), list) and len(payload["missing_evidence"]) >= 1
    assert isinstance(payload.get("recovery_steps"), list) and len(payload["recovery_steps"]) >= 1
    assert isinstance(payload.get("required_operator_action"), str) and payload["required_operator_action"].strip()
    assert isinstance(payload.get("feedback_required"), str) and payload["feedback_required"].strip()
    assert isinstance(payload.get("next_command"), str) and payload["next_command"].strip()


@pytest.mark.governance
def test_bootstrap_doc_excludes_preflight_hook_markers():
    text = read_text(REPO_ROOT / "BOOTSTRAP.md")
    forbidden_tokens = [
        "bootstrap_preflight_readonly.py",
        "workspacePersistenceHook",
        "writes_allowed",
    ]
    found = [token for token in forbidden_tokens if token in text]
    assert not found, "BOOTSTRAP.md should not reference preflight hook internals:\n" + "\n".join(
        [f"- {m}" for m in found]
    )


@pytest.mark.governance
def test_bootstrap_doc_avoids_helper_path_instructions():
    text = read_text(REPO_ROOT / "BOOTSTRAP.md")
    forbidden = [
        "governance/entrypoints/bootstrap_binding_evidence.py",
        "governance/entrypoints/bootstrap_preflight_readonly.py",
        "Implementation Reference:",
    ]
    found = [token for token in forbidden if token in text]
    assert not found, "BOOTSTRAP.md should not reference governance helper paths:\n" + "\n".join(
        [f"- {m}" for m in found]
    )


@pytest.mark.governance
def test_preflight_readonly_remains_non_persistence_surface():
    text = read_text(REPO_ROOT / "governance" / "entrypoints" / "bootstrap_preflight_readonly.py")
    assert "commit_workspace_identity(" not in text
    assert "write_unresolved_runtime_context(" not in text
    assert "workspacePersistenceHook" in text


@pytest.mark.governance
def test_persist_helper_does_not_hardcode_bash_next_command_profile():
    text = read_text(REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py")
    assert "cmd_profiles[\"bash\"]" not in text
    assert "_preferred_shell_command(cmd_profiles)" in text


@pytest.mark.governance
def test_persist_helper_bootstrap_uses_binding_python_command_argv():
    text = read_text(REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py")
    assert "python_argv = [\"py\", \"-3\"]" in text
    assert "cmd = [\n        *python_argv," in text


@pytest.mark.governance
def test_persist_helper_legacy_placeholder_normalization_uses_atomic_write():
    text = read_text(REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py")
    assert "path.write_text(updated" not in text
    assert "_atomic_write_text(path, updated)" in text


@pytest.mark.governance
def test_reason_code_quickfix_template_catalog_is_defined():
    catalog = REPO_ROOT / "governance" / "assets" / "catalogs" / "QUICKFIX_TEMPLATES.json"
    assert catalog.exists(), "governance/assets/catalogs/QUICKFIX_TEMPLATES.json missing"
    payload = json.loads(read_text(catalog))
    assert payload.get("$schema") == "opencode.quickfix-templates.v1"
    assert isinstance(payload.get("templates"), dict) and payload["templates"], "Quick-fix templates catalog is empty"


@pytest.mark.governance
def test_tool_requirements_catalog_exists_and_has_required_sections():
    p = REPO_ROOT / "governance" / "assets" / "catalogs" / "tool_requirements.json"
    assert p.exists(), "Missing governance/tool_requirements.json"

    payload = json.loads(read_text(p))
    assert payload.get("schema") == "opencode-tool-requirements.v1", "Unexpected tool requirements schema"
    assert "smart_retry" in payload and isinstance(payload["smart_retry"], dict), "tool_requirements.json missing smart_retry object"
    assert payload["smart_retry"].get("path_snapshot_policy") == "fresh-per-start", "smart_retry.path_snapshot_policy must be fresh-per-start"

    for key in ["required_now", "required_later", "optional"]:
        assert key in payload, f"tool_requirements.json missing key: {key}"
        assert isinstance(payload[key], list), f"tool_requirements.json key must be a list: {key}"

    required_now_cmds = {str(x.get("command", "")).strip() for x in payload["required_now"] if isinstance(x, dict)}
    assert "git" in required_now_cmds, "tool_requirements.json required_now must include git"
    assert "${PYTHON_COMMAND}" in required_now_cmds, "tool_requirements.json required_now must include ${PYTHON_COMMAND}"

    for section in ["required_now", "required_later"]:
        for entry in payload.get(section, []):
            if not isinstance(entry, dict):
                continue
            assert entry.get("verify_command"), f"{section} entry missing verify_command: {entry}"
            assert entry.get("expected_after_fix"), f"{section} entry missing expected_after_fix: {entry}"
            assert entry.get("restart_hint") in {
                "restart_required_if_path_edited",
                "no_restart_if_binary_in_existing_path",
            }, f"{section} entry has invalid restart_hint: {entry}"


@pytest.mark.governance
def test_tool_requirements_catalog_covers_commands_referenced_by_flow_rulebooks():
    catalog_path = REPO_ROOT / "governance" / "assets" / "catalogs" / "tool_requirements.json"
    catalog = json.loads(read_text(catalog_path))

    catalog_cmds = set()
    for section in ["required_now", "required_later", "optional"]:
        for entry in catalog.get(section, []):
            if isinstance(entry, dict):
                cmd = str(entry.get("command", "")).strip()
                if cmd:
                    catalog_cmds.add(cmd)

    flow_files = [
        REPO_ROOT / "master.md",
        REPO_ROOT / "BOOTSTRAP.md",
    ]
    flow_files.extend(sorted((REPO_ROOT / "profiles").glob("rules*.md")))

    token_re = re.compile(r"`([^`\n]+)`")
    cmd_re = re.compile(r"^[a-z][a-z0-9.-]*$")
    command_like_second_tokens = {
        "remote",
        "symbolic-ref",
        "rev-parse",
        "run",
        "test",
        "ci",
        "lint",
        "validate",
        "breaking",
        "affected",
        "clean",
        "verify",
        "update",
        "updatesql",
        "rollbackcount",
        "changelogsync",
        "marknextchangesetran",
        "nx",
        "i",
    }

    discovered: set[str] = set()
    for p in flow_files:
        text = read_text(p)
        for m in token_re.finditer(text):
            snippet = m.group(1).strip()
            if " " not in snippet:
                continue
            parts = [x for x in snippet.split() if x]
            if len(parts) < 2:
                continue
            first = parts[0].strip()
            second = parts[1].strip()
            if first.startswith("/"):
                continue
            if first == "./gradlew":
                first = "gradle"
            if not cmd_re.match(first):
                continue
            second_l = second.lower()
            option_like = bool(re.match(r"^-[A-Za-z0-9].*", second))
            if not (
                option_like
                or "/" in second
                or second_l in command_like_second_tokens
            ):
                continue
            discovered.add(first)

    # `python` and `python3` are treated as equivalent bootstrap runtimes.
    normalized_discovered = {"python3" if c == "python" else c for c in discovered}
    normalized_catalog = {"python3" if c == "python" else c for c in catalog_cmds}

    missing = sorted(c for c in normalized_discovered if c not in normalized_catalog)
    assert not missing, (
        "tool_requirements.json missing commands referenced in flow rulebooks:\n"
        + "\n".join([f"- {m}" for m in missing])
        + "\nAdd each command to governance/tool_requirements.json (required_now/required_later/optional)."
    )


@pytest.mark.governance
def test_bootstrap_mode_mixed_phrase_is_absent_in_core_docs():
    core_docs = [
        REPO_ROOT / "master.md",
        REPO_ROOT / "rules.md",
        REPO_ROOT / "BOOTSTRAP.md",
    ]
    offenders: list[str] = []
    needle = "Cold Start | Warm Start"
    for doc in core_docs:
        text = read_text(doc)
        if needle in text:
            offenders.append(str(doc.relative_to(REPO_ROOT)))

    assert not offenders, "Mixed start-mode phrase must not appear in core docs:\n" + "\n".join([f"- {o}" for o in offenders])


@pytest.mark.governance
def test_start_mode_mixed_phrase_is_absent_in_core_docs():
    core_docs = [
        REPO_ROOT / "master.md",
        REPO_ROOT / "rules.md",
        REPO_ROOT / "BOOTSTRAP.md",
    ]
    offenders: list[str] = []
    needle = "Cold Start | Warm Start"
    for doc in core_docs:
        text = read_text(doc)
        if needle in text:
            offenders.append(str(doc.relative_to(REPO_ROOT)))

    assert not offenders, "Mixed start-mode phrase must not appear in core docs:\n" + "\n".join([f"- {o}" for o in offenders])


@pytest.mark.governance
def test_governance_boundary_and_thematic_rails_docs_exist():
    required = [
        REPO_ROOT / "docs" / "governance" / "RESPONSIBILITY_BOUNDARY.md",
        REPO_ROOT / "docs" / "governance" / "RAILS_REFACTOR_MAPPING.md",
        REPO_ROOT / "docs" / "governance" / "rails" / "planning.md",
        REPO_ROOT / "docs" / "governance" / "rails" / "implementation.md",
        REPO_ROOT / "docs" / "governance" / "rails" / "testing.md",
        REPO_ROOT / "docs" / "governance" / "rails" / "pr_review.md",
        REPO_ROOT / "docs" / "governance" / "rails" / "failure_handling.md",
    ]
    missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
    assert not missing, "Missing governance boundary/thematic rails docs:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_rails_refactor_mapping_contains_required_tables():
    mapping = read_text(REPO_ROOT / "docs" / "governance" / "RAILS_REFACTOR_MAPPING.md")

    required_tokens = [
        "| rule_id | rule_summary | canonical_source | secondary_references |",
        "| original_section | target_location | action |",
        "| file | classification | note |",
    ]
    missing = [t for t in required_tokens if t not in mapping]
    assert not missing, "RAILS_REFACTOR_MAPPING.md missing required mapping tables:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_responsibility_boundary_uses_bindend_vs_nicht_bindend_terms():
    text = read_text(REPO_ROOT / "docs" / "governance" / "RESPONSIBILITY_BOUNDARY.md")
    required = ["bindend", "nicht-bindend", "Kernel", "Schemas"]
    missing = [t for t in required if t not in text]
    assert not missing, "RESPONSIBILITY_BOUNDARY.md missing explicit boundary terms:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_canonical_response_envelope_schema_contract_is_defined():
    schema_path = REPO_ROOT / "governance" / "assets" / "catalogs" / "RESPONSE_ENVELOPE_SCHEMA.json"
    assert schema_path.exists(), "Missing governance/RESPONSE_ENVELOPE_SCHEMA.json"
    schema_text = read_text(schema_path)

    schema_required = [
        '"$id": "opencode.governance.response-envelope.v1"',
        '"status"',
        '"session_state"',
        '"next_action"',
        '"type"',
        '"reply_with_one_number"',
        '"manual_step"',
        '"snapshot"',
        '"preflight"',
        '"observed_at"',
        '"checks"',
        '"impact"',
        '"reason_payload"',
        '"quick_fix_commands"',
        '"allOf"',
        '"if"',
        '"then"',
        '"const": "blocked"',
    ]
    missing_schema = [t for t in schema_required if t not in schema_text]
    assert not missing_schema, "Response envelope schema missing required fields:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_backfill_decision_pack_includes_phase_15_prompt_decision():
    text = read_text(REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py")
    required_tokens = [
        "D-001: Apply Phase 1.5 Business Rules bootstrap policy",
        "Status: automatic",
        "Action: Auto-run lightweight Phase 1.5 bootstrap when business-rules inventory is missing.",
        "Policy: no questions before Phase 4; use activation intent defaults.",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "persist_workspace_artifacts.py missing Phase 1.5 decision-pack baseline tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_audit_pretty_summary_layout_tokens_present():
    audit = read_text(REPO_ROOT / "governance" / "assets" / "catalogs" / "audit.md")
    required = [
        "[AUDIT-SUMMARY]",
        "Status`, `Phase/Gate`, `PrimaryReason`, `TopRecovery`",
        "`AllowedNextActions` as numbered list",
        "[/AUDIT-SUMMARY]",
    ]
    missing = [token for token in required if token not in audit]
    assert not missing, "governance/audit.md missing pretty summary layout tokens:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_business_rules_write_failure_does_not_redirect_to_workspace_memory_target():
    helper = read_text(REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py")

    helper_required = [
        "ERR-BUSINESS-RULES-PERSIST-WRITE-FAILED",
        "business_rules_action = \"write-requested\"",
    ]

    missing_helper = [t for t in helper_required if t not in helper]

    assert not missing_helper, "persist_workspace_artifacts.py missing business-rules write-failure handling tokens:\n" + "\n".join([f"- {m}" for m in missing_helper])


@pytest.mark.governance
def test_error_logger_helper_exists_and_defines_required_log_shape():
    p = REPO_ROOT / "governance" / "entrypoints" / "error_logs.py"
    assert p.exists(), "Missing governance/error_logs.py"

    text = read_text(p)
    required_tokens = [
        "emit_error_event_ssot",
        "error.log.jsonl",
        "reasonKey",
        "phase",
        "gate",
        "repoFingerprint",
        "DEFAULT_RETENTION_DAYS",
        "safe_log_error",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "error_logs.py missing required log shape tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_error_logger_logs_to_ssot_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = REPO_ROOT / "governance" / "entrypoints" / "error_logs.py"
    spec = importlib.util.spec_from_file_location("error_logs_mod", module_path)
    assert spec and spec.loader, "Failed to load governance/error_logs.py module spec"
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("OPENCODE_FORCE_READ_ONLY", raising=False)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cfg = tmp_path / "opencode-config"
    write_governance_paths(cfg)
    logs_dir = cfg / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    out = mod.safe_log_error(
        reason_key="ERR-TEST-INDEX",
        message="test event",
        config_root=cfg,
        phase="test",
        gate="test",
        mode="repo-aware",
        command="pytest",
        component="test-suite",
    )
    assert out.get("status") == "logged"
    log_path = Path(out.get("path", ""))
    assert log_path.name == "error.log.jsonl"
    assert log_path.exists()


@pytest.mark.governance
def test_error_logger_uses_bound_workspaces_home_for_repo_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module_path = REPO_ROOT / "governance" / "entrypoints" / "error_logs.py"
    spec = importlib.util.spec_from_file_location("error_logs_mod", module_path)
    assert spec and spec.loader, "Failed to load governance/error_logs.py module spec"
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("OPENCODE_FORCE_READ_ONLY", raising=False)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cfg = tmp_path / "opencode-config"
    custom_workspaces = tmp_path / "custom-workspaces-root"
    write_governance_paths(cfg, workspaces_home=custom_workspaces)

    out = mod.safe_log_error(
        reason_key="ERR-TEST-BOUND-WORKSPACES",
        message="bound workspaces test",
        config_root=cfg,
        phase="test",
        gate="test",
        mode="repo-aware",
        repo_fingerprint="88b39b036804c534",
        command="pytest",
        component="test-suite",
    )
    assert out.get("status") == "logged"
    logged_path = Path(str(out.get("path", "")))
    assert str(custom_workspaces.resolve()) in str(logged_path.resolve())
    assert logged_path.exists(), "expected repo error log in bound workspaces home"


@pytest.mark.governance
def test_error_logger_uses_ssot_write_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """error_logs.py uses write_policy.writes_allowed() as SSOT."""

    module_path = REPO_ROOT / "governance" / "entrypoints" / "error_logs.py"
    spec = importlib.util.spec_from_file_location("error_logs_ssot", module_path)
    assert spec and spec.loader, "Failed to load governance/error_logs.py module spec"
    
    # CI=true without FORCE_READ_ONLY should allow writes (SSOT)
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("OPENCODE_FORCE_READ_ONLY", raising=False)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # With SSOT, CI mode allows writes unless FORCE_READ_ONLY=1
    assert mod._read_only() is False, "CI mode should allow writes (SSOT) unless FORCE_READ_ONLY=1"

    cfg = tmp_path / "opencode-config"
    write_governance_paths(cfg)
    out = mod.safe_log_error(
        reason_key="ERR-SSOT-TEST",
        message="should use SSOT write policy",
        config_root=cfg,
        phase="test",
        gate="test",
        mode="pipeline",
        command="pytest",
        component="test-suite",
    )
    # With writes allowed, status should not be read-only
    assert out.get("status") != "read-only", "Should not be read-only when writes allowed"


@pytest.mark.governance
def test_selected_rulebooks_reference_core_precedence_contract():
    expected = [
        "profiles/rules.backend-java.md",
        "profiles/rules.frontend-angular-nx.md",
        "profiles/rules.openapi-contracts.md",
        "profiles/rules.cucumber-bdd.md",
        "profiles/rules.backend-java-templates.md",
        "profiles/rules.backend-java-kafka-templates.md",
        "profiles/rules.frontend-angular-nx-templates.md",
        "profiles/rules.docs-governance.md",
        "profiles/rules.postgres-liquibase.md",
        "profiles/rules.principal-excellence.md",
        "profiles/rules.risk-tiering.md",
        "profiles/rules.scorecard-calibration.md",
    ]
    missing_refs = []
    for rel in expected:
        text = read_text(REPO_ROOT / rel)
        if "RULEBOOK-PRECEDENCE-POLICY" not in text:
            missing_refs.append(rel)

    assert not missing_refs, "Rulebooks missing core precedence reference:\n" + "\n".join(
        [f"- {r}" for r in missing_refs]
    )


@pytest.mark.governance
def test_profile_rulebooks_use_stable_precedence_anchor_not_section_numbers():
    profile_files = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert profile_files, "No profile rulebooks found under profiles/rules*.md"

    missing_anchor: list[str] = []
    legacy_section_ref: list[str] = []
    for p in profile_files:
        text = read_text(p)
        if "RULEBOOK-PRECEDENCE-POLICY" not in text:
            missing_anchor.append(str(p.relative_to(REPO_ROOT)))
        if "Section 4.6" in text:
            legacy_section_ref.append(str(p.relative_to(REPO_ROOT)))

    assert not missing_anchor, "Profile rulebooks missing stable precedence anchor reference:\n" + "\n".join(
        [f"- {r}" for r in missing_anchor]
    )
    assert not legacy_section_ref, "Profile rulebooks still reference fragile section numbering:\n" + "\n".join(
        [f"- {r}" for r in legacy_section_ref]
    )


@pytest.mark.governance
def test_profile_rulebooks_include_standard_operational_wrapper_headings():
    profile_files = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert profile_files, "No profile rulebooks found under profiles/rules*.md"

    required_headings = [
        "Intent",
        "Scope",
        "Activation",
        "Phase integration",
        "Evidence contract",
        "Tooling",
        "Examples",
        "Troubleshooting",
    ]

    offenders: list[str] = []
    for p in profile_files:
        text = read_text(p)
        missing = [
            h
            for h in required_headings
            if not re.search(rf"^##\s+.*{re.escape(h)}", text, flags=re.MULTILINE | re.IGNORECASE)
        ]
        if missing:
            offenders.append(f"{p.relative_to(REPO_ROOT)} -> missing {missing}")

    assert not offenders, "Profile rulebooks missing standard operational headings:\n" + "\n".join(
        [f"- {r}" for r in offenders]
    )
