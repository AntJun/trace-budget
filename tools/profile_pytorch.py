"""Record and validate a real PyTorch CPU profiler export on a hosted runner."""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from fractions import Fraction
from pathlib import Path

from tracebudget.__main__ import write_atomic
from tracebudget.core import Capture, InputError, compare, parse_policy, parse_trace, read_json
from tracebudget.report import render_html, render_junit

STAGE = "tracebudget.inference_batch"
CATEGORY = "user_annotation"
TORCH_VERSION = "2.14.1+cpu"
SAMPLES = 30

POLICY = {
    "version": 1, "min_samples": 20,
    "rules": [{"name": STAGE, "category": CATEGORY, "metric": "p95",
               "max_regression_pct": 25, "min_delta_ms": 0.1}],
}


def public_projection(capture: Capture, expected_samples: int = SAMPLES) -> dict:
    if type(expected_samples) is not int or expected_samples < 1 or expected_samples > 10000:
        raise InputError("expected_samples must be between 1 and 10000")
    selected = [span for span in capture.spans if span.name == STAGE and span.category == CATEGORY]
    if len(selected) != expected_samples:
        raise InputError("producer export has an unexpected number of named inference spans")
    selected.sort(key=lambda span: (span.timestamp_us, span.source_index))
    origin = Fraction(selected[0].timestamp_us)
    events = [
        {"ph": "X", "name": STAGE, "cat": CATEGORY, "pid": 1, "tid": 1,
         "ts": float(Fraction(span.timestamp_us) - origin), "dur": span.duration_ms * 1000}
        for span in selected
    ]
    return {"traceEvents": events, "capture_kind": "measured",
            "producer": "PyTorch CPU profiler", "projection": "named inference spans only"}


def validate_projection(raw_old: Capture, raw_new: Capture, old: dict, new: dict) -> None:
    policy = parse_policy(POLICY)
    raw_report = compare(raw_old, raw_new, policy, warmup=3)
    public_report = compare(parse_trace(old), parse_trace(new), policy, warmup=3)
    if raw_report["exit_code"] != public_report["exit_code"]:
        raise InputError("projection changed the producer budget decision")
    for raw_row, public_row in zip(raw_report["results"], public_report["results"]):
        for side in ("baseline", "candidate"):
            before, after = raw_row[side], public_row[side]
            if before is None or after is None or before["count"] != after["count"]:
                raise InputError("projection changed the producer sample count")
            for key in ("mean_ms", "median_ms", "p95_ms", "max_ms"):
                if not math.isclose(before[key], after[key], rel_tol=1e-12, abs_tol=1e-12):
                    raise InputError("projection changed the producer timing statistics")


def record() -> tuple[dict, dict, list[dict]]:
    import torch
    from torch.profiler import ProfilerActivity, profile, record_function

    if str(torch.__version__) != TORCH_VERSION:
        raise InputError("this compatibility example requires the pinned PyTorch CPU version")
    torch.manual_seed(7)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    model = torch.nn.Sequential(
        torch.nn.Linear(128, 64), torch.nn.ReLU(), torch.nn.Linear(64, 16)
    ).eval()
    inputs = torch.randn(64, 128)

    def vectorized():
        return model(inputs)

    def per_row():
        return torch.cat([model(row.unsqueeze(0)) for row in inputs], dim=0)

    captures = []
    diagnostics = []
    full_captures = []
    with torch.inference_mode():
        reference = vectorized()
        torch.testing.assert_close(per_row(), reference, rtol=1e-4, atol=1e-6)
        for operation in (vectorized, per_row):
            for _ in range(8):
                operation()
            # A single unscheduled recording avoids exporting only a final cycle.
            with profile(activities=[ProfilerActivity.CPU], record_shapes=False,
                         profile_memory=False, with_stack=False, with_flops=False) as recording:
                for _ in range(SAMPLES):
                    with record_function(STAGE):
                        result = operation()
            torch.testing.assert_close(result, reference, rtol=1e-4, atol=1e-6)
            # The full producer export exists only in remote temporary storage.
            # Public artifacts are reconstructed from explicit safe fields.
            with tempfile.TemporaryDirectory(prefix="tracebudget-profiler-") as temporary:
                raw_path = Path(temporary) / "capture.json"
                recording.export_chrome_trace(str(raw_path))
                raw_capture = parse_trace(read_json(raw_path))
                if not any(span.category == "cpu_op" for span in raw_capture.spans):
                    raise InputError("producer export contains no CPU operator spans")
                public = public_projection(raw_capture)
                full_captures.append(raw_capture)
                diagnostics.append({
                    "raw_events_validated": raw_capture.event_count,
                    "raw_duration_spans_validated": len(raw_capture.spans),
                    "raw_unsupported_events": raw_capture.ignored_events,
                    "public_spans": len(public["traceEvents"]),
                })
                captures.append(public)
    validate_projection(full_captures[0], full_captures[1], captures[0], captures[1])
    return captures[0], captures[1], diagnostics


