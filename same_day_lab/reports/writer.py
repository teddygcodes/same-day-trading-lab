"""Assemble the deterministic JSON + Markdown report.

The ``report_hash`` is computed over the *analytical core* only — OR levels, fills,
P&L, the sweep table, crossover, and verdict — and deliberately EXCLUDES volatile
provenance (wall-clock timestamps, file paths, git commit, ingest id, raw hash).
Two runs of the same fixture + config therefore produce an identical report_hash.

No Sharpe/Sortino/annualized/equity-curve/HTML/marketing language by design.
"""

import json
import os
import subprocess

from .. import DATA_WARNING
from ..hashing import content_hash

SMOKE_NOTE = "ORB is a smoke test, not a validated edge."
STRATEGY_NAME = "orb_long_5m"


def _strategy_note(strategy: str) -> str:
    if strategy == STRATEGY_NAME:
        return SMOKE_NOTE
    return f"{strategy} is a pre-registered hypothesis, not a validated edge."


def git_commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _r(x, n=4):
    return None if x is None else round(x, n)


def _trade_block(trade) -> dict | None:
    if trade is None:
        return None
    return {
        "fill_bar_ts": trade.fill_bar_ts.isoformat(),
        "exit_signal_bar_ts": trade.exit_signal_bar_ts.isoformat() if trade.exit_signal_bar_ts else None,
        "exit_fill_bar_ts": trade.exit_fill_bar_ts.isoformat() if trade.exit_fill_bar_ts else None,
        "exit_reason": trade.exit_reason,
        "target_price": _r(trade.notes.get("target_price")),
        "stop_price": _r(trade.notes.get("stop_price")),
        "naive": {
            "entry": _r(trade.naive_entry_price),
            "exit": _r(trade.naive_exit_price),
            "pnl": _r(trade.naive_pnl, 6),
        },
        "pessimistic": {
            "entry": _r(trade.pessimistic_entry_price),
            "exit": _r(trade.pessimistic_exit_price),
            "pnl": _r(trade.pessimistic_pnl, 6),
        },
    }


def build_report(
    *,
    run_id,
    symbol,
    session_date,
    strategy,
    provider,
    feed,
    config_hash,
    ingest_run_id,
    raw_hash,
    quality_summary,
    bar_count_expected,
    bar_count_actual,
    replay_result,
    data_valid,
    data_reasons,
    verdict,
    pessimistic_default_pnl,
    pessimistic_pass_pnl,
    started_at,
    completed_at,
) -> dict:
    signal = replay_result.get("signal")
    trade = replay_result.get("trade")
    context = replay_result.get("strategy_context")
    crossover = replay_result.get("crossover")

    signal_block = (
        {"signal_bar_ts": signal.signal_bar_ts.isoformat(), "trigger_price": _r(signal.trigger_price)}
        if signal is not None
        else None
    )
    proof = None
    if trade is not None:
        proof = {
            "signal_bar_ts": trade.signal_bar_ts.isoformat(),
            "fill_bar_ts": trade.fill_bar_ts.isoformat(),
            "distinct": trade.signal_bar_ts != trade.fill_bar_ts,
        }

    # Analytical core — the only thing report_hash covers.
    core = {
        "symbol": symbol,
        "session_date": session_date,
        "strategy": strategy,
        "config_hash": config_hash,
        "bars": {"expected": bar_count_expected, "actual": bar_count_actual},
        "quality_summary": quality_summary,
        "data_valid": data_valid,
        "strategy_context": (
            {k: _r(v) for k, v in context.items()} if context else None
        ),
        "signal": signal_block,
        "trade": _trade_block(trade),
        "friction_sweep": (trade.friction_sweep if trade is not None else None),
        "crossover": crossover,
        "pessimistic_default_pnl": _r(pessimistic_default_pnl, 6),
        "pessimistic_pass_pnl": _r(pessimistic_pass_pnl, 6),
        "verdict": verdict,
    }
    report_hash = content_hash(core)

    report = {
        "data_warning": DATA_WARNING,
        "run": {
            "run_id": run_id,
            "strategy": strategy,
            "started_at_utc": started_at,
            "completed_at_utc": completed_at,
        },
        "provider": provider,
        "feed": feed,
        "git_commit": git_commit(),
        "ingest_run_id": ingest_run_id,
        "raw_hash": raw_hash,
        "no_lookahead_proof": proof,
        "data_reasons": data_reasons,
        **core,
        "note": _strategy_note(strategy),
        "report_hash": report_hash,
    }
    return report


