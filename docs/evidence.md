# Project evidence and application notes

Repository: https://github.com/AntJun/trace-budget
Live demonstration: https://antjun.github.io/trace-budget/
CI evidence: https://github.com/AntJun/trace-budget/actions/workflows/ci.yml

## Implemented scope

- A Python 3.11+ command-line tool with no runtime dependencies.
- Chrome Trace Event X and nested B/E parsing, strict policy validation,
  sample sufficiency checks, and deterministic per-span latency budgets.
- Self-contained HTML, JSON, and JUnit reports with controlled failure behavior.
- Cross-platform CI, package/CLI checks, input/output safeguards, and public-data audits.
- Synthetic game-frame/inference fixtures plus a measured CPU workload.

Validation results and measured values should be read from the linked CI run and
report JSON for the specific revision. Feature descriptions alone establish no
test pass, production adoption, employment experience, or user contribution.

## Target-role connection

| Role family | Relevant evidence | Further evidence needed |
|---|---|---|
| Junior software / developer tools | CLI design, validation, packaging, tests, readable failures | Candidate review and an explanation of the implementation |
| Game tools / performance infrastructure | Frame-span budgets, trace format interoperability, CI artifacts | Real engine exports; engine/C++ work requires separate evidence |
| Systems / platform | Bounded input, numeric edge cases, Linux/Windows CI, reproducible artifacts | Service operation, concurrency, and production use |
| AI infrastructure | Inference-span fixture and a format accepted by PyTorch profiler exports | A genuine PyTorch-export compatibility test |
| Security engineering | Input validation, escaped reports, limited CI permissions, history audit | Detection engineering, security operations, or authorized assessment work |

## CV entry draft

**TraceBudget | Open-source developer tool | Python, GitHub Actions, Chrome Trace Event**

- Performance regression CLI with exact stage policies, p95 and absolute/relative
  budgets, sample checks, and deterministic CI exit codes.
- Self-contained HTML, JSON, and JUnit evidence from synthetic fixtures and a
  measured algorithmic slowdown, with strict input validation and report escaping.

These are artifact descriptions. Review the code and demonstrations before
representing individual implementation ownership in an application.
No production impact or unmeasured performance claim is included.

## Two-minute review

1. Open the synthetic report and identify the failing frame stage.
2. Inspect its policy and explain absolute thresholds and relative delta floors.
3. Open the measured report and method JSON.
4. Explain how incomplete evidence receives exit 2 and why repeated controlled
   captures are needed to assess timing noise.
5. Inspect the tests and explain one parser or reporting edge case.
