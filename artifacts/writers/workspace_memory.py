def render_workspace_memory(*, date: str, repo_name: str, repo_fingerprint: str) -> str:
    return "\n".join(
        [
            "WorkspaceMemory:",
            '  Version: "1.0"',
            "  Repo:",
            f'    RepoName: "{repo_name}"',
            f'    RepoFingerprint: "{repo_fingerprint}"',
            f'  UpdatedAt: "{date}"',
            "  Provenance:",
            '    Source: "Phase2+Phase5"',
            '    EvidenceMode: "evidence-required"',
            "  Conventions: {}",
            "  Patterns: {}",
            "  Decisions:",
            "    Defaults: []",
            "  Deviations: []",
            "",
        ]
    )
