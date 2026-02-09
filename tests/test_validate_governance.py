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
        "STABILITY_SLA.md",
    ]
    missing = [f for f in required if not (REPO_ROOT / f).exists()]
    assert not missing, f"Missing: {missing}"


@pytest.mark.governance
def test_stability_sla_is_normative_and_aligned_with_core_contracts():
    sla = read_text(REPO_ROOT / "STABILITY_SLA.md")
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    sla_required = [
        "## 1) Single Canonical Precedence",
        "master > core rules > active profile > activated addons/templates > ticket",
        "## 3) Fail-Closed for Required",
        "## 7) SESSION_STATE Versioning and Isolation",
        "BLOCKED-STATE-OUTDATED",
        "## 10) Regression Gates (CI Required)",
    ]
    master_required = [
        "`STABILITY_SLA.md` is the normative Go/No-Go contract for governance releases.",
        "Stability sync note (binding): governance release/readiness decisions MUST also satisfy `STABILITY_SLA.md`.",
        "4. Activated templates/addon rulebooks (manifest-driven)",
        "SUGGEST: ranked profile shortlist with evidence (top 1 marked recommended)",
        "Detected multiple plausible profiles. Reply with ONE number:",
        "0) abort/none",
    ]
    rules_required = [
        "Governance release stability is normatively defined by `STABILITY_SLA.md`",
        "Release/readiness decisions MUST satisfy `STABILITY_SLA.md` invariants; conflicts are resolved fail-closed.",
        "4) activated addon rulebooks (including templates and shared governance add-ons)",
        "Master Prompt > Core Rulebook > Active Profile Rulebook > Activated Addon/Template Rulebooks > Ticket > Repo docs",
        "provide a ranked shortlist of plausible profiles with brief evidence per candidate",
        "request explicit selection using a single targeted numbered prompt",
        "0=abort/none",
    ]

    missing_sla = [token for token in sla_required if token not in sla]
    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]

    assert not missing_sla, "STABILITY_SLA.md missing required canonical tokens:\n" + "\n".join([f"- {m}" for m in missing_sla])
    assert not missing_master, "master.md missing STABILITY_SLA integration tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing STABILITY_SLA integration tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )

    precedence_blocks = []
    lines = master.splitlines()
    i = 0
    while i < len(lines):
        if not re.match(r"^\s*\d+\.\s+", lines[i]):
            i += 1
            continue
        block = []
        while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
            block.append(lines[i].strip())
            i += 1
        normalized = "\n".join(block).lower()
        if (
            "master prompt" in normalized
            and "rules.md" in normalized
            and "active profile" in normalized
            and "ticket" in normalized
        ):
            precedence_blocks.append(block)

    assert master.count("## 1. PRIORITY ORDER") == 1, "master.md must contain exactly one canonical PRIORITY ORDER section"
    assert len(precedence_blocks) == 1, "master.md must contain exactly one numbered precedence fragment"
    canonical = "\n".join(precedence_blocks[0])
    assert "4. Activated templates/addon rulebooks (manifest-driven)" in canonical
    assert "5. Ticket specification" in canonical
    assert "DO NOT read rulebooks from the repository" not in master, (
        "master.md contains legacy repository phrasing; use precise 'repo working tree' terminology"
    )
    assert "Master Prompt > Core Rulebook > Profile Rulebook > Ticket > Repo docs" not in rules, (
        "rules.md still contains legacy precedence fragment without addon/template layer"
    )

    # Context-sensitive guard: numbered precedence-like lists near precedence/priority/resolution
    # terms must not reintroduce a shortened legacy order.
    lines = master.splitlines()
    for i, line in enumerate(lines):
        if not re.search(r"\b(precedence|priority|resolution)\b", line, flags=re.IGNORECASE):
            continue
        w_start = max(0, i - 12)
        w_end = min(len(lines), i + 13)
        window = lines[w_start:w_end]

        j = 0
        while j < len(window):
            if not re.match(r"^\s*\d+\.\s+", window[j]):
                j += 1
                continue
            block = []
            while j < len(window) and re.match(r"^\s*\d+\.\s+", window[j]):
                block.append(window[j].strip())
                j += 1
            block_text = "\n".join(block).lower()
            looks_like_precedence = (
                "master" in block_text and "rules" in block_text and "profile" in block_text and "ticket" in block_text
            )
            missing_addon_layer = "activated templates/addon rulebooks" not in block_text
            assert not (looks_like_precedence and missing_addon_layer), (
                "master.md contains a secondary precedence-like numbered list near precedence/priority/resolution context"
            )


