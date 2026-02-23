from __future__ import annotations

from cli.bootstrap import main as bootstrap_main


def main(argv: list[str] | None = None) -> int:
    return bootstrap_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
