import json
import math
import random
import tempfile
import unittest
from pathlib import Path

from tracebudget.core import (
    InputError, compare, parse_policy, parse_trace, percentile, read_json,
)


def capture(values, name="frame", cat="game", pid=1):
    return parse_trace([
        {"ph": "X", "name": name, "cat": cat, "ts": i * 100000,
         "dur": value * 1000, "pid": pid, "tid": 1}
        for i, value in enumerate(values)
    ])


def policy(**rule):
    return parse_policy({"version": 1, "min_samples": 1,
                         "rules": [{"name": "frame", "category": "game", **rule}]})


class TraceTests(unittest.TestCase):
    def test_both_root_shapes_and_microseconds(self):
        data = [{"ph": "X", "name": "s", "ts": 0, "dur": 2500}]
        self.assertEqual(parse_trace(data), parse_trace({"traceEvents": data}))
        self.assertEqual(parse_trace(data).spans[0].duration_ms, 2.5)

    def test_display_unit_does_not_change_trace_units(self):
        result = parse_trace({"displayTimeUnit": "ns",
                              "traceEvents": [{"ph": "X", "name": "s", "ts": 0, "dur": 1000}]})
        self.assertEqual(result.spans[0].duration_ms, 1)

    def test_nested_begin_end_and_independent_lanes(self):
        data = [
            {"ph": "B", "name": "outer", "ts": 0, "pid": 1, "tid": 1},
            {"ph": "B", "name": "other", "ts": 500, "pid": 1, "tid": 2},
            {"ph": "B", "name": "inner", "ts": 1000, "pid": 1, "tid": 1},
            {"ph": "E", "ts": 3000, "pid": 1, "tid": 1},
            {"ph": "E", "ts": 4000, "pid": 1, "tid": 2},
            {"ph": "E", "ts": 5000, "pid": 1, "tid": 1},
        ]
        self.assertEqual({s.name: s.duration_ms for s in parse_trace(data).spans},
                         {"outer": 5, "inner": 2, "other": 3.5})

    def test_unordered_pairs_are_sorted(self):
        data = [
            {"ph": "E", "ts": 1000, "pid": 1, "tid": 1},
            {"ph": "B", "name": "x", "ts": 0, "pid": 1, "tid": 1},
        ]
        self.assertEqual(parse_trace(data).spans[0].duration_ms, 1)

    def test_large_integer_timestamp_precision(self):
        start = 9007199254740992
        data = [
            {"ph": "B", "name": "x", "ts": start, "pid": 1, "tid": 1},
            {"ph": "E", "ts": start + 1, "pid": 1, "tid": 1},
        ]
        self.assertEqual(parse_trace(data).spans[0].duration_ms, 0.001)

    def test_mixed_integer_float_timestamp_precision(self):
        data = [
            {"ph": "B", "name": "x", "ts": 999999999999999999, "pid": 1, "tid": 1},
            {"ph": "E", "ts": 1e18, "pid": 1, "tid": 1},
        ]
        self.assertEqual(parse_trace(data).spans[0].duration_ms, 0.001)

    def test_equal_time_begin_then_end_is_zero(self):
        data = [{"ph": "B", "name": "x", "ts": 0, "pid": 1, "tid": 1},
                {"ph": "E", "ts": 0, "pid": 1, "tid": 1}]
        self.assertEqual(parse_trace(data).spans[0].duration_ms, 0)

    def test_bad_pairing_and_end_labels(self):
        begin = {"ph": "B", "name": "x", "cat": "a", "ts": 0, "pid": 1, "tid": 1}
        end = {"ph": "E", "ts": 1, "pid": 1, "tid": 1}
        for data in ([end], [begin], [begin, {**end, "tid": 2}],
                     [begin, {**end, "name": "wrong"}],
                     [begin, {**end, "cat": "wrong"}],
                     [{**begin, "ts": 2}, end],
                     [{**begin, "pid": True}, end]):
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_trace(data)

    def test_invalid_supported_events_fail_even_without_a_rule(self):
        base = {"ph": "X", "name": "unruled", "ts": 0, "dur": 1}
        for patch in ({"dur": -1}, {"dur": True}, {"dur": "1"}, {"ts": False},
                      {"dur": math.inf}, {"dur": math.nan}, {"ts": -1},
                      {"ts": 10 ** 500}, {"name": ""}, {"name": "\x00"},
                      {"name": "\ud800"}, {"name": "\ufffe"}):
            with self.subTest(patch=patch), self.assertRaises(InputError):
                parse_trace([{**base, **patch}])

    def test_bad_shapes(self):
        for data in ({}, "bad", [None], [{"name": "x"}],
                     {"traceEvents": {}}, [{"ph": 4}]):
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_trace(data)

    def test_ignored_phases_count_toward_limit(self):
        data = [{"ph": "M", "args": {"private": "excluded"}},
                {"ph": "X", "name": "x", "ts": 0, "dur": 1}]
        result = parse_trace(data, max_events=2)
        self.assertEqual(result.ignored_events, 1)
        with self.assertRaises(InputError):
            parse_trace(data, max_events=1)
        with self.assertRaises(InputError):
            parse_trace([{"ph": "C"}])

    def test_category_normalization(self):
        result = parse_trace([{"ph": "X", "name": "x", "cat": "ui, render,ui",
                               "ts": 0, "dur": 1}])
        self.assertEqual(result.spans[0].category, "render,ui")

    def test_randomized_complete_and_paired_equivalence(self):
        rng = random.Random(7)
        durations = [rng.randint(1, 5000) for _ in range(250)]
        complete = []
        paired = []
        for i, duration in enumerate(durations):
            start = i * 10000
            complete.append({"ph": "X", "name": "x", "ts": start, "dur": duration})
            paired += [{"ph": "B", "name": "x", "ts": start, "pid": 1, "tid": 1},
                       {"ph": "E", "ts": start + duration, "pid": 1, "tid": 1}]
        rng.shuffle(complete)
        rng.shuffle(paired)
        a = [s.duration_ms for s in parse_trace(complete).spans]
        b = [s.duration_ms for s in parse_trace(paired).spans]
        self.assertEqual(a, b)


