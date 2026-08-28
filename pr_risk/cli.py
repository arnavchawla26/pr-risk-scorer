"""Command-line entry point: `pr-risk [diff-file]` (reads stdin if no file given)."""
from __future__ import annotations

import argparse
import subprocess
import sys

from .scorer import format_text_report, score_diff_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pr-risk",
        description=(
            "Score a git diff / PR patch for risk: committed secrets, vendored "
            "directories committed by accident, oversized changes, binary files, "
            "and source changes with no accompanying test."
        ),
    )
    parser.add_argument(
        "diff_file",
        nargs="?",
        help="Path to a unified diff/patch file. Omit to read from stdin, "
        "or use --git-range instead.",
    )
    parser.add_argument(
        "--git-range",
        metavar="RANGE",
        help="Run `git diff RANGE` in the current directory and score that "
        "(e.g. --git-range main...HEAD, or --git-range HEAD~1).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--fail-over",
        type=int,
        default=None,
        metavar="SCORE",
        help="Exit with status 1 if the risk score is at or above SCORE. Useful as a CI gate.",
    )
    return parser


def _read_diff_text(args: argparse.Namespace) -> str:
    if args.git_range:
        result = subprocess.run(
            ["git", "diff", args.git_range],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            raise SystemExit(2)
        return result.stdout

    if args.diff_file:
        with open(args.diff_file, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.read()

    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    diff_text = _read_diff_text(args)
    report = score_diff_text(diff_text)

    if args.json:
        print(report.to_json())
    else:
        print(format_text_report(report))

    if args.fail_over is not None and report.risk_score >= args.fail_over:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
