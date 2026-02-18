#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from governance.render.response_formatter import render_response


def _read_payload(path_arg: str) -> dict[str, Any]:
    if path_arg == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path_arg).read_text(encoding="utf-8")

    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("payload root must be a JSON object")
    return payload


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render governance response envelopes in markdown/plain/json.")
    parser.add_argument(
        "--input",
        default="-",
        help="Path to response envelope JSON (default: stdin '-').",
    )
    parser.add_argument(
        "--format",
        default="auto",
        choices=("auto", "markdown", "plain", "json"),
        help="Output format contract. auto=markdown for interactive TTY, json for non-TTY.",
    )
    parser.add_argument(
        "--output-mode",
        choices=("STRICT", "COMPAT"),
        default=None,
        help="Optional expected envelope mode validation.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    try:
        payload = _read_payload(args.input)
    except json.JSONDecodeError as exc:
        print(f"FAIL: invalid JSON input: {exc}")
        return 1
    except (OSError, ValueError) as exc:
        print(f"FAIL: unable to read payload: {exc}")
        return 1

    if args.output_mode is not None:
        mode = payload.get("mode")
        if mode != args.output_mode:
            print(f"FAIL: output mode mismatch, expected {args.output_mode}, got {mode!r}")
            return 1

    try:
        rendered = render_response(payload, output_format=args.format)
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
