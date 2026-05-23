"""ReplayClock — owns the full ordered bar list privately and advances one bar
at a time. The full list is never handed out; callers only ever receive a
ReplayView of completed bars. This is the other half of the no-lookahead
guarantee (the engine cannot accidentally pass the whole series to a strategy).
"""

from .view import ReplayView


class ReplayClock:
    def __init__(self, bars):
        self._bars = tuple(bars)   # private, ordered, never exposed
        self._pos = 0              # number of completed (exposed) bars

    def advance(self):
        """Complete the next bar and return it, or None when exhausted."""
        if self._pos >= len(self._bars):
            return None
        bar = self._bars[self._pos]
        self._pos += 1
        return bar

    def current_view(self) -> ReplayView:
        """A snapshot view of bars completed so far (a copy, not a live handle)."""
        return ReplayView(self._bars[: self._pos])

    def is_done(self) -> bool:
        return self._pos >= len(self._bars)
