from __future__ import annotations


PRECEDENCE_ORDER: tuple[str, ...] = (
    "engine_master_policy",
    "pack_lock",
    "mode_policy",
    "host_permissions",
    "repo_docs_constraints",
)


def precedence_order() -> tuple[str, ...]:
    return PRECEDENCE_ORDER