@pytest.mark.governance
def test_stability_sla_required_ci_gates_are_wired():
    sla = read_text(REPO_ROOT / "STABILITY_SLA.md")
    ci = read_text(REPO_ROOT / ".github/workflows/ci.yml")

    sla_required = [
        "governance-lint",
        "pytest -m governance",
        "pytest -m e2e_governance",
        "template quality gate",
    ]
    ci_required = [
        "governance-lint:",
        "validate-governance:",
        "governance-e2e:",
        "pytest -q -m governance",
        "pytest -q -m e2e_governance",
        "release-readiness:",
        "needs: [conventional-pr-title, governance-lint, spec-guards, test-installer, validate-governance, governance-e2e, build-artifacts]",
    ]

    missing_sla = [token for token in sla_required if token not in sla]
    missing_ci = [token for token in ci_required if token not in ci]

    assert not missing_sla, "STABILITY_SLA.md missing required CI gate tokens:\n" + "\n".join([f"- {m}" for m in missing_sla])
    assert not missing_ci, ".github/workflows/ci.yml missing SLA-aligned CI gate wiring:\n" + "\n".join(
        [f"- {m}" for m in missing_ci]
    )


@pytest.mark.governance
def test_precedence_ambiguity_and_evidence_mapping_contracts_are_consistent():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "Canonical conflict precedence is defined once in Section 1 (`PRIORITY ORDER`) and MUST NOT be redefined here.",
        "They MUST NOT be interpreted as a second precedence model; canonical conflict precedence remains Section 1 (`PRIORITY ORDER`).",
        "DO NOT read rulebooks from the repo working tree",
        "BLOCKED-MISSING-RULEBOOK:<file>",
    ]
    master_forbidden = [
        "4) Precedence and merge",
        "`rules.md` (core) > active profile > templates/addons refinements.",
        "lookup orders below define **resolution precedence**",
        "DO NOT read rulebooks from the repository",
    ]
    rules_required = [
        "conservative mode is planning-only",
        "BLOCKED-AMBIGUOUS-PROFILE",
    ]
    start_required = [
        "Runtime resolution scope note (binding):",
        "`${REPO_OVERRIDES_HOME}`",
        "`${OPENCODE_HOME}`",
        "When profile signals are ambiguous, provide a ranked profile shortlist with evidence",
        "request explicit numbered selection (`1=<recommended> | 2=<alt> | 3=<alt> | 4=fallback-minimum | 0=abort/none`)",
    ]
    schema_required = [
        "`BLOCKED-MISSING-RULEBOOK:<file>`",
        "Claim verification mapping (binding):",
        "`verified` claims require `result=pass`",
        "claims MUST remain `not-verified`",
    ]

    missing_master = [token for token in master_required if token not in master]
    found_master_forbidden = [token for token in master_forbidden if token in master]
    missing_rules = [token for token in rules_required if token not in rules]
    missing_start = [token for token in start_required if token not in start]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing precedence/terminology tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not found_master_forbidden, "master.md still contains secondary precedence drift fragments:\n" + "\n".join(
        [f"- {m}" for m in found_master_forbidden]
    )
    assert not missing_rules, "rules.md missing ambiguity fail-closed tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing runtime resolution scope-note tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing claim mapping/top-tier blocking tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_governance_lint_script_exists_and_passes():
    script = REPO_ROOT / "scripts" / "governance_lint.py"
    assert script.exists(), "Missing scripts/governance_lint.py"

    r = run([sys.executable, str(script)])
    assert r.returncode == 0, f"governance_lint failed:\n{r.stdout}\n{r.stderr}"


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
def test_session_state_outputs_require_terminal_next_step_line():
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "After every `SESSION_STATE` block",
        "NEXT_STEP: <value of SESSION_STATE.Next>",
    ]
    schema_required = [
        "Every response containing `SESSION_STATE` MUST end with a terminal summary line",
        "NEXT_STEP: <value of SESSION_STATE.Next>",
        "output `NEXT_STEP: <SESSION_STATE.Next>` as the terminal line",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing NEXT_STEP terminal-line contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing NEXT_STEP terminal-line contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_conventional_branch_and_commit_contract_is_documented_and_ci_enforced():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    ci = read_text(REPO_ROOT / ".github" / "workflows" / "ci.yml")

    master_required = [
        "### 2.6 Conventional Git Naming Contract (Binding when Git operations are requested)",
        "Branch naming (binding):",
        "Commit subject naming (binding):",
    ]
    rules_required = [
        "## 7.10 Conventional Branch/Commit Contract (Core, Binding)",
        "Branch names (binding):",
        "Commit subjects (binding):",
    ]
    ci_required = [
        "Validate branch name (Conventional)",
        "Validate commit subjects (Conventional Commits)",
        "github.event.pull_request.base.sha",
        "github.event.pull_request.head.sha",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]
    missing_ci = [token for token in ci_required if token not in ci]

    assert not missing_master, "master.md missing conventional git naming contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing conventional branch/commit contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_ci, ".github/workflows/ci.yml missing conventional enforcement tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_ci]
    )


