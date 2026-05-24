"""Cross-strategy × cross-window tournament report (JSON + Markdown).

A **descriptive leaderboard** of the full pre-registered strategy set evaluated over a
**decide** window (in-sample, where we looked) and a **holdout** window (confirmatory).
Its whole job is to make over-reading promising in-sample results HARD:

- **Holdout gate.** A strategy is "carried forward" only if it *survives in both* windows.
- **Multiple-comparisons honesty.** The report states how many strategies were tried, so a
  single decide-window pass reads as weak evidence (no p-values — honest counting).

There is **no tournament winner / validation verdict**: per-strategy, per-day verdicts
stand as-is. ``carried_forward`` is a flag, not a verdict. No portfolio/equity/Sharpe/
drawdown math anywhere (CLAUDE.md prohibitions). This is a thin rollup over v0.3's
per-(strategy, window) aggregates — it forks no fill/verdict logic.

``tournament_hash`` covers only the analytical core (the per-(strategy, window)
``aggregate_hash`` values + the registered set + the two window identities), excluding
volatile provenance — exactly like ``aggregate_hash`` and ``report_hash``.
"""

import json
import os

from .. import DATA_WARNING
from ..hashing import content_hash

# A-priori, counts-only honesty constants — pre-registered, fixed before looking, and
# deliberately NOT tuned to flip any strategy on the real data. A single in-sample PASS is
# weak evidence; the gate demands a strict majority of traded days over a minimum sample.
MIN_TRADED_DAYS = 3          # too few trades in a window -> can't corroborate
SURVIVE_PASS_FRACTION = 0.50  # a strict majority (>50%) of traded days must survive friction

SURVIVES_RULE = (
    f"A strategy survives a window iff, in that window, it traded at least "
    f"{MIN_TRADED_DAYS} days, a strict majority (>{int(SURVIVE_PASS_FRACTION * 100)}%) of "
    "those traded days are PASS_FOR_MORE_TESTING (cleared the friction-survival gate), and "
    "no day is a fill-honesty KILL_STRATEGY. The day floor and pass-fraction are "
    "pre-registered, a-priori honesty constants — fixed before looking and never tuned to "
    "the data. carried_forward = survives the decide window AND the holdout window."
)

NO_VERDICT_NOTE = (
    "Descriptive leaderboard only — no tournament winner or validation verdict. "
    "Per-strategy, per-day verdicts stand; corroboration on the holdout is suggestive, "
    "not proof."
)


def _survives(counts: dict) -> bool:
    traded = counts["traded"]
    if traded < MIN_TRADED_DAYS:
        return False
    if counts["traded_killed_by_friction"] > 0:
        return False
    return counts["traded_survived_pass_threshold"] / traded > SURVIVE_PASS_FRACTION


def _window_summary(aggregate: dict) -> dict:
    c = aggregate["counts"]
    return {
        "days_traded": c["traded"],
        "survived_pass": c["traded_survived_pass_threshold"],
        "killed": c["traded_killed_by_friction"],
        "fill_honesty": aggregate["fill_honesty_headline"],
        "aggregate_hash": aggregate["aggregate_hash"],
        "survives": _survives(c),
    }


