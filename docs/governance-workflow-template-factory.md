# Governance Workflow Template Factory

This runbook standardizes GitHub Actions workflow templates the same way rulebooks are standardized: one catalog, deterministic validation, and scaffolded creation from known archetypes.

Customer install path:

- script: `<config_root>/commands/scripts/workflow_template_factory.py`
- template root: `<config_root>/commands/templates/github-actions/`

## Canonical files

- Catalog: `templates/github-actions/template_catalog.json`
- Factory contract: `diagnostics/GITHUB_ACTIONS_TEMPLATE_FACTORY_CONTRACT.json`
- Factory script: `scripts/workflow_template_factory.py`
- Release shipping of customer-facing scripts is defined in `diagnostics/CUSTOMER_SCRIPT_CATALOG.json`.

## Validate catalog consistency

```bash
${PYTHON_COMMAND} scripts/workflow_template_factory.py
```

Installed-customer variant:

```bash
${PYTHON_COMMAND} commands/scripts/workflow_template_factory.py check --repo-root commands
```

This check is fail-closed and enforced through `scripts/governance_lint.py`.

Validation guarantees:

- every `templates/github-actions/governance-*.yml` file is listed once in the catalog
- every catalog entry points to an existing workflow file
- `template_key` and file name stay deterministic (`templates/github-actions/<template_key>.yml`)
- only approved archetypes are allowed

## Scaffold a new workflow template

```bash
${PYTHON_COMMAND} scripts/workflow_template_factory.py scaffold \
  --template-key governance-example-gate \
  --archetype pr_gate_shadow_live_verify \
  --title "Governance Example Gate" \
  --purpose "Example shadow-to-review governance gate"
```

Installed-customer variant:

```bash
${PYTHON_COMMAND} commands/scripts/workflow_template_factory.py scaffold \
  --repo-root commands \
  --template-key governance-example-gate \
  --archetype pr_gate_shadow_live_verify \
  --title "Governance Example Gate" \
  --purpose "Example shadow-to-review governance gate"
```

Scaffold behavior:

- creates `templates/github-actions/governance-example-gate.yml`
- appends a sorted entry to `templates/github-actions/template_catalog.json`
- starts from an archetype skeleton so new workflows begin with the same governance baseline

## Supported archetypes

- `pr_gate_shadow_live_verify`
- `pipeline_roles_hardened`
- `ruleset_release`
- `golden_output_stability`
- `golden_baseline_update`
