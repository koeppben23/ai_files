#!/usr/bin/env python3
"""Curate extracted YAML rulebooks to pass schema validation."""

from __future__ import annotations

import json
import yaml
from pathlib import Path
import sys
from typing import Optional, List, Dict, Any


def curate_rulebook(path: Path) -> Dict[str, Any]:
    """Apply curation fixes to a rulebook YAML."""
    data = yaml.safe_load(path.read_text())
    
    if data is None:
        return data
    
    metadata = data.get("metadata", {})
    profile_id = metadata.get("id", path.stem)
    
    if "activation" not in data:
        data["activation"] = {
            "type": "manifest",
            "conditions": []
        }
    
    if "evidence_contract" not in data:
        data["evidence_contract"] = {
            "required_artifacts": [],
            "required_fields": []
        }
    
    if "verification_commands" not in data:
        data["verification_commands"] = []
    
    if "phase_integration" not in data:
        data["phase_integration"] = {
            "phases": [],
            "required_outputs": [],
            "required_checks": []
        }
    
    if "references" not in data:
        data["references"] = []
    
    if "patterns" not in data:
        data["patterns"] = []
    
    if "anti_patterns" not in data:
        data["anti_patterns"] = []
    
    if "decision_trees" not in data:
        data["decision_trees"] = []
    
    if "warning_codes" in data:
        for wc in data["warning_codes"]:
            if wc.get("recovery") is None:
                wc["recovery"] = ""
            if not wc.get("triggers"):
                wc["triggers"] = []
    
    if "decision_trees" in data:
        fixed_trees = []
        for dt in data["decision_trees"]:
            if "title" in dt:
                del dt["title"]
            
            if "root" in dt and dt["root"]:
                root = dt["root"]
                if isinstance(root, dict):
                    if "yes" in root and isinstance(root.get("yes"), bool):
                        root["yes"] = {"node_type": "leaf", "result": str(root.get("yes", ""))}
                    if "no" in root and isinstance(root.get("no"), bool):
                        root["no"] = {"node_type": "leaf", "result": str(root.get("no", ""))}
                    
                    if "yes" in root and isinstance(root.get("yes"), dict):
                        for key in ["yes", "no"]:
                            if key in root.get("yes", {}):
                                if isinstance(root["yes"].get(key), bool):
                                    root["yes"][key] = {"node_type": "leaf", "result": str(root["yes"].get(key) if root["yes"].get(key) else "")}
                    if "no" in root and isinstance(root.get("no"), dict):
                        for key in ["yes", "no"]:
                            if key in root.get("no", {}):
                                if isinstance(root["no"].get(key), bool):
                                    root["no"][key] = {"node_type": "leaf", "result": str(root["no"].get(key) if root["no"].get(key) else "")}
            
            fixed_trees.append(dt)
        data["decision_trees"] = fixed_trees
    
    return data


def main(argv: list[str] | None = None) -> int:
    profiles_dir = Path("rulesets/profiles")
    
    if not profiles_dir.exists():
        print(f"ERROR: {profiles_dir} not found", file=sys.stderr)
        return 1
    
    curated = 0
    for yaml_file in sorted(profiles_dir.glob("*.yml")):
        original = yaml_file.read_text()
        curated_data = curate_rulebook(yaml_file)
        curated_yaml = yaml.dump(curated_data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)
        
        if original != curated_yaml:
            yaml_file.write_text(curated_yaml)
            curated += 1
            print(f"Curated: {yaml_file.name}")
    
    print(f"\nTotal curated: {curated} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