def write_example(folder: Path, baseline: dict, candidate: dict, diagnostics: list[dict]) -> dict:
    policy = parse_policy(POLICY)
    old, new = parse_trace(baseline), parse_trace(candidate)
    report = compare(old, new, policy, warmup=3)
    if report["exit_code"] not in (0, 1):
        raise InputError("producer comparison has incomplete evidence")
    if compare(old, old, policy, warmup=3)["exit_code"] != 0:
        raise InputError("producer self-comparison failed")
    for name, value in (("baseline.json", baseline), ("candidate.json", candidate),
                        ("policy.json", POLICY), ("report.json", report)):
        write_atomic(folder / name, json.dumps(value, indent=2, allow_nan=False) + "\n")
    write_atomic(folder / "index.html",
                 render_html(report, "PyTorch CPU profiler: batched vs. per-row inference"))
    write_atomic(folder / "junit.xml", render_junit(report))
    method = {
        "capture_kind": "measured", "producer": "torch.profiler.export_chrome_trace",
        "producer_version": TORCH_VERSION, "device": "CPU", "intra_op_threads": 1,
        "inter_op_threads": 1, "model": "Linear(128,64), ReLU, Linear(64,16)",
        "batch_shape": [64, 128], "output_shape": [64, 16], "random_seed": 7,
        "mode": "inference_mode, model.eval", "samples_per_variant": SAMPLES,
        "pre_capture_warmups_per_variant": 8, "discarded_warmup_samples": 3,
        "retained_samples_per_variant": SAMPLES - 3,
        "baseline_implementation": "one vectorized batch",
        "candidate_implementation": "64 single-row calls concatenated into one batch",
        "output_equivalence": "torch.testing.assert_close; rtol=1e-4, atol=1e-6",
        "profiler_options": {"record_shapes": False, "profile_memory": False,
                             "with_stack": False, "with_flops": False},
        "projection": "Only the fixed inference annotation is retained. Lane IDs are normalized; timestamps are relative. Raw exports are deleted and never uploaded.",
        "captures": diagnostics, "raw_and_public_statistics_and_decisions_match": True,
        "interpretation": "CPU inclusive wall durations under profiler overhead. The two variants are captured sequentially; cache, ordering, and runner noise can affect results.",
        "validation": "Complete comparisons and a passing self-comparison are required. Compatibility does not require a particular timing outcome.",
    }
    write_atomic(folder / "method.json", json.dumps(method, indent=2, allow_nan=False) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/pytorch"))
    args = parser.parse_args(argv)
    try:
        baseline, candidate, diagnostics = record()
        report = write_example(args.output, baseline, candidate, diagnostics)
    except (InputError, OSError) as exc:
        message = str(exc) if isinstance(exc, InputError) else "cannot write producer artifacts"
        print("PyTorch compatibility error: " + message)
        return 2
    print("Validated full PyTorch CPU exports and matching inference outputs.")
    print("Published only the fixed inference-stage projection.")
    print("Producer compatibility checks passed. Observed budget result:", report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