class BudgetTests(unittest.TestCase):
    def test_quantile_definition(self):
        self.assertAlmostEqual(percentile([4, 1, 3, 2], 0.95), 3.85)
        self.assertEqual(percentile([7], 0.95), 7)
        with self.assertRaises(InputError):
            percentile([], 0.95)

    def test_exact_thresholds_pass(self):
        result = compare(capture([100]), capture([110]),
                         policy(max_ms=110, max_regression_pct=10, min_delta_ms=10))
        self.assertEqual(result["exit_code"], 0)

    def test_decimal_percentage_and_delta_equalities(self):
        old, new = capture([0.3]), capture([0.33])
        self.assertEqual(compare(old, new, policy(max_regression_pct=10))["exit_code"], 0)
        self.assertEqual(compare(old, new, policy(max_regression_pct=0, min_delta_ms=0.03))["exit_code"], 0)

    def test_decimal_mean_and_median_absolute_equalities(self):
        for metric in ("mean", "median"):
            with self.subTest(metric=metric):
                result = compare(capture([0.1, 0.2]), capture([0.1, 0.2]),
                                 policy(metric=metric, max_ms=0.15))
                self.assertEqual(result["exit_code"], 0)

    def test_growth_beyond_numeric_guard_still_fails(self):
        result = compare(capture([0.3]), capture([0.33000000001]),
                         policy(max_regression_pct=10))
        self.assertEqual(result["exit_code"], 1)

    def test_relative_requires_both_thresholds(self):
        old, new = capture([100]), capture([111])
        self.assertEqual(compare(old, new, policy(max_regression_pct=10, min_delta_ms=12))["exit_code"], 0)
        self.assertEqual(compare(old, new, policy(max_regression_pct=10, min_delta_ms=5))["exit_code"], 1)

    def test_absolute_independent_of_relative(self):
        result = compare(capture([100]), capture([101]),
                         policy(max_ms=100, max_regression_pct=50, min_delta_ms=50))
        self.assertEqual(result["exit_code"], 1)

    def test_zero_baseline(self):
        old = capture([0])
        gate = policy(max_regression_pct=10, min_delta_ms=0.5)
        self.assertEqual(compare(old, capture([0.1]), gate)["exit_code"], 0)
        result = compare(old, capture([1]), gate)
        self.assertEqual(result["exit_code"], 1)
        self.assertIsNone(result["results"][0]["delta_pct"])
        json.dumps(result, allow_nan=False)

    def test_extreme_finite_ratio_remains_serializable(self):
        result = compare(capture([1e-320]), capture([1e12]),
                         policy(max_regression_pct=10))
        json.dumps(result, allow_nan=False)
        self.assertEqual(result["exit_code"], 1)

    def test_grouping_ignores_pid_and_separates_categories(self):
        result = compare(capture([1], pid=100), capture([1], pid=999), policy(max_ms=2))
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(compare(capture([1]), capture([1], cat="other"),
                                 policy(max_ms=2))["exit_code"], 2)

    def test_warmup_uses_start_timestamp(self):
        raw = [{"ph": "X", "name": "frame", "cat": "game", "ts": timestamp, "dur": duration * 1000}
               for timestamp, duration in ((30, 1), (10, 100), (20, 2))]
        result = compare(parse_trace(raw), parse_trace(raw), policy(max_ms=2), warmup=1)
        self.assertEqual(result["results"][0]["candidate"]["median_ms"], 1.5)

    def test_equal_time_warmup_uses_source_index(self):
        raw = [{"ph": "X", "name": "frame", "cat": "game", "ts": 0, "dur": d}
               for d in (100000, 2000)]
        result = compare(parse_trace(raw), parse_trace(raw), policy(max_ms=3), warmup=1)
        self.assertEqual(result["exit_code"], 0)

    def test_missing_and_warmup_exhausted_are_incomplete(self):
        gate = policy(max_ms=2)
        self.assertEqual(compare(capture([1]), capture([1], name="other"), gate)["exit_code"], 2)
        self.assertEqual(compare(capture([1]), capture([1]), gate, warmup=1)["exit_code"], 2)

    def test_incomplete_takes_precedence_and_keeps_regression(self):
        gate = parse_policy({"version": 1, "min_samples": 1, "rules": [
            {"name": "frame", "category": "game", "max_ms": 1},
            {"name": "missing", "max_ms": 1}]})
        result = compare(capture([1]), capture([2]), gate)
        self.assertEqual(result["exit_code"], 2)
        self.assertEqual(result["summary"], {"rules": 2, "regressions": 1, "incomplete": 1})

    def test_reports_are_deterministic(self):
        gate = policy(max_ms=20)
        self.assertEqual(compare(capture([1, 2, 3]), capture([2, 3, 4]), gate),
                         compare(capture([1, 2, 3]), capture([2, 3, 4]), gate))

    def test_policy_rejects_invalid_shapes(self):
        valid = {"version": 1, "min_samples": 1, "rules": [{"name": "x", "max_ms": 1}]}
        cases = [
            {**valid, "version": True}, {**valid, "unknown": 1},
            {**valid, "min_samples": True}, {**valid, "min_samples": 1.5},
            {**valid, "min_samples": 0}, {**valid, "rules": []},
            {**valid, "rules": [{"name": "x"}]},
            {**valid, "rules": [{"name": "x", "max_ms": -1}]},
            {**valid, "rules": [{"name": "x", "max_ms": True}]},
            {**valid, "rules": [{"name": "x", "max_ms": math.inf}]},
            {**valid, "rules": [{"name": "x", "max_ms": 1, "metric": "p99"}]},
            {**valid, "rules": [{"name": "x", "max_ms": 1, "extra": 0}]},
            {**valid, "rules": valid["rules"] * 2},
            {**valid, "rules": [{"name": "x", "max_ms": 1, "min_delta_ms": 1}]},
        ]
        for item in cases:
            with self.subTest(item=item), self.assertRaises(InputError):
                parse_policy(item)

    def test_file_limits_duplicate_keys_and_invalid_encoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_bytes(b"[]")
            self.assertEqual(read_json(path, 2), [])
            with self.assertRaises(InputError):
                read_json(path, 1)
            with self.assertRaises(InputError):
                read_json(path, 10 ** 100)
            for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"["):
                path.write_bytes(raw)
                with self.assertRaises(InputError):
                    read_json(path)
