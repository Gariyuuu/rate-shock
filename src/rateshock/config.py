"""Central configuration: paths, tickers, event windows, and analysis constants.

Every magic number used in the study lives here so the report and the code
cannot drift apart.
"""
from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
RESULTS = ROOT / "results"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"
DOCS = ROOT / "docs"

for _p in (RAW, INTERIM, PROCESSED, TABLES, FIGURES, DOCS):
    _p.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Assets
# --------------------------------------------------------------------------
# SPDR Select Sector ETFs. XLRE was spun out of XLK/XLF in Oct 2015 and so has
# a materially shorter history than the other nine -- handled explicitly.
SECTORS = {
    "XLF": "Financials",
    "XLK": "Technology",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLI": "Industrials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLB": "Materials",
}
BENCHMARKS = {"SPY": "S&P 500 ETF", "QQQ": "Nasdaq 100 ETF"}
CROSS_ASSETS = {
    "IEF": "7-10y Treasuries",
    "TLT": "20y+ Treasuries",
    "GLD": "Gold",
}
# Kept deliberately separate: BTC trades 24/7, so its "daily" bar is not
# comparable to a 09:30-16:00 ET equity bar around a 14:00 ET announcement.
OPTIONAL_ASSETS = {"BTC-USD": "Bitcoin (24/7, exploratory only)"}

ALL_EQUITY = list(SECTORS) + list(BENCHMARKS)
ALL_TICKERS = ALL_EQUITY + list(CROSS_ASSETS)

# --------------------------------------------------------------------------
# Event windows, in TRADING days relative to the announcement day (day 0).
# --------------------------------------------------------------------------
DAILY_WINDOWS = {
    "m5_p5": (-5, 5),
    "m1_p1": (-1, 1),
    "d0_p1": (0, 1),
    "d0_p5": (0, 5),
}
PRIMARY_WINDOW = "d0_p1"   # announcement day + 1, the pre-registered baseline
CAR_WINDOW = (-5, 5)       # for event-time CAR curves

# --------------------------------------------------------------------------
# Surprise measure
# --------------------------------------------------------------------------
# Bauer & Swanson (2023) MPS is reported in PERCENTAGE POINTS (same units as the
# underlying ED4/SFR5 futures rate change). Multiply by 100 to get basis points.
MPS_TO_BPS = 100.0
# Betas are reported per this many bp of surprise so they read as "% move per
# 25bp tighter-than-expected surprise".
BETA_SCALE_BPS = 25.0

# SIGN CONVENTION (single source of truth, asserted in tests):
#   surprise_bps > 0  <=>  market rates repriced UP in the 30-minute window
#                     <=>  policy was TIGHTER than expected (hawkish surprise)
SURPRISE_SIGN_CONVENTION = (
    "Positive surprise = tighter-than-expected policy (futures-implied rates "
    "rose in the 30-minute window around the announcement)."
)

# --------------------------------------------------------------------------
# Inflation regime
# --------------------------------------------------------------------------
# Baseline: headline CPI YoY at or above 3% counts as "high inflation".
# Sensitivity thresholds are re-estimated in the robustness battery.
INFLATION_THRESHOLD = 3.0
INFLATION_THRESHOLD_ALTS = [2.0, 2.5, 3.5, 4.0]
# Alternative, threshold-free definition used as a robustness check.
INFLATION_REGIME_ALT_RULE = "median"

# --------------------------------------------------------------------------
# Sample
# --------------------------------------------------------------------------
# Sector ETFs began trading 1998-12-16; the Bauer-Swanson update ends 2023-12-13.
SAMPLE_START = "1998-12-22"
SAMPLE_END = "2023-12-31"

COVID_START = "2020-02-01"
COVID_END = "2020-12-31"
MARCH_2020 = "2020-03"

RANDOM_SEED = 20240101
