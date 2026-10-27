"""Integration checks against the installed command-line interface."""

import json
import subprocess
import sys
from pathlib import Path

folder = Path(sys.argv[1])
for candidate, expected in (("candidate.json", 1), ("baseline.json", 0)):
    result = subprocess.run(
        [sys.executable, "-m", "tracebudget", str(folder / "baseline.json"),
         str(folder / candidate), "--policy", str(folder / "policy.json"),
         "--warmup", "3", "--json", str(folder / "cli-report.json")],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != expected:
        raise SystemExit(f"CLI integration failed: expected {expected}, got {result.returncode}")
    report = json.loads((folder / "cli-report.json").read_text(encoding="utf-8"))
    if report["exit_code"] != expected:
        raise SystemExit("CLI result and JSON exit code disagree")
print("CLI integration checks passed.")
