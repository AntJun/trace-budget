"""Strict trace parsing and deterministic, per-span performance budgets."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


class InputError(ValueError):
    """An input is invalid or insufficient for a reliable gate."""


def number(value: Any, label: str, minimum: float = 0) -> float | int:
    original = value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{label} must be a finite number")
    try:
        value = float(value)
    except OverflowError as exc:
        raise InputError(f"{label} is outside the supported range") from exc
    if not math.isfinite(value) or value < minimum or value > 1e18:
        raise InputError(f"{label} is outside the supported range")
    return original if isinstance(original, int) else value


def label(value: Any, field: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not value and not empty) or len(value) > 200:
        raise InputError(f"{field} must be a string of at most 200 characters")
    if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE, 0xFFFF)
           for c in value):
        raise InputError(f"{field} contains an unsupported control character")
    return value


def category(value: Any) -> str:
    text = label(value, "category", empty=True)
    return ",".join(sorted({part.strip() for part in text.split(",") if part.strip()}))


def _pairs(items: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise InputError("JSON contains a duplicate object key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise InputError("JSON contains a nonfinite numeric constant")


def read_json(path: Path, max_bytes: int = 64 * 1024 * 1024) -> Any:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1 or max_bytes > 256 * 1024 * 1024:
        raise InputError("max_bytes must be between 1 byte and 256 MiB")
    try:
        with path.open("rb") as source:
            raw = source.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise InputError("JSON exceeds the configured byte limit")
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_pairs,
                          parse_constant=_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError("cannot read valid UTF-8 JSON") from exc


@dataclass(frozen=True)
class Span:
    name: str
    category: str
    timestamp_us: float
    duration_ms: float
    source_index: int = 0


@dataclass
class Capture:
    spans: list[Span]
    event_count: int
    ignored_events: int


def _lane(event: dict) -> tuple:
    parts = []
    for field in ("pid", "tid"):
        value = event.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise InputError("B/E events require integer or string pid and tid")
        if len(str(value)) > 200:
            raise InputError("pid/tid exceeds the supported length")
        # Type tags prevent the integer 1 and string "1" from sharing a stack.
        parts.append((type(value).__name__, value))
    return tuple(parts)


def parse_trace(data: Any, max_events: int = 1_000_000) -> Capture:
    if isinstance(max_events, bool) or not isinstance(max_events, int) or max_events < 1:
        raise InputError("max_events must be a positive integer")
    events = data.get("traceEvents") if isinstance(data, dict) else data
    if not isinstance(events, list):
        raise InputError("trace must be an array or an object with traceEvents")
    if len(events) > max_events:
        raise InputError("trace exceeds the configured event limit")
    ordered = []
    ignored = 0
    for index, event in enumerate(events):
        if not isinstance(event, dict) or not isinstance(event.get("ph"), str):
            raise InputError(f"event {index} must be an object with a phase")
        if event["ph"] not in ("X", "B", "E"):
            ignored += 1
            continue
        timestamp = number(event.get("ts"), f"event {index} timestamp")
        ordered.append((timestamp, index, event))
    ordered.sort(key=lambda item: (item[0], item[1]))
    stacks = defaultdict(list)
    spans = []
    for timestamp, index, event in ordered:
        phase = event["ph"]
        if phase == "E":
            stack = stacks[_lane(event)]
            if not stack:
                raise InputError(f"event {index} has no matching begin")
            start, name, cat, source_index = stack.pop()
            if "name" in event and event["name"] != name:
                raise InputError(f"event {index} closes a different span")
            if "cat" in event and category(event["cat"]) != cat:
                raise InputError(f"event {index} closes a different category")
            spans.append(Span(name, cat, start, float((Fraction(timestamp) - Fraction(start)) / 1000), source_index))
            continue
        name = label(event.get("name"), f"event {index} name")
        cat = category(event.get("cat", ""))
        if phase == "B":
            stacks[_lane(event)].append((timestamp, name, cat, index))
        else:
            duration = number(event.get("dur"), f"event {index} duration")
            spans.append(Span(name, cat, timestamp, duration / 1000, index))
    if any(stacks.values()):
        raise InputError("trace contains an unclosed begin event")
    if not spans:
        raise InputError("trace contains no supported duration spans")
    return Capture(sorted(spans, key=lambda span: (span.timestamp_us, span.source_index)), len(events), ignored)


@dataclass(frozen=True)
class Rule:
    name: str
    category: str
    metric: str
    max_ms: float | None
    max_regression_pct: float | None
    min_delta_ms: float


@dataclass(frozen=True)
class Policy:
    min_samples: int
    rules: tuple[Rule, ...]


def parse_policy(data: Any) -> Policy:
    if not isinstance(data, dict) or set(data) - {"version", "min_samples", "rules"}:
        raise InputError("policy has an invalid shape or unknown fields")
    if type(data.get("version")) is not int or data["version"] != 1:
        raise InputError("policy version must be the integer 1")
    minimum = data.get("min_samples", 20)
    if type(minimum) is not int or minimum < 1:
        raise InputError("min_samples must be a positive integer")
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules or len(rules) > 1000:
        raise InputError("policy must contain between 1 and 1000 rules")
    result = []
    seen = set()
    allowed = {"name", "category", "metric", "max_ms", "max_regression_pct", "min_delta_ms"}
    for item in rules:
        if not isinstance(item, dict) or set(item) - allowed:
            raise InputError("rule has an invalid shape or unknown fields")
        name = label(item.get("name"), "rule name")
        cat = category(item.get("category", ""))
        metric = item.get("metric", "p95")
        if metric not in ("p95", "median", "mean", "max"):
            raise InputError("rule metric must be p95, median, mean, or max")
        key = (cat, name, metric)
        if key in seen:
            raise InputError("policy contains a duplicate selector and metric")
        seen.add(key)
        if "max_ms" not in item and "max_regression_pct" not in item:
            raise InputError("each rule requires an absolute or relative budget")
        absolute = number(item["max_ms"], "max_ms") if "max_ms" in item else None
        relative = (number(item["max_regression_pct"], "max_regression_pct")
                    if "max_regression_pct" in item else None)
        delta = number(item.get("min_delta_ms", 0), "min_delta_ms")
        if "min_delta_ms" in item and relative is None:
            raise InputError("min_delta_ms requires max_regression_pct")
        result.append(Rule(name, cat, metric, absolute, relative, delta))
    return Policy(minimum, tuple(result))


def percentile(values: list[float], q: float) -> float:
    """Linear interpolation at rank (n - 1) * q, with endpoints included."""
    if not values:
        raise InputError("cannot summarize an empty sample")
    if not math.isfinite(q) or q < 0 or q > 1:
        raise InputError("quantile must be between 0 and 1")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q
    lo = math.floor(rank)
    hi = math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def summarize(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean_ms": math.fsum(values) / len(values),
        "median_ms": percentile(values, 0.5),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values),
    }


def exceeds(value: float, limit: float) -> bool:
    """Apply a four-ULP guard for arithmetic noise at an equality boundary."""
    tolerance = 4 * max(math.ulp(value), math.ulp(limit))
    return value > limit and value - limit > tolerance


def compare(baseline: Capture, candidate: Capture, policy: Policy, warmup: int = 0) -> dict:
    if type(warmup) is not int or warmup < 0:
        raise InputError("warmup must be a nonnegative integer")
    groups = []
    for capture in (baseline, candidate):
        group = defaultdict(list)
        for span in sorted(capture.spans, key=lambda item: (item.timestamp_us, item.source_index)):
            group[(span.category, span.name)].append(span.duration_ms)
        groups.append(group)
    results = []
    for rule in policy.rules:
        key = (rule.category, rule.name)
        old = groups[0].get(key, [])[warmup:]
        new = groups[1].get(key, [])[warmup:]
        row = {
            "name": rule.name, "category": rule.category, "metric": rule.metric,
            "budgets": {"max_ms": rule.max_ms,
                        "max_regression_pct": rule.max_regression_pct,
                        "min_delta_ms": rule.min_delta_ms},
            "baseline": summarize(old) if old else None,
            "candidate": summarize(new) if new else None,
            "status": "pass", "reasons": [], "delta_ms": None, "delta_pct": None,
        }
        if len(old) < policy.min_samples or len(new) < policy.min_samples:
            row["status"] = "incomplete"
            row["reasons"] = ["insufficient samples after warmup"]
        else:
            before = row["baseline"][rule.metric + "_ms"]
            after = row["candidate"][rule.metric + "_ms"]
            delta = after - before
            pct = delta / before * 100 if before > 0 else None
            if pct is not None and not math.isfinite(pct):
                pct = None
            row["delta_ms"] = delta
            row["delta_pct"] = pct
            if rule.max_ms is not None and exceeds(after, rule.max_ms):
                row["reasons"].append("absolute budget exceeded")
            if rule.max_regression_pct is not None:
                # A zero baseline cannot define a percentage. Any positive
                # candidate above the delta floor exceeds the relative gate.
                relative_fail = exceeds(after, before * (1 + rule.max_regression_pct / 100))
                delta_fail = exceeds(after, before + rule.min_delta_ms)
                if relative_fail and delta_fail:
                    row["reasons"].append("relative budget and delta floor exceeded")
            if row["reasons"]:
                row["status"] = "regression"
        results.append(row)
    incomplete = sum(row["status"] == "incomplete" for row in results)
    regressions = sum(row["status"] == "regression" for row in results)
    code = 2 if incomplete else 1 if regressions else 0
    return {
        "schema_version": 1, "tool_version": "0.1.0",
        "status": "incomplete" if incomplete else "regression" if regressions else "pass",
        "exit_code": code, "warmup_per_group": warmup, "min_samples": policy.min_samples,
        "summary": {"rules": len(results), "regressions": regressions, "incomplete": incomplete},
        "inputs": {
            "baseline": {"events": baseline.event_count, "spans": len(baseline.spans),
                         "ignored_events": baseline.ignored_events},
            "candidate": {"events": candidate.event_count, "spans": len(candidate.spans),
                          "ignored_events": candidate.ignored_events},
        },
        "results": results,
    }
