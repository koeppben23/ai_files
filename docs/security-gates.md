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

## Evidence semantics and coverage caveat

Scanner output can be structurally valid while still representing partial coverage.

- If dependency manifests are absent (`requirements*.txt`), `pip-audit` emits `pip-audit.empty.json` and reports no findings.
- Treat this as "no dependency manifest evidence available" rather than proof that dependencies are secure.
- For customer/security reporting, dependency claims should be marked `NOT_VERIFIED` until manifest-backed dependency evidence exists.
- Deterministic reason-code mapping should use `NOT_VERIFIED-MISSING-EVIDENCE` for dependency-security claims without manifest evidence.

## Blocking semantics

The gate blocks when either condition holds:

1. any finding severity in `block_on_severities` has count > 0
2. scanner status is not `success` and `fail_closed_on_scanner_error=true`
