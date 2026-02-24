from __future__ import annotations

from pathlib import Path


def test_no_diagnostics_imports_in_python_files() -> None:
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for path in root.rglob("*.py"):
        if any(part in {".git", ".venv", "__pycache__", "dist"} for part in path.parts):
            continue
        if path.name == "test_no_diagnostics_imports.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if (
            "import diagnostics" in text
            or "from diagnostics" in text
            or "import routing" in text
            or "from routing" in text
        ):
            violations.append(str(path.relative_to(root)))
    assert not violations, f"diagnostics/routing imports are forbidden: {violations}"


def test_diagnostics_directory_removed() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "diagnostics").exists(), "diagnostics/ directory must not exist"
    routing_files = list((root / "routing").rglob("*.py")) if (root / "routing").exists() else []
    assert not routing_files, "routing/ legacy python modules must not exist"
