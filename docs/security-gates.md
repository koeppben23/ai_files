# Security Gates

This runbook documents deterministic security checks and policy enforcement.

## Workflow

- `.github/workflows/security.yml`

Scanners included:

- `gitleaks` (secret scanning)
- `pip-audit` (Python dependency findings)
- `actionlint` + `zizmor` (workflow hardening checks)
- `CodeQL` (SAST)

## Policy source

- `diagnostics/SECURITY_GATE_POLICY.json`

Key policy controls:

- `block_on_severities`: findings at these severities block the gate
- `fail_closed_on_scanner_error`: scanner failures block the gate
- `session_state_evidence_key`: canonical evidence mapping key (`SESSION_STATE.BuildEvidence.Security`)

## Evidence outputs

Each scanner writes a summary JSON file in `diagnostics/security-evidence/`.

The final policy gate aggregates all scanner summaries with:

```bash
python3 scripts/evaluate_security_evidence.py \
  --policy diagnostics/SECURITY_GATE_POLICY.json \
  --input diagnostics/security-evidence/<scanner>.summary.json \
  --output diagnostics/security-evidence/security_summary.json
```

`security_summary.json` is the machine-readable security evidence artifact for governance review.

## Blocking semantics

The gate blocks when either condition holds:

1. any finding severity in `block_on_severities` has count > 0
2. scanner status is not `success` and `fail_closed_on_scanner_error=true`
