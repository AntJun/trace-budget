# TraceBudget

[![CI](https://github.com/AntJun/trace-budget/actions/workflows/ci.yml/badge.svg)](https://github.com/AntJun/trace-budget/actions/workflows/ci.yml)

**Catch performance regressions in profiler captures before release.**

TraceBudget compares Chrome Trace Event JSON captures against explicit latency budgets.
It gives CI a predictable exit code and reviewers a self-contained HTML report,
machine-readable JSON, and JUnit results. Python 3.11+. Zero runtime dependencies.

[Explore the live demo](https://antjun.github.io/trace-budget/) |
[Read the design](docs/design.md) |
[Review the evidence](docs/evidence.md)

## The problem it solves

A profiler capture can contain thousands of duration slices. A release engineer needs
a repeatable answer to a narrower question: did this change push a particular stage
past its latency budget?

TraceBudget turns selected stage names into reviewable checks. Typical uses include
game-frame processing, application startup stages, batch processing, and instrumented
inference stages exported as Chrome JSON. PyTorch can export this format; compatibility
with a particular producer should be checked against the supported subset below.

Perfetto supplies comprehensive trace analysis and SQL metrics. TraceBudget focuses
on a small install footprint, explicit budget policies, and artifacts that fit a CI review.

## Try the examples

Install from a checkout, or install a specific commit using pip:

~~~sh
python -m pip install .
python -m tracebudget.demo --output artifacts/demo
tracebudget artifacts/demo/baseline.json artifacts/demo/candidate.json \
  --policy artifacts/demo/policy.json --warmup 3 \
  --html artifacts/report.html --json artifacts/report.json \
  --junit artifacts/junit.xml
~~~

The synthetic comparison returns **exit 1** because its frame stage deliberately regresses.
The inference stage stays within its configured budgets.

The demo also records a real Python CPU workload. It compares set membership with
linear list membership using the same deterministic query batch. The generated
measured captures, method, and reports are in artifacts/demo/measured/. Each capture
has 45 samples; the report discards the first 5 and evaluates the remaining 40.
This deliberately introduced algorithmic slowdown demonstrates the tool's behavior.
Its timing values depend on the runner and workload.

The [live demo](https://antjun.github.io/trace-budget/) includes both examples and their JSON evidence.
GitHub Actions generates, tests, audits, and publishes the reports without deployment credentials
stored in the repository.

## Define a policy

~~~json
{
  "version": 1,
  "min_samples": 20,
  "rules": [
    {
      "name": "frame",
      "category": "game",
      "metric": "p95",
      "max_ms": 16.67,
      "max_regression_pct": 10,
      "min_delta_ms": 0.5
    }
  ]
}
~~~

Rules match a case-sensitive span name and category. Comma-delimited categories are
trimmed, deduplicated, and sorted in both captures and policies. An absent category
becomes an empty string. Groups pool spans across all processes and threads, allowing
process/thread IDs to change between captures. Use distinct instrumentation categories
when separate stages share a name.

Supported statistics: p95, median, mean, and max. The default is p95.
Percentiles use linear interpolation at rank (n - 1) * q. A p95 absolute budget bounds
the p95 statistic; individual observations can exceed it.

A rule fails when either condition holds:

- The candidate statistic exceeds max_ms.
- Percentage growth exceeds max_regression_pct **and** the absolute increase
  exceeds min_delta_ms.

Every comparison uses strict greater-than boundaries and unrounded values.
A rule requires at least one budget. The delta floor defaults to zero and requires
a percentage budget. Duplicate selector/statistic combinations and unknown fields
are rejected to expose policy mistakes.

Both captures must retain at least min_samples observations for every rule.
The default minimum is 20. Warmup removes the earliest N spans independently
from each category/name group in each capture, ordered by start timestamp and source order.

With a zero baseline, any positive candidate satisfies the percentage-growth condition;
the configured delta floor still applies. Percentage change is null when the baseline
is zero or the ratio exceeds the finite numeric range.

## CI behavior

| Exit | Meaning |
|---|---|
| 0 | Every rule is complete and within budget |
| 1 | At least one complete rule regressed |
| 2 | Invalid input, incomplete evidence, or an output error |

Incomplete evidence takes precedence over regressions. Reports preserve both findings.
Missing stages, warmup exhaustion, and too few samples always produce an incomplete decision.

~~~yaml
- name: Enforce stage budgets
  run: |
    python -m tracebudget baseline.json candidate.json \
      --policy policy.json --warmup 5 \
      --html artifacts/report.html --json artifacts/report.json \
      --junit artifacts/junit.xml
~~~

Upload artifacts in a subsequent always-running step so a failed gate remains reviewable.
TraceBudget supplies the analysis command. Your workflow supplies capture collection,
baseline selection, and artifact retention.

## Supported input and boundaries

- A JSON event array, or an object containing a traceEvents array.
- Complete X duration slices and properly nested B/E slices.
- Microsecond ts/dur values; displayTimeUnit does not change their interpretation.
- Independent B/E stacks keyed by typed pid/tid. Missing optional end labels are accepted;
  supplied name/category labels must match the begin.
- Stable timestamp/source-order sorting, including unordered event arrays.
- Finite, nonnegative timestamps/durations up to 1e18 microseconds.
  Integer timestamps retain integer subtraction, including values beyond 2^53.
- A default 64 MiB input limit, one million events per capture, one MiB policy limit,
  and 1,000 policy rules. --max-mb and --max-events configure capture limits.

Malformed supported events invalidate the capture, including events outside configured groups.
Unknown phases are ignored and counted in reports. Async events, flows, counters, native
Perfetto protobufs, GPU timing interpretation, and CPU self-time are outside v0.1.0.

Each duration is an inclusive elapsed slice. Nested work and waiting can be included.
A frame-latency budget requires an actual frame span. A CPU launch span alone does
not establish GPU execution time. Summed overlapping slices do not establish total
program elapsed time.

Comparisons are descriptive. There is no statistical-significance test or automatic
baseline promotion. Use representative, controlled captures, sufficient samples,
and repeat runs to investigate measurement noise.

## Privacy and secure handling

TraceBudget does not make network requests. Reports retain only configured span names,
categories, aggregate timing statistics, budget decisions, and input counts.
Raw args, process metadata, thread IDs, timestamps, and source file paths are excluded.
Names and categories can contain sensitive text; sanitize them before sharing reports.

HTML is script-free, escapes input-derived labels, and includes a restrictive content
security policy. JUnit escapes labels and rejects XML-invalid characters at input.
Errors identify event indexes without dumping raw events. Terminal labels use JSON escaping.
Outputs cannot overwrite inputs or each other and are replaced atomically per file.

This repository uses constructed demonstration data and a self-contained integer workload.
No production captures, user records, credentials, contact details, or private environment
configuration are required. CI runs a credential scan and checks public contact data
through all reachable git history and generated demo files. These checks complement
pre-publication review.

## Development

~~~sh
python -m unittest discover -s tests -v
python -m tracebudget.demo --output artifacts/demo
python tools/check_demo.py artifacts/demo
python tools/audit_public.py --history artifacts/demo
~~~

CI covers Linux and Windows, package installation, CLI behavior, parser invariants,
budget boundaries, incomplete evidence, report escaping, and generated-artifact review.
Actions are pinned to full commit SHAs. Pull-request code receives read-only repository permissions;
publication runs after successful checks on main.

## License and maintainer

MIT. Maintained by [AntJun](https://github.com/AntJun).

References: [Chrome JSON in Perfetto](https://perfetto.dev/docs/getting-started/other-formats) |
[PyTorch profiler](https://docs.pytorch.org/docs/stable/profiler.html) |
[Perfetto trace summaries](https://perfetto.dev/docs/analysis/trace-summary).
