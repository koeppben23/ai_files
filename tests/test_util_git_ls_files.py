from __future__ import annotations

from pathlib import Path

from tests import util


class _Result:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_git_ls_files_falls_back_to_glob_when_git_unavailable(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "profiles" / "addons").mkdir(parents=True)
    (repo_root / "profiles" / "addons" / "python.addon.yml").write_text("addon_key: python\n", encoding="utf-8")
    (repo_root / "profiles" / "addons" / "java.addon.yml").write_text("addon_key: java\n", encoding="utf-8")

    monkeypatch.setattr(util, "REPO_ROOT", repo_root)
    monkeypatch.setattr(util, "run", lambda *_args, **_kwargs: _Result(returncode=1, stderr="not a git repo"))

    files = util.git_ls_files("profiles/addons/*.addon.yml")

    assert files == [
        "profiles/addons/java.addon.yml",
        "profiles/addons/python.addon.yml",
    ]
