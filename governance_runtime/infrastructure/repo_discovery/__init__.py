"""Repository discovery infrastructure module."""
from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import (
    discover_structural_facts,
    StructuralFacts,
    Confidence,
    Evidence,
    ModuleFact,
    EntryPointFact,
    DataStoreFact,
    TestingFact,
    BuildAndToolingFact,
)

__all__ = [
    "discover_structural_facts",
    "StructuralFacts",
    "Confidence",
    "Evidence",
    "ModuleFact",
    "EntryPointFact",
    "DataStoreFact",
    "TestingFact",
    "BuildAndToolingFact",
]
