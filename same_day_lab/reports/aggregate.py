"""Multi-day aggregate report (JSON + Markdown).

A **descriptive distribution** of independent per-day outcomes — NOT a portfolio
track record. There is **no aggregate verdict**: per-day verdicts stand as-is and the
range output never emits a PASS that would imply the strategy is validated. No
Sharpe/Sortino/annualized/equity-curve/drawdown anything (CLAUDE.md prohibition).

``aggregate_hash`` covers only the analytical core (per-day ``report_hash`` values +
the range identity), excluding volatile provenance — exactly like ``report_hash``.
"""

import json
import os

from .. import DATA_WARNING
from ..hashing import content_hash

NO_VERDICT_NOTE = (
    "Descriptive distribution only — no aggregate validation verdict. "
    "Per-day verdicts stand as-is; naive fills can never validate a strategy."
)


def build_aggregate(
    *,
    symbol: str,
    start: str,
    end: str,
    config_hash: str,
    per_day: list[dict],
    missing_weekdays: list[str],
) -> dict:
    days = sorted(per_day, key=lambda p: p["session_date"])
    traded = [p for p in days if p["traded"]]

    def _count(pred, rows=days):
        return sum(1 for p in rows if pred(p))

    fill_honesty = _count(
        lambda p: p["naive_pnl"] is not None
        and p["naive_pnl"] > 0
        and p["pessimistic_default_pnl"] is not None
        and p["pessimistic_default_pnl"] <= 0,
        traded,
    )

    counts = {
        "days_ingested": len(days),
        "invalid_data": _count(lambda p: p["verdict"] == "INVALID_DATA"),
        "invalid_replay": _count(lambda p: p["verdict"] == "INVALID_REPLAY"),
        "no_signal": _count(lambda p: p["data_valid"] and p["replay_valid"] and not p["traded"]),
        "traded": len(traded),
        "traded_naive_gt0": _count(lambda p: p["naive_pnl"] is not None and p["naive_pnl"] > 0, traded),
        "traded_pessimistic_default_gt0": _count(
            lambda p: p["pessimistic_default_pnl"] is not None and p["pessimistic_default_pnl"] > 0, traded
        ),
        "traded_survived_pass_threshold": _count(lambda p: p["verdict"] == "PASS_FOR_MORE_TESTING", traded),
        "traded_killed_by_friction": _count(lambda p: p["verdict"] == "KILL_STRATEGY", traded),
    }

    distribution: dict[str, int] = {}
    for p in traded:
        key = "none" if p["crossover_cents"] is None else str(p["crossover_cents"])
        distribution[key] = distribution.get(key, 0) + 1

    per_day_table = [
        {
            "date": p["session_date"],
            "report_hash": p["report_hash"],
            "data_valid": p["data_valid"],
            "verdict": p["verdict"],
            "traded": p["traded"],
            "exit_reason": p["exit_reason"],
            "naive_pnl": p["naive_pnl"],
            "pessimistic_default_pnl": p["pessimistic_default_pnl"],
            "pessimistic_pass_pnl": p["pessimistic_pass_pnl"],
            "crossover_cents": p["crossover_cents"],
        }
        for p in days
    ]

    # Deterministic core — the only thing aggregate_hash covers.
    core = {
        "symbol": symbol,
        "range": {"start": start, "end": end},
        "config_hash": config_hash,
        "days": [{"date": p["session_date"], "report_hash": p["report_hash"]} for p in days],
        "missing_weekdays": sorted(missing_weekdays),
    }
    aggregate_hash = content_hash(core)

    disposition = (
        f"{counts['traded']} of {counts['days_ingested']} ingested day(s) traded; "
        f"naive looked profitable on {counts['traded_naive_gt0']}, pessimistic + friction "
        f"killed {fill_honesty}; {counts['traded_survived_pass_threshold']} survived the "
        f"pass threshold; {counts['invalid_data']} INVALID_DATA, {counts['no_signal']} "
        f"no-signal. No aggregate verdict."
    )

    return {
        "data_warning": DATA_WARNING,
        "kind": "aggregate",
        "symbol": symbol,
        "range": {"start": start, "end": end},
        "config_hash": config_hash,
        "counts": counts,
        "crossover_cents_distribution": distribution,
        "fill_honesty_headline": fill_honesty,
        "per_day": per_day_table,
        "missing_weekdays": sorted(missing_weekdays),
        "disposition": disposition,
        "note": NO_VERDICT_NOTE,
        "aggregate_hash": aggregate_hash,
    }


def _f(x) -> str:
    return "—" if x is None else f"{x:+.4f}"


def _aggregate_markdown(report: dict) -> str:
    r = report
    lines = [r["data_warning"], ""]
    lines.append(f"# same-day-trading-lab aggregate — {r['symbol']} {r['range']['start']} → {r['range']['end']}")
    lines.append("")
    lines.append(f"- Config hash: `{r['config_hash'][:16]}…`  Aggregate hash: `{r['aggregate_hash'][:16]}…`")
    lines.append(f"- _{r['note']}_")
    lines.append("")

    if r["missing_weekdays"]:
        lines.append("## Missing weekdays (no ingest — record/ingest them, or they were holidays)")
        lines.append(", ".join(r["missing_weekdays"]))
        lines.append("")

    lines.append("## Per-day")
    lines.append("| date | data_valid | verdict | traded | exit | naive | pess_default | pess_pass | crossover_c |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for p in r["per_day"]:
        lines.append(
            f"| {p['date']} | {p['data_valid']} | {p['verdict']} | {p['traded']} | "
            f"{p['exit_reason'] or '—'} | {_f(p['naive_pnl'])} | {_f(p['pessimistic_default_pnl'])} | "
            f"{_f(p['pessimistic_pass_pnl'])} | {('—' if p['crossover_cents'] is None else p['crossover_cents'])} |"
        )
    lines.append("")

    c = r["counts"]
    lines.append("## Aggregate counts")
    lines.append(f"- Days ingested: **{c['days_ingested']}**  (INVALID_DATA {c['invalid_data']}, "
                 f"INVALID_REPLAY {c['invalid_replay']}, no-signal {c['no_signal']}, traded {c['traded']})")
    lines.append(f"- Among traded: naive>0 **{c['traded_naive_gt0']}**, pessimistic-default>0 "
                 f"**{c['traded_pessimistic_default_gt0']}**, survived pass-threshold "
                 f"**{c['traded_survived_pass_threshold']}**, KILL **{c['traded_killed_by_friction']}**")
    lines.append(f"- Crossover (cents) distribution: {r['crossover_cents_distribution']}")
    lines.append("")
    lines.append(f"## Fill-honesty headline\n**{r['fill_honesty_headline']}** day(s) where naive looked "
                 f"profitable but pessimistic fills killed it.\n")
    lines.append(f"_{r['disposition']}_\n")
    return "\n".join(lines) + "\n"


def write_aggregate(report: dict, reports_dir: str) -> tuple[str, str]:
    os.makedirs(reports_dir, exist_ok=True)
    stem = f"{report['symbol']}_{report['range']['start']}_{report['range']['end']}_aggregate"
    json_path = os.path.join(reports_dir, f"{stem}.json")
    md_path = os.path.join(reports_dir, f"{stem}.md")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    with open(md_path, "w") as f:
        f.write(_aggregate_markdown(report))
    return json_path, md_path
