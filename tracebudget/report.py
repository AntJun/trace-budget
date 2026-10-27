"""Script-free HTML and JUnit representations of a comparison."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET


def _value(summary: dict | None, metric: str) -> str:
    return "\u2014" if summary is None else f'{summary[metric + "_ms"]:.3f}'


def render_html(report: dict, title: str = "Performance budget report") -> str:
    escape = html.escape
    rows = []
    for row in report["results"]:
        budgets = row["budgets"]
        limits = []
        if budgets["max_ms"] is not None:
            limits.append(f'absolute > {budgets["max_ms"]:g} ms')
        if budgets["max_regression_pct"] is not None:
            limits.append(f'relative > {budgets["max_regression_pct"]:g}% '
                          f'and delta > {budgets["min_delta_ms"]:g} ms')
        delta = "\u2014" if row["delta_ms"] is None else f'{row["delta_ms"]:+.3f} ms'
        pct = ("undefined" if row["delta_pct"] is None
               else f'{row["delta_pct"]:+.1f}%')
        counts = " / ".join(str(row[key]["count"] if row[key] else 0)
                            for key in ("baseline", "candidate"))
        explanation = "; ".join(row["reasons"]) or "within configured budgets"
        rows.append(
            '<tr><td><strong>' + escape(row["name"]) + "</strong><br><small>"
            + escape(row["category"] or "(uncategorized)") + "</small></td><td>"
            + escape(row["metric"]) + "</td><td>" + counts + "</td><td>"
            + _value(row["baseline"], row["metric"]) + "</td><td>"
            + _value(row["candidate"], row["metric"]) + "</td><td>"
            + delta + "<br><small>" + pct + "</small></td><td><span class=\""
            + row["status"] + "\">" + row["status"].upper() + "</span><br><small>"
            + escape(explanation) + "<br>" + escape("; ".join(limits)) + "</small></td></tr>"
        )
    inputs = report["inputs"]
    ignored = sum(item["ignored_events"] for item in inputs.values())
    diagnostics = (
        f'Baseline: {inputs["baseline"]["events"]} events, '
        f'{inputs["baseline"]["spans"]} duration spans. '
        f'Candidate: {inputs["candidate"]["events"]} events, '
        f'{inputs["candidate"]["spans"]} duration spans. '
        f'{ignored} unsupported-phase events ignored.'
    )
    return """<!doctype html>
<html lang="en-US"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>""" + escape(title) + """ | TraceBudget</title>
<style>
:root{color-scheme:light;font:16px/1.55 system-ui,sans-serif;color:#172a42;background:#f3f6fa}
*{box-sizing:border-box}body{margin:0}main{max-width:1220px;margin:auto;padding:48px 24px}
header{border-top:5px solid #235dd2;padding:26px 30px;background:#fff;border-radius:6px}
.brand{font-weight:800;color:#235dd2;letter-spacing:.03em}h1{font-size:clamp(1.8rem,4vw,2.6rem);line-height:1.2;margin:14px 0}
p{max-width:86ch}a{color:#174cba}section{margin-top:28px}.cards{display:flex;flex-wrap:wrap;gap:16px}
.card{background:#fff;border:1px solid #d8e0eb;border-radius:6px;padding:20px;flex:1;min-width:160px}
.card strong{display:block;font-size:1.7rem}.table-wrap{overflow-x:auto;background:#fff;border:1px solid #d8e0eb;border-radius:6px}
table{border-collapse:collapse;width:100%;text-align:left}caption{text-align:left;padding:18px 20px;font-weight:700}
th,td{padding:16px 20px;vertical-align:top;border-top:1px solid #d8e0eb}th{background:#f8fafd;font-size:.85rem}
small{font-size:.8rem;color:#4e6077}.pass{color:#11633c}.regression{color:#a12129}.incomplete{color:#8d4d00}
.pass,.regression,.incomplete{font-weight:800}footer{margin-top:32px;font-size:.85rem;color:#4e6077}
code{font-size:.9em;background:#e8eef8;padding:2px 5px;border-radius:3px}
</style></head><body><main><header><div class="brand">TraceBudget / 0.1.0</div>
<h1>""" + escape(title) + """</h1><p>Review latency budgets before a change reaches users.
Each row compares the same named span across two profiler captures.</p></header>
<section class="cards" aria-label="Result summary">
<div class="card">Overall result<strong class=\"""" + report["status"] + "\">" + report["status"].upper() + """</strong></div>
<div class="card">Rules evaluated<strong>""" + str(report["summary"]["rules"]) + """</strong></div>
<div class="card">Regressions<strong>""" + str(report["summary"]["regressions"]) + """</strong></div>
<div class="card">Incomplete rules<strong>""" + str(report["summary"]["incomplete"]) + """</strong></div></section>
<section class="table-wrap"><table><caption>Per-span duration budgets (milliseconds)</caption>
<thead><tr><th scope="col">Span / category</th><th scope="col">Statistic</th>
<th scope="col">Samples<br>baseline / candidate</th><th scope="col">Baseline (ms)</th>
<th scope="col">Candidate (ms)</th><th scope="col">Change</th><th scope="col">Decision / failure condition</th></tr></thead>
<tbody>""" + "".join(rows) + """</tbody></table></section><section><h2>How to read this report</h2><p>"""
        + escape(diagnostics) + f"""</p><p>Warmup: {report["warmup_per_group"]} earliest spans removed
per category/name group in each capture, pooled across threads. Minimum required:
{report["min_samples"]} retained samples in both captures. Percentiles use linear
interpolation at rank <code>(n - 1) * q</code>. Decisions use unrounded values.</p>
<p>Durations include nested work and waiting time. Percentages are undefined for a
zero baseline or a ratio outside the finite numeric range. This report supplies
descriptive comparisons; repeated controlled captures are needed to assess noise.
Raw event arguments, process metadata, thread IDs, timestamps, and file paths are excluded.</p></section>
<footer>Maintained by <a href="https://github.com/AntJun">AntJun</a> &middot;
<a href="https://github.com/AntJun/trace-budget">Source and usage</a> &middot;
Exit codes: 0 pass, 1 regression, 2 invalid or incomplete input.</footer></main></body></html>
"""


def render_junit(report: dict) -> str:
    summary = report["summary"]
    suite = ET.Element("testsuite", name="TraceBudget", tests=str(summary["rules"]),
                       failures=str(summary["regressions"]), errors=str(summary["incomplete"]))
    for row in report["results"]:
        case = ET.SubElement(suite, "testcase", classname=row["category"] or "uncategorized",
                             name=row["name"] + " [" + row["metric"] + "]")
        message = "; ".join(row["reasons"])
        if row["status"] != "pass":
            kind = "error" if row["status"] == "incomplete" else "failure"
            ET.SubElement(case, kind, message=message).text = message
    return ET.tostring(suite, encoding="unicode", xml_declaration=True) + "\n"