@pytest.mark.governance
def test_control_plane_precision_contracts_for_overrides_reload_and_priority_order():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        "${REPO_OVERRIDES_HOME}",
        "workspace-only override bucket; never repo-local",
        "`repo working tree` = checked-out project files under version control.",
        "`workspace repo bucket` = `${REPO_HOME}` under `${WORKSPACES_HOME}/<repo_fingerprint>`",
        "DO NOT read rulebooks from the repo working tree",
        "Rulebooks may only be loaded from trusted governance roots outside the repo working tree",
        "Workspace-local override (optional, outside the repo): `${REPO_OVERRIDES_HOME}/rules.md`",
        "Workspace-local override (optional, outside the repo): `${REPO_OVERRIDES_HOME}/profiles/rules*.md`",
        "4. Activated templates/addon rulebooks (manifest-driven)",
        "`README-RULES.md` (if present) is descriptive/executive summary only and non-normative.",
        "Precedence sync note (binding): this priority order MUST stay consistent with `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.",
        "### 2.2.1 Operator Reload Contract (Binding)",
        "`/reload-addons`",
        "Run only Phase 1.3 + Phase 1.4 logic",
        "Auto-advance to implementation/gates is forbidden from reload output",
        "activation-required-by-evidence = true; otherwise false.",
        "`SESSION_STATE.AddonsEvidence.<addon_key>.required` stores this evidence-based activation requirement",
    ]
    rules_required = [
        "## 7.11 Operator Reload Contract (Core, Binding)",
        "Execute only Phase 1.3 + Phase 1.4 reload logic.",
        "Reload is a control-plane operation, not an implementation permission.",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]

    assert not missing_master, "master.md missing control-plane precision contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing reload control-plane contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )

    assert master.count("## 1. PRIORITY ORDER") == 1, "master.md must define exactly one canonical priority order section"
    assert "DO NOT read rulebooks from the repository" not in master, (
        "master.md contains legacy ambiguous phrase; use 'repo working tree' terminology instead"
    )


@pytest.mark.governance
def test_deterministic_addon_conflict_resolution_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        "Addon/template tie-breakers at same precedence level (binding):",
        "prefer the most restrictive compatible rule",
        "prefer narrower scope over generic scope",
        "BLOCKED-ADDON-CONFLICT",
    ]
    rules_required = [
        "Deterministic addon conflict resolution (binding):",
        "preserve higher-level precedence",
        "prefer narrower scope over generic scope",
        "BLOCKED-ADDON-CONFLICT",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]

    assert not missing_master, "master.md missing deterministic addon tie-break contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing deterministic addon conflict contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )


