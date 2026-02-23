from typing import Dict, Any, Optional, Tuple


PHASE_RANKS = {
    "0-None": 0,
    "1.1-Bootstrap": 1,
    "1.3-RulebookLoad": 2,
    "2.1-RepoHeuristics": 3,
    "2.2-RulebookHeuristics": 4,
    "4-Ready": 5,
    "5-Execute": 6,
    "6-PostFlight": 7,
}


def phase_rank(phase: str) -> int:
    return PHASE_RANKS.get(phase, 0)


def is_rulebook_required_phase(phase: str) -> bool:
    return phase_rank(phase) >= phase_rank("4-Ready")


def parse_phase_token(token: str) -> Tuple[str, Optional[str]]:
    if "-" in token:
        parts = token.split("-", 1)
        try:
            rank = int(parts[0])
            return f"{rank}-{parts[1]}", None
        except ValueError:
            return token, None
    return token, None
