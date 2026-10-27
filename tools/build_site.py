"""Build a compact public demo page from credential-free generated captures."""

import shutil
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
destination.mkdir(parents=True, exist_ok=True)
shutil.copytree(source, destination / "synthetic", dirs_exist_ok=True)
shutil.copytree(source / "measured", destination / "measured", dirs_exist_ok=True)
producer = Path(sys.argv[3]) if len(sys.argv) > 3 else None
producer_card = ""
if producer is not None:
    if not (producer / "method.json").is_file():
        raise SystemExit("PyTorch producer artifacts are incomplete.")
    shutil.copytree(producer, destination / "pytorch", dirs_exist_ok=True)
    producer_card = """<article><span class="tag">REAL PROFILER EXPORT</span>
<h2>PyTorch CPU inference, captured and checked</h2>
<p>The official CPU profiler records a small model with two equivalent inference implementations.
Only the fixed stage annotation is published; raw exports are excluded.</p>
<a href="pytorch/index.html">Explore the PyTorch report</a><br>
<a href="pytorch/method.json">Inspect the producer validation</a></article>"""
# Keep the synthetic example independent from the measured workload directory.
shutil.rmtree(destination / "synthetic" / "measured")
(destination / "index.html").write_text("""<!doctype html>
<html lang="en-US"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>TraceBudget | Performance budgets in CI</title>
<style>
:root{font:17px/1.6 system-ui,sans-serif;color:#172a42;background:#f3f6fa}*{box-sizing:border-box}
body{margin:0}main{max-width:1040px;padding:64px 24px;margin:auto}nav{display:flex;justify-content:space-between;gap:20px}
.brand{font-weight:800;color:#235dd2}h1{font-size:clamp(2.5rem,6vw,4.2rem);line-height:1.08;max-width:15ch;margin:56px 0 24px}
.lead{font-size:1.15rem;max-width:66ch;color:#4e6077}a{color:#174cba}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px;margin-top:36px}
article{background:#fff;border:1px solid #d8e0eb;border-top:4px solid #235dd2;border-radius:6px;padding:28px}
h2{line-height:1.25}code{font-size:.86em}pre{overflow:auto;background:#172a42;color:#fff;padding:24px;border-radius:6px}
.tag{font-size:.75rem;letter-spacing:.08em;font-weight:700}footer{margin-top:48px;color:#4e6077;font-size:.85rem}
</style></head><body><main><nav><span class="brand">TraceBudget / 0.1.0</span>
<a href="https://github.com/AntJun/trace-budget">View source on GitHub</a></nav>
<h1>Catch the slow stage before release.</h1>
<p class="lead">Compare two Chrome Trace Event captures against explicit latency budgets.
Get a useful CI decision and a report that explains each stage. Python 3.11+. Zero runtime dependencies.</p>
<div class="grid"><article><span class="tag">SYNTHETIC FIXTURE</span><h2>A game frame crosses its budget</h2>
<p>Deterministic frame and inference spans demonstrate absolute and relative checks.
These values are illustrative test data.</p>
<a href="synthetic/index.html">Explore the synthetic report</a><br><a href="synthetic/report.json">Inspect JSON evidence</a></article>
<article><span class="tag">MEASURED WORKLOAD</span><h2>An algorithm change introduces a slowdown</h2>
<p>A GitHub-hosted runner compares set and linear-list membership using the same query batch.
The slowdown is deliberate; timings vary with each build.</p>
<a href="measured/index.html">Explore the measured report</a><br><a href="measured/method.json">Read the measurement method</a></article>__PRODUCER_CARD__</div>
<section><h2>One command, reviewable artifacts</h2><pre><code>python -m tracebudget baseline.json candidate.json \\
  --policy policy.json --warmup 5 \\
  --html report.html --json report.json --junit junit.xml</code></pre>
<p>Exit codes: <strong>0 pass</strong>, <strong>1 regression</strong>,
<strong>2 invalid or incomplete</strong>. Missing stages and insufficient samples stay visible.</p>
<p>Supports complete <code>X</code> slices and nested <code>B/E</code> pairs.
Reports use inclusive per-span durations. Raw arguments, process metadata, thread IDs,
timestamps, and source paths are excluded. Selected span names and categories remain visible.</p>
<p><a href="https://github.com/AntJun/trace-budget#readme">Read the usage and analysis limits</a></p></section>
<footer>Maintained by AntJun. MIT licensed. Generated and tested on GitHub-hosted runners.</footer>
</main></body></html>
""".replace("__PRODUCER_CARD__", producer_card), encoding="utf-8")
