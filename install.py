#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import governance_runtime.install.install as _impl

for _name, _value in _impl.__dict__.items():
    if not _name.startswith("__"):
        globals()[_name] = _value

_runtime_main = _impl.main


def main(argv: list[str]) -> int:
    args = list(argv)
    if "--source-dir" not in args:
        args.extend(["--source-dir", str(Path(__file__).resolve().parent)])
    return _runtime_main(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
