from __future__ import annotations

from dataclasses import dataclass, field

from governance.application.ports.rulebook_source import RulebookSourcePort
from governance.domain.errors.events import ErrorEvent
from governance.domain.models.rulebooks import RulebookSet


@dataclass(frozen=True)
class LoadedRulebooks:
    rules: RulebookSet
    source: str
    addons: dict[str, str] = field(default_factory=dict)
    errors: tuple[ErrorEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LoadRulebooksInput:
    active_profile: str
    source: str
    required_addons: tuple[str, ...] = field(default_factory=tuple)


class LoadRulebooksService:
    def __init__(self, *, source_port: RulebookSourcePort) -> None:
        self._source_port = source_port

    def run(self, payload: LoadRulebooksInput) -> LoadedRulebooks:
        errors: list[ErrorEvent] = []

        core = self._source_port.load("core")
        profile = self._source_port.load(f"profile:{payload.active_profile}")
        master = self._source_port.load("master")

        addons_loaded: list = []
        addons_audit: dict[str, str] = {}
        for addon in payload.required_addons:
            ref = self._source_port.load(f"addon:{addon}")
            if ref is None:
                addons_audit[addon] = "missing"
                errors.append(
                    ErrorEvent(
                        code="RULEBOOK_ADDON_MISSING",
                        severity="error",
                        message="Required rulebook addon missing.",
                        expected="addon rulebook loaded",
                        observed={"addon": addon},
                    )
                )
                continue
            addons_audit[addon] = "loaded"
            addons_loaded.append(ref)

        if core is None:
            errors.append(
                ErrorEvent(
                    code="RULEBOOK_CORE_MISSING",
                    severity="error",
                    message="Core rulebook missing.",
                    expected="core rulebook loaded",
                    observed={"identifier": "core"},
                )
            )
        if profile is None:
            errors.append(
                ErrorEvent(
                    code="RULEBOOK_PROFILE_MISSING",
                    severity="error",
                    message="Profile rulebook missing.",
                    expected="profile rulebook loaded",
                    observed={"identifier": payload.active_profile},
                )
            )

        return LoadedRulebooks(
            rules=RulebookSet(core=core, master=master, profile=profile, addons=tuple(addons_loaded)),
            source=payload.source,
            addons=addons_audit,
            errors=tuple(errors),
        )


def to_gate_payload(result: LoadedRulebooks) -> dict[str, object]:
    return {
        "core": "loaded" if result.rules.core is not None else "",
        "profile": "loaded" if result.rules.profile is not None else "",
        "templates": "loaded" if result.rules.master is not None else "",
        "addons": result.addons,
    }
