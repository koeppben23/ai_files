from __future__ import annotations

import json
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

import pytest

from .util import REPO_ROOT, read_text, run


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
def test_all_profile_rulebooks_define_scorecard_calibration_v211():
    calibration = read_text(REPO_ROOT / "profiles" / "rules.scorecard-calibration.md")
    required_tokens = [
        "## Principal Hardening v2.1.1 - Scorecard Calibration (Binding)",
        "### CAL-1 Standard criterion weights by tier (binding)",
        "`TIER-LOW`: each active criterion weight = `2`",
        "`TIER-MEDIUM`: each active criterion weight = `3`",
        "`TIER-HIGH`: each active criterion weight = `5`",
        "CalibrationVersion: v2.1.1",
        "WARN-SCORECARD-CALIBRATION-INCOMPLETE",
    ]
    missing = [token for token in required_tokens if token not in calibration]
    assert not missing, "rules.scorecard-calibration.md missing v2.1.1 calibration sections:\n" + "\n".join(
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
def test_backend_java_kafka_addon_activation_is_conditional_and_phase_split():
    text = read_text(REPO_ROOT / "profiles" / "rules.backend-java.md")
    required = [
        "In **Phase 1/2**, the workflow MUST evaluate whether Kafka addon is required",
        "SESSION_STATE.AddonsEvidence.kafka.required = true | false",
        "In **code-phase** (Phase 4+), load and record this addon ONLY when `required = true`",
        "If `required = false`, keep:",
        "SESSION_STATE.LoadedRulebooks.addons.kafka = \"\"",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "rules.backend-java.md missing conditional Kafka activation semantics:\n" + "\n".join(
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
        "new_profile.md": [
            "# Governance Factory - New Profile",
            "## Required Input (Binding)",
            "## Generation Contract (Binding)",
            "## Principal Conformance Checklist (Binding)",
            "## Shared Principal Governance Contracts (Binding)",
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
        ],
        "new_addon.md": [
            "# Governance Factory - New Addon",
            "## Required Input (Binding)",
            "## Manifest Contract (Binding)",
            "## Rulebook Contract (Binding)",
            "## Principal Conformance Checklist (Binding)",
            "## Shared Principal Governance Contracts (Binding)",
            "rules.principal-excellence.md",
            "rules.risk-tiering.md",
            "rules.scorecard-calibration.md",
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
def test_factory_contract_diagnostic_exists_and_is_calibrated():
    p = REPO_ROOT / "diagnostics" / "PROFILE_ADDON_FACTORY_CONTRACT.json"
    assert p.exists(), "Missing diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json"

    text = read_text(p)
    required_tokens = [
        '"schema": "governance.factory.contract.v1"',
        '"requiredProfileSections"',
        '"sharedContractRulebooks"',
        '"requiredLoadedRulebookAddonKeys"',
        '"requiredAddonManifestFields"',
        '"requiredWarningCodes"',
        '"canonicalRiskTiers"',
        '"scoreThresholds"',
        '"TIER-HIGH": 0.9',
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "Factory diagnostics contract incomplete:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_master_defines_repo_scoped_session_state_with_global_pointer():
    text = read_text(REPO_ROOT / "master.md")
    required_tokens = [
        "${SESSION_STATE_POINTER_FILE}",
        "${SESSION_STATE_FILE}",
        "${SESSION_STATE_POINTER_FILE}` = `${OPENCODE_HOME}/SESSION_STATE.json",
        "${SESSION_STATE_FILE}` = `${REPO_HOME}/SESSION_STATE.json",
        "global active-session pointer",
        "repo-scoped canonical session state",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "master.md missing repo-scoped session state topology tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


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
    p = REPO_ROOT / "diagnostics" / "bootstrap_session_state.py"
    assert p.exists(), "Missing diagnostics/bootstrap_session_state.py"

    text = read_text(p)
    required_tokens = [
        "SESSION_STATE.json",
        "opencode-session-pointer.v1",
        "activeSessionStateFile",
        "workspaces",
        "1.1-Bootstrap",
        "BLOCKED-BOOTSTRAP-NOT-SATISFIED",
        "--repo-fingerprint",
        "--config-root",
        "--force",
        "--dry-run",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "bootstrap_session_state.py missing required behavior tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_session_state_bootstrap_recovery_script_creates_state_file(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "bootstrap_session_state.py"
    cfg = tmp_path / "opencode-config"
    repo_fp = "demo-repo-123456"

    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--config-root", str(cfg)])
    assert r.returncode == 0, f"bootstrap_session_state.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    pointer_file = cfg / "SESSION_STATE.json"
    assert pointer_file.exists(), "Expected global SESSION_STATE pointer to be created"

    pointer = json.loads(read_text(pointer_file))
    assert pointer.get("schema") == "opencode-session-pointer.v1"
    assert pointer.get("activeRepoFingerprint") == repo_fp
    expected_pointer_target = f"${{WORKSPACES_HOME}}/{repo_fp}/SESSION_STATE.json"
    assert pointer.get("activeSessionStateFile") == expected_pointer_target

    state_file = cfg / "workspaces" / repo_fp / "SESSION_STATE.json"
    assert state_file.exists(), "Expected repo-scoped SESSION_STATE.json to be created"

    data = json.loads(read_text(state_file))
    assert "SESSION_STATE" in data and isinstance(data["SESSION_STATE"], dict)
    ss = data["SESSION_STATE"]

    required_keys = [
        "Phase",
        "Mode",
        "ConfidenceLevel",
        "Next",
        "Bootstrap",
        "Scope",
        "LoadedRulebooks",
        "RulebookLoadEvidence",
        "Gates",
    ]
    missing = [k for k in required_keys if k not in ss]
    assert not missing, "SESSION_STATE bootstrap missing required keys:\n" + "\n".join([f"- {m}" for m in missing])

    assert ss["Phase"] == "1.1-Bootstrap"
    assert ss["Mode"] == "BLOCKED"
    assert ss["Next"] == "BLOCKED-BOOTSTRAP-NOT-SATISFIED"


@pytest.mark.governance
def test_workspace_persistence_backfill_script_exists_and_defines_required_targets():
    p = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    assert p.exists(), "Missing diagnostics/persist_workspace_artifacts.py"

    text = read_text(p)
    required_tokens = [
        "repo-cache.yaml",
        "repo-map-digest.md",
        "decision-pack.md",
        "workspace-memory.yaml",
        "${REPO_CACHE_FILE}",
        "${REPO_DIGEST_FILE}",
        "${REPO_DECISION_PACK_FILE}",
        "${WORKSPACE_MEMORY_FILE}",
        "--repo-fingerprint",
        "--repo-root",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "persist_workspace_artifacts.py missing required tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_workspace_persistence_backfill_script_creates_missing_artifacts(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_fp = "demo-repo-654321"

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

    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--config-root", str(cfg)])
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    expected = [
        workspace / "repo-cache.yaml",
        workspace / "repo-map-digest.md",
        workspace / "decision-pack.md",
        workspace / "workspace-memory.yaml",
    ]
    missing_files = [str(p) for p in expected if not p.exists()]
    assert not missing_files, "Workspace artifact backfill missing files:\n" + "\n".join(
        [f"- {m}" for m in missing_files]
    )


@pytest.mark.governance
def test_workspace_persistence_backfill_derives_fingerprint_from_repo_root(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_root = tmp_path / "repo"

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

    expected_fp = hashlib.sha256(
        "git@github.com:example/derived-repo.git|main".encode("utf-8")
    ).hexdigest()[:16]

    r = run([
        sys.executable,
        str(script),
        "--repo-root",
        str(repo_root),
        "--config-root",
        str(cfg),
        "--quiet",
    ])
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    assert payload.get("repoFingerprint") == expected_fp
    assert payload.get("fingerprintSource") == "git-metadata"

    workspace = cfg / "workspaces" / expected_fp
    assert (workspace / "repo-cache.yaml").exists()
    assert (workspace / "repo-map-digest.md").exists()
    assert (workspace / "decision-pack.md").exists()
    assert (workspace / "workspace-memory.yaml").exists()


@pytest.mark.governance
def test_start_md_includes_workspace_persistence_autohook():
    text = read_text(REPO_ROOT / "start.md")
    required_tokens = [
        "Auto-Persistence Hook (OpenCode)",
        "persist_workspace_artifacts.py",
        "--repo-root",
        "workspacePersistenceHook",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "start.md missing workspace persistence auto-hook tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_master_requires_phase_21_to_prompt_for_phase_15_decision_when_not_explicitly_set():
    text = read_text(REPO_ROOT / "master.md")
    required_tokens = [
        'Decision Pack MUST include: "Run Phase 1.5 now? (A=Yes, B=No)"',
        "Run Phase 1.5 ONLY if the user approves",
        '"Run Phase 1.5 (Business Rules Discovery) now?"',
        "Execute Phase 1.5 ONLY if the user approves that decision.",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "master.md missing mandatory Phase 2.1 -> Phase 1.5 decision prompts:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_backfill_decision_pack_includes_phase_15_prompt_decision():
    text = read_text(REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py")
    required_tokens = [
        "D-001: Run Phase 1.5 (Business Rules Discovery) now?",
        "A) Yes",
        "B) No",
        "Recommendation:",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "persist_workspace_artifacts.py missing Phase 1.5 decision-pack baseline tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_error_logger_helper_exists_and_defines_required_log_shape():
    p = REPO_ROOT / "diagnostics" / "error_logs.py"
    assert p.exists(), "Missing diagnostics/error_logs.py"

    text = read_text(p)
    required_tokens = [
        "opencode.error-log.v1",
        "reasonKey",
        "phase",
        "gate",
        "repoFingerprint",
        "errors-",
        "errors-global-",
        "opencode.error-index.v1",
        "DEFAULT_RETENTION_DAYS",
        "errors-index.json",
        "safe_log_error",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "error_logs.py missing required log shape tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_error_logger_updates_index_and_prunes_old_global_logs(tmp_path: Path):
    module_path = REPO_ROOT / "diagnostics" / "error_logs.py"
    spec = importlib.util.spec_from_file_location("error_logs_mod", module_path)
    assert spec and spec.loader, "Failed to load diagnostics/error_logs.py module spec"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    cfg = tmp_path / "opencode-config"
    logs_dir = cfg / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    old_file = logs_dir / "errors-global-2000-01-01.jsonl"
    old_file.write_text('{"legacy":true}\n', encoding="utf-8")

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

    # retention should prune the very old synthetic file
    assert not old_file.exists(), "Expected old global error log file to be pruned by retention"

    index_file = logs_dir / "errors-index.json"
    assert index_file.exists(), "Expected global error index file"

    idx = json.loads(read_text(index_file))
    assert idx.get("schema") == "opencode.error-index.v1"
    assert isinstance(idx.get("totalEvents"), int) and idx["totalEvents"] >= 1
    assert isinstance(idx.get("byReason"), dict)
    assert idx["byReason"].get("ERR-TEST-INDEX", 0) >= 1


@pytest.mark.governance
def test_rules_define_canonical_rulebook_precedence_contract():
    text = read_text(REPO_ROOT / "rules.md")
    required_tokens = [
        "### 4.6 Canonical Rulebook Precedence (Binding)",
        "master.md",
        "rules.md",
        "active profile rulebook",
        "activated addon rulebooks (including templates and shared governance add-ons)",
        "Activation remains manifest-owned for addons",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "rules.md missing canonical precedence contract tokens:\n" + "\n".join([f"- {m}" for m in missing])


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
        if "Section 4.6" not in text:
            missing_refs.append(rel)

    assert not missing_refs, "Rulebooks missing core precedence reference:\n" + "\n".join(
        [f"- {r}" for r in missing_refs]
    )