@pytest.mark.governance
def test_monorepo_scope_invariant_blocks_repo_wide_addon_activation_without_scope():
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "In monorepos/multi-component repositories, if `ComponentScopePaths` is missing at code-phase,",
        "repo-wide addon activation is non-deterministic and MUST trigger `BLOCKED-MISSING-EVIDENCE`",
    ]
    schema_required = [
        "In monorepos/multi-component repositories at code-phase, if `ComponentScopePaths` is missing and addon activation would otherwise be repo-wide/ambiguous",
        "`Next = BLOCKED-MISSING-EVIDENCE`",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing monorepo scope invariant tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing monorepo scope invariant tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_machine_readable_reason_payload_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "Machine-readable diagnostics (binding):",
        "`SESSION_STATE.Diagnostics.ReasonPayloads`",
        "`reason_code`",
        "`surface` (`build|tests|static|addons|profile|state|contracts|security|performance|other`)",
        "`recovery_steps` (array, max 3 concrete steps)",
        "BLOCKED/WARN/NOT_VERIFIED outputs MUST include `SESSION_STATE.Diagnostics.ReasonPayloads`",
    ]
    schema_required = [
        "### 2.1.0 Reason Payloads (machine-readable, binding when reason codes are emitted)",
        "`BLOCKED-*`, `WARN-*`, `NOT_VERIFIED-*`",
        "`reason_code`",
        "`surface` (enum: `build|tests|static|addons|profile|state|contracts|security|performance|other`)",
        "`recovery_steps` (array of strings; 1..3 concrete steps)",
        "`next_command`",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing machine-readable reason payload contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing machine-readable reason payload contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_operator_explain_commands_are_defined_as_read_only_contracts():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        '"/why-blocked" (read-only diagnostics)',
        '"/explain-activation" (read-only activation report)',
        "### 2.2.2 Operator Explain Contracts (Binding, read-only)",
        "Both commands are read-only",
        "MUST NOT claim new implementation/build evidence",
    ]
    rules_required = [
        "## 7.12 Operator Explain Contracts (Core, Binding)",
        "`/why-blocked`",
        "`/explain-activation`",
        "Commands MUST be read-only",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]

    assert not missing_master, "master.md missing operator explain command contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing operator explain command contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )


@pytest.mark.governance
def test_capability_first_activation_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "Normalize repository capabilities (binding)",
        "SESSION_STATE.RepoFacts.Capabilities",
        "SESSION_STATE.RepoFacts.CapabilityEvidence",
        "Activation decisions MUST be capability-first, with hard-signal fallback",
        "capabilities_any",
        "capabilities_all",
    ]
    rules_required = [
        "### 4.9 Capability-First Activation (Binding)",
        "`capabilities_any` / `capabilities_all`",
        "hard-signal fallback (`signals`)",
        "`BLOCKED-MISSING-EVIDENCE`",
    ]
    schema_required = [
        "`SESSION_STATE.RepoFacts` (object; see Section 2.2)",
        "### 2.2 RepoFacts Capabilities (binding)",
        "CapabilityEvidence",
        "Activation decisions in Phase 1.4/Phase 4 entry MUST be capability-first with hard-signal fallback",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing capability-first activation contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing capability-first activation contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing RepoFacts capability contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_session_state_versioning_and_migration_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "SESSION_STATE versioning (binding):",
        "`session_state_version` (integer)",
        "`ruleset_hash` (string digest over active governance rule set)",
        "`Next = BLOCKED-STATE-OUTDATED`",
        "`BLOCKED-STATE-OUTDATED`:",
    ]
    schema_required = [
        "`SESSION_STATE.session_state_version` (integer)",
        "`SESSION_STATE.ruleset_hash` (string)",
        "### Session-state versioning and migration (binding)",
        "`Next=BLOCKED-STATE-OUTDATED`",
        "`BLOCKED-STATE-OUTDATED`",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing session-state versioning contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing session-state versioning contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_build_evidence_schema_includes_scope_precision_and_typed_artifacts():
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "SHOULD include `scope_paths` or `modules` per evidence item",
        "SHOULD include typed artifacts (`log|junit|sarif|coverage|other`)",
        "MAY include `command_line` and `env_fingerprint` for reproducibility",
    ]
    schema_required = [
        "scope_paths:",
        "modules:",
        "env_fingerprint:",
        "type: \"log|junit|sarif|coverage|other\"",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing evidence precision tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing evidence precision tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


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
def test_proof_carrying_explain_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        "concrete trigger facts (files/keys/signals)",
        "compact decision trace (`facts -> capability -> addon/profile -> surface -> outcome`)",
    ]
    rules_required = [
        "## 7.13 Proof-Carrying Explain Output (Core, Binding)",
        "facts -> capability -> addon/profile -> surface -> outcome",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]

    assert not missing_master, "master.md missing proof-carrying explain tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing proof-carrying explain tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])


