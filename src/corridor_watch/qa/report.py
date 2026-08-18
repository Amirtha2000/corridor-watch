"""Render QA check results into a delivery report (Markdown + JSON).

The JSON is machine-readable (for dashboards / regression tracking across
deliveries); the Markdown is what a Project Manager or customer-facing
colleague can read without opening a terminal.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from corridor_watch.qa.checks import CheckResult

_BADGE = {"info": "ℹ️", "warning": "⚠️", "error": "⛔"}


def write_report(
    results: list[CheckResult],
    out_dir: str | Path,
    run_name: str,
    context: dict | None = None,
) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    n_fail_err = sum(1 for r in results if not r.passed and r.severity.value == "error")
    n_fail_warn = sum(1 for r in results if not r.passed and r.severity.value == "warning")
    verdict = "DELIVERY BLOCKED" if n_fail_err else ("PASS WITH WARNINGS" if n_fail_warn else "PASS")

    # --- JSON ---------------------------------------------------------------
    payload = {
        "run": run_name,
        "generated": stamp,
        "verdict": verdict,
        "context": context or {},
        "checks": [r.as_dict() for r in results],
    }
    json_path = out / f"qa_{run_name}.json"
    json_path.write_text(json.dumps(payload, indent=2))

    # --- Markdown -----------------------------------------------------------
    lines = [
        f"# QA report — {run_name}",
        "",
        f"Generated: {stamp}  ",
        f"**Verdict: {verdict}**  ",
        f"Checks: {len(results)} total · {n_fail_err} blocking failure(s) · {n_fail_warn} warning(s)",
        "",
        "| Status | Severity | Check | Result |",
        "|--------|----------|-------|--------|",
    ]
    for r in results:
        status = "✅" if r.passed else "❌"
        lines.append(
            f"| {status} | {_BADGE[r.severity.value]} {r.severity.value} | {r.check} | {r.message} |"
        )
    if context:
        lines += ["", "## Run context", ""]
        lines += [f"- **{k}**: {v}" for k, v in context.items()]

    md_path = out / f"qa_{run_name}.md"
    md_path.write_text("\n".join(lines))
    return md_path, json_path
