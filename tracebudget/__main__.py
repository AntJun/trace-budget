"""Command-line entry point; all analysis runs without network access."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .core import InputError, compare, parse_policy, parse_trace, read_json
from .report import render_html, render_junit


def _nonnegative(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("requires an integer") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("requires a nonnegative integer")
    return value


def _positive(text: str) -> int:
    value = _nonnegative(text)
    if value == 0:
        raise argparse.ArgumentTypeError("requires a positive integer")
    return value


def _megabytes(text: str) -> int:
    value = _positive(text)
    if value > 256:
        raise argparse.ArgumentTypeError("max-mb must be between 1 and 256")
    return value


def aliases(first: Path, second: Path) -> bool:
    if first.resolve() == second.resolve():
        return True
    return first.exists() and second.exists() and first.samefile(second)


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tracebudget", description="Gate Chrome Trace Event captures against performance budgets.")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--warmup", type=_nonnegative, default=0,
                        help="earliest spans discarded per category/name group in each capture")
    parser.add_argument("--max-mb", type=_megabytes, default=64)
    parser.add_argument("--max-events", type=_positive, default=1_000_000)
    parser.add_argument("--json", type=Path, dest="json_path")
    parser.add_argument("--html", type=Path, dest="html_path")
    parser.add_argument("--junit", type=Path, dest="junit_path")
    args = parser.parse_args(argv)
    try:
        inputs = (args.baseline, args.candidate, args.policy)
        outputs = [path for path in (args.json_path, args.html_path, args.junit_path) if path]
        duplicate = any(aliases(path, previous) for i, path in enumerate(outputs)
                        for previous in outputs[:i])
        if duplicate or any(aliases(path, source) for path in outputs for source in inputs):
            raise InputError("output paths must be distinct and cannot overwrite inputs")
        policy = parse_policy(read_json(args.policy, min(args.max_mb * 1024 * 1024, 1024 * 1024)))
        captures = []
        for input_path in (args.baseline, args.candidate):
            captures.append(parse_trace(read_json(input_path, args.max_mb * 1024 * 1024),
                                        args.max_events))
        report = compare(*captures, policy, warmup=args.warmup)
        if args.json_path:
            write_atomic(args.json_path, json.dumps(report, indent=2, allow_nan=False) + "\n")
        if args.html_path:
            write_atomic(args.html_path, render_html(report))
        if args.junit_path:
            write_atomic(args.junit_path, render_junit(report))
        print(f'TraceBudget: {report["status"].upper()} | '
              f'{report["summary"]["regressions"]} regression(s), '
              f'{report["summary"]["incomplete"]} incomplete rule(s)')
        for row in report["results"]:
            # JSON escaping prevents control sequences in labels from reaching terminals.
            selector = json.dumps([row["category"], row["name"]], ensure_ascii=True)
            print(f'{row["status"].upper():10} {row["metric"]:6} {selector}')
        return report["exit_code"]
    except (InputError, OSError, ValueError, RecursionError) as exc:
        message = str(exc) if isinstance(exc, InputError) else "cannot read or write report files"
        print("TraceBudget input error: " + message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
