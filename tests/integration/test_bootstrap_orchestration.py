from governance.infrastructure.adapters.filesystem.in_memory import InMemoryFS


def test_inmemory_fs_supports_atomic_write_contract() -> None:
    fs = InMemoryFS()
    fs.write_text_atomic(path=__import__("pathlib").Path("/tmp/test"), content="ok")
    assert fs.exists(__import__("pathlib").Path("/tmp/test")) is True
