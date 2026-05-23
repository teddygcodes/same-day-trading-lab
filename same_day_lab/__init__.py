"""same-day-trading-lab — a deterministic historical-replay fill-honesty lab."""

# Verbatim provenance warning printed at the top of every report and stored as the
# ingest source_warning. Single source of truth so it cannot drift between sites.
DATA_WARNING = """\
DATA WARNING:
This run may use Alpaca free/IEX feed bars. IEX represents only a subset of US
equity market volume. Reported volume is not consolidated-tape volume. Bar
highs/lows may exclude prints from other venues. No quote/spread data is present.
Spreads and fills are modeled, not observed. Do not interpret any P&L as achievable."""