def build_tournament(
    *,
    symbol: str,
    config_hash: str,
    decide_window: dict,
    holdout_window: dict,
    strategies: list[str],
    results: dict[str, dict],
) -> dict:
    """Roll up per-(strategy, window) aggregates into a descriptive leaderboard.

    ``results`` maps each strategy name to ``{"decide": aggregate, "holdout": aggregate}``
    (aggregates as returned by ``runner.aggregate_range``). ``decide_window`` /
    ``holdout_window`` are ``{"start", "end"}`` dicts.
    """
    strategies = sorted(strategies)

    # Missing weekdays are per (symbol, window) — identical across strategies since ingest
    # is per (symbol, date). Take them from any strategy's aggregate for the window.
    any_strategy = strategies[0]
    decide_missing = sorted(results[any_strategy]["decide"]["missing_weekdays"])
    holdout_missing = sorted(results[any_strategy]["holdout"]["missing_weekdays"])

    leaderboard = []
    for s in strategies:
        decide = _window_summary(results[s]["decide"])
        holdout = _window_summary(results[s]["holdout"])
        leaderboard.append(
            {
                "strategy": s,
                "decide": decide,
                "holdout": holdout,
                "carried_forward": decide["survives"] and holdout["survives"],
            }
        )

    n = len(strategies)
    carried = sum(1 for row in leaderboard if row["carried_forward"])
    caveat = (
        f"{n} strategies evaluated; with {n} tries a single in-sample PASS is weak — "
        "corroboration on the holdout is required, and even that is suggestive, not proof."
    )
    disposition = (
        f"{carried} of {n} strategies carried forward (survived both windows). "
        "Descriptive only — not a verdict."
    )

    # Deterministic core — the only thing tournament_hash covers.
    core = {
        "symbol": symbol,
        "config_hash": config_hash,
        "strategies": strategies,
        "decide_window": {"start": decide_window["start"], "end": decide_window["end"]},
        "holdout_window": {"start": holdout_window["start"], "end": holdout_window["end"]},
        "results": [
            {
                "strategy": s,
                "decide_aggregate_hash": results[s]["decide"]["aggregate_hash"],
                "holdout_aggregate_hash": results[s]["holdout"]["aggregate_hash"],
            }
            for s in strategies
        ],
    }
    tournament_hash = content_hash(core)

    return {
        "data_warning": DATA_WARNING,
        "kind": "tournament",
        "symbol": symbol,
        "config_hash": config_hash,
        "strategies_evaluated": strategies,
        "n_strategies": n,
        "decide_window": {**decide_window, "missing_weekdays": decide_missing},
        "holdout_window": {**holdout_window, "missing_weekdays": holdout_missing},
        "survives_rule": SURVIVES_RULE,
        "leaderboard": leaderboard,
        "multiple_comparisons_caveat": caveat,
        "disposition": disposition,
        "note": NO_VERDICT_NOTE,
        "tournament_hash": tournament_hash,
    }


def _tournament_markdown(report: dict) -> str:
    r = report
    lines = [r["data_warning"], ""]
    lines.append(f"# same-day-trading-lab tournament — {r['symbol']}")
    lines.append("")
    dw, hw = r["decide_window"], r["holdout_window"]
    lines.append(f"- Decide window (in-sample, where we looked): **{dw['start']} → {dw['end']}**")
    lines.append(f"- Holdout window (confirmatory, unseen): **{hw['start']} → {hw['end']}**")
    lines.append(f"- Config hash: `{r['config_hash'][:16]}…`  Tournament hash: `{r['tournament_hash'][:16]}…`")
    lines.append("")
    lines.append(f"## ⚠ Multiple-comparisons caveat\n**{r['multiple_comparisons_caveat']}**\n")
    lines.append(f"_Survives rule:_ {r['survives_rule']}\n")

    lines.append("## Leaderboard")
    lines.append(
        "| strategy | decide: traded | survived_pass | KILL | fill-honesty | survives "
        "| holdout: traded | survived_pass | KILL | fill-honesty | survives | carried_forward |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in r["leaderboard"]:
        d, h = row["decide"], row["holdout"]
        lines.append(
            f"| `{row['strategy']}` | {d['days_traded']} | {d['survived_pass']} | {d['killed']} | "
            f"{d['fill_honesty']} | {d['survives']} | {h['days_traded']} | {h['survived_pass']} | "
            f"{h['killed']} | {h['fill_honesty']} | {h['survives']} | **{row['carried_forward']}** |"
        )
    lines.append("")

    if dw["missing_weekdays"]:
        lines.append("## Missing weekdays — decide (no ingest; record/ingest them, or holidays)")
        lines.append(", ".join(dw["missing_weekdays"]))
        lines.append("")
    if hw["missing_weekdays"]:
        lines.append("## Missing weekdays — holdout (no ingest; record/ingest them, or holidays)")
        lines.append(", ".join(hw["missing_weekdays"]))
        lines.append("")

    lines.append(f"_{r['disposition']}_\n")
    lines.append(f"_{r['note']}_\n")
    return "\n".join(lines) + "\n"


def write_tournament(report: dict, reports_dir: str) -> tuple[str, str]:
    os.makedirs(reports_dir, exist_ok=True)
    dw, hw = report["decide_window"], report["holdout_window"]
    stem = (
        f"{report['symbol']}_{dw['start']}_{dw['end']}__{hw['start']}_{hw['end']}_tournament"
    )
    json_path = os.path.join(reports_dir, f"{stem}.json")
    md_path = os.path.join(reports_dir, f"{stem}.md")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)
    with open(md_path, "w") as f:
        f.write(_tournament_markdown(report))
    return json_path, md_path
