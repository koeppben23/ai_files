#!/usr/bin/env python3
import sys


def main() -> int:
    try:
        from governance.entrypoints.bootstrap_executor import main as executor_main
    except Exception as exc:
        print("Bootstrap launcher error:", exc, file=sys.stderr)
        return 1
    return int(executor_main())


if __name__ == "__main__":
    raise SystemExit(main())
