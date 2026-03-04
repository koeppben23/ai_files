def decision_pack_section(date: str, date_compact: str) -> str:
    return "\n".join(
        [
            f"## Decision Pack -- {date}",
            "D-001: Record Business Rules bootstrap outcome",
            f"ID: DP-{date_compact}-001",
            "Status: automatic",
            "Action: Persist business-rules outcome as extracted|skipped|not-applicable|deferred.",
            "Policy: business-rules-status.md is always written; business-rules.md is written only when outcome=extracted with extractor evidence.",
            "What would change it: scope evidence or Phase 1.5 extraction state.",
            "",
        ]
    )


def render_decision_pack_create(*, date: str, date_compact: str, repo_name: str) -> str:
    section = decision_pack_section(date, date_compact)
    return "# Decision Pack\n" f"Repo: {repo_name}\n" f"LastUpdated: {date}\n\n" f"{section}"
