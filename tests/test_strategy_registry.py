import pytest

from same_day_lab.config import load_config
from same_day_lab.strategy import DEFAULT_STRATEGY, STRATEGIES, get_strategy
from same_day_lab.strategy.orb_long import OrbLongStrategy
from same_day_lab.strategy.or_fade_long import OrFadeLongStrategy
from same_day_lab.strategy.vwap_reclaim_long import VwapReclaimLongStrategy


def test_registry_holds_exactly_the_three_strategies():
    assert set(STRATEGIES) == {"orb_long_5m", "vwap_reclaim_long", "or_fade_long"}
    assert DEFAULT_STRATEGY == "orb_long_5m"


def test_get_strategy_resolves_each_class():
    assert get_strategy("orb_long_5m") is OrbLongStrategy
    assert get_strategy("vwap_reclaim_long") is VwapReclaimLongStrategy
    assert get_strategy("or_fade_long") is OrFadeLongStrategy


def test_get_strategy_raises_clearly_on_unknown_name():
    with pytest.raises(ValueError) as exc:
        get_strategy("orb_long_10m")
    msg = str(exc.value)
    assert "orb_long_10m" in msg
    assert "or_fade_long" in msg  # the clear message lists the known names


def test_from_config_builds_usable_instances():
    cfg = load_config()
    for name in STRATEGIES:
        strat = get_strategy(name).from_config(cfg)
        assert hasattr(strat, "on_bar")
        assert hasattr(strat, "strategy_context")
        assert strat.strategy_context() is None  # nothing seen yet
