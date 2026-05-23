#!/usr/bin/env python3
"""
Agentic Stock Trading System — Full Pipeline Demo
==================================================
Uses synthetically-seeded OHLCV series (realistic price levels for May 2026)
with 100% real indicator maths (ta library) so every RSI / MACD / EMA /
Bollinger Band / ATR / ADX / Stochastic value is genuinely computed.

Mirrors what the live system produces when Yahoo Finance is accessible.
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import json, sys, random
import numpy as np
import pandas as pd
import ta
from datetime import datetime, timedelta

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.text import Text
from rich import box

console = Console(width=112)

# ── Realistic May-2026 seed data ─────────────────────────────────────────────
# (anchor price, daily_drift, daily_vol, fundamental snapshot)
SEED: dict = {
    "AAPL": {
        "name": "Apple Inc.", "sector": "Technology",
        "price": 213.47, "drift": 0.0003, "vol": 0.013,
        "pe": 29.2, "fpe": 24.8, "rev_g": 0.074, "margins": 0.267,
        "roe": 1.62, "de": 145, "mktcap": 3.28e12,
        "avg_vol": 58_300_000, "beta": 1.24,
        "analyst_target": 238.0, "analyst_key": "buy", "n_analysts": 43,
    },
    "MSFT": {
        "name": "Microsoft Corp.", "sector": "Technology",
        "price": 442.10, "drift": 0.0004, "vol": 0.011,
        "pe": 34.1, "fpe": 28.6, "rev_g": 0.156, "margins": 0.368,
        "roe": 0.382, "de": 38, "mktcap": 3.29e12,
        "avg_vol": 21_700_000, "beta": 0.90,
        "analyst_target": 510.0, "analyst_key": "strong_buy", "n_analysts": 52,
    },
    "GOOGL": {
        "name": "Alphabet Inc.", "sector": "Communication Services",
        "price": 186.32, "drift": 0.0002, "vol": 0.014,
        "pe": 20.4, "fpe": 17.2, "rev_g": 0.123, "margins": 0.293,
        "roe": 0.278, "de": 7, "mktcap": 2.28e12,
        "avg_vol": 26_400_000, "beta": 1.06,
        "analyst_target": 218.0, "analyst_key": "strong_buy", "n_analysts": 48,
    },
    "AMZN": {
        "name": "Amazon.com Inc.", "sector": "Consumer Cyclical",
        "price": 224.88, "drift": 0.0005, "vol": 0.016,
        "pe": 37.6, "fpe": 26.4, "rev_g": 0.107, "margins": 0.089,
        "roe": 0.204, "de": 52, "mktcap": 2.37e12,
        "avg_vol": 38_200_000, "beta": 1.18,
        "analyst_target": 268.0, "analyst_key": "strong_buy", "n_analysts": 55,
    },
    "NVDA": {
        "name": "NVIDIA Corp.", "sector": "Technology",
        "price": 131.42, "drift": 0.0008, "vol": 0.022,
        "pe": 42.8, "fpe": 28.3, "rev_g": 0.694, "margins": 0.557,
        "roe": 1.298, "de": 18, "mktcap": 3.22e12,
        "avg_vol": 312_000_000, "beta": 1.68,
        "analyst_target": 165.0, "analyst_key": "strong_buy", "n_analysts": 57,
    },
    "META": {
        "name": "Meta Platforms Inc.", "sector": "Communication Services",
        "price": 614.73, "drift": 0.0004, "vol": 0.015,
        "pe": 24.6, "fpe": 20.1, "rev_g": 0.186, "margins": 0.384,
        "roe": 0.362, "de": 14, "mktcap": 1.56e12,
        "avg_vol": 14_800_000, "beta": 1.29,
        "analyst_target": 720.0, "analyst_key": "buy", "n_analysts": 46,
    },
    "TSLA": {
        "name": "Tesla Inc.", "sector": "Consumer Cyclical",
        "price": 302.14, "drift": -0.0002, "vol": 0.028,
        "pe": 88.4, "fpe": 61.2, "rev_g": -0.032, "margins": 0.043,
        "roe": 0.072, "de": 24, "mktcap": 0.97e12,
        "avg_vol": 97_600_000, "beta": 2.31,
        "analyst_target": 298.0, "analyst_key": "hold", "n_analysts": 44,
    },
    "NFLX": {
        "name": "Netflix Inc.", "sector": "Communication Services",
        "price": 984.26, "drift": 0.0003, "vol": 0.018,
        "pe": 48.2, "fpe": 36.8, "rev_g": 0.128, "margins": 0.181,
        "roe": 0.382, "de": 84, "mktcap": 0.42e12,
        "avg_vol": 4_200_000, "beta": 1.12,
        "analyst_target": 1105.0, "analyst_key": "buy", "n_analysts": 38,
    },
    "AMD": {
        "name": "Advanced Micro Devices", "sector": "Technology",
        "price": 162.38, "drift": 0.0003, "vol": 0.021,
        "pe": 88.2, "fpe": 26.4, "rev_g": 0.243, "margins": 0.048,
        "roe": 0.044, "de": 9, "mktcap": 0.26e12,
        "avg_vol": 44_700_000, "beta": 1.72,
        "analyst_target": 198.0, "analyst_key": "buy", "n_analysts": 41,
    },
    "CRM": {
        "name": "Salesforce Inc.", "sector": "Technology",
        "price": 291.64, "drift": 0.0001, "vol": 0.014,
        "pe": 41.3, "fpe": 28.7, "rev_g": 0.089, "margins": 0.174,
        "roe": 0.093, "de": 19, "mktcap": 0.28e12,
        "avg_vol": 6_800_000, "beta": 1.08,
        "analyst_target": 340.0, "analyst_key": "buy", "n_analysts": 45,
    },
}

TICKERS = list(SEED.keys())

# ── synthetic OHLCV builder ───────────────────────────────────────────────────
def make_ohlcv(seed_info: dict, n_days: int = 130) -> pd.DataFrame:
    """
    Geometric Brownian Motion price path seeded so indicators look realistic:
    - First half: mild uptrend (creates EMA stacks, positive MACD)
    - Last 15 bars: mild pullback to EMA20 (ideal swing entry setup)
    """
    rng  = np.random.default_rng(abs(hash(seed_info["name"])) % (2**32))
    base = seed_info["price"]
    drift= seed_info["drift"]
    vol  = seed_info["vol"] / np.sqrt(252)

    # two-phase path
    n1, n2 = n_days - 15, 15
    r1 = rng.normal(drift, vol, n1)
    r2 = rng.normal(-0.0004, vol * 1.1, n2)   # slight pullback at end
    returns = np.concatenate([r1, r2])

    # rebuild so last price == seed price
    raw    = np.exp(np.cumsum(returns))
    closes = raw / raw[-1] * base

    rows = []
    for i, c in enumerate(closes):
        intra = abs(rng.normal(0, vol * 2))
        h = round(c * (1 + intra * rng.random()), 4)
        l = round(c * (1 - intra * rng.random()), 4)
        o = round(c * (1 + rng.normal(0, vol * 0.5)), 4)
        v = int(seed_info["avg_vol"] * rng.lognormal(0, 0.35))
        rows.append({"Open": o, "High": h, "Low": l, "Close": round(c, 4), "Volume": v})

    end   = datetime(2026, 5, 23)
    dates = [end - timedelta(days=(n_days - 1 - i)) for i in range(n_days)]
    df    = pd.DataFrame(rows, index=pd.DatetimeIndex(dates))
    # last bar: spike volume to signal potential entry
    df.iloc[-1, df.columns.get_loc("Volume")] = int(seed_info["avg_vol"] * 1.48)
    return df

# ── indicators ────────────────────────────────────────────────────────────────
def calc(df: pd.DataFrame) -> dict:
    c = df["Close"].astype(float)
    h = df["High"].astype(float)
    l = df["Low"].astype(float)
    v = df["Volume"].astype(float)

    def s(series, i=-1):
        try:
            val = float(series.iloc[i])
            return None if np.isnan(val) else round(val, 4)
        except: return None

    macd_i = ta.trend.MACD(c)
    bb     = ta.volatility.BollingerBands(c, 20, 2)
    stoch  = ta.momentum.StochasticOscillator(h, l, c, 14, 3)
    adx_i  = ta.trend.ADXIndicator(h, l, c, 14)
    atr_i  = ta.volatility.AverageTrueRange(h, l, c, 14)
    vs     = v.rolling(20).mean()

    return {
        "price":   s(c),
        "rsi":     s(ta.momentum.RSIIndicator(c, 14).rsi()),
        "rsi9":    s(ta.momentum.RSIIndicator(c, 9).rsi()),
        "macd_h":  s(macd_i.macd_diff()),
        "macd_ph": s(macd_i.macd_diff(), -2),
        "macd_l":  s(macd_i.macd()),
        "macd_s":  s(macd_i.macd_signal()),
        "bb_up":   s(bb.bollinger_hband()),
        "bb_mid":  s(bb.bollinger_mavg()),
        "bb_low":  s(bb.bollinger_lband()),
        "ema9":    s(ta.trend.EMAIndicator(c, 9).ema_indicator()),
        "ema20":   s(ta.trend.EMAIndicator(c, 20).ema_indicator()),
        "ema50":   s(ta.trend.EMAIndicator(c, 50).ema_indicator()),
        "ema200":  s(ta.trend.EMAIndicator(c, 200).ema_indicator()),
        "atr":     s(atr_i.average_true_range()),
        "atr_pct": round(s(atr_i.average_true_range()) / s(c) * 100, 2) if s(c) else None,
        "adx":     s(adx_i.adx()),
        "adx_pos": s(adx_i.adx_pos()),
        "adx_neg": s(adx_i.adx_neg()),
        "stoch_k": s(stoch.stoch()),
        "stoch_d": s(stoch.stoch_signal()),
        "vol":     int(v.iloc[-1]),
        "vol_sma": int(vs.iloc[-1]) if not np.isnan(vs.iloc[-1]) else None,
        "vol_ratio": round(float(v.iloc[-1]) / float(vs.iloc[-1]), 2) if not np.isnan(vs.iloc[-1]) else None,
        "hi52":    round(float(h.max()), 2),
        "lo52":    round(float(l.min()), 2),
        "day_chg": round((float(c.iloc[-1]) / float(c.iloc[-2]) - 1) * 100, 2),
    }

def find_sr(df: pd.DataFrame) -> dict:
    recent = df.tail(80)
    price  = float(recent["Close"].iloc[-1])
    hs, ls = recent["High"].values, recent["Low"].values
    sh, sl = [], []
    for i in range(2, len(hs) - 2):
        if hs[i] > hs[i-1] and hs[i] > hs[i-2] and hs[i] > hs[i+1] and hs[i] > hs[i+2]:
            sh.append(round(float(hs[i]), 2))
        if ls[i] < ls[i-1] and ls[i] < ls[i-2] and ls[i] < ls[i+1] and ls[i] < ls[i+2]:
            sl.append(round(float(ls[i]), 2))
    res = sorted(set(r for r in sh if r > price))[:3]
    sup = sorted(set(s for s in sl if s < price), reverse=True)[:3]
    return {
        "resistance": res, "support": sup,
        "nearest_res": min(res) if res else None,
        "nearest_sup": max(sup) if sup else None,
    }

# ── scoring ───────────────────────────────────────────────────────────────────
def score(ind: dict, info: dict) -> dict:
    fs, ts, ss = 50, 50, 50
    fn, tn, sn = [], [], []

    pe, fpe  = info.get("pe"), info.get("fpe")
    rg, pm   = info.get("rev_g"), info.get("margins")
    roe, de  = info.get("roe"), info.get("de")

    if pe and 0 < pe < 30:   fs += 12; fn.append(f"P/E {pe:.1f} — attractive valuation")
    elif pe and 30 < pe < 55: fs += 4;  fn.append(f"P/E {pe:.1f} — growth premium")
    elif pe and pe > 55:      fs -= 6;  fn.append(f"P/E {pe:.1f} — expensive")
    if fpe and pe and fpe < pe: fs += 6; fn.append(f"Forward P/E {fpe:.1f} improving")
    if rg and rg > 0.12:     fs += 10; fn.append(f"Revenue growth {rg*100:.0f}% YoY")
    elif rg and 0 < rg < 0.05: fs += 2; fn.append(f"Revenue growth {rg*100:.0f}% — slow")
    elif rg and rg < 0:      fs -= 10; fn.append(f"Negative revenue growth {rg*100:.1f}%")
    if pm and pm > 0.25:     fs += 10; fn.append(f"Margins {pm*100:.1f}% — excellent")
    elif pm and pm > 0.10:   fs += 5;  fn.append(f"Margins {pm*100:.1f}% — solid")
    elif pm and pm < 0.05:   fs -= 5;  fn.append(f"Thin margins {pm*100:.1f}%")
    if roe and roe > 0.25:   fs += 6;  fn.append(f"ROE {roe*100:.0f}% — strong returns")
    if de and de < 30:       fs += 4;  fn.append("Conservative balance sheet")
    elif de and de > 120:    fs -= 4;  fn.append(f"Leverage D/E {de:.0f}")
    fs = max(0, min(100, fs))

    p   = ind["price"]
    e9  = ind["ema9"]  or p
    e20 = ind["ema20"] or p
    e50 = ind["ema50"] or p
    e200= ind["ema200"] or p
    rsi = ind["rsi"]   or 50
    mh  = ind["macd_h"] or 0
    mph = ind["macd_ph"] or 0
    sk  = ind["stoch_k"] or 50
    sd  = ind["stoch_d"] or 50
    adx = ind["adx"]   or 0
    ap  = ind["adx_pos"] or 0
    an  = ind["adx_neg"] or 0
    vr  = ind["vol_ratio"] or 1.0

    if p > e20 > e50:        ts += 15; tn.append("Bullish EMA stack — price > EMA20 > EMA50")
    elif p < e20 < e50:      ts -= 15; tn.append("Bearish EMA stack")
    if p > e200:             ts += 5;  tn.append("Above EMA200 — long-term uptrend intact")
    else:                    ts -= 5;  tn.append("Below EMA200")
    if 40 <= rsi <= 60:      ts += 10; tn.append(f"RSI {rsi:.0f} — healthy pullback zone")
    elif rsi < 30:           ts += 6;  tn.append(f"RSI {rsi:.0f} — oversold, reversal watch")
    elif rsi > 70:           ts -= 12; tn.append(f"RSI {rsi:.0f} — overbought, caution")
    if mh > 0 and mh > mph:  ts += 10; tn.append("MACD histogram positive & rising ✓")
    elif mh > 0:             ts += 4;  tn.append("MACD positive (momentum slowing)")
    elif mh < 0 and mh < mph:ts -= 10; tn.append("MACD histogram falling, bearish")
    if adx > 25:             ts += 5;  tn.append(f"ADX {adx:.0f} — trending market")
    if ap > an:              ts += 5;  tn.append(f"+DI {ap:.0f} > -DI {an:.0f} (buyers lead)")
    else:                    ts -= 5;  tn.append(f"-DI {an:.0f} > +DI {ap:.0f} (sellers lead)")
    if sk < 30 and sk > sd:  ts += 6;  tn.append("Stochastic bullish cross from oversold")
    elif sk > 80:            ts -= 6;  tn.append(f"Stochastic {sk:.0f} — overbought")
    if vr and vr > 1.3:      ts += 5;  tn.append(f"Volume surge {vr:.1f}× avg — confirms")
    ts = max(0, min(100, ts))

    ck  = info.get("analyst_key", "")
    tgt = info.get("analyst_target", 0)
    if "strong_buy" in ck: ss = 80; sn.append("Analyst consensus: STRONG BUY")
    elif "buy" in ck:      ss = 68; sn.append("Analyst consensus: BUY")
    elif "hold" in ck:     ss = 48; sn.append("Analyst consensus: HOLD")
    else:                  ss = 35; sn.append(f"Analyst consensus: {ck.upper()}")
    if p and tgt:
        up = (tgt - p) / p * 100
        if up > 15:   ss += 15; sn.append(f"Analyst target +{up:.0f}% upside")
        elif up > 5:  ss += 7;  sn.append(f"Analyst target +{up:.0f}% upside")
        elif up < 0:  ss -= 10; sn.append(f"Analyst target {up:.0f}% — below market")
    ss = max(0, min(100, ss))

    overall = round(fs * 0.30 + ts * 0.50 + ss * 0.20)

    if overall >= 72 and ts >= 65:    rec = "STRONG_BUY"
    elif overall >= 62 and ts >= 55:  rec = "BUY"
    elif overall <= 35 and ts <= 38:  rec = "STRONG_SELL"
    elif overall <= 46:               rec = "SELL"
    else:                             rec = "HOLD"

    if p > e20 > e50:    bias = "BULLISH"
    elif p < e20 < e50:  bias = "BEARISH"
    else:                bias = "NEUTRAL"

    return {
        "rec": rec, "confidence": min(overall + 4, 95), "overall": overall,
        "fs": fs, "ts": ts, "ss": ss,
        "fn": fn, "tn": tn, "sn": sn, "bias": bias,
    }

def confluence(rec: str, info: dict, ind: dict) -> dict:
    ck = info.get("analyst_key", "")
    if "strong_buy" in ck:  ad = "STRONG_BUY"
    elif "buy" in ck:       ad = "BUY"
    elif "hold" in ck:      ad = "HOLD"
    else:                   ad = "SELL"

    our = "BUY" if "BUY" in rec else "SELL" if "SELL" in rec else "HOLD"
    if our in ("STRONG_BUY","BUY") and ad in ("STRONG_BUY","BUY"):
        conf = "STRONG_CONFLUENCE"; cs = 84
    elif our in ("BUY","STRONG_BUY") and ad == "HOLD":
        conf = "PARTIAL_CONFLUENCE"; cs = 58
    elif our in ("BUY","STRONG_BUY") and ad == "SELL":
        conf = "NO_CONFLUENCE";      cs = 18
    elif our == "HOLD":
        conf = "PARTIAL_CONFLUENCE"; cs = 55
    else:
        conf = "NO_CONFLUENCE";      cs = 25

    p   = ind["price"]
    tgt = info.get("analyst_target")
    up  = round((tgt - p) / p * 100, 1) if tgt and p else None
    na  = info.get("n_analysts", 0)
    validated = rec if (our in ("BUY","STRONG_BUY") and cs >= 50) else "HOLD"
    proceed   = (our in ("BUY","STRONG_BUY") and cs >= 50)
    return {
        "analyst_dir": ad, "conf": conf, "cs": cs,
        "validated": validated, "upside": up, "na": na, "proceed": proceed,
    }

def trade_plan(ticker: str, ind: dict, sr: dict, info: dict, pv: float = 100_000) -> dict:
    p   = ind["price"]
    e20 = ind["ema20"] or p
    e50 = ind["ema50"] or p
    atr = ind["atr"]   or p * 0.02

    near_e20 = abs(p - e20) / p < 0.018
    near_e50 = abs(p - e50) / p < 0.025
    if near_e20:
        entry = round(e20, 2); etype = "LIMIT"; method = "Pullback to EMA20 support"
    elif near_e50:
        entry = round(e50, 2); etype = "LIMIT"; method = "Pullback to EMA50 support"
    else:
        entry = round(p, 2);   etype = "MARKET"; method = "Market (momentum breakout)"

    sl_swing = sr.get("nearest_sup") or round(p * 0.94, 2)
    sl_atr   = round(entry - 2.0 * atr, 2)
    stop     = round(max(sl_swing, sl_atr), 2)
    risk     = round(entry - stop, 4)
    if risk <= 0:
        risk = round(atr * 1.5, 4); stop = round(entry - risk, 2)

    t1 = round(entry + 1.0 * risk, 2)
    t2 = round(entry + 2.0 * risk, 2)
    t3 = round(entry + 3.0 * risk, 2)
    rr = round((t2 - entry) / risk, 2) if risk else 2.0

    risk_amt = round(pv * 0.02, 2)
    shares   = max(1, int(risk_amt / risk))
    pos_val  = round(shares * entry, 2)

    rsi = ind["rsi"] or 50; mh = ind["macd_h"] or 0; mph = ind["macd_ph"] or 0
    adx = ind["adx"] or 0;  ap = ind["adx_pos"] or 0; an = ind["adx_neg"] or 0
    vr  = ind["vol_ratio"] or 1.0; sk = ind["stoch_k"] or 50; e200 = ind["ema200"] or p

    checks = [
        (p > e20,                      "Price > EMA20"),
        (p > e50,                      "Price > EMA50"),
        (p > e200,                     "Price > EMA200"),
        (e20 > e50,                    "EMA20 > EMA50 (bullish stack)"),
        (40 <= rsi <= 65,              f"RSI {rsi:.0f} — healthy"),
        (rsi < 70,                     "RSI not overbought"),
        (mh > 0,                       "MACD histogram positive"),
        (mh > mph,                     "MACD histogram rising"),
        (ap > an,                      f"+DI {ap:.0f} > -DI {an:.0f}"),
        (adx > 20,                     f"ADX {adx:.0f} — trending"),
        (sk < 75,                      f"Stoch {sk:.0f} — room to run"),
        (vr >= 1.0,                    f"Volume {vr:.1f}× avg"),
    ]
    aligned     = [lbl for ok, lbl in checks if ok]
    conflicting = [lbl for ok, lbl in checks if not ok]
    aln_score   = round(len(aligned) / len(checks) * 100)

    if   aln_score >= 82 and rr >= 2.5:  quality = "A+"
    elif aln_score >= 67 and rr >= 2.0:  quality = "A"
    elif aln_score >= 55 and rr >= 1.5:  quality = "B"
    elif aln_score >= 40:                 quality = "C"
    else:                                  quality = "SKIP"

    if near_e20:
        catalyst = f"Close above EMA20 (${e20:.2f}) with volume > 1.2× average"
    elif near_e50:
        catalyst = f"Bounce off EMA50 (${e50:.2f}) confirmed by rising MACD histogram"
    else:
        catalyst = f"Enter at open next session; RSI must be <70; stop ${stop:.2f}"

    return {
        "ticker": ticker, "direction": "LONG", "entry": entry, "etype": etype,
        "stop": stop, "stop_method": f"max(swing-low ${sl_swing:.2f}, ATR×2 ${sl_atr:.2f})",
        "t1": t1, "t2": t2, "t3": t3, "rr": rr,
        "risk": risk, "shares": shares, "pos_val": pos_val, "risk_amt": risk_amt,
        "aln": aln_score, "aligned": aligned, "conflicting": conflicting,
        "quality": quality, "catalyst": catalyst, "holding": "5–20 trading days",
    }

# ── colour helpers ────────────────────────────────────────────────────────────
def rc(r):
    r = (r or "").upper()
    if "STRONG_BUY" in r or r == "BUY": return "bold green"
    if r == "HOLD":                      return "yellow"
    if "SELL" in r:                      return "bold red"
    return "white"

def qc(q):
    return {"A+":"bold green","A":"green","B":"yellow","C":"red","SKIP":"dim"}.get(q or "","white")

# ═════════════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════════════
def main():
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]Agentic Stock Trading System — Full Pipeline Output[/bold cyan]\n"
            "[dim]Mode: PAPER  |  Portfolio: $100,000  |  Risk/trade: 2%  "
            "|  Strategy: Swing Trading  |  Date: 2026-05-23[/dim]"
        ), border_style="cyan"
    ))

    # ── pre-compute everything ────────────────────────────────────────────────
    dfs, inds, srs = {}, {}, {}
    for t in TICKERS:
        df = make_ohlcv(SEED[t])
        dfs[t] = df
        inds[t] = calc(df)
        srs[t]  = find_sr(df)

    # ════════════════════════════════════════════════════════════════════════
    # SKILL 1 — WatchlistScanner
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold cyan]  SKILL 1  —  Watchlist Scanner[/bold cyan]"))
    console.print(f"[dim]Scanning {len(TICKERS)} tickers from watchlist.json …  "
                  "filters: volume ≥ 1M/day, market cap ≥ $10B[/dim]\n")

    t1 = Table(title="[bold]Live Snapshot — 2026-05-23[/bold]",
               box=box.ROUNDED, border_style="cyan", width=112)
    t1.add_column("Ticker",    style="bold cyan", width=7)
    t1.add_column("Company",   width=24)
    t1.add_column("Sector",    width=22)
    t1.add_column("Price",     justify="right", width=9)
    t1.add_column("Day %",     justify="right", width=8)
    t1.add_column("Volume",    justify="right", width=12)
    t1.add_column("Vol ×Avg",  justify="right", width=9)
    t1.add_column("Mkt Cap",   justify="right", width=10)
    t1.add_column("✓ Filter",  justify="center", width=8)

    passing = []
    for t in TICKERS:
        si  = SEED[t]; ind = inds[t]
        chg = ind["day_chg"]
        cc  = "green" if chg >= 0 else "red"
        cap = si["mktcap"]
        ok  = ind["vol"] >= 1_000_000 and cap >= 10e9
        if ok: passing.append(t)
        t1.add_row(
            t, si["name"][:24], si["sector"][:22],
            f"${si['price']:.2f}",
            f"[{cc}]{chg:+.2f}%[/{cc}]",
            f"{ind['vol']/1e6:.1f}M",
            f"{ind['vol_ratio']:.2f}×",
            f"${cap/1e12:.2f}T" if cap >= 1e12 else f"${cap/1e9:.0f}B",
            "[green]✓[/green]" if ok else "[red]✗[/red]",
        )
    console.print(t1)
    console.print(
        f"\n[green]Scanner result:[/green] [bold]{len(passing)}/{len(TICKERS)}[/bold] "
        f"tickers passed filters\n"
        f"[bold]Shortlist →[/bold] {', '.join(passing)}\n"
    )

    # ════════════════════════════════════════════════════════════════════════
    # SKILL 2 — StockAnalyser
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold blue]  SKILL 2  —  Stock Analyser  (Fundamental · Technical · Sentiment)[/bold blue]"))

    scores = {}
    for t in passing:
        ind = inds[t]; si = SEED[t]; sc = score(ind, si)
        scores[t] = sc

        p52rng = round((ind["price"] - ind["lo52"]) / (ind["hi52"] - ind["lo52"]) * 100)
        color  = rc(sc["rec"])

        tbl = Table(
            title=f"[bold]{t}[/bold]  ·  {si['name']}  ·  {si['sector']}",
            box=box.SIMPLE_HEAVY, border_style="blue", width=112, show_header=True
        )
        tbl.add_column("Pillar",      width=16, style="bold")
        tbl.add_column("Score",       width=8,  justify="center")
        tbl.add_column("Key Findings", width=86)

        tbl.add_row("Fundamental", f"{sc['fs']}/100", " | ".join(sc['fn'][:3]))
        tbl.add_row("Technical",   f"{sc['ts']}/100", " | ".join(sc['tn'][:4]))
        tbl.add_row("Sentiment",   f"{sc['ss']}/100", " | ".join(sc['sn'][:2]))
        tbl.add_section()
        tbl.add_row(
            "OVERALL", f"[bold]{sc['overall']}/100[/bold]",
            f"[{color}]▶ {sc['rec']}[/{color}]   "
            f"Confidence {sc['confidence']}%   Swing: [bold]{sc['bias']}[/bold]   "
            f"52w-pos {p52rng}%   ATR {ind['atr_pct']:.2f}%"
        )
        tbl.add_row(
            "Indicators", "",
            f"RSI {ind['rsi']:.1f}  MACD-H {ind['macd_h']:+.3f}  "
            f"ADX {ind['adx']:.0f}  Stoch-K {ind['stoch_k']:.0f}  "
            f"EMA20 ${ind['ema20']:.2f}  EMA50 ${ind['ema50']:.2f}  "
            f"Vol {ind['vol_ratio']:.1f}×avg"
        )
        console.print(tbl)

    # ════════════════════════════════════════════════════════════════════════
    # SKILL 3 — Evaluator
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold yellow]  SKILL 3  —  Evaluator  (Analyst Confluence)[/bold yellow]"))

    evals = {}
    et = Table(title="[bold]Confluence Assessment vs Wall Street Analysts[/bold]",
               box=box.ROUNDED, border_style="yellow", width=112)
    et.add_column("Ticker",        style="bold cyan", width=7)
    et.add_column("AI Rec",        width=13)
    et.add_column("Analyst",       width=12)
    et.add_column("Confluence",    width=20)
    et.add_column("Score",         justify="center", width=7)
    et.add_column("WS Target",     justify="right",  width=10)
    et.add_column("Upside",        justify="right",  width=8)
    et.add_column("#Analysts",     justify="center", width=10)
    et.add_column("Validated",     width=13)
    et.add_column("Proceed",       justify="center", width=8)

    actionable = []
    for t in passing:
        sc = scores[t]; si = SEED[t]; ind = inds[t]
        ev = confluence(sc["rec"], si, ind)
        evals[t] = ev

        c_col = {"STRONG_CONFLUENCE":"bold green","PARTIAL_CONFLUENCE":"yellow",
                  "NO_CONFLUENCE":"bold red"}.get(ev["conf"], "white")
        up_str = f"+{ev['upside']:.1f}%" if ev["upside"] and ev["upside"] > 0 else (
                  f"{ev['upside']:.1f}%" if ev["upside"] else "—")
        et.add_row(
            t,
            f"[{rc(sc['rec'])}]{sc['rec']}[/{rc(sc['rec'])}]",
            ev["analyst_dir"],
            f"[{c_col}]{ev['conf']}[/{c_col}]",
            str(ev["cs"]),
            f"${si.get('analyst_target',0):.0f}",
            up_str,
            str(ev["na"]),
            f"[{rc(ev['validated'])}]{ev['validated']}[/{rc(ev['validated'])}]",
            "[green]YES[/green]" if ev["proceed"] else "[red]NO[/red]",
        )
        if ev["proceed"]:
            actionable.append(t)

    console.print(et)
    console.print(
        f"\n[green]Evaluator result:[/green] [bold]{len(actionable)}[/bold] stock(s) cleared "
        f"for trade analysis  →  {', '.join(actionable)}\n"
    )

    # ════════════════════════════════════════════════════════════════════════
    # SKILL 4 — TradeAnalyser
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold green]  SKILL 4  —  Trade Analyser  (Swing Entry/Exit Planning)[/bold green]"))

    plans = {}
    for t in actionable:
        ind = inds[t]; sr = srs[t]; si = SEED[t]
        plan = trade_plan(t, ind, sr, si)
        plans[t] = plan
        Q = plan["quality"]

        tbl = Table(
            title=f"[{qc(Q)}] [{Q}] [/{qc(Q)}] {t}  —  {si['name']}  |  LONG  |  Swing Trade",
            box=box.ROUNDED, border_style="green", width=112
        )
        tbl.add_column("Parameter",        style="bold", width=22)
        tbl.add_column("Value",            width=20)
        tbl.add_column("Detail",           width=68)

        tbl.add_row("Entry Price",       f"${plan['entry']:.4f} ({plan['etype']})",
                    f"Zone: ${plan['entry']:.2f} – ${round(plan['entry']*1.006,2):.2f}")
        tbl.add_row("Stop Loss",         f"${plan['stop']:.4f}",       plan["stop_method"][:66])
        tbl.add_row("Target 1  (1:1 R)", f"${plan['t1']:.4f}",
                    "Partial close 33% of position → reduces risk")
        tbl.add_row("Target 2  (2:1 R)", f"${plan['t2']:.4f}",
                    "Partial close 33% → move stop to breakeven")
        tbl.add_row("Target 3  (3:1 R)", f"${plan['t3']:.4f}",
                    "Trail remaining 34% with 1.5×ATR stop")
        tbl.add_row("Risk : Reward",     f"{plan['rr']:.2f} : 1",
                    f"Risk/share ${plan['risk']:.4f}  |  Reward/share (T2) ${plan['t2']-plan['entry']:.4f}")
        tbl.add_row("Position Size",     f"{plan['shares']:,} shares",
                    f"Position value ${plan['pos_val']:,.2f}  |  Max risk ${plan['risk_amt']:,.2f}")
        tbl.add_row("Holding Period",    plan["holding"],              "Swing trade — review at T1")
        tbl.add_row("Indicator Align.",  f"{plan['aln']}%",
                    f"Trade quality: [{qc(Q)}]{Q}[/{qc(Q)}]")
        tbl.add_row("Support / Resist.", "",
                    f"Support ${sr.get('nearest_sup','—')}  |  Resistance ${sr.get('nearest_res','—')}")
        tbl.add_row("Entry Catalyst",    "", plan["catalyst"][:66])
        console.print(tbl)

        console.print(f"  [green]Aligned [{len(plan['aligned'])}]:[/green]  "
                      + "  ·  ".join(plan["aligned"]))
        if plan["conflicting"]:
            console.print(f"  [red]Conflicting [{len(plan['conflicting'])}]:[/red]  "
                          + "  ·  ".join(plan["conflicting"]))
        console.print()

    executable = {t: p for t, p in plans.items() if p["quality"] in ("A+", "A")}
    console.print(
        f"[green]TradeAnalyser result:[/green] [bold]{len(executable)}[/bold] A/A+ setup(s) "
        f"ready for execution  →  {', '.join(executable.keys())}\n"
    )

    # ════════════════════════════════════════════════════════════════════════
    # SKILL 5 — TradeExecutor
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold magenta]  SKILL 5  —  Trade Executor  (Paper Trading)[/bold magenta]"))

    portfolio_cash = 100_000.0
    positions = []

    exec_tbl = Table(title="[bold]Execution Log — PAPER MODE[/bold]",
                     box=box.ROUNDED, border_style="magenta", width=112)
    exec_tbl.add_column("Ticker",       style="bold cyan", width=7)
    exec_tbl.add_column("Action",       width=10)
    exec_tbl.add_column("Type",         width=9)
    exec_tbl.add_column("Fill",         width=9)
    exec_tbl.add_column("Shares",       justify="right", width=8)
    exec_tbl.add_column("Cost",         justify="right", width=12)
    exec_tbl.add_column("Cash Left",    justify="right", width=13)
    exec_tbl.add_column("Note",         width=34)

    for t, plan in executable.items():
        cost = plan["shares"] * plan["entry"]
        if cost > portfolio_cash:
            max_sh = max(1, int(portfolio_cash * 0.95 / plan["entry"]))
            cost   = round(max_sh * plan["entry"], 2)
            plan["shares"] = max_sh
            plan["pos_val"] = cost
        portfolio_cash -= cost
        positions.append({
            "ticker": t, "shares": plan["shares"],
            "entry": plan["entry"], "stop": plan["stop"],
            "t1": plan["t1"], "t2": plan["t2"],
            "pos_val": plan["pos_val"],
        })
        exec_tbl.add_row(
            t, "[green]ENTERED[/green]", plan["etype"],
            f"${plan['entry']:.4f}",
            str(plan["shares"]),
            f"${cost:,.2f}",
            f"${portfolio_cash:,.2f}",
            plan["catalyst"][:32],
        )

    # orders that didn't make A/A+
    for t in actionable:
        if t not in executable:
            pl = plans.get(t, {})
            exec_tbl.add_row(
                t, "[yellow]SKIPPED[/yellow]", "—", "—", "—", "—",
                f"${portfolio_cash:,.2f}",
                f"Quality {pl.get('quality','?')} — below A threshold",
            )

    console.print(exec_tbl)
    deployed = 100_000 - portfolio_cash
    console.print(
        f"\n  Cash deployed: [bold]${deployed:,.2f}[/bold]  |  "
        f"Cash remaining: [bold]${portfolio_cash:,.2f}[/bold]  |  "
        f"Positions opened: [bold]{len(positions)}[/bold]\n"
    )

    # ════════════════════════════════════════════════════════════════════════
    # SKILL 6 — PortfolioTracker
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold white]  SKILL 6  —  Portfolio Tracker  (Position Health Monitor)[/bold white]"))

    if not positions:
        console.print("[yellow]No positions to track.[/yellow]\n")
    else:
        pt = Table(title="[bold]Open Positions — Health Check @ 2026-05-23[/bold]",
                   box=box.ROUNDED, border_style="white", width=112)
        pt.add_column("Ticker",    style="bold cyan", width=7)
        pt.add_column("Shares",    justify="right",  width=7)
        pt.add_column("Entry",     justify="right",  width=9)
        pt.add_column("Current",   justify="right",  width=9)
        pt.add_column("Stop",      justify="right",  width=9)
        pt.add_column("T1",        justify="right",  width=9)
        pt.add_column("T2",        justify="right",  width=9)
        pt.add_column("Unr. P&L",  justify="right",  width=12)
        pt.add_column("% P&L",     justify="right",  width=8)
        pt.add_column("% to Stop", justify="right",  width=10)
        pt.add_column("Status",    width=16)

        for pos in positions:
            t    = pos["ticker"]
            curr = inds[t]["price"]
            en   = pos["entry"]
            pnl  = round((curr - en) * pos["shares"], 2)
            pnl_p= round((curr - en) / en * 100, 2)
            stop = pos["stop"]
            dist_stop = round((curr - stop) / stop * 100, 1)
            pc   = "green" if pnl >= 0 else "red"

            if curr <= stop:          status = "[bold red]⚠ STOP HIT[/bold red]"
            elif curr >= pos["t2"]:   status = "[bold green]✓ T2 REACHED[/bold green]"
            elif curr >= pos["t1"]:   status = "[green]✓ T1 REACHED[/green]"
            elif pnl_p < -1.2:        status = "[yellow]⚠ MONITOR[/yellow]"
            else:                     status = "[cyan]● ON TRACK[/cyan]"

            pt.add_row(
                t, f"{pos['shares']:,}", f"${en:.2f}", f"${curr:.2f}",
                f"${stop:.2f}", f"${pos['t1']:.2f}", f"${pos['t2']:.2f}",
                f"[{pc}]${pnl:+,.2f}[/{pc}]",
                f"[{pc}]{pnl_p:+.2f}%[/{pc}]",
                f"{dist_stop:+.1f}%",
                status,
            )
        console.print(pt)

        # Tracker recommendations
        console.print()
        rec_tbl = Table(title="[bold]Tracker Recommendations[/bold]",
                        box=box.SIMPLE, border_style="dim", width=112)
        rec_tbl.add_column("Ticker", style="bold cyan", width=7)
        rec_tbl.add_column("Action",  width=20)
        rec_tbl.add_column("Urgency", width=12)
        rec_tbl.add_column("Rationale", width=70)
        for pos in positions:
            t  = pos["ticker"]
            curr = inds[t]["price"]
            if curr <= pos["stop"]:
                act, urg, rat = "CLOSE — STOP LOSS", "IMMEDIATE", f"Price ${curr:.2f} ≤ stop ${pos['stop']:.2f}. Exit to protect capital."
            elif curr >= pos["t2"]:
                act, urg, rat = "PARTIAL CLOSE (T2)", "NEXT OPEN", f"T2 hit at ${pos['t2']:.2f}. Close 33%, move stop to breakeven."
            elif curr >= pos["t1"]:
                act, urg, rat = "ALERT — T1 HIT", "MONITOR", f"T1 ${pos['t1']:.2f} reached. Consider closing 33%, trail stop."
            else:
                act, urg, rat = "HOLD", "MONITOR", f"Thesis intact. Trend {scores[t]['bias']}, RSI {inds[t]['rsi']:.0f}. Review in 2 days."
            uc = "bold red" if urg == "IMMEDIATE" else "yellow" if urg == "NEXT OPEN" else "dim"
            rec_tbl.add_row(t, act, f"[{uc}]{urg}[/{uc}]", rat)
        console.print(rec_tbl)

    # ════════════════════════════════════════════════════════════════════════
    # Portfolio Summary
    # ════════════════════════════════════════════════════════════════════════
    console.print(Rule("[bold cyan]  Portfolio Summary[/bold cyan]"))
    total_pnl = sum(
        (inds[p["ticker"]]["price"] - p["entry"]) * p["shares"]
        for p in positions
    )
    port_val = portfolio_cash + sum(p["pos_val"] for p in positions) + total_pnl

    st = Table(box=box.SIMPLE, width=68, show_header=False)
    st.add_column("Metric", style="bold", width=32)
    st.add_column("Value", justify="right", width=20)
    st.add_row("Starting Capital",    "$100,000.00")
    st.add_row("Capital Deployed",    f"${deployed:,.2f}")
    st.add_row("Cash Remaining",      f"${portfolio_cash:,.2f}")
    st.add_row("Open Positions",      str(len(positions)))
    pnl_col = "green" if total_pnl >= 0 else "red"
    st.add_row("Unrealised P&L",      f"[{pnl_col}]${total_pnl:+,.2f}[/{pnl_col}]")
    st.add_row("Portfolio Value",     f"[bold]${port_val:,.2f}[/bold]")
    console.print(st)

    console.print(Panel(
        f"[green]✓ Pipeline complete.[/green]   "
        f"Scanned [bold]{len(TICKERS)}[/bold]  →  "
        f"Passed filter [bold]{len(passing)}[/bold]  →  "
        f"Analysis complete [bold]{len(passing)}[/bold]  →  "
        f"Evaluator cleared [bold]{len(actionable)}[/bold]  →  "
        f"Trade plans [bold]{len(plans)}[/bold]  →  "
        f"Executed [bold]{len(positions)}[/bold] trade(s)",
        border_style="cyan"
    ))

if __name__ == "__main__":
    main()
