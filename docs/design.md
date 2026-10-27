# Design and engineering decisions

## User and success criteria

The primary user is a developer reviewing a change to an instrumented stage.
A useful result identifies the stage, effective threshold, baseline/candidate statistic,
sample counts, and reason for a failure. A malformed capture or missing stage must remain visible.

A successful invocation accepts two valid captures and one policy, produces a
deterministic decision, and optionally writes HTML, JSON, and JUnit artifacts.
The pipeline can preserve these artifacts when a budget fails.

## Architecture

~~~text
Capture JSON --> bounded reader --> strict span parser -----+
                                                           |
Policy JSON ---> strict policy validator ------------------+--> compare
                                                               |
                                      HTML / JSON / JUnit <-----+
                                                               |
                                                       exit 0 / 1 / 2
~~~

core.py owns parsing, grouping, statistics, and decisions. report.py renders an
already evaluated comparison. __main__.py handles paths, bounded I/O, atomic file
replacement, and terminal output. demo.py supplies fixture and measured examples.

Keeping these responsibilities separate makes report changes independent of gate semantics.

## Trade-offs

| Decision | Benefit | Limit |
|---|---|---|
| Standard library runtime | Small dependency surface and easy CI integration | JSON decoding holds the bounded capture in memory |
| Exact name/category matching | Reviewable policy and stable cross-capture identity | Instrumentation naming requires discipline |
| Pool all lanes by category/name | Process and thread ID changes do not break checks | Different workloads need distinct categories |
| Inclusive durations | Works directly with common duration slices | Supplies no self-time or GPU-time interpretation |
| p95 linear interpolation | Deterministic, explicit calculation | Small samples and correlated spans can mislead |
| Absolute plus relative budgets | Supports user-facing targets and baseline drift | Thresholds require workload-specific calibration |
| Per-file atomic outputs | Prevents partially written individual reports | Multiple output files form no transaction |

Supported slices are sorted by start timestamp and original source index.
B/E pairing uses per-lane stacks; supplied end labels must match. Begin source
indexes survive pairing so equal-start warmup order follows the original input.
Integer time values preserve subtraction precision. Threshold checks compare the
candidate statistic directly with its effective bound and use a four-ULP equality
guard. This prevents decimal representation noise from flagging an exact boundary.

Comma-delimited categories are canonicalized as sets. This makes "render,ui"
and "ui,render" equivalent. Names remain exact and case-sensitive.

## Failure and threat model

Untrusted captures can contain malformed numbers, enormous arrays, script markup,
terminal control sequences, arbitrary args, or private labels.
The reader bounds bytes before decoding. The parser bounds event counts and label lengths,
rejects duplicate JSON keys/nonfinite values, and reports event indexes without values.
Policy validation rejects misspelled fields and non-executable rules.

Every supported event is validated, including events outside the policy.
All unknown phases count toward the capture limit and appear as ignored counts.

Reports never copy raw args or metadata. Configured names/categories remain visible;
the tool has no universal sensitive-label classifier. HTML contains no active scripts
or external assets. JUnit input restrictions cover XML-invalid controls and surrogates.
The CLI escapes terminal labels and refuses output/input aliases.

## Evaluation

Deterministic synthetic fixtures provide known budget outcomes.
Randomized equivalence checks compare X slices with B/E recordings.
Boundary tests cover exact thresholds, zero baselines, insufficient samples,
large integer timestamps, malformed unruled events, and finite serialization.

The measured example alternates set/list lookup order across 45 sample pairs.
Both variants check 400 deterministic integers against 4,000 stored values.
The report removes five warmup observations per variant.
Each recorded span covers one complete query batch. Construction of the set/list
is outside the measured span.

This is a controlled demonstration of one algorithmic regression. It establishes
no commercial impact, cross-application speedup, or statistical significance.

## Next evidence to collect

A game or application team could export representative frame/startup traces,
choose budgets from user-facing targets, and evaluate the gate across repeated
controlled changes. A genuine PyTorch export would extend producer compatibility evidence.
Lane selectors and native Perfetto import can follow an observed user need.
