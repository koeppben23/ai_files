#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SURFACES = {
    "api_contract",
    "backend_templates",
    "bdd_framework",
    "build_tooling",
    "db_migration",
    "e2e_test_framework",
    "frontend_api_client",
    "frontend_templates",
    "governance_docs",
    "linting",
    "messaging",
    "principal_review",
    "release",
    "risk_model",
    "scorecard_calibration",
    "security",
    "static",
    "test_framework",
}
ALLOWED_CAPABILITIES = {
    "angular",
    "cucumber",
    "cypress",
    "governance_docs",
    "java",
    "kafka",
    "liquibase",
    "nx",
    "openapi",
    "spring",
}
ALLOWED_EVIDENCE_KINDS = {"unit-test", "integration-test", "contract-test", "e2e", "lint", "build"}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_master_priority_uniqueness(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    count = master.count("## 1. PRIORITY ORDER")
    if count != 1:
        issues.append(f"master.md: expected exactly one '## 1. PRIORITY ORDER', found {count}")

    # Duplicate-detector for legacy precedence fragments anywhere in master.md.
    lines = master.splitlines()
    precedence_blocks: list[tuple[int, list[str]]] = []
    i = 0
    while i < len(lines):
        if not re.match(r"^\s*\d+\.\s+", lines[i]):
            i += 1
            continue
        start = i
        block: list[str] = []
        while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
            block.append(lines[i].strip())
            i += 1

        normalized = "\n".join(block).lower()
        is_precedence = (
            "master prompt" in normalized
            and "rules.md" in normalized
            and "active profile" in normalized
            and "ticket" in normalized
        )
        if is_precedence:
            precedence_blocks.append((start + 1, block))

    if len(precedence_blocks) != 1:
        locations = [f"line {line_no}" for line_no, _ in precedence_blocks]
        issues.append(
            "master.md: expected exactly one numbered precedence list containing "
            "Master Prompt/rules.md/Active profile/Ticket; found "
            f"{len(precedence_blocks)} ({', '.join(locations) if locations else 'none'})"
        )
        return

    _line_no, canonical = precedence_blocks[0]
    canonical_text = "\n".join(canonical)
    if "4. Activated templates/addon rulebooks (manifest-driven)" not in canonical_text:
        issues.append("master.md: canonical precedence list missing '4. Activated templates/addon rulebooks (manifest-driven)'")
    if "5. Ticket specification" not in canonical_text:
        issues.append("master.md: canonical precedence list missing '5. Ticket specification'")

    stability_note = (
        "Stability sync note (binding): governance release/readiness decisions MUST also satisfy `STABILITY_SLA.md`."
    )
    if stability_note not in master:
        issues.append("master.md: missing Stability sync note near priority order")

    if "DO NOT read rulebooks from the repository" in master:
        issues.append(
            "master.md: contains legacy phrase 'DO NOT read rulebooks from the repository'; use 'repo working tree' wording"
        )

    forbidden_secondary_precedence_fragments = [
        "4) Precedence and merge",
        "`rules.md` (core) > active profile > templates/addons refinements.",
        "lookup orders below define **resolution precedence**",
    ]
    found_forbidden = [frag for frag in forbidden_secondary_precedence_fragments if frag in master]
    if found_forbidden:
        issues.append(f"master.md: contains secondary precedence fragment(s) {found_forbidden}")

    # Context-sensitive duplicate detector: any numbered list near precedence/priority/resolution
    # language that references master/rules/profile/ticket semantics is suspicious.
    context_hits: list[str] = []
    for idx, line in enumerate(lines):
        if not re.search(r"\b(precedence|priority|resolution)\b", line, flags=re.IGNORECASE):
            continue

        win_start = max(0, idx - 12)
        win_end = min(len(lines), idx + 13)
        window = lines[win_start:win_end]

        j = 0
        while j < len(window):
            if not re.match(r"^\s*\d+\.\s+", window[j]):
                j += 1
                continue
            block: list[str] = []
            while j < len(window) and re.match(r"^\s*\d+\.\s+", window[j]):
                block.append(window[j].strip())
                j += 1

            block_text = "\n".join(block).lower()
            looks_like_precedence = (
                "master" in block_text and "rules" in block_text and "profile" in block_text and "ticket" in block_text
            )
            missing_addon_layer = "activated templates/addon rulebooks" not in block_text
            if looks_like_precedence and missing_addon_layer:
                context_hits.append(f"line {win_start + 1}")

    if context_hits:
        issues.append(
            "master.md: found potential secondary precedence list near precedence/priority/resolution context "
            f"({', '.join(sorted(set(context_hits)))})"
        )


def check_anchor_presence(issues: list[str]) -> None:
    rules = read_text(ROOT / "rules.md")
    for anchor in ["RULEBOOK-PRECEDENCE-POLICY", "ADDON-CLASS-BEHAVIOR-POLICY"]:
        if anchor not in rules:
            issues.append(f"rules.md: missing required anchor '{anchor}'")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
        return value[1:-1]
    return value


def parse_manifest(path: Path) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    scalars: dict[str, str] = {}
    list_fields: dict[str, list[str]] = {
        "path_roots": [],
        "owns_surfaces": [],
        "touches_surfaces": [],
        "capabilities_any": [],
        "capabilities_all": [],
    }
    errors: list[str] = []
    active_list_key: str | None = None

    for line_no, raw in enumerate(read_text(path).splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        top = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*?)\s*$", raw)
        if top:
            key, val = top.group(1), top.group(2)
            if key in list_fields:
                active_list_key = key if val == "" else None
                if val:
                    errors.append(f"{path}: line {line_no}: {key} must be multiline list")
                continue
            active_list_key = None
            scalars[key] = _unquote(val)
            continue

        if active_list_key:
            m = re.match(r"^\s{2}-\s*(.*?)\s*$", raw)
            if not m:
                errors.append(f"{path}: line {line_no}: malformed {active_list_key} entry")
                continue
            root = _unquote(m.group(1))
            list_fields[active_list_key].append(root)

    return scalars, list_fields, errors


def _validate_relative_paths(issues: list[str], manifest: Path, path_roots: list[str]) -> None:
    if not path_roots:
        issues.append(f"{manifest}: path_roots must be non-empty")
    for root in path_roots:
        p = Path(root)
        if root == "/":
            issues.append(f"{manifest}: path_roots must not be '/'")
        if p.is_absolute():
            issues.append(f"{manifest}: path_roots must be relative, found '{root}'")
        if ".." in p.parts:
            issues.append(f"{manifest}: path_roots must not contain traversal, found '{root}'")


def _validate_surface_fields(issues: list[str], manifest: Path, list_fields: dict[str, list[str]]) -> None:
    owns = list_fields.get("owns_surfaces", [])
    touches = list_fields.get("touches_surfaces", [])
    if not owns:
        issues.append(f"{manifest}: owns_surfaces must be non-empty")
    if not touches:
        issues.append(f"{manifest}: touches_surfaces must be non-empty")

    for field_name, values in (("owns_surfaces", owns), ("touches_surfaces", touches)):
        seen = set()
        for value in values:
            if value in seen:
                issues.append(f"{manifest}: duplicate {field_name} entry '{value}'")
            seen.add(value)
            if value not in ALLOWED_SURFACES:
                issues.append(f"{manifest}: unsupported {field_name} value '{value}'")


def _validate_capability_fields(issues: list[str], manifest: Path, list_fields: dict[str, list[str]]) -> None:
    caps_any = list_fields.get("capabilities_any", [])
    caps_all = list_fields.get("capabilities_all", [])
    if not caps_any and not caps_all:
        issues.append(f"{manifest}: capabilities_any/capabilities_all must include at least one capability")

    for field_name, values in (("capabilities_any", caps_any), ("capabilities_all", caps_all)):
        seen = set()
        for value in values:
            if value in seen:
                issues.append(f"{manifest}: duplicate {field_name} entry '{value}'")
            seen.add(value)
            if value not in ALLOWED_CAPABILITIES:
                issues.append(f"{manifest}: unsupported {field_name} value '{value}'")


def _validate_surface_ownership_uniqueness(
    issues: list[str], manifests_data: list[tuple[Path, dict[str, str], dict[str, list[str]]]]
) -> None:
    owners: dict[str, str] = {}
    for manifest, scalars, list_fields in manifests_data:
        addon_key = scalars.get("addon_key") or manifest.name
        for surface in list_fields.get("owns_surfaces", []):
            existing = owners.get(surface)
            if existing and existing != addon_key:
                issues.append(
                    f"{manifest}: owns_surfaces conflict on '{surface}' (also owned by addon_key={existing})"
                )
            else:
                owners[surface] = addon_key


def _validate_capability_catalog_completeness(
    issues: list[str], manifests_data: list[tuple[Path, dict[str, str], dict[str, list[str]]]]
) -> None:
    used_caps: set[str] = set()
    cap_has_signal_mapping: dict[str, bool] = {c: False for c in ALLOWED_CAPABILITIES}

    for manifest, _scalars, list_fields in manifests_data:
        caps = set(list_fields.get("capabilities_any", []) + list_fields.get("capabilities_all", []))
        used_caps.update(caps)

        text = read_text(manifest)
        has_signals_any = bool(re.search(r"^\s{2}any:\s*$", text, flags=re.MULTILINE))
        has_any_entries = bool(re.search(r"^\s{4}-\s*[a-z_]+:\s*.+$", text, flags=re.MULTILINE))
        has_signal_mapping = has_signals_any and has_any_entries
        if has_signal_mapping:
            for cap in caps:
                if cap in cap_has_signal_mapping:
                    cap_has_signal_mapping[cap] = True

    missing_usage = sorted(c for c in ALLOWED_CAPABILITIES if c not in used_caps)
    if missing_usage:
        issues.append(f"capability catalog entries unused by manifests: {', '.join(missing_usage)}")

    missing_mapping = sorted(c for c, ok in cap_has_signal_mapping.items() if not ok)
    if missing_mapping:
        issues.append(f"capability catalog entries missing signal/evidence mapping: {', '.join(missing_mapping)}")


def check_manifest_contract(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    if not manifests:
        issues.append("profiles/addons: no addon manifests found")
        return

    manifests_data: list[tuple[Path, dict[str, str], dict[str, list[str]]]] = []
    for manifest in manifests:
        scalars, list_fields, errors = parse_manifest(manifest)
        issues.extend(errors)
        manifests_data.append((manifest, scalars, list_fields))

        mv = scalars.get("manifest_version", "")
        if mv != "1":
            issues.append(f"{manifest}: expected manifest_version=1, found '{mv or '<missing>'}'")

        rb = scalars.get("rulebook", "")
        if not rb:
            issues.append(f"{manifest}: missing rulebook")
        else:
            rb_path = ROOT / "profiles" / rb if not rb.startswith("profiles/") else ROOT / rb
            if not rb_path.exists():
                issues.append(f"{manifest}: referenced rulebook does not exist: {rb}")

        addon_class = scalars.get("addon_class", "")
        if addon_class not in {"required", "advisory"}:
            issues.append(f"{manifest}: invalid addon_class '{addon_class or '<missing>'}'")

        _validate_relative_paths(issues, manifest, list_fields.get("path_roots", []))
        _validate_surface_fields(issues, manifest, list_fields)
        _validate_capability_fields(issues, manifest, list_fields)

    _validate_surface_ownership_uniqueness(issues, manifests_data)
    _validate_capability_catalog_completeness(issues, manifests_data)


def check_required_addon_references(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    for manifest in manifests:
        scalars, _list_fields, _errors = parse_manifest(manifest)
        if scalars.get("addon_class") != "required":
            continue
        rb = scalars.get("rulebook", "")
        rb_path = ROOT / "profiles" / rb if rb and not rb.startswith("profiles/") else ROOT / rb
        if not rb or not rb_path.exists():
            issues.append(f"{manifest}: required addon must reference existing rulebook")


def check_template_quality_gate(issues: list[str]) -> None:
    templates = sorted((ROOT / "profiles").glob("rules*templates*.md"))
    for tpl in templates:
        text = read_text(tpl)
        lower = text.lower()

        required_tokens = [
            "Inputs required:",
            "Outputs guaranteed:",
            "Evidence expectation:",
            "Golden examples:",
            "Anti-example:",
            "evidence_kinds_required:",
        ]
        missing = [t for t in required_tokens if t not in text]
        if missing:
            issues.append(f"{tpl}: missing template quality tokens {missing}")

        # parse evidence_kinds_required list
        m = re.search(r"^\s*evidence_kinds_required:\s*$", text, flags=re.MULTILINE)
        kinds: list[str] = []
        if m:
            for line in text[m.end() :].splitlines():
                mm = re.match(r"^\s{2}-\s*(.*?)\s*$", line)
                if mm:
                    v = _unquote(mm.group(1))
                    if v:
                        kinds.append(v)
                    continue
                if not line.strip():
                    continue
                break
        if not kinds:
            issues.append(f"{tpl}: evidence_kinds_required must be non-empty")
        for k in kinds:
            if k not in ALLOWED_EVIDENCE_KINDS:
                issues.append(f"{tpl}: unsupported evidence kind '{k}'")

        # forbid strong claims without evidence-gate phrasing
        forbidden_claims = ["always passes", "always succeeds", "guaranteed pass"]
        for claim in forbidden_claims:
            if claim in lower and "evidence" not in lower:
                issues.append(f"{tpl}: contains forbidden claim '{claim}' without evidence-gate phrasing")
        if "verified" in lower and "evidence" not in lower:
            issues.append(f"{tpl}: contains 'verified' claims but no 'evidence' wording")


def check_stability_sla_contract(issues: list[str]) -> None:
    sla_path = ROOT / "STABILITY_SLA.md"
    if not sla_path.exists():
        issues.append("STABILITY_SLA.md: missing required stability SLA document")
        return

    sla = read_text(sla_path)
    master = read_text(ROOT / "master.md")
    rules = read_text(ROOT / "rules.md")
    ci = read_text(ROOT / ".github" / "workflows" / "ci.yml")

    sla_required_tokens = [
        "# Stability-SLA: AI Governance System (Go/No-Go)",
        "## 1) Single Canonical Precedence",
        "master > core rules > active profile > activated addons/templates > ticket",
        "## 2) Deterministic Activation",
        "## 3) Fail-Closed for Required",
        "## 4) Surface Ownership and Conflict Safety",
        "BLOCKED-ADDON-CONFLICT:<surface>",
        "## 7) SESSION_STATE Versioning and Isolation",
        "BLOCKED-STATE-OUTDATED",
        "## 10) Regression Gates (CI Required)",
        "governance-lint",
        "pytest -m governance",
        "template quality gate",
        "PASS: all 10 criteria are satisfied and enforced by required CI checks.",
    ]
    missing_sla = [token for token in sla_required_tokens if token not in sla]
    if missing_sla:
        issues.append(f"STABILITY_SLA.md: missing required tokens {missing_sla}")

    master_required_tokens = [
        "`STABILITY_SLA.md`",
        "normative Go/No-Go contract",
        "Stability sync note (binding): governance release/readiness decisions MUST also satisfy `STABILITY_SLA.md`.",
        "4. Activated templates/addon rulebooks (manifest-driven)",
        "SUGGEST: ranked profile shortlist with evidence (top 1 marked recommended)",
        "Detected multiple plausible profiles. Reply with ONE number",
    ]
    missing_master = [token for token in master_required_tokens if token not in master]
    if missing_master:
        issues.append(f"master.md: missing stability SLA integration tokens {missing_master}")

    rules_required_tokens = [
        "Governance release stability is normatively defined by `STABILITY_SLA.md`",
        "Release/readiness decisions MUST satisfy `STABILITY_SLA.md` invariants; conflicts are resolved fail-closed.",
        "4) activated addon rulebooks (including templates and shared governance add-ons)",
        "Master Prompt > Core Rulebook > Active Profile Rulebook > Activated Addon/Template Rulebooks > Ticket > Repo docs",
        "provide a ranked shortlist of plausible profiles with brief evidence per candidate",
        "request explicit selection using a single targeted numbered prompt",
    ]
    missing_rules = [token for token in rules_required_tokens if token not in rules]
    if missing_rules:
        issues.append(f"rules.md: missing stability SLA integration tokens {missing_rules}")

    if "Master Prompt > Core Rulebook > Profile Rulebook > Ticket > Repo docs" in rules:
        issues.append("rules.md: contains legacy precedence fragment without addon/template layer")

    ci_required_tokens = [
        "governance-lint:",
        "validate-governance:",
        "governance-e2e:",
        "pytest -q -m governance",
        "pytest -q -m e2e_governance",
        "release-readiness:",
        "needs: [conventional-pr-title, governance-lint, spec-guards, test-installer, validate-governance, governance-e2e, build-artifacts]",
    ]
    missing_ci = [token for token in ci_required_tokens if token not in ci]
    if missing_ci:
        issues.append(f".github/workflows/ci.yml: missing SLA-aligned required gate tokens {missing_ci}")


def check_factory_contract_alignment(issues: list[str]) -> None:
    new_addon = read_text(ROOT / "new_addon.md")
    new_profile = read_text(ROOT / "new_profile.md")
    factory_json = read_text(ROOT / "diagnostics" / "PROFILE_ADDON_FACTORY_CONTRACT.json")

    addon_required_tokens = [
        "owns_surfaces",
        "touches_surfaces",
        "capabilities_any",
        "capabilities_all",
        "phase semantics MUST reference canonical `master.md` phase labels",
        "SESSION_STATE.AddonsEvidence.<addon_key>",
        "SESSION_STATE.RepoFacts.CapabilityEvidence",
        "SESSION_STATE.Diagnostics.ReasonPayloads",
        "tracking keys are audit/trace pointers (map entries), not activation signals",
    ]
    missing_addon = [token for token in addon_required_tokens if token not in new_addon]
    if missing_addon:
        issues.append(f"new_addon.md: missing factory alignment tokens {missing_addon}")

    profile_required_tokens = [
        "applicability_signals",
        "MUST NOT be used as profile-selection activation logic",
        "Preferred: `profiles/rules_<profile_key>.md`",
        "Accepted legacy alias: `profiles/rules.<profile_key>.md`",
        "phase semantics MUST reference canonical `master.md` phase labels",
        "SESSION_STATE.AddonsEvidence.<addon_key>",
        "SESSION_STATE.RepoFacts.CapabilityEvidence",
        "SESSION_STATE.Diagnostics.ReasonPayloads",
        "tracking keys are audit/trace pointers (map entries), not activation signals",
    ]
    missing_profile = [token for token in profile_required_tokens if token not in new_profile]
    if missing_profile:
        issues.append(f"new_profile.md: missing factory alignment tokens {missing_profile}")

    json_required_tokens = [
        '"requiredAddonManifestFields"',
        '"owns_surfaces"',
        '"touches_surfaces"',
        '"recommendedAddonManifestFields"',
        '"capabilities_any"',
        '"capabilities_all"',
    ]
    missing_json = [token for token in json_required_tokens if token not in factory_json]
    if missing_json:
        issues.append(f"diagnostics/PROFILE_ADDON_FACTORY_CONTRACT.json: missing factory alignment tokens {missing_json}")


def check_diagnostics_reason_contract_alignment(issues: list[str]) -> None:
    audit = read_text(ROOT / "diagnostics" / "audit.md")
    persist = read_text(ROOT / "diagnostics" / "persist_workspace_artifacts.py")

    audit_required_tokens = [
        "Reason key semantics (binding):",
        "audit-only diagnostics keys",
        "They are NOT canonical governance `reason_code` values",
        "MUST NOT be written into `SESSION_STATE.Diagnostics.ReasonPayloads.reason_code`",
        "auditReasonKey `BR_MISSING_SESSION_GATE_STATE`",
        "auditReasonKey `BR_MISSING_RULEBOOK_RESOLUTION`",
        "auditReasonKey `BR_SCOPE_ARTIFACT_MISSING`",
    ]
    missing_audit = [token for token in audit_required_tokens if token not in audit]
    if missing_audit:
        issues.append(f"diagnostics/audit.md: missing reason-key boundary tokens {missing_audit}")

    persist_required_tokens = [
        '"status": "blocked"',
        '"reason_code": "BLOCKED-WORKSPACE-PERSISTENCE"',
        '"recovery_steps"',
        '"next_command"',
    ]
    missing_persist = [token for token in persist_required_tokens if token not in persist]
    if missing_persist:
        issues.append(f"diagnostics/persist_workspace_artifacts.py: missing quiet blocked payload tokens {missing_persist}")


def check_start_evidence_boundaries(issues: list[str]) -> None:
    start = read_text(ROOT / "start.md")

    required_tokens = [
        "'reason_code':'BLOCKED-MISSING-BINDING-FILE'",
        "'nonEvidence':'debug-only'",
        "Fallback computed payloads are debug output only (`nonEvidence`) and MUST NOT be treated as binding evidence.",
        "Helper output is operational convenience status only and MUST NOT be treated as canonical repo identity evidence.",
        "Repo identity remains governed by `master.md` evidence contracts",
    ]
    missing_required = [token for token in required_tokens if token not in start]
    if missing_required:
        issues.append(f"start.md: missing evidence-boundary tokens {missing_required}")

    forbidden_tokens = [
        "Treat it as **evidence**.",
        "# last resort: compute the same payload that the installer would write",
    ]
    found_forbidden = [token for token in forbidden_tokens if token in start]
    if found_forbidden:
        issues.append(f"start.md: contains forbidden fallback-evidence tokens {found_forbidden}")


def check_unified_next_action_footer_contract(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    rules = read_text(ROOT / "rules.md")
    start = read_text(ROOT / "start.md")

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
    if missing_master:
        issues.append(f"master.md: missing unified next-action footer tokens {missing_master}")
    if missing_rules:
        issues.append(f"rules.md: missing unified next-action footer tokens {missing_rules}")
    if missing_start:
        issues.append(f"start.md: missing unified next-action footer tokens {missing_start}")


def check_standard_blocker_envelope_contract(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    rules = read_text(ROOT / "rules.md")
    start = read_text(ROOT / "start.md")

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
    ]
    start_required = [
        "If blocked, include the standard blocker envelope (`status`, `reason_code`, `missing_evidence`, `recovery_steps`, `next_command`).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]
    if missing_master:
        issues.append(f"master.md: missing blocker envelope tokens {missing_master}")
    if missing_rules:
        issues.append(f"rules.md: missing blocker envelope tokens {missing_rules}")
    if missing_start:
        issues.append(f"start.md: missing blocker envelope tokens {missing_start}")


def check_start_mode_banner_contract(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    rules = read_text(ROOT / "rules.md")
    start = read_text(ROOT / "start.md")

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
    if missing_master:
        issues.append(f"master.md: missing start-mode banner tokens {missing_master}")
    if missing_rules:
        issues.append(f"rules.md: missing start-mode banner tokens {missing_rules}")
    if missing_start:
        issues.append(f"start.md: missing start-mode banner tokens {missing_start}")


def check_confidence_impact_snapshot_contract(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    rules = read_text(ROOT / "rules.md")
    start = read_text(ROOT / "start.md")

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
    if missing_master:
        issues.append(f"master.md: missing confidence-impact snapshot tokens {missing_master}")
    if missing_rules:
        issues.append(f"rules.md: missing confidence-impact snapshot tokens {missing_rules}")
    if missing_start:
        issues.append(f"start.md: missing confidence-impact snapshot tokens {missing_start}")


def check_quick_fix_commands_contract(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    rules = read_text(ROOT / "rules.md")
    start = read_text(ROOT / "start.md")

    master_required = [
        "Quick-fix commands (mandatory for blockers):",
        "QuickFixCommands",
        "1-3 copy-paste-ready commands",
        'QuickFixCommands: ["none"]',
    ]
    rules_required = [
        "### 7.3.5 Quick-Fix Commands for Blockers (Binding)",
        "`QuickFixCommands` with 1-3 exact copy-paste commands aligned to the active `reason_code`.",
        'output `QuickFixCommands: ["none"]`.',
    ]
    start_required = [
        "If blocked, include `QuickFixCommands` with 1-3 copy-paste commands (or `[\"none\"]` if not command-driven).",
    ]

    missing_master = [t for t in master_required if t not in master]
    missing_rules = [t for t in rules_required if t not in rules]
    missing_start = [t for t in start_required if t not in start]
    if missing_master:
        issues.append(f"master.md: missing quick-fix command tokens {missing_master}")
    if missing_rules:
        issues.append(f"rules.md: missing quick-fix command tokens {missing_rules}")
    if missing_start:
        issues.append(f"start.md: missing quick-fix command tokens {missing_start}")


def main() -> int:
    issues: list[str] = []
    check_master_priority_uniqueness(issues)
    check_anchor_presence(issues)
    check_manifest_contract(issues)
    check_required_addon_references(issues)
    check_template_quality_gate(issues)
    check_stability_sla_contract(issues)
    check_factory_contract_alignment(issues)
    check_diagnostics_reason_contract_alignment(issues)
    check_start_evidence_boundaries(issues)
    check_unified_next_action_footer_contract(issues)
    check_standard_blocker_envelope_contract(issues)
    check_start_mode_banner_contract(issues)
    check_confidence_impact_snapshot_contract(issues)
    check_quick_fix_commands_contract(issues)

    if issues:
        print("Governance lint FAILED:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Governance lint OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
