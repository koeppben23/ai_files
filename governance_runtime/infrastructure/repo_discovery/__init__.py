"""Repository discovery infrastructure module."""
from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import (
    discover_structural_facts,
    StructuralFacts,
    DiscoveredFacts,
    Confidence,
    Evidence,
    ModuleFact,
    EntryPointFact,
    DataStoreFact,
    TestingFact,
    BuildAndToolingFact,
)
from governance_runtime.infrastructure.repo_discovery.semantic_discovery import (
    discover_semantic_facts,
    SemanticFacts,
    SSOTFact,
    InvariantFact,
    ConventionFact,
    PatternFact,
    DefaultFact,
    DeviationFact,
)

__all__ = [
    # Structural discovery
    "discover_structural_facts",
    "StructuralFacts",
    "DiscoveredFacts",
    "Confidence",
    "Evidence",
    "ModuleFact",
    "EntryPointFact",
    "DataStoreFact",
    "TestingFact",
    "BuildAndToolingFact",
    # Semantic discovery
    "discover_semantic_facts",
    "SemanticFacts",
    "SSOTFact",
    "InvariantFact",
    "ConventionFact",
    "PatternFact",
    "DefaultFact",
    "DeviationFact",
]
