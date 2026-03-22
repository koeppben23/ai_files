# Architecture Violation Inventory

## Type A: Real Infrastructure (IO/Persistenz/Pfad/Systemzeit)

| File | Import | Line | Fix |
|------|--------|------|-----|
| phase5_normalizer.py | append_jsonl | L169 | Inject as audit_sink |
| phase5_normalizer.py | now_iso | L168 | Inject as clock |
| legacy_compat.py | now_iso | L25 | Inject as clock |
| legacy_compat.py | load_json | L85 | Inject as json_loader |
| llm_caller.py | write_json_atomic | L142 | Return data, let caller persist |
| orchestrator.py | load_json | L348 | Inject as json_loader |

## Type B: Pure Helpers (stateless, no IO)

| File | Import | Line | Fix |
|------|--------|------|-----|
| phase5_normalizer.py | safe_str | L30 | Move to shared/string_utils.py |
| orchestrator.py | coerce_int | L39 | Move to shared/number_utils.py |
| orchestrator.py | sha256_text | L40 | Move to shared/hash_utils.py |

## Already Allowlisted (audit_readout_builder.py)

| Import | Reason |
|--------|--------|
| verify_repository_manifest | Composition Root |
| verify_run_archive | Composition Root |
| parse_session_pointer_document | Composition Root |
| resolve_active_session_state_path | Composition Root |
