# Initial retrospective

## What the design achieves

The narrow trace format keeps the tool small enough to inspect.
Clear failure precedence prevents missing data from receiving a passing gate.
Separate parsers, comparisons, and renderers keep decision behavior testable.

The examples exercise two different claims: synthetic data establishes deterministic
expected outcomes; the measured workload records actual elapsed durations from
a deliberate algorithm change.

## Limits and mitigations

- Input JSON is decoded in memory. Byte/event limits bound accepted captures.
- Group pooling can combine unrelated work. Distinct category/name instrumentation
  and representative captures are required.
- A p95 computed from correlated spans gives a descriptive summary.
  Repeat captures under controlled conditions before relying on marginal changes.
- Trace producer conventions vary. The documented subset is explicit; unsupported
  phases are counted and malformed supported slices are rejected.
- Aggregate reports still retain selected labels. Review and sanitize labels
  before publication.
- Automated scanners have coverage limits. Public inputs are deliberately constructed
  without credentials, personal data, or private environment state.

## Scope for the next increment

The PyTorch increment adds a real producer export with explicit safe labels,
validated output equivalence, and a public projection checked against raw timing statistics.
Next, investigate false alarms across multiple runs and add a real game-engine capture. Expand input support in response
to demonstrated compatibility needs.
