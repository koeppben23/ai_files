"""Embedded SESSION_STATE schema loaded from JSON resource.

This module provides the SESSION_STATE schema for runtime validation.
The schema is loaded from the JSON file at diagnostics/schemas/session_state.core.v1.schema.json
using importlib.resources, which works for both filesystem and frozen package contexts.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Final


def _load_schema() -> dict[str, object]:
    """Load schema from JSON resource, with hardcoded fallback."""
    try:
        schema_text = resources.files("diagnostics.schemas").joinpath("session_state.core.v1.schema.json").read_text(encoding="utf-8")
        return json.loads(schema_text)
    except Exception:
        # Hardcoded fallback for frozen/embedded contexts where resources API fails
        # This MUST be kept in sync with session_state.core.v1.schema.json
        return _HARDCODED_FALLBACK_SCHEMA


_HARDCODED_FALLBACK_SCHEMA: dict[str, object] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "diagnostics/schemas/session_state.core.v1.schema.json",
    "title": "SESSION_STATE Core Schema",
    "description": "Core structural validation for SESSION_STATE documents after Phase 1 bootstrap.",
    "type": "object",
    "required": ["SESSION_STATE"],
    "properties": {
        "SESSION_STATE": {
            "type": "object",
            "required": [
                "session_state_version",
                "ruleset_hash",
                "Phase",
                "Mode",
                "OutputMode",
                "ConfidenceLevel",
                "Next",
                "Bootstrap",
                "Scope",
                "RepoFacts",
                "LoadedRulebooks",
                "AddonsEvidence",
                "RulebookLoadEvidence",
                "ActiveProfile",
                "ProfileSource",
                "ProfileEvidence",
                "Gates",
            ],
            "properties": {
                "session_state_version": {"type": "integer", "minimum": 1},
                "ruleset_hash": {"type": "string", "minLength": 1},
                "Phase": {
                    "type": "string",
                    "enum": [
                        "1", "1.1-Bootstrap", "1.2-ProfileDetection", "1.3-CoreRulesActivation",
                        "2", "2.1-DecisionPack", "1.5-BusinessRules",
                        "3A", "3B-1", "3B-2",
                        "4", "5", "5.3", "5.4", "5.5", "5.6", "6",
                    ],
                },
                "Mode": {"type": "string", "enum": ["NORMAL", "DEGRADED", "DRAFT", "BLOCKED"]},
                "OutputMode": {"type": "string", "enum": ["ARCHITECT", "IMPLEMENT", "VERIFY"]},
                "ConfidenceLevel": {"type": "integer", "minimum": 0, "maximum": 100},
                "Next": {"type": "string", "minLength": 1},
                "Bootstrap": {
                    "type": "object",
                    "required": ["Present", "Satisfied", "Evidence"],
                    "properties": {
                        "Present": {"type": "boolean"},
                        "Satisfied": {"type": "boolean"},
                        "Evidence": {"type": "string"},
                    },
                    "additionalProperties": False,
                },
                "Scope": {
                    "type": "object",
                    "properties": {
                        "Repository": {"type": "string"},
                        "RepositoryType": {"type": "string"},
                        "ExternalAPIs": {"type": "array", "items": {"type": "string"}},
                        "BusinessRules": {"type": "string", "enum": ["not-applicable", "pending", "extracted"]},
                    },
                    "additionalProperties": True,
                },
                "RepoFacts": {
                    "type": "object",
                    "properties": {
                        "Capabilities": {"type": "array", "items": {"type": "string"}},
                        "CapabilityEvidence": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
                    },
                    "additionalProperties": True,
                },
                "LoadedRulebooks": {
                    "type": "object",
                    "properties": {
                        "core": {"type": "string"},
                        "profile": {"type": "string"},
                        "templates": {"type": "string"},
                        "addons": {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                    "additionalProperties": True,
                },
                "AddonsEvidence": {"type": "object", "additionalProperties": True},
                "RulebookLoadEvidence": {"type": "object", "additionalProperties": True},
                "ActiveProfile": {"type": "string"},
                "ProfileSource": {
                    "type": "string",
                    "enum": [
                        "user-explicit", "auto-detected-single", "repo-fallback",
                        "deferred", "component-scope-inferred", "component-scope-filtered", "ambiguous",
                    ],
                },
                "ProfileEvidence": {"type": "string"},
                "Gates": {
                    "type": "object",
                    "properties": {
                        "P5-Architecture": {"type": "string", "enum": ["pending", "approved", "rejected"]},
                        "P5.3-TestQuality": {"type": "string", "enum": ["pending", "pass", "pass-with-exceptions", "fail"]},
                        "P5.4-BusinessRules": {"type": "string", "enum": ["pending", "compliant", "compliant-with-exceptions", "gap-detected", "not-applicable"]},
                        "P5.5-TechnicalDebt": {"type": "string", "enum": ["pending", "approved", "rejected", "not-applicable"]},
                        "P5.6-RollbackSafety": {"type": "string", "enum": ["pending", "approved", "rejected", "not-applicable"]},
                        "P6-ImplementationQA": {"type": "string", "enum": ["pending", "ready-for-pr", "fix-required"]},
                    },
                    "additionalProperties": True,
                },
                "session_run_id": {"type": "string"},
                "repo_fingerprint": {"type": "string"},
                "workspace_ready": {"type": "boolean"},
                "workspace_ready_gate_committed": {"type": "boolean"},
                "Diagnostics": {
                    "type": "object",
                    "properties": {
                        "ReasonPayloads": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["reason_code", "surface"],
                                "properties": {
                                    "reason_code": {"type": "string", "pattern": "^(BLOCKED-|WARN-|NOT_VERIFIED-|OK$)"},
                                    "surface": {"type": "string"},
                                    "signals_used": {"type": "array", "items": {"type": "string"}},
                                    "recovery_steps": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 3},
                                    "next_command": {"type": "string"},
                                },
                            },
                        },
                        "TransitionTrace": {"type": "array", "items": {"type": "object"}},
                    },
                    "additionalProperties": True,
                },
                "CodebaseContext": {
                    "type": "object",
                    "properties": {
                        "ExistingAbstractions": {"type": "array"},
                        "DependencyGraph": {"type": "array"},
                        "PatternFingerprint": {"type": "object"},
                        "TechnicalDebtMarkers": {"type": "array"},
                    },
                    "additionalProperties": True,
                },
                "FeatureComplexity": {
                    "type": "object",
                    "required": ["Class", "Reason", "PlanningDepth"],
                    "properties": {
                        "Class": {"type": "string", "enum": ["SIMPLE-CRUD", "REFACTORING", "MODIFICATION", "COMPLEX", "STANDARD"]},
                        "Reason": {"type": "string"},
                        "PlanningDepth": {"type": "string", "enum": ["minimal", "standard", "full", "maximum"]},
                    },
                    "additionalProperties": False,
                },
                "BuildToolchain": {
                    "type": "object",
                    "properties": {
                        "CompileAvailable": {"type": "boolean"},
                        "CompileCmd": {"type": "string"},
                        "TestAvailable": {"type": "boolean"},
                        "TestCmd": {"type": "string"},
                        "FullVerifyCmd": {"type": "string"},
                        "BuildSystem": {"type": "string"},
                        "MissingTool": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
                "BuildEvidence": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["not-provided", "partially-provided", "provided-by-user", "verified-by-tool"]},
                        "CompileResult": {"type": "string", "enum": ["pass", "fail", "skipped"]},
                        "TestResult": {"type": "string", "enum": ["pass", "fail", "skipped"]},
                        "IterationsUsed": {
                            "type": "object",
                            "properties": {
                                "Compile": {"type": "integer", "minimum": 0, "maximum": 3},
                                "Test": {"type": "integer", "minimum": 0, "maximum": 3},
                            },
                        },
                        "ToolOutput": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        }
    },
    "additionalProperties": True,
}

SESSION_STATE_CORE_SCHEMA: Final[dict[str, object]] = _load_schema()
