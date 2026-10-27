# Validation

[CI workflow](https://github.com/AntJun/trace-budget/actions/workflows/ci.yml) |
[Live examples](https://antjun.github.io/trace-budget/)

## Automated checks

The CI workflow evaluates the checked-out revision with:

- 54 standard-library unit and integration tests on Linux/Python 3.11,
  Linux/Python 3.14, and Windows/Python 3.14.
- Package installation, the console entry point, and deterministic CLI exit codes.
- Synthetic trace parsing and budget boundaries, including incomplete evidence,
  decimal equality, mixed timestamp precision, and file aliases.
- Report escaping and a public-data audit of generated artifacts.
- Credential scanning and a contact-data audit across fetched Git history.

The workflow page supplies the actual status for each revision. A passing check
applies to its tested source and configured environments.

## Real PyTorch producer

The optional producer job uses the official PyTorch 2.14.1+cpu wheel on Ubuntu 24.04
with Python 3.11. It records a fixed CPU model with two equivalent inference paths:
one vectorized batch and 64 per-row calls concatenated into the same batch shape.

The producer checks:

- Matching outputs using torch.testing.assert_close with explicit tolerances.
- Full-export parsing and the presence of CPU operator spans.
- Exactly 30 fixed inference annotations per implementation.
- A passing self-comparison.
- Matching selected statistics and budget decisions before and after projection.

The public projection retains the fixed stage label, duration, relative timestamp,
and normalized lane IDs. Raw arguments, metadata, internal labels, and original
identifiers are excluded. Raw exports are deleted from temporary storage and
are never uploaded.

[Producer report](https://antjun.github.io/trace-budget/pytorch/index.html) |
[Measurement method](https://antjun.github.io/trace-budget/pytorch/method.json)

## Example workloads

| Example | Data source | Purpose |
|---|---|---|
| Game-frame and inference fixture | Deterministic synthetic spans | Known absolute and relative budget outcomes |
| Membership lookup | Instrumented Python set/list operations | Measured detection of a deliberate algorithmic slowdown |
| PyTorch CPU inference | Actual profiler exports from fixed generated tensors | Producer interoperability and safe projection |

The membership report retains 40 samples per implementation after five warmup
samples are discarded. The PyTorch report retains 27 samples per implementation
after three recorded warmup samples are discarded, following eight untimed warmups.

## Reproduce the checks

Run these commands from a checkout in the intended development environment:

~~~sh
python -m unittest discover -s tests -v
python -m pip install .
tracebudget --help
python -m tracebudget.demo --output artifacts/demo
python tools/check_demo.py artifacts/demo
python tools/audit_public.py --history artifacts/demo
~~~

The optional producer requires its separately pinned integration dependency:

~~~sh
python -m pip install -r examples/pytorch-requirements.txt
python -m tools.profile_pytorch --output artifacts/pytorch
python tools/audit_public.py artifacts/pytorch
~~~

## Measurement boundaries

Durations are inclusive elapsed slices. They can contain nested work, waiting,
and profiler overhead. Grouped spans are pooled by the configured category/name.
A CPU annotation supplies no GPU execution measurement.

The producer variants are recorded sequentially. Cache state, ordering, scheduling,
and runner noise can affect timings. Compatibility requires complete evidence
and equivalent outputs; it accepts either complete budget outcome.

Use repeated controlled captures to investigate marginal changes. These examples
establish no production impact, statistical significance, or general performance gain.
