# Governance Customer Scripts

This runbook defines which helper scripts are customer-relevant and shipped in release archives.

After `install.py`, these scripts are installed under `<config_root>/commands/scripts/`.
Customers can run them directly from that installed path without GitHub access.

## Canonical source

- Catalog file: `diagnostics/CUSTOMER_SCRIPT_CATALOG.json`
- Catalog checker CLI (`scripts/customer_script_catalog.py`) is a maintainer/internal helper and is not installed for customers.
- Markdown exclusions from release archives: `diagnostics/CUSTOMER_MARKDOWN_EXCLUDE.json`

## List shipped customer scripts

Check entries in `diagnostics/CUSTOMER_SCRIPT_CATALOG.json` where:

- `customer_relevant: true`
- `ship_in_release: true`

## Validate catalog contract

```bash
python3 scripts/governance_lint.py
```

Validation is fail-closed and enforced by `python3 scripts/governance_lint.py`.

## Customer-essential scripts (tier=essential)

- `scripts/rulebook_factory.py`
- `scripts/workflow_template_factory.py`
- `scripts/build_ruleset_lock.py`
- `scripts/run_quality_benchmark.py`
- `scripts/generate_golden_outputs.py`
- `scripts/governance_lint.py`
- `scripts/validate_addons.py`

## OpenCode templates for new governance artifacts

In addition to the CLI scripts, OpenCode provides Markdown templates for creating new rulebooks and addons interactively:

- `new_profile.md` — OpenCode template for creating a new profile rulebook (`profiles/rules_<profile>.md`)
- `new_addon.md` — OpenCode template for creating a new addon rulebook + manifest pair (`profiles/rules_<addon>.md`, `profiles/addons/<addon_key>.addon.yml`)

Run `/new_profile` or `/new_addon` in an OpenCode session to invoke these templates.

## Rulebook generation quick start

Generate a profile rulebook:

```bash
python3 scripts/rulebook_factory.py profile \
  --profile-key backend-rust \
  --stack-scope "Rust backend services" \
  --applicability-signal "cargo-lock-present" \
  --quality-focus "deterministic tests" \
  --quality-focus "api contract stability" \
  --blocking-policy "missing required evidence blocks Phase 4 entry"
```

Generate an addon manifest + addon rulebook pair:

```bash
python3 scripts/rulebook_factory.py addon \
  --addon-key rustApiTemplates \
  --addon-class required \
  --rulebook-name backend-rust-templates \
  --signal fileGlob="**/*.rs" \
  --domain-scope "Template and API conformance for Rust services" \
  --critical-quality-claim "template outputs are evidence-backed" \
  --owns-surface backend_templates \
  --touches-surface api_contract \
  --capability-any rust
```
