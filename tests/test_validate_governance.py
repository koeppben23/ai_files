from __future__ import annotations

import re
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text


@pytest.mark.governance
def test_required_files_present():
    required = [
        "master.md",
        "rules.md",
        "start.md",
        "SESSION_STATE_SCHEMA.md",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    assert not missing, f"Missing: {missing}"


@pytest.mark.governance
def test_blocked_consistency_schema_vs_master():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    master = read_text(REPO_ROOT / "master.md")

    s = set(re.findall(r"BLOCKED-[A-Z-]+", schema))
    m = set(re.findall(r"BLOCKED-[A-Z-]+", master))

    missing_in_master = s - m
    missing_in_schema = m - s
    assert not missing_in_master, f"Missing in master: {sorted(missing_in_master)}"
    assert not missing_in_schema, f"Missing in schema: {sorted(missing_in_schema)}"


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
def test_master_min_template_lists_extended_phase_values():
    master = read_text(REPO_ROOT / "master.md")
    required_tokens = [
        "1.1-Bootstrap",
        "1.2-ProfileDetection",
        "1.3-CoreRulesActivation",
        "2.1-DecisionPack",
        "5.6",
    ]
    missing = [t for t in required_tokens if t not in master]
    assert not missing, "master MIN template missing phase tokens:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_master_bootstrap_fields_match_schema_contract():
    master = read_text(REPO_ROOT / "master.md")
    required = ["Bootstrap:", "Present:", "Satisfied:", "Evidence:"]
    missing = [k for k in required if k not in master]
    assert not missing, "master bootstrap section missing required schema fields:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_schema_phase4_ticket_record_declares_must_include():
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")
    assert "When Phase 4 planning is produced, the workflow MUST include:" in schema


@pytest.mark.governance
def test_gate_scorecard_and_review_of_review_contract_present():
    rules = read_text(REPO_ROOT / "rules.md")
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    assert "### 7.7.2 Gate Review Scorecard" in rules
    assert "### 7.7.4 Review-of-Review Consistency Check" in rules
    assert "Gate Review Scorecard (binding):" in master
    assert "review-of-review" in master
    assert "GateScorecards" in schema


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
    required_snippets = [
        "## Principal Excellence Contract (Binding)",
        "### Gate Review Scorecard (binding)",
        "### Claim-to-evidence (binding)",
        "### Exit criteria (binding)",
        "### Recovery when evidence is missing (binding)",
        "WARN-PRINCIPAL-EVIDENCE-MISSING",
    ]

    profile_files = sorted((REPO_ROOT / "profiles").glob("rules*.md"))
    assert profile_files, "No profile rulebooks found under profiles/rules*.md"

    offenders: list[str] = []
    for path in profile_files:
        text = read_text(path)
        missing = [snippet for snippet in required_snippets if snippet not in text]
        if missing:
            offenders.append(f"{path.relative_to(REPO_ROOT)} -> missing {missing}")

    assert not offenders, "Missing principal excellence contract in profile rulebooks:\n" + "\n".join(
        [f"- {line}" for line in offenders]
    )


@pytest.mark.governance
def test_java_profile_and_templates_include_principal_scorecard_artifact_shape():
    targets = [
        REPO_ROOT / "profiles" / "rules.backend-java.md",
        REPO_ROOT / "profiles" / "rules.backend-java-templates.md",
        REPO_ROOT / "profiles" / "rules.backend-java-kafka-templates.md",
    ]

    required = [
        "SESSION_STATE:",
        "GateScorecards:",
        "principal_excellence:",
        "PRINCIPAL-QUALITY-CLAIMS-EVIDENCED",
        "PRINCIPAL-DETERMINISM-AND-TEST-RIGOR",
        "PRINCIPAL-ROLLBACK-OR-RECOVERY-READY",
    ]

    problems: list[str] = []
    for path in targets:
        text = read_text(path)
        missing = [token for token in required if token not in text]
        if missing:
            problems.append(f"{path.relative_to(REPO_ROOT)} -> missing {missing}")

    assert not problems, "Java principal scorecard contract incomplete:\n" + "\n".join(
        [f"- {line}" for line in problems]
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
    addon_rulebooks = [
        "profiles/rules.frontend-angular-nx-templates.md",
        "profiles/rules.cucumber-bdd.md",
        "profiles/rules.postgres-liquibase.md",
        "profiles/rules.docs-governance.md",
        "profiles/rules.frontend-cypress-testing.md",
        "profiles/rules.frontend-openapi-ts-client.md",
        "profiles/rules.backend-java-kafka-templates.md",
        "profiles/rules.openapi-contracts.md",
        "profiles/rules.backend-java-templates.md",
    ]
    required_tokens = [
        "## Principal Hardening v2.1 - Standard Risk Tiering (Binding)",
        "### RTN-1 Canonical tiers (binding)",
        "`TIER-LOW`",
        "`TIER-MEDIUM`",
        "`TIER-HIGH`",
        "### RTN-4 Required SESSION_STATE shape (binding)",
        "RiskTiering:",
        "WARN-RISK-TIER-UNRESOLVED",
    ]

    problems: list[str] = []
    for rel in addon_rulebooks:
        text = read_text(REPO_ROOT / Path(rel))
        missing = [token for token in required_tokens if token not in text]
        if missing:
            problems.append(f"{rel} -> missing {missing}")

    assert not problems, "Addon rulebooks missing v2.1 risk tiering normalization:\n" + "\n".join(
        [f"- {line}" for line in problems]
    )


@pytest.mark.governance
def test_addon_rulebooks_use_scorecard_calibration_v211():
    addon_rulebooks = [
        "profiles/rules.frontend-angular-nx-templates.md",
        "profiles/rules.cucumber-bdd.md",
        "profiles/rules.postgres-liquibase.md",
        "profiles/rules.docs-governance.md",
        "profiles/rules.frontend-cypress-testing.md",
        "profiles/rules.frontend-openapi-ts-client.md",
        "profiles/rules.backend-java-kafka-templates.md",
        "profiles/rules.openapi-contracts.md",
        "profiles/rules.backend-java-templates.md",
    ]
    required_tokens = [
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

    problems: list[str] = []
    for rel in addon_rulebooks:
        text = read_text(REPO_ROOT / Path(rel))
        missing = [token for token in required_tokens if token not in text]
        if missing:
            problems.append(f"{rel} -> missing {missing}")

    assert not problems, "Addon rulebooks missing v2.1.1 scorecard calibration:\n" + "\n".join(
        [f"- {line}" for line in problems]
    )
