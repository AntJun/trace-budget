"""Generate synthetic fixtures and a measured, credential-free CPU example."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from .__main__ import write_atomic
from .core import compare, parse_policy, parse_trace
from .report import render_html, render_junit


POLICY = {
    "version": 1,
    "min_samples": 20,
    "rules": [
        {"name": "frame", "category": "game", "metric": "p95", "max_ms": 16.67,
         "max_regression_pct": 10, "min_delta_ms": 0.5},
        {"name": "inference", "category": "model", "metric": "p95", "max_ms": 10,
         "max_regression_pct": 15, "min_delta_ms": 0.2},
    ],
}


def synthetic() -> tuple[dict, dict]:
    captures = []
    for regressed in (False, True):
        events = []
        for index in range(60):
            # The slow frame is deliberately deterministic for repeatable tests.
            frame = 12000 + index % 10 * 200 + (6000 if regressed else 0)
            inference = 5000 + index % 7 * 100
            for name, cat, duration, lane in (
                ("frame", "game", frame, 1), ("inference", "model", inference, 2)):
                events.append({"ph": "X", "name": name, "cat": cat, "pid": 1,
                               "tid": lane, "ts": index * 40000, "dur": duration})
        captures.append({"traceEvents": events, "capture_kind": "synthetic"})
    return tuple(captures)


def measured() -> tuple[dict, dict, dict]:
    values = list(range(4000))
    index = set(values)
    queries = [i * 13 % 8000 for i in range(400)]
    events = [[], []]
    origin = time.perf_counter_ns()
    # Alternate the two implementations to reduce monotonic thermal/order bias.
    # Each sample includes the same fixed batch of membership checks.
    for sample in range(45):
        for variant in ((0, 1) if sample % 2 == 0 else (1, 0)):
            container = index if variant == 0 else values
            start = time.perf_counter_ns()
            hits = sum(query in container for query in queries)
            end = time.perf_counter_ns()
            if hits != 308:
                raise RuntimeError("workload membership result changed")
            events[variant].append({
                "ph": "X", "cat": "lookup", "name": "membership_batch",
                "pid": 1, "tid": 1, "ts": (start - origin) / 1000,
                "dur": (end - start) / 1000,
            })
    policy = {
        "version": 1, "min_samples": 30,
        "rules": [{"name": "membership_batch", "category": "lookup", "metric": "p95",
                   "max_regression_pct": 25, "min_delta_ms": 0.1}],
    }
    return ({"traceEvents": events[0], "capture_kind": "measured"},
            {"traceEvents": events[1], "capture_kind": "measured"}, policy)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    args = parser.parse_args(argv)
    baseline, candidate = synthetic()
    report = compare(parse_trace(baseline), parse_trace(candidate), parse_policy(POLICY), warmup=3)
    for name, value in (("baseline.json", baseline), ("candidate.json", candidate),
                        ("policy.json", POLICY), ("report.json", report)):
        write_atomic(args.output / name, json.dumps(value, indent=2, allow_nan=False) + "\n")
    write_atomic(args.output / "index.html", render_html(report, "Synthetic game and inference example"))
    write_atomic(args.output / "junit.xml", render_junit(report))
    old, new, policy = measured()
    measured_report = compare(parse_trace(old), parse_trace(new), parse_policy(policy), warmup=5)
    for name, value in (("baseline.json", old), ("candidate.json", new),
                        ("policy.json", policy), ("report.json", measured_report)):
        write_atomic(args.output / "measured" / name, json.dumps(value, indent=2, allow_nan=False) + "\n")
    write_atomic(args.output / "measured" / "index.html",
                 render_html(measured_report, "Measured set lookup vs. linear list lookup"))
    write_atomic(args.output / "measured" / "junit.xml", render_junit(measured_report))
    facts = {
        "capture_kind": "measured", "clock": "time.perf_counter_ns",
        "samples_per_variant": 45, "warmup_per_variant": 5,
        "items": 4000, "queries_per_sample": 400, "expected_hits": 308,
        "baseline_implementation": "set membership", "candidate_implementation": "list membership",
        "scope": "One instrumented Python CPU workload on this GitHub-hosted runner.",
        "limitation": "This demonstrates detection of a deliberate algorithmic slowdown; hardware and other applications can behave differently.",
    }
    write_atomic(args.output / "measured" / "method.json", json.dumps(facts, indent=2) + "\n")
    print("Generated synthetic and measured reports.")
    print("Synthetic gate:", report["status"])
    print("Measured gate:", measured_report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
