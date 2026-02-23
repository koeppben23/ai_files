def decision_pack_section(date: str, date_compact: str) -> str:
    return "\n".join(
        [
            f"## Decision Pack -- {date}",
            "D-001: Run Phase 1.5 (Business Rules Discovery) now?",
            f"ID: DP-{date_compact}-001",
            "Status: proposed",
            "A) Yes",
            "B) No",
            "Recommendation: A (run lightweight Phase 1.5 to establish initial domain evidence)",
            "Evidence: Bootstrap seed context; lightweight discovery can improve downstream gate quality",
            "What would change it: keep B only when operator explicitly defers business-rules discovery",
            "",
        ]
    )


def render_decision_pack_create(*, date: str, date_compact: str, repo_name: str) -> str:
    section = decision_pack_section(date, date_compact)
    return "# Decision Pack\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"
