from pathlib import Path


def test_desktop_bootstrap_subdir_placeholder(tmp_path: Path) -> None:
    repo = tmp_path / "repo" / "docs" / "subdir"
    repo.mkdir(parents=True)
    assert repo.is_dir()
