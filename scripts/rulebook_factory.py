#!/usr/bin/env python3
"""Scaffold governance profile/addon rulebooks and addon manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


PROFILE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ADDON_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")
RULEBOOK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*$")


def _write_file(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"target exists (use --force): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _require_non_empty(name: str, values: list[str]) -> list[str]:
    cleaned = [v.strip() for v in values if v.strip()]
    if not cleaned:
        raise ValueError(f"missing required input: {name}")
    return cleaned


def _parse_signal_entries(values: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    for raw in values:
        item = raw.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"invalid --signal value '{raw}'; expected key=value")
        key, val = item.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key or not val:
            raise ValueError(f"invalid --signal value '{raw}'; expected key=value")
        parsed.append((key, val))
    if not parsed:
        raise ValueError("missing required input: --signal key=value (at least one)")
    return parsed


def _render_profile_rulebook(
    *,
    profile_key: str,
    stack_scope: str,
    applicability_signals: list[str],
    quality_focus: list[str],
    blocking_policy: str,
) -> str:
    applicability = "\n".join(f"- {signal}" for signal in applicability_signals)
    quality = "\n".join(f"- {focus}" for focus in quality_focus)
    return (
        f"# Profile Rulebook: {profile_key}\n\n"
        "## Canonical Precedence Reference (Binding)\n"
        "- This profile delegates precedence to `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.\n"
        "- This rulebook MUST NOT redefine local precedence order.\n\n"
        "## Deterministic Applicability (Binding)\n"
        f"- Stack scope: {stack_scope}\n"
        "- applicability_signals (descriptive only; not independent activation logic):\n"
        f"{applicability}\n\n"
        "## Architecture and Test Quality Expectations (Binding)\n"
        f"{quality}\n\n"
        "## Canonical Evidence Paths (Binding)\n"
        "- `SESSION_STATE.AddonsEvidence.<addon_key>`\n"
        "- `SESSION_STATE.RepoFacts.CapabilityEvidence`\n"
        "- `SESSION_STATE.Diagnostics.ReasonPayloads`\n\n"
        "## Phase Integration (Binding)\n"
        "- Phase 2 / 2.1: determine deterministic profile fit using repository capabilities and hard signals.\n"
        "- Phase 4: implementation execution must remain evidence-first and fail-closed for required contracts.\n"
        "- Phase 5: run verification and claim mapping according to canonical reason/evidence rules.\n"
        "- Phase 6: closure requires deterministic summary and reproducible evidence pointers.\n"
        "- phase semantics MUST reference canonical `master.md` phase labels and MUST NOT redefine them locally.\n\n"
        "## Blocking Policy (Binding)\n"
        f"- {blocking_policy}\n"
        "- Claims without evidence mapping MUST be marked `not-verified`.\n\n"
        "## Shared Principal Governance Contracts (Binding)\n"
        "- rules.principal-excellence.md\n"
        "- rules.risk-tiering.md\n"
        "- rules.scorecard-calibration.md\n"
        "- SESSION_STATE.LoadedRulebooks.addons.principalExcellence\n"
        "- SESSION_STATE.LoadedRulebooks.addons.riskTiering\n"
        "- SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration\n"
        "- tracking keys are audit/trace pointers (map entries), not activation signals\n\n"
        "## Examples (GOOD/BAD)\n"
        "- GOOD: Evidence-backed profile behavior with explicit recovery and next action.\n"
        "- BAD: Implicit applicability decisions without capability/signal evidence.\n\n"
        "## Troubleshooting\n"
        "- Symptom: profile selected ambiguously -> Cause: insufficient capability evidence -> Fix: provide ranked shortlist and explicit selection.\n"
        "- Symptom: claims not-verified -> Cause: missing typed artifacts -> Fix: capture build/test artifacts and rerun verification.\n"
        "- Symptom: phase mismatch -> Cause: local phase aliases -> Fix: align wording to canonical `master.md` phase labels.\n"
    )


def _render_addon_manifest(
    *,
    addon_key: str,
    addon_class: str,
    rulebook_name: str,
    path_roots: list[str],
    owns_surfaces: list[str],
    touches_surfaces: list[str],
    capabilities_any: list[str],
    capabilities_all: list[str],
    signals: list[tuple[str, str]],
) -> str:
    roots = "\n".join(f"  - {root}" for root in path_roots)
    owns = "\n".join(f"  - {surface}" for surface in owns_surfaces)
    touches = "\n".join(f"  - {surface}" for surface in touches_surfaces)
    signal_lines = "\n".join(f"    - {key}: {value}" for key, value in signals)

    lines = [
        f"addon_key: {addon_key}",
        f"addon_class: {addon_class}",
        f"rulebook: rules.{rulebook_name}.md",
        "manifest_version: 1",
        "path_roots:",
        roots,
        "owns_surfaces:",
        owns,
        "touches_surfaces:",
        touches,
    ]
    if capabilities_any:
        lines.extend(["capabilities_any:", "\n".join(f"  - {cap}" for cap in capabilities_any)])
    if capabilities_all:
        lines.extend(["capabilities_all:", "\n".join(f"  - {cap}" for cap in capabilities_all)])

    lines.extend(["signals:", "  any:", signal_lines])
    return "\n".join(lines) + "\n"


def _render_addon_rulebook(
    *,
    addon_key: str,
    addon_class: str,
    domain_scope: str,
    critical_quality_claims: list[str],
) -> str:
    claims = "\n".join(f"- {claim}" for claim in critical_quality_claims)
    class_behavior = (
        f"- Addon class: {addon_class} (missing code-phase rulebook -> `BLOCKED-MISSING-ADDON:{addon_key}`)"
        if addon_class == "required"
        else "- Addon class: advisory (missing evidence -> WARN + recovery, non-blocking)."
    )

    return (
        f"# Addon Rulebook: {addon_key}\n\n"
        "## Canonical Precedence Reference (Binding)\n"
        "- This addon delegates precedence to `rules.md` anchor `RULEBOOK-PRECEDENCE-POLICY`.\n"
        "- This rulebook MUST NOT redefine local precedence order.\n\n"
        "## Addon Class and Activation Semantics (Binding)\n"
        f"{class_behavior}\n"
        "- Activation remains manifest-owned (`profiles/addons/*.addon.yml`) with capability-first evaluation and hard-signal fallback.\n\n"
        "## Domain Scope (Binding)\n"
        f"- {domain_scope}\n\n"
        "## Critical Quality Claims (Binding)\n"
        f"{claims}\n"
        "- Claims without evidence mapping MUST be marked `not-verified`.\n\n"
        "## Canonical Evidence Paths (Binding)\n"
        "- `SESSION_STATE.AddonsEvidence.<addon_key>`\n"
        "- `SESSION_STATE.RepoFacts.CapabilityEvidence`\n"
        "- `SESSION_STATE.Diagnostics.ReasonPayloads`\n\n"
        "## Phase Integration (Binding)\n"
        "- Phase 2 / 2.1: evaluate deterministic addon applicability from capability and signal evidence.\n"
        "- Phase 4: apply addon constraints to implementation and required checks.\n"
        "- Phase 5.3: enforce principal scorecard quality thresholds and verification mapping.\n"
        "- Phase 6: include addon-specific closure evidence and deterministic next action.\n"
        "- phase semantics MUST reference canonical `master.md` phase labels and MUST NOT redefine them locally.\n\n"
        "## Shared Principal Governance Contracts (Binding)\n"
        "- rules.principal-excellence.md\n"
        "- rules.risk-tiering.md\n"
        "- rules.scorecard-calibration.md\n"
        "- SESSION_STATE.LoadedRulebooks.addons.principalExcellence\n"
        "- SESSION_STATE.LoadedRulebooks.addons.riskTiering\n"
        "- SESSION_STATE.LoadedRulebooks.addons.scorecardCalibration\n"
        "- tracking keys are audit/trace pointers (map entries), not activation signals\n\n"
        "## Warnings and Recovery (Binding)\n"
        "- WARN-PRINCIPAL-EVIDENCE-MISSING\n"
        "- WARN-SCORECARD-CALIBRATION-INCOMPLETE\n\n"
        "## Examples (GOOD/BAD)\n"
        "- GOOD: Addon decision backed by capability evidence and deterministic manifest signals.\n"
        "- BAD: Addon behavior claimed without evidence or with local precedence override.\n\n"
        "## Troubleshooting\n"
        "- Symptom: addon blocked unexpectedly -> Cause: missing required evidence -> Fix: collect required artifacts and rerun gate.\n"
        "- Symptom: addon warnings persist -> Cause: advisory evidence gap -> Fix: execute recovery steps and ingest evidence.\n"
        "- Symptom: activation mismatch -> Cause: capabilities/signals conflict -> Fix: inspect manifest and normalize deterministic selectors.\n"
    )


def run_profile(args: argparse.Namespace) -> dict[str, object]:
    profile_key = args.profile_key.strip()
    if not PROFILE_KEY_RE.fullmatch(profile_key):
        raise ValueError("invalid --profile-key; expected lowercase kebab-case")

    output_root = Path(args.output_root).resolve()
    profiles_dir = output_root / "profiles"
    file_name = f"rules.{profile_key}.md" if args.legacy_name else f"rules_{profile_key}.md"
    rulebook_path = profiles_dir / file_name

    content = _render_profile_rulebook(
        profile_key=profile_key,
        stack_scope=args.stack_scope.strip(),
        applicability_signals=_require_non_empty("--applicability-signal", args.applicability_signal),
        quality_focus=_require_non_empty("--quality-focus", args.quality_focus),
        blocking_policy=args.blocking_policy.strip(),
    )

    if not args.dry_run:
        _write_file(rulebook_path, content, force=args.force)

    return {
        "status": "OK",
        "mode": "profile",
        "dry_run": args.dry_run,
        "rulebook": str(rulebook_path.relative_to(output_root)),
    }


def run_addon(args: argparse.Namespace) -> dict[str, object]:
    addon_key = args.addon_key.strip()
    if not ADDON_KEY_RE.fullmatch(addon_key):
        raise ValueError("invalid --addon-key; expected alphanumeric key like backendPythonTemplates")

    rulebook_name = args.rulebook_name.strip()
    if not RULEBOOK_NAME_RE.fullmatch(rulebook_name):
        raise ValueError("invalid --rulebook-name")

    output_root = Path(args.output_root).resolve()
    profiles_dir = output_root / "profiles"
    manifests_dir = profiles_dir / "addons"
    manifest_path = manifests_dir / f"{addon_key}.addon.yml"
    rulebook_path = profiles_dir / f"rules.{rulebook_name}.md"

    path_roots = _require_non_empty("--path-root", args.path_root)
    owns_surfaces = _require_non_empty("--owns-surface", args.owns_surface)
    touches_surfaces = _require_non_empty("--touches-surface", args.touches_surface)
    critical_claims = _require_non_empty("--critical-quality-claim", args.critical_quality_claim)
    capabilities_any = [v.strip() for v in args.capability_any if v.strip()]
    capabilities_all = [v.strip() for v in args.capability_all if v.strip()]
    if not capabilities_any and not capabilities_all:
        raise ValueError("at least one capability is required (--capability-any or --capability-all)")

    manifest = _render_addon_manifest(
        addon_key=addon_key,
        addon_class=args.addon_class,
        rulebook_name=rulebook_name,
        path_roots=path_roots,
        owns_surfaces=owns_surfaces,
        touches_surfaces=touches_surfaces,
        capabilities_any=capabilities_any,
        capabilities_all=capabilities_all,
        signals=_parse_signal_entries(args.signal),
    )
    rulebook = _render_addon_rulebook(
        addon_key=addon_key,
        addon_class=args.addon_class,
        domain_scope=args.domain_scope.strip(),
        critical_quality_claims=critical_claims,
    )

    if not args.dry_run:
        _write_file(manifest_path, manifest, force=args.force)
        _write_file(rulebook_path, rulebook, force=args.force)

    return {
        "status": "OK",
        "mode": "addon",
        "dry_run": args.dry_run,
        "manifest": str(manifest_path.relative_to(output_root)),
        "rulebook": str(rulebook_path.relative_to(output_root)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold governance profile/addon rulebooks and manifests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("profile", help="Generate a profile rulebook")
    profile.add_argument("--profile-key", required=True)
    profile.add_argument("--stack-scope", required=True)
    profile.add_argument("--applicability-signal", action="append", default=[])
    profile.add_argument("--quality-focus", action="append", default=[])
    profile.add_argument("--blocking-policy", required=True)
    profile.add_argument("--output-root", default=".")
    profile.add_argument("--legacy-name", action="store_true", help="Use legacy rules.<profile>.md naming")
    profile.add_argument("--force", action="store_true")
    profile.add_argument("--dry-run", action="store_true")

    addon = subparsers.add_parser("addon", help="Generate addon manifest + addon rulebook")
    addon.add_argument("--addon-key", required=True)
    addon.add_argument("--addon-class", required=True, choices=["required", "advisory"])
    addon.add_argument("--rulebook-name", required=True)
    addon.add_argument("--signal", action="append", default=[])
    addon.add_argument("--domain-scope", required=True)
    addon.add_argument("--critical-quality-claim", action="append", default=[])
    addon.add_argument("--path-root", action="append", default=["."])
    addon.add_argument("--owns-surface", action="append", default=[])
    addon.add_argument("--touches-surface", action="append", default=[])
    addon.add_argument("--capability-any", action="append", default=[])
    addon.add_argument("--capability-all", action="append", default=[])
    addon.add_argument("--output-root", default=".")
    addon.add_argument("--force", action="store_true")
    addon.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.command == "profile":
            payload = run_profile(args)
        else:
            payload = run_addon(args)
    except ValueError as exc:
        print(json.dumps({"status": "BLOCKED", "message": str(exc)}, ensure_ascii=True))
        return 2

    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
