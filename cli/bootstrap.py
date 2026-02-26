#!/usr/bin/env python3
import sys

def main():
    try:
        import governance.entrypoints.bootstrap_preflight_readonly as bp
        return bp.main()
    except Exception as e:
        print("Bootstrap launcher error:", e, file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
