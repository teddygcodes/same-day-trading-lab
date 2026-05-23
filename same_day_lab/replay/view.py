"""ReplayView — the only window a strategy gets onto the bar stream.

It holds a snapshot tuple of bars completed *so far* and exposes no method that
returns a future bar, the full store, or the clock. This is the structural half
of the no-lookahead guarantee: a strategy literally cannot reach a future bar.
"""


class ReplayView:
    def __init__(self, completed):
        self._completed = tuple(completed)

    def completed_bars(self):
        return self._completed

    def last_bar(self):
        return self._completed[-1] if self._completed else None

    def bar_count(self):
        return len(self._completed)

    def regular_market_bars(self):
        return tuple(b for b in self._completed if b.is_regular_market_hours)
