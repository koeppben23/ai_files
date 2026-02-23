from __future__ import annotations

from governance.application.use_cases.load_rulebooks import (
    LoadRulebooksInput,
    LoadRulebooksService,
    to_gate_payload,
)
from governance.domain.models.rulebooks import RulebookRef


class _FakeSource:
    def __init__(self, mapping: dict[str, RulebookRef]) -> None:
        self.mapping = mapping

    def load(self, identifier: str) -> RulebookRef | None:
        return self.mapping.get(identifier)


def _ref(identifier: str) -> RulebookRef:
    return RulebookRef(identifier=identifier, sha256="a" * 64, anchors_version="v1", source_kind="test")


def test_load_rulebooks_records_missing_required_addon() -> None:
    service = LoadRulebooksService(
        source_port=_FakeSource({
            "core": _ref("core"),
            "profile:python": _ref("profile:python"),
        })
    )
    result = service.run(
        LoadRulebooksInput(active_profile="python", source="test", required_addons=("pythonExcellence",))
    )

    assert result.addons["pythonExcellence"] == "missing"
    assert any(err.code == "RULEBOOK_ADDON_MISSING" for err in result.errors)


def test_gate_payload_reports_core_and_profile_loaded() -> None:
    service = LoadRulebooksService(
        source_port=_FakeSource(
            {
                "core": _ref("core"),
                "profile:python": _ref("profile:python"),
                "addon:userMaxQuality": _ref("addon:userMaxQuality"),
            }
        )
    )
    result = service.run(
        LoadRulebooksInput(active_profile="python", source="test", required_addons=("userMaxQuality",))
    )

    gate_payload = to_gate_payload(result)
    assert gate_payload["core"] == "loaded"
    assert gate_payload["profile"] == "loaded"
