def decision_pack_section(date: str, date_compact: str) -> str:
    return "\n".join(
        [
            f"## Decision Pack -- {date}",
            "D-001: Apply Phase 1.5 Business Rules bootstrap policy",
            f"ID: DP-{date_compact}-001",
            "Status: automatic",
            "Action: Auto-run lightweight Phase 1.5 bootstrap when business-rules inventory is missing.",
            "Policy: no questions before Phase 4; use activation intent defaults.",
            "What would change it: activation intent or mode policy disables auto bootstrap.",
            "",
        ]
    )


def render_decision_pack_create(*, date: str, date_compact: str, repo_name: str) -> str:
    section = decision_pack_section(date, date_compact)
    return "# Decision Pack\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"