def _sweep_markdown(table, crossover) -> str:
    if not table:
        return "_No trade — no friction sweep._\n"
    cents = sorted({r["cents"] for r in table})
    bps = sorted({r["bps"] for r in table})
    lookup = {(r["cents"], r["bps"]): r["pnl"] for r in table}
    lines = ["| cents \\ bps | " + " | ".join(str(b) for b in bps) + " |"]
    lines.append("|" + "---|" * (len(bps) + 1))
    for c in cents:
        row = [f"**{c}**"] + [f"{lookup[(c, b)]:+.4f}" for b in bps]
        lines.append("| " + " | ".join(row) + " |")
    cc = crossover.get("crossover_cents") if crossover else None
    note = (
        f"\nCrossover (at {crossover['axis_bps']} bps): pessimistic P&L turns "
        f"non-positive at **{cc} cents**."
        if cc is not None
        else "\nNo crossover along the axis: still profitable at max friction "
        "(NOT proof of edge)."
    )
    return "\n".join(lines) + "\n" + (note if crossover else "")


def _markdown(report) -> str:
    r = report
    lines = []
    # DATA WARNING is the first content block.
    lines.append(r["data_warning"])
    lines.append("")
    lines.append(f"# same-day-trading-lab report — {r['symbol']} {r['session_date']}")
    lines.append("")
    lines.append(f"- **Verdict:** `{r['verdict']}`")
    lines.append(f"- Strategy: `{r['run']['strategy']}` — _{r['note']}_")
    lines.append(f"- Provider/feed: {r['provider']} / {r['feed']}")
    lines.append(f"- Config hash: `{r['config_hash'][:16]}…`  Report hash: `{r['report_hash'][:16]}…`")
    lines.append(f"- Git commit: `{r['git_commit']}`")
    lines.append(f"- Ingest: `{r['ingest_run_id']}`  raw_hash: `{r['raw_hash'][:16]}…`")
    lines.append(f"- Bars expected/actual: {r['bars']['expected']}/{r['bars']['actual']}")
    lines.append(f"- Data valid: {r['data_valid']}" + (f" — reasons: {r['data_reasons']}" if r["data_reasons"] else ""))
    qs = r.get("quality_summary") or {}
    mb = qs.get("missing_bar_count", 0)
    if mb or qs.get("halt_suspected"):
        halt = qs.get("halt_runs") or []
        suffix = f"  — halt_suspected: {len(halt)} run(s) ≥ threshold" if qs.get("halt_suspected") else ""
        lines.append(f"- Missing RTH minutes: **{mb}** (gaps are not fabricated){suffix}")
        shown = qs.get("missing_bars", [])[:12]
        if shown:
            more = "" if len(qs.get("missing_bars", [])) <= 12 else f" … (+{len(qs['missing_bars']) - 12} more)"
            lines.append(f"  - missing: {', '.join(shown)}{more}")
    lines.append("")

    if r["strategy_context"]:
        ctx = ", ".join(f"{k} {v}" for k, v in r["strategy_context"].items())
        lines.append(f"## Strategy context\n{ctx}\n")
    if r["no_lookahead_proof"]:
        p = r["no_lookahead_proof"]
        lines.append("## No-lookahead proof")
        lines.append(f"signal_bar_ts `{p['signal_bar_ts']}` != fill_bar_ts `{p['fill_bar_ts']}` → **{p['distinct']}**\n")

    if r["trade"]:
        t = r["trade"]
        lines.append("## Fills (per share)")
        lines.append(f"- Exit reason: **{t['exit_reason']}**  (target {t['target_price']}, stop {t['stop_price']})")
        lines.append(f"- Naive (fantasy): entry {t['naive']['entry']} → exit {t['naive']['exit']} = **{t['naive']['pnl']:+.4f}**")
        lines.append(f"- Pessimistic: entry {t['pessimistic']['entry']} → exit {t['pessimistic']['exit']} = **{t['pessimistic']['pnl']:+.4f}**")
        lines.append(f"- Pessimistic @ pass-threshold: **{r['pessimistic_pass_pnl']:+.4f}**")
        lines.append("\n_Naive fills are a labeled lie and can never validate a strategy._\n")
        lines.append("## Friction sweep (pessimistic P&L per share)")
        lines.append(_sweep_markdown(r["friction_sweep"], r["crossover"]))
    else:
        lines.append("## Trade\n_No trade triggered this session._\n")

    return "\n".join(lines) + "\n"


def write_reports(report: dict, reports_dir: str) -> tuple[str, str]:
    os.makedirs(reports_dir, exist_ok=True)
    stem = f"{report['symbol']}_{report['session_date']}_{report['run']['run_id']}"
    json_path = os.path.join(reports_dir, f"{stem}.json")
    md_path = os.path.join(reports_dir, f"{stem}.md")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    with open(md_path, "w") as f:
        f.write(_markdown(report))
    return json_path, md_path
