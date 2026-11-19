"""Independent reference for the VAH / VAL / POC that kof_levels_rr.pine draws.

Same algorithm as the Pine script (volume of each 1-minute bar spread evenly over the rows its
high-low range touches; 70% value area grown from the POC two rows at a time, larger side first),
so a difference against TradingView's Session Volume Profile points at the data, the row grid or
the volume spreading, not at a different value-area rule.

Input: CSV with columns time_key (bar END time, exchange-local), open, high, low, close, volume.
Run:   python3 tradingview/ref_profile.py bars.csv --tick 0.01 --ticks-per-row 4
"""
import argparse
import math
from collections import defaultdict

import pandas as pd

VA_PCT = 0.70


def row_index(price: float, base: float, size: float) -> int:
    """Row number of a price; rows are [base + i*size, base + (i+1)*size)."""
    return math.floor((price - base) / size + 1e-9)


def profile(bars: pd.DataFrame, size: float, anchor: str):
    """Return (VAH, VAL, POC) for one session of 1-minute bars.

    anchor 'open': rows start at the session's first open (what the Pine script does).
    anchor 'grid': rows start at a multiple of the row size (price grid).
    """
    base = float(bars.iloc[0]["open"]) if anchor == "open" else 0.0
    vol = defaultdict(float)
    for r in bars.itertuples():
        lo, hi = row_index(r.low, base, size), row_index(r.high, base, size)
        share = r.volume / (hi - lo + 1)
        for i in range(lo, hi + 1):
            vol[i] += share
    lo_i, hi_i = min(vol), max(vol)
    best = max(vol.values())
    poc = min(i for i in vol if vol[i] == best)  # lowest row wins a tie, as the Pine loop does
    total = sum(vol.values())
    lo = hi = poc
    acc = vol[poc]
    while acc < total * VA_PCT and (lo > lo_i or hi < hi_i):
        up = sum(vol.get(hi + k, 0.0) for k in (1, 2)) if hi < hi_i else 0.0
        dn = sum(vol.get(lo - k, 0.0) for k in (1, 2)) if lo > lo_i else 0.0
        if hi < hi_i and up >= dn:
            hi = min(hi_i, hi + 2)
            acc += up
        else:
            lo = max(lo_i, lo - 2)
            acc += dn
    return base + (hi + 1) * size, base + lo * size, base + (poc + 0.5) * size


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tick", type=float, required=True, help="min tick, e.g. 0.25 MNQ, 0.01 QQQ")
    ap.add_argument("--ticks-per-row", type=int, default=4)
    ap.add_argument("--start", default="09:30", help="RTH start (bar-end labels: first bar ends 09:31)")
    ap.add_argument("--end", default="16:00")
    a = ap.parse_args()
    size = a.tick * a.ticks_per_row
    df = pd.read_csv(a.csv)
    df["t"] = pd.to_datetime(df["time_key"])
    # bars are labelled by end time: bar 09:31 covers 09:30-09:31
    df["start"] = df["t"] - pd.Timedelta(minutes=1)
    hm = df["start"].dt.strftime("%H:%M")
    df = df[(hm >= a.start) & (hm < a.end)]
    print(f"row size {size:g}; columns: VAH VAL POC for anchor=open | anchor=grid")
    for day, g in df.groupby(df["start"].dt.date):
        o = profile(g, size, "open")
        gr = profile(g, size, "grid")
        print(f"{day}  open: {o[0]:.2f} {o[1]:.2f} {o[2]:.3f} | grid: {gr[0]:.2f} {gr[1]:.2f} {gr[2]:.3f}  ({len(g)} bars)")


if __name__ == "__main__":
    main()
