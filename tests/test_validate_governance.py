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
def test_why_blocked_requires_brief_then_detail_layering():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        "Response SHOULD be layered:",
        "brief layer first: one-line blocker summary + one primary recovery command",
        "detail layer second: full trace/evidence payload",
    ]
    rules_required = [
        "start with a concise blocker brief (reason + one primary recovery command)",
        "then provide full detail payload (facts, trace, evidence pointers)",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]

    assert not missing_master, "master.md missing /why-blocked brief-detail tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing /why-blocked brief-detail tokens:\n" + "\n".join(
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

    identity_map_file = cfg / "workspaces" / repo_fp / "repo-identity-map.yaml"
    assert identity_map_file.exists(), "Expected repo identity map to be created in repo workspace"
    identity_map = json.loads(read_text(identity_map_file))
    assert identity_map.get("schema") == "opencode-repo-identity-map.v1"
    repos = identity_map.get("repositories")
    assert isinstance(repos, dict)
    assert repo_fp in repos
    assert repos[repo_fp].get("repoName") == repo_fp

    data = json.loads(read_text(state_file))
    assert "SESSION_STATE" in data and isinstance(data["SESSION_STATE"], dict)
    ss = data["SESSION_STATE"]

    required_keys = [
        "session_state_version",
        "ruleset_hash",
        "Phase",
        "Mode",
        "ConfidenceLevel",
        "Next",
        "OutputMode",
        "DecisionSurface",
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
    assert ss["Next"] == "BLOCKED-START-REQUIRED"
    assert ss["OutputMode"] == "ARCHITECT"
    assert ss["session_state_version"] == 1
    assert isinstance(ss["ruleset_hash"], str) and ss["ruleset_hash"]
    assert isinstance(ss["DecisionSurface"], dict)
    rle = ss["RulebookLoadEvidence"]
    assert isinstance(rle.get("top_tier"), dict)
    assert rle["top_tier"].get("quality_index") == "${COMMANDS_HOME}/QUALITY_INDEX.md"
    assert rle["top_tier"].get("conflict_resolution") == "${COMMANDS_HOME}/CONFLICT_RESOLUTION.md"


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
def test_workspace_persistence_backfill_writes_business_rules_when_phase15_extracted(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_fp = "phase15-repo-999999"

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

    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--config-root", str(cfg), "--quiet"])
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    actions = payload.get("actions", {})
    assert actions.get("businessRulesInventory") in {"created", "kept", "overwritten"}

    business_rules = workspace / "business-rules.md"
    assert business_rules.exists(), "business-rules.md should be written when Phase 1.5 is extracted"
    text = business_rules.read_text(encoding="utf-8")
    assert "SchemaVersion: BRINV-1" in text
    assert "Source: Phase 1.5 Business Rules Discovery" in text

    updated = json.loads(session_file.read_text(encoding="utf-8"))
    ss = updated["SESSION_STATE"]
    br = ss.get("BusinessRules", {})
    assert br.get("InventoryFilePath") == "${REPO_BUSINESS_RULES_FILE}"
    assert br.get("InventoryFileStatus") == "written"


@pytest.mark.governance
def test_workspace_persistence_normalizes_legacy_placeholder_phrasing_without_force(tmp_path: Path):
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    cfg = tmp_path / "opencode-config"
    repo_fp = "normalize-placeholders-001"

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

    r = run([sys.executable, str(script), "--repo-fingerprint", repo_fp, "--config-root", str(cfg), "--quiet"])
    assert r.returncode == 0, f"persist_workspace_artifacts.py failed:\nSTDERR:\n{r.stderr}\nSTDOUT:\n{r.stdout}"

    payload = json.loads(r.stdout)
    actions = payload.get("actions", {})
    assert actions.get("repoCache") == "normalized"
    assert actions.get("decisionPack") == "normalized"

    cache_text = cache_file.read_text(encoding="utf-8")
    decision_text = decision_file.read_text(encoding="utf-8")
    assert "Backfill placeholder: refresh after Phase 2 discovery." not in cache_text
    assert "Seed snapshot: refresh after evidence-backed Phase 2 discovery." in cache_text
    assert "Backfill initialization only" not in decision_text
    assert "Bootstrap seed only" in decision_text


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
    assert isinstance(payload.get("missing_evidence"), list) and len(payload["missing_evidence"]) >= 1
    assert isinstance(payload.get("recovery_steps"), list) and len(payload["recovery_steps"]) >= 1
    assert isinstance(payload.get("required_operator_action"), str) and payload["required_operator_action"].strip()
    assert isinstance(payload.get("feedback_required"), str) and payload["feedback_required"].strip()
    assert isinstance(payload.get("next_command"), str) and payload["next_command"].strip()


@pytest.mark.governance
def test_start_md_includes_workspace_persistence_autohook():
    text = "\n".join(
        [
            read_text(REPO_ROOT / "start.md"),
            read_text(REPO_ROOT / "diagnostics" / "start_preflight_persistence.py"),
        ]
    )
    required_tokens = [
        "Auto-Persistence Hook (OpenCode)",
        "persist_workspace_artifacts.py",
        "bootstrap_session_state.py",
        "--repo-root",
        "--no-session-update",
        "workspacePersistenceHook",
        "preflight",
        "available",
        "missing",
        "impact",
        "next",
        "WARN-WORKSPACE-PERSISTENCE",
        "bootstrap-session-failed",
        "missing-git-for-identity-bootstrap",
        "identity-bootstrap-fingerprint-missing",
        "identity-bootstrap-failed",
        "ERR-WORKSPACE-PERSISTENCE-MISSING-IDENTITY-MAP",
        "required_operator_action",
        "feedback_required",
        "ERR-WORKSPACE-PERSISTENCE-HOOK-MISSING",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "start.md missing workspace persistence auto-hook tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_start_md_resolves_installed_diagnostics_helpers_not_workspace_relative_paths():
    text = read_text(REPO_ROOT / "start.md")

    forbidden = [
        "python3 diagnostics/start_binding_evidence.py",
        "python3 diagnostics/start_preflight_persistence.py",
    ]
    found_forbidden = [token for token in forbidden if token in text]
    assert not found_forbidden, "start.md still uses workspace-relative diagnostics helper paths:\n" + "\n".join(
        [f"- {m}" for m in found_forbidden]
    )

    required = [
        "commands'/'diagnostics'/'start_binding_evidence.py",
        "commands'/'diagnostics'/'start_preflight_persistence.py",
        "runpy.run_path",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, "start.md missing installed diagnostics helper resolution tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_start_prefers_host_binding_evidence_and_defers_profile_selection_at_bootstrap():
    text = read_text(REPO_ROOT / "start.md")
    required_tokens = [
        "`/start` MUST attempt host-provided evidence first and MUST NOT request operator-provided variable binding before that attempt.",
        "rules.md` load evidence is deferred until Phase 4.",
        "`/start` MUST NOT require explicit profile selection to complete bootstrap when `master.md` bootstrap evidence is available",
        "paste the full file contents for master.md (bootstrap minimum); defer rules.md/profile rulebook contents to their phase gates",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "start.md missing bootstrap evidence/profile deferral tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_unambiguous_profile_rulebooks_are_auto_loaded_without_operator_prompt():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Rulebook auto-load behavior (binding):",
        "MUST auto-load core/profile rulebooks from canonical installer paths without asking the operator to provide rulebook files.",
    ]
    rules_required = [
        "Unambiguous rulebook auto-load (binding):",
        "MUST NOT ask the operator to provide/paste rulebook files.",
    ]
    start_required = [
        "`/start` MUST auto-load canonical rulebooks and MUST NOT request operator rulebook paste/path input.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing unambiguous rulebook auto-load tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing unambiguous rulebook auto-load tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing unambiguous rulebook auto-load tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_start_invocation_guard_prevents_repeat_start_prompt_in_same_turn():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "`/start` invocation guard (binding):",
        "MUST NOT ask operator to run `/start` again in the same turn.",
    ]
    rules_required = [
        "## 7.11.1 /start Re-invocation Loop Guard (Core, Binding)",
        "MUST NOT ask operator to run `/start` again in the same turn.",
    ]
    start_required = [
        "Command invocation guard (binding): when `start.md` is injected by the `/start` command, treat `/start` as already invoked in this turn.",
        "assistant MUST NOT request the operator to run `/start` again",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing /start invocation guard tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing /start invocation guard tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing /start invocation guard tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_profile_autodetect_runs_before_manual_selection_prompt():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Autodetect-first refinement (binding):",
        "Attempt deterministic repo-signal ranking before asking operator.",
        "auto-select without operator prompt",
    ]
    rules_required = [
        "first attempt deterministic ranking from repo signals and ticket/context signals; if one top profile is uniquely supported, auto-select it",
    ]
    start_required = [
        "`/start` MUST attempt deterministic repo-signal autodetection first and auto-select when one candidate is uniquely supported.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing profile autodetect-first tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing profile autodetect-first tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing profile autodetect-first tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_rules_define_deterministic_backend_java_default_when_unambiguous():
    text = read_text(REPO_ROOT / "rules.md")
    required_tokens = [
        "Deterministic Java default (binding):",
        "the assistant SHOULD set active profile to `backend-java` without requesting explicit profile selection.",
        "Explicit profile-selection prompts are required only when repository indicators are materially ambiguous",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "rules.md missing deterministic backend-java default tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_phase2_prefers_host_repo_root_before_manual_path_prompt():
    text = read_text(REPO_ROOT / "master.md")
    required_tokens = [
        "Repo root defaulting behavior (binding):",
        "Phase 2 MUST use that path as the default `RepoRoot` candidate.",
        "MUST request filesystem/access authorization (if required by host policy)",
        "Operator path prompts are allowed only when no host-provided repository root is available",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "master.md missing Phase-2 repo-root defaulting tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_phase21_does_not_require_ticket_goal_and_defers_mandatory_ticket_to_phase4():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        "Ticket-goal handling in Phase 2.1 (binding):",
        "Phase 2.1 MUST execute automatically from Phase 2 evidence and MUST NOT require explicit `ticketGoal` input.",
        "`ticketGoal` becomes mandatory at Phase 4 entry (Step 0)",
    ]
    rules_required = [
        "Phase 2.1 ticket-goal policy (binding):",
        "Phase 2.1 Decision Pack generation MUST NOT block on missing `ticketGoal`.",
        "In Phase 1.5 / 2 / 2.1 / 3A / 3B, the assistant MUST NOT request \"provide ticket\" or \"provide change request\" as `NextAction`.",
        "`ticketGoal` is REQUIRED at Phase 4 entry (Step 0)",
    ]

    missing_master = [token for token in master_required if token not in master]
    missing_rules = [token for token in rules_required if token not in rules]
    assert not missing_master, "master.md missing Phase-2.1 ticket-goal deferral tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing Phase-2.1 ticket-goal deferral tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )


@pytest.mark.governance
def test_phase2_and_phase15_do_not_force_ticket_prompt_without_ticket_goal():
    master = read_text(REPO_ROOT / "master.md")
    required_tokens = [
        "otherwise → Phase 3A (auto-not-applicable path allowed) then continue to Phase 3B routing",
        "ticket prompt is deferred until Phase 4 entry.",
        "Otherwise: Proceed to Phase 3A (auto-not-applicable path allowed), then continue to Phase 3B routing",
    ]
    missing = [t for t in required_tokens if t not in master]
    assert not missing, "master.md missing no-early-ticket-prompt tokens for Phase 2/1.5 exits:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_phase15_requires_repo_code_evidence_and_forbids_readme_only_extraction():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    master_required = [
        "Phase 1.5 evidence source contract (binding):",
        "The assistant MUST read repository code/tests for Business Rules extraction.",
        "README-only/documentation-only rules MUST NOT be counted as extracted business rules.",
        "Any rule lacking repository code evidence MUST be marked `CANDIDATE`",
    ]
    rules_required = [
        "Repository documentation (`README*`, `CONTRIBUTING*`, `AGENTS*`, comments) MUST NOT be used as sole evidence for BR extraction.",
        "README-only/documentation-only BRs MUST be marked `CANDIDATE` and MUST NOT count as extracted `ACTIVE` rules.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    assert not missing_master, "master.md missing Phase-1.5 code-evidence tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing BR extraction evidence-source tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )


@pytest.mark.governance
def test_start_md_fallback_binding_and_identity_evidence_boundaries_are_fail_closed():
    text = "\n".join(
        [
            read_text(REPO_ROOT / "start.md"),
            read_text(REPO_ROOT / "diagnostics" / "start_binding_evidence.py"),
        ]
    )

    required_tokens = [
        "Fallback computed payloads are debug output only (`nonEvidence`) and MUST NOT be treated as binding evidence.",
        "If installer-owned binding file is missing, workflow MUST block with `BLOCKED-MISSING-BINDING-FILE`",
        "Helper output is operational convenience status only and MUST NOT be treated as canonical repo identity evidence.",
        "Repo identity remains governed by `master.md` evidence contracts",
    ]
    missing = [token for token in required_tokens if token not in text]

    token_alternatives = [
        ["'reason_code':'BLOCKED-MISSING-BINDING-FILE'", '"reason_code": "BLOCKED-MISSING-BINDING-FILE"'],
        ["'reason_code':'BLOCKED-VARIABLE-RESOLUTION'", '"reason_code": "BLOCKED-VARIABLE-RESOLUTION"'],
        [
            "'missing_evidence':['${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)']",
            '"${COMMANDS_HOME}/governance.paths.json (installer-owned binding evidence)"',
        ],
        ["'next_command':'/start'", '"next_command": "/start"'],
        ["'nonEvidence':'debug-only'", '"nonEvidence": "debug-only"'],
    ]
    for choices in token_alternatives:
        if not any(token in text for token in choices):
            missing.append(choices[0])

    assert not missing, "start.md missing evidence-boundary fail-closed tokens:\n" + "\n".join([f"- {m}" for m in missing])

    forbidden_tokens = [
        "Treat it as **evidence**.",
        "# last resort: compute the same payload that the installer would write",
        "or provide operator binding evidence plus filesystem proof artifacts",
        "paste the full file contents for master.md, rules.md, and the selected profile.",
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
        "End every response with `[NEXT-ACTION]` footer (`Status`, `Next`, `Why`, `Command`) per `master.md` (also required in COMPAT mode)",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing next-action footer tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing next-action footer tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing next-action footer tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_short_status_tag_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Responses SHOULD include a compact deterministic `status_tag` (`<PHASE>-<GATE>-<STATE>`) for quick operator scanning",
    ]
    rules_required = [
        "Deterministic short status tag (recommended):",
        "Format: `<PHASE>-<GATE>-<STATE>` (uppercase, hyphen-separated).",
        "Example: `P2-PROFILE-DETECTION-WARN`.",
    ]
    start_required = [
        "Responses SHOULD include a compact `status_tag` for scanability (`<PHASE>-<GATE>-<STATE>`).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing status-tag contract tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing status-tag contract tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing status-tag contract tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_quick_fix_confidence_labels_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Blocked recovery guidance SHOULD label primary quick-fix command confidence as `safe` or `review-first`",
    ]
    rules_required = [
        "Quick-fix confidence labeling (recommended):",
        "`safe` (read-only or low-risk local command)",
        "`review-first` (mutating command that should be reviewed before execution)",
    ]
    start_required = [
        "When `QuickFixCommands` are emitted, `/start` SHOULD label primary command confidence as `safe` or `review-first`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing quick-fix confidence tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing quick-fix confidence tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing quick-fix confidence tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_next_action_wording_quality_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "`NextAction` wording SHOULD include concrete context (active phase/gate/scope) and avoid generic continuation text",
    ]
    rules_required = [
        "NextAction wording quality (binding):",
        "`NextAction.Next` and `[NEXT-ACTION].Why` SHOULD be context-specific, not generic.",
        "Avoid placeholder phrasing like \"continue\" without target context.",
    ]
    start_required = [
        "`NextAction` wording SHOULD include concrete context (active phase/gate/scope) rather than generic continuation text.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing next-action wording quality tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing next-action wording quality tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing next-action wording quality tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_compact_transition_line_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "On phase/mode changes, responses SHOULD include a compact one-line transition summary (`[TRANSITION] from -> to | reason: ...`)",
    ]
    rules_required = [
        "Compact transition line (recommended):",
        "`[TRANSITION] <from> -> <to> | reason: <short reason>`",
    ]
    start_required = [
        "On phase/mode changes, response SHOULD include a compact transition line: `[TRANSITION] <from> -> <to> | reason: <short reason>`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing transition-line tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing transition-line tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing transition-line tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_state_unchanged_ack_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "If state does not change, responses SHOULD acknowledge `state_unchanged` with a concise reason",
    ]
    rules_required = [
        "No-change acknowledgment (recommended):",
        "explicitly state `state_unchanged` with a one-line reason.",
    ]
    start_required = [
        "If no phase/mode/gate transition occurred, response SHOULD acknowledge `state_unchanged` with a concise reason.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing state-unchanged tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing state-unchanged tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing state-unchanged tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_conversational_post_start_fixtures_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Conversational post-start intents SHOULD remain regression-tested with deterministic fixtures (`what_phase`, `discovery_done`, `workflow_unchanged`)",
        "Preferred fixture source for conversational intent goldens: `diagnostics/UX_INTENT_GOLDENS.json`",
    ]
    rules_required = [
        "### 7.3.18 Conversational UX Regression Fixtures (Binding)",
        "`what_phase`",
        "`discovery_done`",
        "`workflow_unchanged`",
        "keeps canonical status vocabulary (`BLOCKED|WARN|OK|NOT_VERIFIED`)",
        "canonical fixture source SHOULD be `diagnostics/UX_INTENT_GOLDENS.json`",
    ]
    start_required = [
        "Conversational post-start replies SHOULD stay covered by deterministic fixture intents (`what_phase`, `discovery_done`, `workflow_unchanged`).",
        "Preferred conversational fixture source: `diagnostics/UX_INTENT_GOLDENS.json`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing conversational fixture tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing conversational fixture tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing conversational fixture tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_governance_pr_operator_impact_note_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "For PRs that modify governance rulebooks/contracts, PR body SHOULD include `What changed for operators?`",
    ]
    rules_required = [
        "Governance-change PR operator-impact note (recommended):",
        "`What changed for operators?`",
        "2-5 bullets focused on operator-visible behavior changes.",
    ]
    start_required = [
        "When preparing a PR that changes governance contracts, response SHOULD include an operator-impact section (`What changed for operators?`).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing governance PR operator-impact tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing governance PR operator-impact tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing governance PR operator-impact tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_short_intent_routing_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Short operator follow-up questions SHOULD route through deterministic intents (`where_am_i`, `what_blocks_me`, `what_now`) before verbose diagnostics",
    ]
    rules_required = [
        "### 7.3.19 Short-Intent Routing for Operator Questions (Binding)",
        "`where_am_i`",
        "`what_blocks_me`",
        "`what_now`",
    ]
    start_required = [
        "Short follow-up questions SHOULD route via deterministic intents (`where_am_i`, `what_blocks_me`, `what_now`) before optional verbose diagnostics.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing short-intent routing tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing short-intent routing tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing short-intent routing tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_phase_progress_bar_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Responses SHOULD include a compact phase progress bar (`phase_progress_bar`, e.g. `[##----] 2/6`) for quick orientation",
    ]
    rules_required = [
        "Recommended compact progress bar:",
        "`phase_progress_bar`",
        "`[##----] 2/6`",
    ]
    start_required = [
        "Responses SHOULD include `phase_progress_bar` (for example: `[##----] 2/6`) aligned to the current phase.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing progress-bar tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing progress-bar tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing progress-bar tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_primary_blocker_prioritization_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "For multi-blocker states, responses MUST prioritize one primary blocker (`primary_reason_code`) with a single primary recovery command",
    ]
    rules_required = [
        "Top-1 blocker prioritization (binding):",
        "`primary_reason_code`",
        "`next_command` and `QuickFixCommands[0]` MUST target the same primary blocker.",
    ]
    start_required = [
        "If multiple blockers exist, `/start` SHOULD present one `primary_reason_code` first and keep one primary recovery command.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing primary-blocker tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing primary-blocker tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing primary-blocker tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_reason_code_quickfix_template_catalog_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Recovery guidance SHOULD source reason-specific command templates from `diagnostics/QUICKFIX_TEMPLATES.json` when available",
    ]
    rules_required = [
        "Reason-code quick-fix template catalog (recommended):",
        "`diagnostics/QUICKFIX_TEMPLATES.json`",
        "Template lookup key is canonical `reason_code`.",
    ]
    start_required = [
        "`/start` SHOULD use `diagnostics/QUICKFIX_TEMPLATES.json` for reason-code-specific recovery command text when available.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing quickfix-template catalog tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing quickfix-template catalog tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing quickfix-template catalog tokens:\n" + "\n".join([f"- {m}" for m in missing_start])

    catalog = REPO_ROOT / "diagnostics" / "QUICKFIX_TEMPLATES.json"
    assert catalog.exists(), "diagnostics/QUICKFIX_TEMPLATES.json missing"
    payload = json.loads(read_text(catalog))
    assert payload.get("$schema") == "opencode.quickfix-templates.v1"
    assert isinstance(payload.get("templates"), dict) and payload["templates"], "Quick-fix templates catalog is empty"


@pytest.mark.governance
def test_no_change_delta_only_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "For no-change turns, responses SHOULD be delta-only and avoid repeating unchanged diagnostic blocks",
    ]
    rules_required = [
        "In no-change cases, response SHOULD be delta-only (only what changed, or explicitly `no_delta`).",
    ]
    start_required = [
        "For no-change turns, response SHOULD be delta-only (or explicit `no_delta`) instead of repeating unchanged diagnostics.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing no-change delta-only tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing no-change delta-only tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing no-change delta-only tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_operator_persona_modes_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Responses SHOULD support operator persona modes (`compact`, `standard`, `audit`) as presentation-density controls without changing gate behavior",
    ]
    rules_required = [
        "### 7.3.20 Operator Persona Response Modes (Binding)",
        "`compact` (minimal concise output)",
        "`standard` (default balanced output)",
        "`audit` (full diagnostic detail)",
    ]
    start_required = [
        "Response persona modes SHOULD be supported (`compact`, `standard`, `audit`) as presentation-density controls only.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing persona-mode tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing persona-mode tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing persona-mode tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_governance_pr_reviewer_focus_hints_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Governance PRs SHOULD also include `Reviewer focus` bullets that point to highest-risk contract changes.",
    ]
    rules_required = [
        "Governance-change PR reviewer-focus hints (recommended):",
        "`Reviewer focus`",
        "Hints SHOULD reference concrete files/sections to speed targeted review.",
    ]
    start_required = [
        "Governance PR summaries SHOULD also include `Reviewer focus` bullets for highest-risk contract deltas.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing PR reviewer-focus tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing PR reviewer-focus tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing PR reviewer-focus tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_start_and_master_require_host_git_identity_discovery_before_operator_prompt():
    master = read_text(REPO_ROOT / "master.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "attempt host-side identity discovery first when tool access is available",
        "git remote get-url origin",
        "git symbolic-ref refs/remotes/origin/HEAD",
        "git rev-parse --show-toplevel",
        "destructive or mutating git commands during identity collection",
        "Bootstrap tool preflight (binding):",
        "runtime MUST probe required external commands via PATH",
        "preflight result MUST be reported as structured diagnostics",
        "MUST NOT block by itself",
        "Required-command inventory derivation (binding):",
        "MUST load a deterministic command inventory from `${COMMANDS_HOME}/diagnostics/tool_requirements.json`",
        "If that file is unavailable, `/start` MUST fail over to deriving the inventory by scanning canonical governance artifacts",
        "`required_now` (bootstrap/runtime essentials)",
        "`required_later` (phase/profile-gated tools)",
        "`optional` (advisory)",
        "rerunning `/start` MUST refresh the inventory/probe and continue without stale blocker state",
    ]
    start_required = [
        "Identity discovery order (binding):",
        "`/start` MUST collect repo identity evidence first via non-destructive git commands",
        "before requesting operator-provided evidence",
        "MUST block with identity-missing reason and provide copy-paste recovery commands",
        "Bootstrap command preflight (binding):",
        "`/start` MUST check required external commands in `PATH` first",
        "`/start` MUST load command requirements from `${COMMANDS_HOME}/diagnostics/tool_requirements.json` when available",
        "If `diagnostics/tool_requirements.json` is unavailable, `/start` MUST derive the command list by scanning canonical governance artifacts",
        "`required_now`, `required_later`, and `optional`",
        "MUST print the resolved command inventory and probe result (`available`/`missing`)",
        "Preflight diagnostics are informational and MUST NOT create a blocker by themselves",
        "`preflight: ok`",
        "`preflight: degraded`",
        "rerunning `/start` MUST recompute the inventory from files",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing host git identity-discovery tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_start, "start.md missing host git identity-discovery tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_tool_requirements_catalog_exists_and_has_required_sections():
    p = REPO_ROOT / "diagnostics" / "tool_requirements.json"
    assert p.exists(), "Missing diagnostics/tool_requirements.json"

    payload = json.loads(read_text(p))
    assert payload.get("schema") == "opencode-tool-requirements.v1", "Unexpected tool requirements schema"
    assert "smart_retry" in payload and isinstance(payload["smart_retry"], dict), "tool_requirements.json missing smart_retry object"
    assert payload["smart_retry"].get("path_snapshot_policy") == "fresh-per-start", "smart_retry.path_snapshot_policy must be fresh-per-start"

    for key in ["required_now", "required_later", "optional"]:
        assert key in payload, f"tool_requirements.json missing key: {key}"
        assert isinstance(payload[key], list), f"tool_requirements.json key must be a list: {key}"

    required_now_cmds = {str(x.get("command", "")).strip() for x in payload["required_now"] if isinstance(x, dict)}
    assert "git" in required_now_cmds, "tool_requirements.json required_now must include git"
    assert "python3" in required_now_cmds, "tool_requirements.json required_now must include python3"

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
    catalog_path = REPO_ROOT / "diagnostics" / "tool_requirements.json"
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
        REPO_ROOT / "start.md",
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
        + "\nAdd each command to diagnostics/tool_requirements.json (required_now/required_later/optional)."
    )


@pytest.mark.governance
def test_bootstrap_preflight_output_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Preflight executes as Phase `0` / `1.1`",
        "Tool probe TTL is zero (`ttl=0`)",
        "Preflight MUST include an `observed_at` timestamp",
        "Preflight output MUST remain compact: maximum 5 checks.",
        "Preflight summary format is fixed to these keys: `available`, `missing`, `impact`, `next`.",
        "Smart retry guidance is mandatory: missing-tool diagnostics MUST include `expected_after_fix` and `restart_hint`.",
        "`restart_required_if_path_edited`",
        "`no_restart_if_binary_in_existing_path`",
    ]
    rules_required = [
        "### 7.3.10 Bootstrap Preflight Output Contract (Binding)",
        "Preflight probes MUST be fresh (`ttl=0`)",
        "Preflight MUST include `observed_at` (timestamp) in diagnostics/state.",
        "Preflight MUST report at most 5 checks.",
        "`available: <comma-separated commands or none>`",
        "`missing: <comma-separated commands or none>`",
        "`impact: <one concise sentence>`",
        "`next: <single concrete next step>`",
        "Missing `required_now` commands are blocker-fix candidates.",
        "Missing `required_later` commands are advisory",
        "### 7.3.13 Smart Retry + Restart Guidance (Binding)",
        "`expected_after_fix` (machine-readable success signal)",
        "`verify_command` (exact command to confirm recovery)",
        "`restart_hint` (enum):",
    ]
    start_required = [
        "Preflight MUST run in Phase `0` / `1.1`",
        "fresh probe signals only (`ttl=0`) and `observed_at` timestamp",
        "Preflight output MUST stay compact (max 5 checks)",
        "fixed keys: `available`, `missing`, `impact`, `next`.",
        "Missing-command diagnostics MUST include `expected_after_fix`, `verify_command`, and `restart_hint`.",
        "`restart_hint` MUST be deterministic: `restart_required_if_path_edited` or `no_restart_if_binary_in_existing_path`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing preflight output contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing preflight output contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing preflight output contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_status_vocab_and_single_nextaction_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Governance status vocabulary is fixed: `BLOCKED | WARN | OK | NOT_VERIFIED`",
        "WARN/blocked separation is strict: required missing evidence => BLOCKED (not WARN)",
        "Each response MUST emit exactly one NextAction mechanism: `command` OR `reply_with_one_number` OR `manual_step`",
        "In COMPAT mode, `NextAction` MUST still resolve to exactly one mechanism",
    ]
    rules_required = [
        "### 7.3.11 Deterministic Status + NextAction Contract (Binding)",
        "Canonical governance status vocabulary (enum):",
        "`BLOCKED`",
        "`WARN`",
        "`OK`",
        "`NOT_VERIFIED`",
        "`WARN` MUST NOT carry required-gate missing evidence",
        "`BLOCKED` MUST include exactly one `reason_code`",
        "exactly one concrete recovery action sentence",
        "one primary copy-paste command",
        "QuickFixCommands",
        "Each response MUST emit exactly one `NextAction` mechanism",
        "`command`, or",
        "`reply_with_one_number`, or",
        "`manual_step`.",
    ]
    start_required = [
        "Status vocabulary MUST remain deterministic: `BLOCKED | WARN | OK | NOT_VERIFIED`.",
        "`WARN` MUST NOT be used when required-gate evidence is missing",
        "Exactly one `NextAction` mechanism is allowed per response",
        "If blocked, use exactly one `reason_code`, one concrete recovery action sentence, and one primary copy-paste command.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing deterministic status/nextaction tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing deterministic status/nextaction tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing deterministic status/nextaction tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_session_transition_invariant_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    master_required = [
        "Session transitions are invariant-checked",
        "stable `session_run_id`",
        "stable `ruleset_hash` unless explicit rehydrate",
        "transition trace entries with `transition_id`",
    ]
    rules_required = [
        "### 7.3.12 Session Transition Invariants (Binding)",
        "`SESSION_STATE.session_run_id` MUST remain stable until verify completes.",
        "`SESSION_STATE.ruleset_hash` MUST remain stable unless explicit rehydrate/reload is performed.",
        "`SESSION_STATE.ActivationDelta.AddonScanHash`",
        "`SESSION_STATE.ActivationDelta.RepoFactsHash`",
        "Every phase/mode transition MUST record a unique `transition_id`",
        "`transition_id` (unique string)",
    ]
    start_required = [
        "Across lifecycle transitions, `session_run_id` and `ruleset_hash` MUST remain stable unless explicit rehydrate/reload is performed.",
        "Every phase/mode transition MUST record a unique `transition_id` diagnostic entry.",
    ]
    schema_required = [
        "### 2.1.4 Transition trace invariants (binding)",
        "`SESSION_STATE.session_run_id` SHOULD be present and MUST remain stable until verify completion.",
        "`SESSION_STATE.ruleset_hash` MUST remain stable unless explicit rehydrate/reload is performed.",
        "`SESSION_STATE.Diagnostics.TransitionTrace[]`",
        "`transition_id` (unique string)",
        "`from_phase`",
        "`to_phase`",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]
    missing_schema = [t for t in schema_required if t not in schema]

    assert not missing_master, "master.md missing transition invariant tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing transition invariant tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing transition invariant tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing transition invariant tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_phase_progress_and_warn_blocked_separation_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Responses include compact phase progress derived from `SESSION_STATE`",
        "`phase`, `active_gate`, `next_gate_condition`",
    ]
    rules_required = [
        "### 7.3.14 Phase Progress + Warn/Blocked Separation (Binding)",
        "`phase` (current `SESSION_STATE.Phase`)",
        "`active_gate` (current gate key or `none`)",
        "`next_gate_condition` (one concise sentence)",
        "`WARN` MUST NOT include required-gate `missing_evidence`.",
        "Required-gate missing evidence MUST produce `BLOCKED`.",
        "`WARN` MAY include `advisory_missing` only.",
        "`RequiredInputs` is for BLOCKED/COMPAT blocker outputs",
    ]
    start_required = [
        "Responses MUST include compact phase progress from `SESSION_STATE`: `phase`, `active_gate`, `next_gate_condition`.",
        "`WARN` may include `advisory_missing` only and MUST NOT emit blocker `RequiredInputs`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing phase-progress tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing warn/blocked separation tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing phase-progress or warn tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


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
        "If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`) when host constraints allow",
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
        "Default cardinality is one command.",
        "Use two commands only for explicit OS split",
        "prefix each command with `macos_linux:` or `windows:`",
    ]
    rules_required = [
        "### 7.3.5 Quick-Fix Commands for Blockers (Binding)",
        "`QuickFixCommands` with 1-3 exact copy-paste commands aligned to the active `reason_code`.",
        'output `QuickFixCommands: ["none"]`.',
        "Command coherence rule: `[NEXT-ACTION].Command`, blocker `next_command`, and `QuickFixCommands[0]` MUST match exactly",
        "Default cardinality is one command.",
        "Use two commands only for explicit OS split",
        "OS label (`macos_linux:` or `windows:`)",
    ]
    start_required = [
        "If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `[\"none\"]` if not command-driven) when host constraints allow.",
        "`QuickFixCommands` defaults to one command; use two only for explicit `macos_linux` vs `windows` splits.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing quick-fix command tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing quick-fix command tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing quick-fix command tokens:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_host_constraint_compat_mode_contract_is_defined_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "Host-constraint compatibility (binding):",
        "DEVIATION.host_constraint = true",
        "RequiredInputs",
        "Recovery",
        "NextAction",
        "COMPAT mode MUST still emit a `[NEXT-ACTION]` block with `Status`, `Next`, `Why`, and `Command` fields.",
        "Strict/compat mode matrix (binding):",
        "STRICT (default when host allows)",
        "Each response MUST declare exactly one output mode (`STRICT` or `COMPAT`).",
    ]
    rules_required = [
        "### 7.3.8 Host Constraint Compatibility Mode (Binding)",
        "DEVIATION.host_constraint = true",
        "COMPAT response shape (minimum required sections):",
        "RequiredInputs",
        "Recovery",
        "NextAction",
        "### 7.3.15 STRICT vs COMPAT Output Matrix (Binding)",
        "STRICT mode (host supports full formatting):",
        "COMPAT mode (`DEVIATION.host_constraint = true`):",
        "Response MUST declare exactly one mode (`STRICT` or `COMPAT`) per turn.",
    ]
    start_required = [
        "If strict output formatting is host-constrained, response MUST include COMPAT sections: `RequiredInputs`, `Recovery`, and `NextAction` and set `DEVIATION.host_constraint = true`.",
        "Response mode MUST be explicit and singular per turn: `STRICT` or `COMPAT`.",
        "`STRICT` requires envelope + `[SNAPSHOT]` + `[NEXT-ACTION]`; `COMPAT` requires `RequiredInputs` + `Recovery` + `NextAction` + `[NEXT-ACTION]`.",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing host-constraint compat tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing host-constraint compat tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing host-constraint compat tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_session_state_output_format_is_fenced_yaml_across_core_docs():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    master_required = [
        "If `SESSION_STATE` is emitted, it MUST still be rendered as fenced YAML",
        "`SESSION_STATE` blocks MUST NOT use placeholder tokens (`...`, `<...>`); unknown fields must be explicit (`unknown|deferred|not-applicable`).",
    ]
    rules_required = [
        "### 7.3.9 SESSION_STATE Formatting Contract (Binding)",
        "Whenever `SESSION_STATE` is emitted in assistant output, it MUST be rendered as a fenced YAML block.",
        "heading line: `SESSION_STATE`",
        "fenced block start: ````yaml",
        "payload root key: `SESSION_STATE:`",
        "Placeholder tokens like `...` or `<...>` are FORBIDDEN inside emitted `SESSION_STATE` blocks.",
        "If values are unknown/deferred, emit explicit values (`unknown`, `deferred`, `not-applicable`) rather than placeholders.",
    ]
    start_required = [
        "`SESSION_STATE` output MUST be formatted as fenced YAML (````yaml` + `SESSION_STATE:` payload)",
        "`SESSION_STATE` output MUST NOT use placeholder tokens (`...`, `<...>`); use explicit unknown/deferred values instead",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]

    assert not missing_master, "master.md missing SESSION_STATE formatting tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing SESSION_STATE formatting tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )
    assert not missing_start, "start.md missing SESSION_STATE formatting tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


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
        "`/start` is mandatory bootstrap for a repo/session.",
        "In hosts that support `/master`: `/master` without valid `/start` evidence MUST map to `BLOCKED-START-REQUIRED`",
        "OpenCode Desktop mapping (host-constrained): `/start` acts as the `/master`-equivalent and performs the ARCHITECT master-run inline.",
        "Canonical operator lifecycle (OpenCode Desktop): `/start` (bootstrap + ARCHITECT master-run) -> `Implement now` (IMPLEMENT) -> `Ingest evidence` (VERIFY).",
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


@pytest.mark.governance
def test_rulebook_discovery_is_restricted_to_trusted_roots():
    master = read_text(REPO_ROOT / "master.md")
    start = read_text(REPO_ROOT / "start.md")

    required_master = [
        "DO NOT read rulebooks from the repo working tree",
        "Rulebooks may only be loaded from trusted governance roots outside the repo working tree:",
        "${COMMANDS_HOME}",
        "${PROFILES_HOME}",
        "${REPO_OVERRIDES_HOME}",
    ]
    required_start = [
        "`/start` enforces installer-owned discovery roots (`${COMMANDS_HOME}`, `${PROFILES_HOME}`) as canonical entrypoint requirements.",
    ]

    missing_master = [t for t in required_master if t not in master]
    missing_start = [t for t in required_start if t not in start]
    assert not missing_master, "master.md missing trusted rulebook discovery tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_start, "start.md missing trusted rulebook discovery tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_start]
    )


@pytest.mark.governance
def test_addon_catalog_contract_is_canonical_and_forbids_generic_manifest_path():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")
    corpus = "\n".join([master, rules, start])

    required_tokens = [
        "${PROFILES_HOME}/addons/*.addon.yml",
        "addon_key",
        "addon_class",
        "rulebook",
        "owns_surfaces",
        "touches_surfaces",
    ]
    missing = [t for t in required_tokens if t not in corpus]
    assert not missing, "Core docs missing canonical addon catalog tokens:\n" + "\n".join([f"- {m}" for m in missing])

    forbidden_tokens = ["addons/manifest.yaml", "addons/manifest.yml", "/addons/manifest.yaml"]
    found = [t for t in forbidden_tokens if t in corpus]
    assert not found, "Core docs reference forbidden non-canonical addon manifest path(s):\n" + "\n".join(
        [f"- {m}" for m in found]
    )


@pytest.mark.governance
def test_canonical_response_envelope_schema_contract_is_defined():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")
    schema_path = REPO_ROOT / "diagnostics" / "RESPONSE_ENVELOPE_SCHEMA.json"
    assert schema_path.exists(), "Missing diagnostics/RESPONSE_ENVELOPE_SCHEMA.json"
    schema_text = read_text(schema_path)

    docs_required = [
        "diagnostics/RESPONSE_ENVELOPE_SCHEMA.json",
        "status",
        "session_state",
        "next_action",
        "next_action.type",
        "snapshot",
    ]
    corpus = "\n".join([master, rules, start])
    missing_docs = [t for t in docs_required if t not in corpus]
    assert not missing_docs, "Docs missing response envelope schema references:\n" + "\n".join(
        [f"- {m}" for m in missing_docs]
    )

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
def test_rulebook_load_evidence_gate_is_fail_closed():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")

    required_master = [
        "### Rulebook Load Evidence (BINDING)",
        "RulebookLoadEvidence",
        "BLOCKED-RULEBOOK-EVIDENCE-MISSING",
        "No phase completion may be claimed.",
    ]
    required_rules = [
        "## 7.17 Rulebook Load Evidence Gate (Core, Binding)",
        "RulebookLoadEvidence",
        "BLOCKED-RULEBOOK-EVIDENCE-MISSING",
        "no phase completion may be claimed",
    ]

    missing_master = [t for t in required_master if t not in master]
    missing_rules = [t for t in required_rules if t not in rules]
    assert not missing_master, "master.md missing fail-closed rulebook evidence gate tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_rules, "rules.md missing fail-closed rulebook evidence gate tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_rules]
    )


@pytest.mark.governance
def test_top_tier_quality_index_claim_requires_loadable_scope_and_evidence_contract():
    master = read_text(REPO_ROOT / "master.md")
    schema = read_text(REPO_ROOT / "SESSION_STATE_SCHEMA.md")

    required_master = [
        "QUALITY_INDEX.md",
        "CONFLICT_RESOLUTION.md",
        "Top-tier load evidence obligation (binding):",
        "SESSION_STATE.RulebookLoadEvidence.top_tier",
    ]
    required_schema = [
        "RulebookLoadEvidence:",
        "top_tier:",
        "quality_index",
        "conflict_resolution",
    ]
    missing_master = [t for t in required_master if t not in master]
    missing_schema = [t for t in required_schema if t not in schema]

    assert not missing_master, "master.md missing top-tier load evidence contract tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_master]
    )
    assert not missing_schema, "SESSION_STATE_SCHEMA.md missing top-tier evidence shape tokens:\n" + "\n".join(
        [f"- {m}" for m in missing_schema]
    )


@pytest.mark.governance
def test_phase4_missing_quality_index_is_fail_closed():
    master = read_text(REPO_ROOT / "master.md")
    required = [
        "In Phase 4+ (code/evidence/gates), unresolved top-tier files MUST block with `BLOCKED-MISSING-RULEBOOK:<file>`.",
        "QUALITY_INDEX.md",
    ]
    missing = [t for t in required if t not in master]
    assert not missing, "master.md missing fail-closed top-tier blocking tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_conflict_resolution_p_levels_are_classifier_not_second_precedence_model():
    conflict = read_text(REPO_ROOT / "CONFLICT_RESOLUTION.md")
    required = [
        "## Mapping to master precedence (binding)",
        "Canonical governance precedence remains defined in `master.md`",
        "P-levels MUST NOT be interpreted as a second precedence model",
    ]
    missing = [t for t in required if t not in conflict]
    assert not missing, "CONFLICT_RESOLUTION.md missing precedence-mapping guard tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


def test_audit_reason_keys_are_declared_audit_only_and_not_reason_code_payloads():
    text = read_text(REPO_ROOT / "diagnostics" / "audit.md")
    required_tokens = [
        "Reason key semantics (binding):",
        "audit-only diagnostics keys",
        "They are NOT canonical governance `reason_code` values",
        "MUST NOT be written into `SESSION_STATE.Diagnostics.ReasonPayloads.reason_code`",
        "diagnostics/map_audit_to_canonical.py --input <audit-report.json>",
        "diagnostics/AUDIT_REASON_CANONICAL_MAP.json",
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
def test_phase_15_reentry_from_later_phases_is_explicit_and_reruns_p54():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    required_master = [
        "Re-entry path: if current phase is `3A`/`3B-*`/`4`/`5*` and operator explicitly requests `Reopen Phase 1.5`, transition back to `1.5-BusinessRules`.",
        "Re-entry is explicit-only (never implicit).",
        "After re-entry execution, `P5.4-BusinessRules` MUST be rerun before readiness can be asserted.",
    ]
    required_rules = [
        "If Phase 1.5 is explicitly re-opened from later phases (`3A`/`3B-*`/`4`/`5*`), Phase 5.4 MUST be rerun before final readiness claims.",
    ]
    required_start = [
        "If current phase is `3A`/`3B-*`/`4`/`5*` and operator asks `Reopen Phase 1.5`, `/start` MUST allow explicit re-entry to `1.5-BusinessRules` and mark BusinessRules compliance for rerun before final readiness.",
    ]

    missing_master = [token for token in required_master if token not in master]
    missing_rules = [token for token in required_rules if token not in rules]
    missing_start = [token for token in required_start if token not in start]

    assert not missing_master, "master.md missing Phase 1.5 re-entry tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing Phase 1.5 re-entry token:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing Phase 1.5 re-entry token:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_backfill_decision_pack_includes_phase_15_prompt_decision():
    text = read_text(REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py")
    required_tokens = [
        "D-001: Run Phase 1.5 (Business Rules Discovery) now?",
        "A) Yes",
        "B) No",
        "Recommendation: A (run lightweight Phase 1.5 to establish initial domain evidence)",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "persist_workspace_artifacts.py missing Phase 1.5 decision-pack baseline tokens:\n" + "\n".join(
        [f"- {m}" for m in missing]
    )


@pytest.mark.governance
def test_start_does_not_require_ticket_before_phase_4():
    text = read_text(REPO_ROOT / "start.md")
    required_tokens = [
        "During Phase `1.5/2/2.1/3A/3B`, `/start` MUST NOT require a task/ticket to proceed; ticket goal is required only at Phase 4 entry.",
    ]
    missing = [token for token in required_tokens if token not in text]
    assert not missing, "start.md missing pre-Phase-4 no-ticket gate token:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_next_action_footer_requires_multiline_pretty_layout_tokens():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")

    required_master = [
        "[NEXT-ACTION]",
        "single-line pipe-joined rendering is not allowed",
    ]
    required_rules = [
        "one field per line (`Status`, `Next`, `Why`, `Command`).",
        "Do not collapse `[NEXT-ACTION]` into one pipe-joined line",
    ]
    required_start = [
        "Render `[NEXT-ACTION]` as multiline footer (one line per field); do not emit a single pipe-joined line.",
    ]

    missing_master = [token for token in required_master if token not in master]
    missing_rules = [token for token in required_rules if token not in rules]
    missing_start = [token for token in required_start if token not in start]

    assert not missing_master, "master.md missing multiline next-action contract tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing multiline next-action contract tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing multiline next-action contract token:\n" + "\n".join([f"- {m}" for m in missing_start])


@pytest.mark.governance
def test_audit_pretty_summary_layout_tokens_present():
    audit = read_text(REPO_ROOT / "diagnostics" / "audit.md")
    required = [
        "[AUDIT-SUMMARY]",
        "Status`, `Phase/Gate`, `PrimaryReason`, `TopRecovery`",
        "`AllowedNextActions` as numbered list",
        "[/AUDIT-SUMMARY]",
    ]
    missing = [token for token in required if token not in audit]
    assert not missing, "diagnostics/audit.md missing pretty summary layout tokens:\n" + "\n".join([f"- {m}" for m in missing])


@pytest.mark.governance
def test_rules_use_canonical_repo_business_rules_file_reference():
    text = read_text(REPO_ROOT / "rules.md")
    assert "${REPO_BUSINESS_RULES_FILE}" in text
    assert "${CONFIG_ROOT}/${REPO_NAME}/business-rules.md" not in text


@pytest.mark.governance
def test_business_rules_write_failure_does_not_redirect_to_workspace_memory_target():
    master = read_text(REPO_ROOT / "master.md")
    rules = read_text(REPO_ROOT / "rules.md")
    start = read_text(REPO_ROOT / "start.md")
    helper = read_text(REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py")

    master_required = [
        "MUST NOT redirect Business Rules persistence to `${WORKSPACE_MEMORY_FILE}` or `SESSION_STATE` fields as a substitute target.",
    ]
    rules_required = [
        "No-fallback-target rule (binding):",
        "MUST NOT be redirected to `workspace-memory.yaml`, `SESSION_STATE`, or any non-canonical artifact as a write fallback.",
    ]
    start_required = [
        "MUST keep `${REPO_BUSINESS_RULES_FILE}` as target and MUST NOT redirect to `${WORKSPACE_MEMORY_FILE}`.",
    ]
    helper_required = [
        "ERR-BUSINESS-RULES-PERSIST-WRITE-FAILED",
        "business_rules_action = \"write-requested\"",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]
    missing_helper = [t for t in helper_required if t not in helper]

    assert not missing_master, "master.md missing business-rules no-redirect tokens:\n" + "\n".join([f"- {m}" for m in missing_master])
    assert not missing_rules, "rules.md missing business-rules no-redirect tokens:\n" + "\n".join([f"- {m}" for m in missing_rules])
    assert not missing_start, "start.md missing business-rules no-redirect tokens:\n" + "\n".join([f"- {m}" for m in missing_start])
    assert not missing_helper, "persist_workspace_artifacts.py missing business-rules write-failure handling tokens:\n" + "\n".join([f"- {m}" for m in missing_helper])


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
