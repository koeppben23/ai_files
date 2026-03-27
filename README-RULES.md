# Rules Overview

This document is a non-normative navigation surface for governance rules.
It does not define runtime behavior.

## Canonical Rule Authorities

- Phase routing, transitions, and gate semantics:
  - Operative control-plane source: `${SPEC_HOME}/phase_api.yaml`
  - Repo-side source of that projected spec: `governance_spec/phase_api.yaml`
  - Runtime enforcement surface: `governance_runtime/kernel/*`
- Core technical and quality constraints:
  - `governance_content/reference/rules.md`
- Multi-phase interpretation guidance:
  - `governance_content/reference/master.md`
- Session-state contract:
  - `SESSION_STATE_SCHEMA.md`

## Operator References

- Product and install surface: `README.md`
- OpenCode lifecycle and rails: `README-OPENCODE.md`
- Binding evidence naming guide: `governance_runtime/docs/BINDING_EVIDENCE_NAMING.md`
- Quickstart flow: `QUICKSTART.md`
- Install path bindings: `governance_content/docs/install-layout.md`

## Scope Notes

- `README-RULES.md` is descriptive only.
- Runtime truth is implemented under `governance_runtime/`.
- Content truth is documented under `governance_content/reference/`.
- Spec truth is versioned under `governance_spec/`.

## Compatibility and Drift Policy

- If this file conflicts with canonical rule authorities, canonical authorities win.
- Keep this file aligned with current `governance_runtime/`, `governance_content/reference/`, and `governance_spec/` contracts.

## License

See `LICENSE`.
