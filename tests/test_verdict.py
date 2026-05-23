import pytest

from same_day_lab.config import load_config
from same_day_lab.reports.verdict import ALLOWED_VERDICTS, decide_verdict


def cfg():
    return load_config()


def test_invalid_replay_short_circuits():
    v = decide_verdict(
        replay_valid=False, data_valid=True, signal_present=True,
        naive_pnl=1.0, pessimistic_default_pnl=1.0, pessimistic_pass_pnl=1.0, config=cfg(),
    )
    assert v == "INVALID_REPLAY"


def test_invalid_data_short_circuits():
    v = decide_verdict(
        replay_valid=True, data_valid=False, signal_present=True,
        naive_pnl=1.0, pessimistic_default_pnl=1.0, pessimistic_pass_pnl=1.0, config=cfg(),
    )
    assert v == "INVALID_DATA"


def test_no_signal_holds():
    v = decide_verdict(
        replay_valid=True, data_valid=True, signal_present=False,
        naive_pnl=None, pessimistic_default_pnl=None, pessimistic_pass_pnl=None, config=cfg(),
    )
    assert v == "HOLD_MORE_DATA"


def test_pass_requires_pessimistic_inputs():
    # naive alone can NEVER reach a verdict decision: missing pessimistic inputs raise.
    with pytest.raises(ValueError):
        decide_verdict(
            replay_valid=True, data_valid=True, signal_present=True,
            naive_pnl=0.25, pessimistic_default_pnl=None, pessimistic_pass_pnl=None, config=cfg(),
        )


def test_naive_profit_but_pessimistic_loss_is_kill():
    v = decide_verdict(
        replay_valid=True, data_valid=True, signal_present=True,
        naive_pnl=0.25, pessimistic_default_pnl=-0.05, pessimistic_pass_pnl=-0.10, config=cfg(),
    )
    assert v == "KILL_STRATEGY"


def test_pass_only_when_survives_min_friction():
    v = decide_verdict(
        replay_valid=True, data_valid=True, signal_present=True,
        naive_pnl=0.40, pessimistic_default_pnl=0.25, pessimistic_pass_pnl=0.03, config=cfg(),
    )
    assert v == "PASS_FOR_MORE_TESTING"


def test_profitable_default_but_dies_before_threshold_holds():
    # the sample-fixture case: profitable at config friction, non-positive at the
    # 5-cent pass threshold, but default still > 0 so it is not a clean KILL.
    v = decide_verdict(
        replay_valid=True, data_valid=True, signal_present=True,
        naive_pnl=0.39, pessimistic_default_pnl=0.25, pessimistic_pass_pnl=-0.30, config=cfg(),
    )
    assert v == "HOLD_MORE_DATA"


def test_naive_cannot_pass_even_when_huge():
    # enormous naive, but pessimistic never survives -> never PASS
    v = decide_verdict(
        replay_valid=True, data_valid=True, signal_present=True,
        naive_pnl=99.0, pessimistic_default_pnl=-1.0, pessimistic_pass_pnl=-1.0, config=cfg(),
    )
    assert v != "PASS_FOR_MORE_TESTING"
    assert v in ALLOWED_VERDICTS
