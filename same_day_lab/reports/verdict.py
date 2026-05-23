"""The verdict — structurally incapable of passing on naive fills alone.

``decide_verdict`` *requires* the pessimistic and friction-sweep results: passing
``None`` for them raises, so a caller that only has naive numbers cannot obtain a
PASS. PASS is granted only when pessimistic P&L survives the configured
min-friction threshold.
"""

ALLOWED_VERDICTS = (
    "PASS_FOR_MORE_TESTING",
    "HOLD_MORE_DATA",
    "KILL_STRATEGY",
    "INVALID_DATA",
    "INVALID_REPLAY",
)


def decide_verdict(
    *,
    replay_valid: bool,
    data_valid: bool,
    signal_present: bool,
    naive_pnl,
    pessimistic_default_pnl,
    pessimistic_pass_pnl,
    config: dict,
) -> str:
    if not replay_valid:
        return "INVALID_REPLAY"
    if not data_valid:
        return "INVALID_DATA"
    if not signal_present:
        return "HOLD_MORE_DATA"  # one day, no trade triggered -> inconclusive

    # Structural gate: a PASS is impossible without the pessimistic + sweep results.
    if pessimistic_default_pnl is None or pessimistic_pass_pnl is None:
        raise ValueError("verdict requires pessimistic + friction-sweep results")

    vcfg = config["verdict"]
    survives = pessimistic_pass_pnl > 0
    if survives and vcfg.get("require_pessimistic_profit_for_pass", True):
        return "PASS_FOR_MORE_TESTING"

    # Not surviving the pass threshold. A clean KILL is fantasy-profitable but loses
    # under the default pessimistic fills; otherwise hold for more data.
    if (naive_pnl is not None and naive_pnl > 0) and pessimistic_default_pnl <= 0:
        return "KILL_STRATEGY"
    return "HOLD_MORE_DATA"
