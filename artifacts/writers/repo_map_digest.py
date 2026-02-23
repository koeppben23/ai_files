def repo_map_digest_section(date: str, repository_type: str) -> str:
    return "\n".join(
        [
            f"## Repo Map Digest -- {date}",
            "Meta:",
            "- GitHead: unknown",
            "- RepoSignature: unknown",
            "- ComponentScope: none",
            "- Provenance: Phase2",
            "",
            f"RepositoryType: {repository_type}",
            "Architecture: unknown",
            "Modules:",
            "- none (no evidence-backed digest yet)",
            "EntryPoints:",
            "- none",
            "DataStores:",
            "- none",
            "BuildAndTooling:",
            "- unknown",
            "Testing:",
            "- unknown",
            "ConventionsDigest:",
            "- Seed snapshot; refresh after evidence-backed Phase 2 discovery.",
            "ArchitecturalInvariants:",
            "- unknown",
            "",
        ]
    )


def render_repo_map_digest_create(*, date: str, repo_name: str, repository_type: str) -> str:
    section = repo_map_digest_section(date, repository_type)
    return "# Repo Map Digest\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"