@pytest.mark.governance
def test_pinning_policy_and_evidence_leakage_contract_are_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "Java: `java -version`",
        "Node: `node --version`",
        "Maven: `mvn -version`",
        "Gradle: `gradle -version` or wrapper equivalent",
        "claims SHOULD remain `not-verified`",
        "SHOULD include `ticket_id` and `session_run_id` for evidence isolation",
        "MUST NOT be treated as repo-wide verification when `ComponentScopePaths` is set",
    ]
    rules_required = [
        "## 7.14 Evidence Scope and Ticket Isolation Guards (Core, Binding)",
        "MUST NOT be treated as repo-wide",
        "Evidence from Ticket A / Session A MUST NOT verify Ticket B / Session B",
        "## 7.16 Toolchain Pinning Evidence Policy (Core, Binding)",
    ]
    schema_required = [
        "ticket_id:",
        "session_run_id:",
        "Evidence SHOULD include `ticket_id` and `session_run_id`",
        "repo-wide evidence scope MUST NOT be used as sole verification basis",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing pinning/evidence-leakage tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing pinning/evidence-leakage tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing pinning/evidence-leakage tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_activation_delta_determinism_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "Activation delta determinism (binding)",
        "`SESSION_STATE.ActivationDelta.AddonScanHash`",
        "`SESSION_STATE.ActivationDelta.RepoFactsHash`",
        "`BLOCKED-ACTIVATION-DELTA-MISMATCH`",
    ]
    rules_required = [
        "## 7.15 Deterministic Activation Delta Contract (Core, Binding)",
        "`ActivationDelta.AddonScanHash`",
        "`ActivationDelta.RepoFactsHash`",
        "`BLOCKED-ACTIVATION-DELTA-MISMATCH`",
    ]
    schema_required = [
        "### 2.3 ActivationDelta (binding)",
        "AddonScanHash",
        "RepoFactsHash",
        "`BLOCKED-ACTIVATION-DELTA-MISMATCH`",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]
    missing_schema = [token for token in schema_required if token not in schema]

    assert not missing_master, "master.md missing activation-delta tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing activation-delta tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing activation-delta tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


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
def test_required_addon_blocking_policy_is_centralized_and_not_redefined_locally():
    core = read_text(REPO_ROOT / "rules.md")
    core_required = [
        "Missing-addon policy is canonical and MUST NOT be redefined locally",
        "addon_class = required",
        "BLOCKED-MISSING-ADDON:<addon_key>",
        "addon_class = advisory",
    ]
    missing_core = [token for token in core_required if token not in core]
    assert not missing_core, "rules.md missing canonical required/advisory policy tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_core]
    )

    must_reference_not_redefine = {
        "profiles/rules.backend-java-templates.md": [
            "Missing-addon handling MUST follow canonical required-addon policy",
            "MUST NOT redefine blocking semantics",
        ],
        "profiles/rules.backend-java-kafka-templates.md": [
            "Missing-addon handling MUST follow canonical required-addon policy",
            "MUST NOT redefine blocking semantics",
        ],
        "profiles/rules.frontend-angular-nx-templates.md": [
            "Missing-addon handling MUST follow canonical required-addon policy",
            "MUST NOT redefine blocking semantics",
        ],
        "profiles/rules.frontend-angular-nx.md": [
            "apply canonical required-addon policy",
            "MUST NOT redefine blocking semantics",
        ],
    }

    problems: list[str] = []
    for rel, required_tokens in must_reference_not_redefine.items():
        text = read_text(REPO_ROOT / rel)
        missing = [token for token in required_tokens if token not in text]
        if missing:
            problems.append(f"{rel} missing {missing}")
        if "Mode = BLOCKED" in text:
            problems.append(f"{rel} still contains local Mode = BLOCKED definition")

    assert not problems, "Local rulebooks redefine canonical blocking policy:\n" + "\n".join(
        [f"- {m}" for m in problems]
    )


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
    p = REPO_ROOT / "diagnostics" / "PROFILE_ADDON_FACTORY_CONTRACT.json"
    assert p.exists(), "Missing diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json"

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
def test_workspace_persistence_quiet_blocked_payload_includes_reason_contract_fields(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    non_repo_root = tmp_path / "not-a-repo"
    non_repo_root.mkdir(parents=True, exist_ok=True)

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
    assert payload.get("reason_code") == "BLOCKED-WORKSPACE-PERSISTENCE"
    assert isinstance(payload.get("recovery_steps"), list) and len(payload["recovery_steps"]) >= 1
    assert isinstance(payload.get("next_command"), str) and payload["next_command"].strip()


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
def test_start_md_fallback_binding_and_identity_evidence_boundaries_are_fail_closed():
    text = read_text(REPO_ROOT / "start.md")

    required_tokens = [
        "'reason_code':'BLOCKED-MISSING-BINDING-FILE'",
        "'nonEvidence':'debug-only'",
        "Fallback computed payloads are debug output only (`nonEvidence`) and MUST NOT be treated as binding evidence.",
        "If installer-owned binding file is missing, workflow MUST block with `BLOCKED-MISSING-BINDING-FILE`",
        "Helper output is operational convenience status only and MUST NOT be treated as canonical repo identity evidence.",
        "Repo identity remains governed by `master.md` evidence contracts",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "start.md missing evidence-boundary fail-closed tokens:\n" + "\n".join([f"- {m}" for m in missing])

    forbidden_tokens = [
        "Treat it as **evidence**.",
        "# last resort: compute the same payload that the installer would write",
    ]
    found = [token for token in forbidden_tokens if token in text]
    assert not found, "start.md still contains legacy fallback-evidence phrasing:\n" + "\n".join([f"- {m}" for m in found])


@pytest.mark.governance
def test_unified_next_action_footer_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "#### Unified Next Action Footer (Binding)",
        "[NEXT-ACTION]",
        "Status: <normal|degraded|draft|blocked>",
        "Next: <single concrete next action>",
        "Why: <one-sentence rationale>",
        "Command: <exact next command or \"none\">",
    ]
    rules_required = [
        "### 7.3.1 Unified Next Action Footer (Binding)",
        "[NEXT-ACTION]",
        "Footer values MUST be consistent with `SESSION_STATE.Mode`, `SESSION_STATE.Next`, and any emitted reason payloads.",
    ]
    start_required = [
        "End every response with `[NEXT-ACTION]` footer (`Status`, `Next`, `Why`, `Command`) per `master.md`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing next-action footer tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing next-action footer tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing next-action footer tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_standard_blocker_envelope_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Machine-readable blocker envelope (mandatory):",
        '"status": "blocked"',
        '"reason_code": "BLOCKED-..."',
        '"missing_evidence": ["..."]',
        '"recovery_steps": ["..."]',
        '"next_command": "..."',
    ]
    rules_required = [
        "### 7.3.2 Standard Blocker Output Envelope (Binding)",
        "`status = blocked`",
        "`reason_code` (`BLOCKED-*`)",
        "`missing_evidence` (array)",
        "`recovery_steps` (array, max 3)",
        "`next_command` (single actionable command or `none`)",
        "deterministically ordered (priority-first, then lexicographic)",
    ]
    start_required = [
        "If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing blocker envelope tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing blocker envelope tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing blocker envelope tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_cold_warm_start_banner_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "### 2.4.1 Session Start Mode Banner (Binding)",
        "[START-MODE] Cold Start | Warm Start - reason:",
        "`Cold Start` when discovery/cache artifacts are absent or invalid.",
        "`Warm Start` only when cache/digest/memory artifacts are present and valid",
    ]
    rules_required = [
        "### 7.3.3 Cold/Warm Start Banner (Binding)",
        "[START-MODE] Cold Start | Warm Start - reason:",
        "Banner decision MUST be evidence-backed",
    ]
    start_required = [
        "At session start, include `[START-MODE] Cold Start | Warm Start - reason: ...` based on discovery artifact validity evidence.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing start-mode banner tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing start-mode banner tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing start-mode banner tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_confidence_impact_snapshot_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "#### Confidence + Impact Snapshot (Binding)",
        "[SNAPSHOT]",
        "Confidence: <0-100>%",
        "Risk: <LOW|MEDIUM|HIGH>",
        "Scope: <repo path/module/component or \"global\">",
    ]
    rules_required = [
        "### 7.3.4 Confidence + Impact Snapshot (Binding)",
        "[SNAPSHOT]",
        "Snapshot values MUST be consistent with `SESSION_STATE`",
    ]
    start_required = [
        "Include `[SNAPSHOT]` block (`Confidence`, `Risk`, `Scope`) with values aligned to current `SESSION_STATE`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing confidence-impact snapshot tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing confidence-impact snapshot tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing confidence-impact snapshot tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_quick_fix_commands_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Quick-fix commands (mandatory for blockers):",
        "QuickFixCommands",
        "1-3 copy-paste-ready commands",
        'QuickFixCommands: ["none"]',
        "Command coherence rule: `[NEXT-ACTION].Command`, blocker `next_command`, and `QuickFixCommands[0]` MUST be identical",
    ]
    rules_required = [
        "### 7.3.5 Quick-Fix Commands for Blockers (Binding)",
        "`QuickFixCommands` with 1-3 exact copy-paste commands aligned to the active `reason_code`.",
        'output `QuickFixCommands: ["none"]`.',
        "Command coherence rule: `[NEXT-ACTION].Command`, blocker `next_command`, and `QuickFixCommands[0]` MUST match exactly",
    ]
    start_required = [
        "If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `[\"none\"]` if not command-driven).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing quick-fix command tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing quick-fix command tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing quick-fix command tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_architect_autopilot_lifecycle_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "### 2.4.2 Architect-Only Autopilot Lifecycle (Binding)",
        "SESSION_STATE.OutputMode = ARCHITECT | IMPLEMENT | VERIFY",
        "Default after `/master` is `ARCHITECT`.",
        "BLOCKED-START-REQUIRED",
        "BLOCKED-MISSING-DECISION",
    ]
    rules_required = [
        "### 7.3.6 Architect-Only Autopilot Lifecycle (Binding)",
        "`SESSION_STATE.OutputMode = ARCHITECT | IMPLEMENT | VERIFY`",
        "`/master` before valid `/start` bootstrap evidence MUST block with `BLOCKED-START-REQUIRED`",
        "`IMPLEMENT` mode requires explicit operator trigger (`Implement now`).",
        "`VERIFY` mode is evidence reconciliation only.",
    ]
    start_required = [
        "`/start` is mandatory before `/master` for a repo/session; `/master` without valid `/start` evidence MUST map to `BLOCKED-START-REQUIRED`",
        "Canonical operator lifecycle: `/start` -> `/master` (ARCHITECT) -> `Implement now` (IMPLEMENT) -> `Ingest evidence` (VERIFY).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing architect-autopilot lifecycle tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing architect-autopilot lifecycle tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing architect-autopilot lifecycle tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )

    schema_required = [
        "`SESSION_STATE.OutputMode` (enum; see Section 4.1)",
        "## 4.1 OutputMode (enum)",
        "`ARCHITECT`",
        "`IMPLEMENT`",
        "`VERIFY`",
        "If `OutputMode = ARCHITECT`, `DecisionSurface` MUST be present",
    ]
    missing_schema = [t for t in schema_required if t not in schema]
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing architect-autopilot lifecycle tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


def test_audit_reason_keys_are_declared_audit_only_and_not_reason_code_payloads():
    text = read_text(REPO_ROOT / "diagnostics" / "audit.md")
    required_tokens = [
        "Reason key semantics (binding):",
        "audit-only diagnostics keys",
        "They are NOT canonical governance `reason_code` values",
        "MUST NOT be written into `SESSION_STATE.Diagnostics.ReasonPayloads.reason_code`",
        "auditReasonKey `BR_MISSING_SESSION_GATE_STATE`",
        "auditReasonKey `BR_MISSING_RULEBOOK_RESOLUTION`",
        "auditReasonKey `BR_SCOPE_ARTIFACT_MISSING`",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "diagnostics/audit.md missing audit reason-key boundary tokens:\n" + "\n".join(
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
        "RULEBOOK-PRECEDENCE-POLICY",
        "ADDON-CLASS-BEHAVIOR-POLICY",
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
