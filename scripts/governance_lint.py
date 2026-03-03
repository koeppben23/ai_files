#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from governance.addon_catalog import (  # noqa: E402
    ALLOWED_CAPABILITIES,
    ALLOWED_EVIDENCE_KINDS,
    ALLOWED_SURFACES,
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Manifest / addon validation helpers (Category B — already-legitimate SSOT)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Category B — legitimate SSOT checks (kept unchanged)
# ---------------------------------------------------------------------------

def check_manifest_contract(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    if not manifests:
        issues.append("profiles/addons: no addon manifests found")
        return

    manifests_data: list[tuple[Path, dict[str, str], dict[str, list[str]]]] = []
    addon_keys: set[str] = set()
    for manifest in manifests:
        scalars, list_fields, errors = parse_manifest(manifest)
        issues.extend(errors)
        manifests_data.append((manifest, scalars, list_fields))

        addon_key = scalars.get("addon_key", "")
        if not addon_key:
            issues.append(f"{manifest}: missing addon_key")
        elif addon_key in addon_keys:
            issues.append(f"{manifest}: duplicate addon_key '{addon_key}'")
        else:
            addon_keys.add(addon_key)

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

        text = read_text(manifest)
        has_signals_any = bool(re.search(r"^signals:\s*$", text, flags=re.MULTILINE)) and bool(
            re.search(r"^\s{2}any:\s*$", text, flags=re.MULTILINE)
        )
        has_any_entries = bool(re.search(r"^\s{4}-\s*[a-z_]+:\s*.+$", text, flags=re.MULTILINE))
        if not (has_signals_any and has_any_entries):
            issues.append(f"{manifest}: signals.any must contain at least one concrete matcher entry")

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


def check_workflow_template_factory_contract(issues: list[str]) -> None:
    contract_path = ROOT / "governance" / "assets" / "catalogs" / "GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json"
    catalog_path = ROOT / "templates" / "github-actions" / "template_catalog.json"
    script_path = ROOT / "scripts" / "workflow_template_factory.py"

    if not contract_path.exists():
        issues.append("governance/GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json: missing workflow template factory contract")
    else:
        contract = read_text(contract_path)
        required_tokens = [
            '"$schema": "opencode.governance.workflow-template-factory.v1"',
            '"template_file_glob": "templates/github-actions/governance-*.yml"',
            '"validate": "${PYTHON_COMMAND} scripts/workflow_template_factory.py"',
        ]
        missing_tokens = [token for token in required_tokens if token not in contract]
        if missing_tokens:
            issues.append(
                "governance/GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json: missing required tokens "
                f"{missing_tokens}"
            )

    if not catalog_path.exists():
        issues.append("templates/github-actions/template_catalog.json: missing workflow template catalog")
        return

    if not script_path.exists():
        issues.append("scripts/workflow_template_factory.py: missing workflow template factory script")
        return

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        issues.append(
            "workflow template factory check failed: "
            + (detail if detail else "unknown failure")
        )


def check_customer_script_catalog_contract(issues: list[str]) -> None:
    catalog_path = ROOT / "governance" / "assets" / "catalogs" / "CUSTOMER_SCRIPT_CATALOG.json"
    script_path = ROOT / "scripts" / "customer_script_catalog.py"

    if not catalog_path.exists():
        issues.append("governance/CUSTOMER_SCRIPT_CATALOG.json: missing customer script catalog")
        return

    catalog = read_text(catalog_path)
    required_tokens = [
        '"schema": "governance.customer-script-catalog.v1"',
        '"path": "scripts/rulebook_factory.py"',
        '"path": "scripts/workflow_template_factory.py"',
        '"ship_in_release": true',
    ]
    missing_tokens = [token for token in required_tokens if token not in catalog]
    if missing_tokens:
        issues.append(
            "governance/CUSTOMER_SCRIPT_CATALOG.json: missing required tokens "
            f"{missing_tokens}"
        )

    if not script_path.exists():
        issues.append("scripts/customer_script_catalog.py: missing catalog checker script")
        return

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        issues.append(
            "customer script catalog check failed: "
            + (detail if detail else "unknown failure")
        )


def check_customer_markdown_exclusion_policy(issues: list[str]) -> None:
    policy_path = ROOT / "governance" / "assets" / "catalogs" / "CUSTOMER_MARKDOWN_EXCLUDE.json"
    if not policy_path.exists():
        issues.append("governance/CUSTOMER_MARKDOWN_EXCLUDE.json: missing markdown exclusion policy")
        return

    payload = read_text(policy_path)
    required_tokens = [
        '"schema": "governance.customer-markdown-exclude.v1"',
        '"release_excluded_markdown"',
    ]
    missing = [token for token in required_tokens if token not in payload]
    if missing:
        issues.append(
            "governance/CUSTOMER_MARKDOWN_EXCLUDE.json: missing required tokens "
            f"{missing}"
        )


def check_security_gate_contract(issues: list[str]) -> None:
    policy_path = ROOT / "governance" / "assets" / "catalogs" / "SECURITY_GATE_POLICY.json"
    script_path = ROOT / "scripts" / "evaluate_security_evidence.py"
    workflow_path = ROOT / ".github" / "workflows" / "security.yml"

    if not policy_path.exists():
        issues.append("governance/SECURITY_GATE_POLICY.json: missing security gate policy")
        return

    policy = read_text(policy_path)
    policy_required_tokens = [
        '"schema": "governance.security-gate-policy.v1"',
        '"block_on_severities"',
        '"critical"',
        '"high"',
        '"fail_closed_on_scanner_error": true',
        '"session_state_evidence_key": "SESSION_STATE.BuildEvidence.Security"',
    ]
    missing_policy = [token for token in policy_required_tokens if token not in policy]
    if missing_policy:
        issues.append(
            "governance/SECURITY_GATE_POLICY.json: missing required tokens "
            f"{missing_policy}"
        )

    if not script_path.exists():
        issues.append("scripts/evaluate_security_evidence.py: missing security evidence evaluator")

    if not workflow_path.exists():
        issues.append(".github/workflows/security.yml: missing security workflow")
        return

    workflow = read_text(workflow_path)
    workflow_required_tokens = [
        "name: Security",
        "gitleaks",
        "pip-audit",
        "CodeQL",
        "actionlint",
        "zizmor",
        "security-policy-gate:",
        "scripts/evaluate_security_evidence.py",
        "governance/assets/catalogs/SECURITY_GATE_POLICY.json",
        "SESSION_STATE.BuildEvidence.Security",
    ]
    missing_workflow = [token for token in workflow_required_tokens if token not in workflow]
    if missing_workflow:
        issues.append(
            ".github/workflows/security.yml: missing required security gate tokens "
            f"{missing_workflow}"
        )


def check_response_contract_validator_presence(issues: list[str]) -> None:
    script = ROOT / "scripts" / "validate_response_contract.py"
    if not script.exists():
        issues.append("scripts/validate_response_contract.py: missing response contract validator")
        return
    text = read_text(script)
    required = [
        "reason_payload",
        "quick_fix_commands",
        "command coherence violated",
        "RulebookLoadEvidence must be present",
    ]
    missing = [t for t in required if t not in text]
    if missing:
        issues.append(f"scripts/validate_response_contract.py: missing validator tokens {missing}")


def check_yaml_rulebook_schema(issues: list[str]) -> None:
    """Validate YAML rulebooks against schema (v2 path) including schema_version compatibility."""
    try:
        import yaml
        from jsonschema import Draft202012Validator
    except ImportError:
        issues.append("YAML schema validation requires: pip install jsonschema pyyaml")
        return

    schema_path = ROOT / "schemas" / "rulebook.schema.json"
    if not schema_path.exists():
        return

    schema = json.loads(schema_path.read_text())
    schema_version = schema.get("version", "")

    rulesets_dir = ROOT / "rulesets"
    if not rulesets_dir.exists():
        return

    for yaml_file in rulesets_dir.glob("**/*.yml"):
        try:
            rulebook = yaml.safe_load(yaml_file.read_text())
            validator = Draft202012Validator(schema)
            errors = list(validator.iter_errors(rulebook))
            if errors:
                for error in errors:
                    issues.append(f"{yaml_file.relative_to(ROOT)}: schema violation at {error.json_path}: {error.message}")
            elif schema_version:
                # Check schema_version compatibility (major version must match)
                rb_schema_ver = (rulebook.get("metadata") or {}).get("schema_version", "")
                if not rb_schema_ver:
                    issues.append(f"{yaml_file.relative_to(ROOT)}: missing metadata.schema_version")
                else:
                    schema_major = schema_version.split(".")[0]
                    rb_major = rb_schema_ver.split(".")[0]
                    if schema_major != rb_major:
                        issues.append(
                            f"{yaml_file.relative_to(ROOT)}: schema_version mismatch: "
                            f"rulebook targets {rb_schema_ver} but schema is {schema_version}"
                        )
        except Exception as e:
            issues.append(f"{yaml_file.relative_to(ROOT)}: failed to parse: {e}")


def check_md_rails_only_tripwire(issues: list[str]) -> None:
    script = ROOT / "governance" / "entrypoints" / "md_lint.py"
    if not script.exists():
        issues.append("governance/md_lint.py: missing MD rails linter")
        return
    files = [
        ROOT / "master.md",
        ROOT / "rules.md",
        ROOT / "BOOTSTRAP.md",
        ROOT / "continue.md",
        ROOT / "review.md",
        ROOT / "docs" / "_archive" / "resume.md",
        ROOT / "docs" / "_archive" / "resume_prompt.md",
        ROOT / "docs" / "_archive" / "new_profile.md",
        ROOT / "docs" / "_archive" / "new_addon.md",
        ROOT / "BOOTSTRAP.md",
    ]
    files.extend(sorted((ROOT / "profiles").glob("rules*.md")))
    file_args = [str(p) for p in files if p.exists()]
    if not file_args:
        issues.append("md_lint failed: no md files found for rails-only gate")
        return
    proc = subprocess.run(
        [sys.executable, str(script), *file_args, "--ci"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode == 0:
        try:
            payload = json.loads(proc.stdout)
        except Exception:
            payload = {}
        findings = payload.get("findings", []) if isinstance(payload, dict) else []
        critical = []
        for item in findings:
            if not isinstance(item, dict):
                continue
            if str(item.get("severity", "")).lower() != "error":
                continue
            if str(item.get("rule_id", "")) != "MD004":
                continue
            critical.append(item)
        if critical:
            issues.append("md_lint failed: MD004 authority language detected")
            return
    if proc.returncode != 0:
        detail = (proc.stdout + "\n" + proc.stderr).strip()
        issues.append("md_lint failed: " + (detail if detail else "unknown failure"))


# ---------------------------------------------------------------------------
# Rescued SSOT checks — structural JSON/Python validation only (no MD reads)
# ---------------------------------------------------------------------------

# Catalog files that carry a version field.
# Files without a version field (pure schemas/contracts) are excluded.
_SCHEMA_CONTRACT_FILES = {
    "AUDIT_REPORT_SCHEMA.json",
    "GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json",
    "PROFILE_ADDON_FACTORY_CONTRACT.json",
    "RESPONSE_ENVELOPE_SCHEMA.json",
    "RUN_SUMMARY_SCHEMA.json",
}

_SEMVER3_RE = re.compile(r"^\d+\.\d+\.\d+$")
_LEGACY_VERSION_KEYS = {"catalog_version", "policy_version"}


def check_catalog_version_format(issues: list[str]) -> None:
    """Enforce semver-3 version format and canonical field name across catalogs.

    Codifies Cluster 1 invariants as a permanent lint gate:
    - All versioned catalogs must have a top-level 'version' field in X.Y.Z format
    - Legacy key names (catalog_version, policy_version) must not be present
    """
    catalogs_dir = ROOT / "governance" / "assets" / "catalogs"
    if not catalogs_dir.is_dir():
        issues.append("governance/assets/catalogs: directory not found")
        return

    for path in sorted(catalogs_dir.glob("*.json")):
        if path.name in _SCHEMA_CONTRACT_FILES:
            continue

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            issues.append(f"{path.name}: failed to read: {exc}")
            continue

        if not isinstance(data, dict):
            issues.append(f"{path.name}: expected JSON object at top level")
            continue

        # Check for legacy keys
        for legacy_key in _LEGACY_VERSION_KEYS:
            if legacy_key in data:
                issues.append(f"{path.name}: uses legacy key '{legacy_key}' — rename to 'version'")

        # Check version field
        version = data.get("version")
        if version is None:
            issues.append(f"{path.name}: missing 'version' field")
            continue

        if not isinstance(version, str):
            issues.append(f"{path.name}: 'version' must be a string, got {type(version).__name__}")
            continue

        if not _SEMVER3_RE.match(version):
            issues.append(f"{path.name}: 'version' must be semver-3 (X.Y.Z), got '{version}'")


def check_artifact_hash_integrity(issues: list[str]) -> None:
    """Verify hashes.json consistency for all governance releases.

    Codifies Cluster 3 invariants as a permanent lint gate:
    - hashes.json in each release must match actual file hashes
    - Catches stale hashes during development
    """
    releases_dir = ROOT / "rulesets" / "governance"
    if not releases_dir.is_dir():
        return  # No releases to check — not an error

    try:
        from governance.infrastructure.artifact_integrity import verify_all_releases
    except ImportError as exc:
        issues.append(f"artifact_integrity module unavailable: {exc}")
        return

    results = verify_all_releases(releases_dir)
    for result in results:
        if not result.passed:
            issues.append(f"hash integrity: {result.summary}")


def check_tenant_config_schema(issues: list[str]) -> None:
    """Verify tenant config schema exists and is valid JSON Schema.

    Codifies Cluster 6a (tenant config) as a permanent lint gate:
    - tenant_config.schema.json must exist under schemas/
    - Must be valid JSON Schema
    """
    schema_path = ROOT / "schemas" / "tenant_config.schema.json"
    if not schema_path.exists():
        return  # Tenant config is optional — no schema is OK

    try:
        import jsonschema
        schema_text = schema_path.read_text(encoding="utf-8")
        schema = json.loads(schema_text)
        jsonschema.Draft202012Validator.check_schema(schema)
    except json.JSONDecodeError as exc:
        issues.append(f"tenant_config.schema.json: invalid JSON: {exc}")
    except jsonschema.SchemaError as exc:
        issues.append(f"tenant_config.schema.json: invalid JSON Schema: {exc}")


def check_tenant_config_references_valid_profiles(issues: list[str]) -> None:
    """Verify tenant config references valid profiles if OPENCODE_TENANT_CONFIG is set.

    If a tenant config exists and points to a profile, verify that profile exists.
    This is informational only — tenant config is optional and fallbacks work.
    """
    import os
    config_path = os.environ.get("OPENCODE_TENANT_CONFIG")
    if not config_path:
        return  # No tenant config — nothing to check

    config_file = Path(config_path)
    if not config_file.exists():
        return  # Config doesn't exist — fail-open handled elsewhere

    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
        default_profile = config.get("default_profile", "")
        if default_profile:
            profile_path = ROOT / "rulesets" / "profiles" / f"rules.{default_profile.replace('profile.', '')}.yml"
            if not profile_path.exists():
                issues.append(f"tenant config references non-existent profile: {default_profile}")
    except (json.JSONDecodeError, OSError):
        pass  # Invalid config — caught by other checks


def check_response_envelope_schema_keys(issues: list[str]) -> None:
    """Structural check on RESPONSE_ENVELOPE_SCHEMA.json (rescued from check_response_envelope_schema_contract)."""
    schema_path = ROOT / "governance" / "assets" / "catalogs" / "RESPONSE_ENVELOPE_SCHEMA.json"
    if not schema_path.exists():
        issues.append("governance/RESPONSE_ENVELOPE_SCHEMA.json: file missing")
        return

    try:
        schema = json.loads(read_text(schema_path))
    except json.JSONDecodeError as exc:
        issues.append(f"governance/RESPONSE_ENVELOPE_SCHEMA.json: invalid JSON: {exc}")
        return

    # Check $id
    expected_id = "opencode.governance.response-envelope.v1"
    actual_id = schema.get("$id", "")
    if actual_id != expected_id:
        issues.append(
            f"governance/RESPONSE_ENVELOPE_SCHEMA.json: expected $id={expected_id!r}, found {actual_id!r}"
        )

    # Check required property keys
    properties = schema.get("properties", {})
    required_properties = ["status", "session_state", "next_action", "snapshot", "reason_payload", "quick_fix_commands"]
    missing = [k for k in required_properties if k not in properties]
    if missing:
        issues.append(f"governance/RESPONSE_ENVELOPE_SCHEMA.json: missing property keys {missing}")


def check_factory_contract_json_keys(issues: list[str]) -> None:
    """Structural check on PROFILE_ADDON_FACTORY_CONTRACT.json (rescued from check_factory_contract_alignment)."""
    contract_path = ROOT / "governance" / "assets" / "catalogs" / "PROFILE_ADDON_FACTORY_CONTRACT.json"
    if not contract_path.exists():
        issues.append("governance/PROFILE_ADDON_FACTORY_CONTRACT.json: file missing")
        return

    try:
        contract = json.loads(read_text(contract_path))
    except json.JSONDecodeError as exc:
        issues.append(f"governance/PROFILE_ADDON_FACTORY_CONTRACT.json: invalid JSON: {exc}")
        return

    # Check top-level keys
    required_keys = ["requiredAddonManifestFields", "recommendedAddonManifestFields"]
    missing_top = [k for k in required_keys if k not in contract]
    if missing_top:
        issues.append(f"governance/PROFILE_ADDON_FACTORY_CONTRACT.json: missing top-level keys {missing_top}")
        return

    # Check required fields contain owns_surfaces, touches_surfaces
    required_fields = contract.get("requiredAddonManifestFields", [])
    if not isinstance(required_fields, list):
        required_fields = []
    for field in ["owns_surfaces", "touches_surfaces"]:
        if field not in required_fields:
            issues.append(
                f"governance/PROFILE_ADDON_FACTORY_CONTRACT.json: requiredAddonManifestFields missing '{field}'"
            )

    # Check recommended fields contain capabilities_any, capabilities_all
    recommended_fields = contract.get("recommendedAddonManifestFields", [])
    if not isinstance(recommended_fields, list):
        recommended_fields = []
    for field in ["capabilities_any", "capabilities_all"]:
        if field not in recommended_fields:
            issues.append(
                f"governance/PROFILE_ADDON_FACTORY_CONTRACT.json: recommendedAddonManifestFields missing '{field}'"
            )


def check_governance_reason_ssot_alignment(issues: list[str]) -> None:
    """SSOT alignment for governance reason contracts (rescued from check_governance_reason_contract_alignment).

    Validates:
    1. persist_workspace_artifacts.py — _PERSISTENCE_REQUIRED_TOKENS membership
    2. map_audit_to_canonical.py — LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON constant + code tokens
    3. AUDIT_REASON_CANONICAL_MAP.json — structural keys
    """
    # 1. Persistence tokens
    try:
        from governance.entrypoints.persist_workspace_artifacts import _PERSISTENCE_REQUIRED_TOKENS
    except ImportError as exc:
        issues.append(f"governance/persist_workspace_artifacts.py: import failed: {exc}")
        _PERSISTENCE_REQUIRED_TOKENS = ()

    required_persistence_tokens = [
        '"status": "blocked"',
        '"reason_code": "BLOCKED-WORKSPACE-PERSISTENCE"',
        '"missing_evidence"',
        '"recovery_steps"',
        '"next_command"',
    ]
    for token in required_persistence_tokens:
        if token not in _PERSISTENCE_REQUIRED_TOKENS:
            issues.append(
                f"governance/persist_workspace_artifacts.py: _PERSISTENCE_REQUIRED_TOKENS missing {token!r}"
            )

    # 2. Audit-to-canonical bridge
    try:
        from governance.entrypoints.map_audit_to_canonical import LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON
    except ImportError as exc:
        issues.append(f"governance/map_audit_to_canonical.py: import failed: {exc}")
        LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON = None

    if LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON is not None:
        if LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON != "WARN-UNMAPPED-AUDIT-REASON":
            issues.append(
                f"governance/map_audit_to_canonical.py: LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON "
                f"expected 'WARN-UNMAPPED-AUDIT-REASON', found {LEGACY_DEFAULT_UNMAPPED_AUDIT_REASON!r}"
            )

    # Text search on .py file for code-level tokens (code is authority, not prose)
    bridge_path = ROOT / "governance" / "entrypoints" / "map_audit_to_canonical.py"
    if bridge_path.exists():
        bridge_text = read_text(bridge_path)
        code_tokens = ["--strict-unmapped", "opencode.audit-canonical-bridge.v1"]
        missing_code = [t for t in code_tokens if t not in bridge_text]
        if missing_code:
            issues.append(f"governance/map_audit_to_canonical.py: missing code tokens {missing_code}")
    else:
        issues.append("governance/map_audit_to_canonical.py: file missing")

    # 3. AUDIT_REASON_CANONICAL_MAP.json — structural check
    map_path = ROOT / "governance" / "assets" / "catalogs" / "AUDIT_REASON_CANONICAL_MAP.json"
    if not map_path.exists():
        issues.append("governance/AUDIT_REASON_CANONICAL_MAP.json: file missing")
        return

    try:
        map_data = json.loads(read_text(map_path))
    except json.JSONDecodeError as exc:
        issues.append(f"governance/AUDIT_REASON_CANONICAL_MAP.json: invalid JSON: {exc}")
        return

    # Check $schema key
    if map_data.get("$schema") != "opencode.audit-reason-map.v1":
        issues.append(
            f"governance/AUDIT_REASON_CANONICAL_MAP.json: expected $schema='opencode.audit-reason-map.v1', "
            f"found {map_data.get('$schema')!r}"
        )

    # Check mappings keys
    mappings = map_data.get("mappings", {})
    required_mappings = ["BR_MISSING_SESSION_GATE_STATE", "BR_MISSING_RULEBOOK_RESOLUTION", "BR_SCOPE_ARTIFACT_MISSING"]
    missing_mappings = [k for k in required_mappings if k not in mappings]
    if missing_mappings:
        issues.append(f"governance/AUDIT_REASON_CANONICAL_MAP.json: missing mapping keys {missing_mappings}")

    # Check default_unmapped
    if map_data.get("default_unmapped") != "WARN-UNMAPPED-AUDIT-REASON":
        issues.append(
            f"governance/AUDIT_REASON_CANONICAL_MAP.json: expected default_unmapped='WARN-UNMAPPED-AUDIT-REASON', "
            f"found {map_data.get('default_unmapped')!r}"
        )


def check_bootstrap_binding_evidence_reason_codes(issues: list[str]) -> None:
    """Verify bootstrap_binding_evidence.py emits registered reason codes (rescued from check_start_evidence_boundaries)."""
    try:
        from governance.domain.reason_codes import (
            BLOCKED_MISSING_BINDING_FILE,
            BLOCKED_VARIABLE_RESOLUTION,
            is_registered_reason_code,
        )
    except ImportError as exc:
        issues.append(f"governance/domain/reason_codes.py: import failed: {exc}")
        return

    # Verify codes are in canonical registry
    for code_name, code_value in [
        ("BLOCKED_MISSING_BINDING_FILE", BLOCKED_MISSING_BINDING_FILE),
        ("BLOCKED_VARIABLE_RESOLUTION", BLOCKED_VARIABLE_RESOLUTION),
    ]:
        if not is_registered_reason_code(code_value):
            issues.append(
                f"governance/domain/reason_codes.py: {code_name} ({code_value!r}) not in canonical registry"
            )

    # Text search bootstrap_binding_evidence.py to verify it actually emits those codes
    binding_path = ROOT / "governance" / "entrypoints" / "bootstrap_binding_evidence.py"
    if not binding_path.exists():
        issues.append("governance/entrypoints/bootstrap_binding_evidence.py: file missing")
        return

    binding_text = read_text(binding_path)
    for code_value in [BLOCKED_MISSING_BINDING_FILE, BLOCKED_VARIABLE_RESOLUTION]:
        if code_value not in binding_text:
            issues.append(
                f"governance/entrypoints/bootstrap_binding_evidence.py: does not emit reason code {code_value!r}"
            )


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Validate governance SSOT contracts (schema, JSON, Python).")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "governance" / "governance_lint_report.json",
        help="Output path for JSON report (default: governance/governance_lint_report.json).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show all issues even on success.")
    parser.add_argument("--skip-yaml", action="store_true", help="Skip YAML schema validation")
    args = parser.parse_args()

    issues: list[str] = []

    # --- SSOT guard (subprocess) ---
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "ssot_guard.py")],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            issues.append("SSOT guard check failed")
            if proc.stdout:
                issues.append(proc.stdout.strip())
            if proc.stderr:
                issues.append(proc.stderr.strip())
    except Exception as exc:
        issues.append(f"SSOT guard check failed to run: {exc}")

    # --- YAML schema validation ---
    if not args.skip_yaml:
        check_yaml_rulebook_schema(issues)

    # --- Addon manifest / catalog checks ---
    check_manifest_contract(issues)
    check_required_addon_references(issues)

    # --- Template quality ---
    check_template_quality_gate(issues)

    # --- JSON contract structural checks ---
    check_workflow_template_factory_contract(issues)
    check_customer_script_catalog_contract(issues)
    check_customer_markdown_exclusion_policy(issues)
    check_security_gate_contract(issues)
    check_response_contract_validator_presence(issues)

    # --- Rescued SSOT checks (JSON + Python imports, no MD) ---
    check_response_envelope_schema_keys(issues)
    check_factory_contract_json_keys(issues)
    check_governance_reason_ssot_alignment(issues)
    check_bootstrap_binding_evidence_reason_codes(issues)

    # --- Cluster 1+3 invariant enforcement ---
    check_catalog_version_format(issues)
    check_artifact_hash_integrity(issues)

    # --- Cluster 6a+8c tenant config enforcement ---
    check_tenant_config_schema(issues)
    check_tenant_config_references_valid_profiles(issues)

    # --- MD rails-only tripwire (verifies MD does NOT have authority) ---
    check_md_rails_only_tripwire(issues)

    # Build report
    report = {
        "schema": "governance.lint-report.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "PASS" if not issues else "FAIL",
        "issue_count": len(issues),
        "issues": issues if issues else [],
    }

    # Write report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if issues:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe_issues = [str(issue).encode(encoding, errors="replace").decode(encoding, errors="replace") for issue in issues]
        print("Governance lint FAILED:")
        for issue in safe_issues:
            print(f"- {issue}")
        print("")
        print(f"Report written to: {output_path}")
        print("For verbose output, run: ${PYTHON_COMMAND} scripts/governance_lint.py --verbose")
        return 1

    if args.verbose:
        print("Governance lint PASSED (no issues found).")
    print("Governance lint OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
