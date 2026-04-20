"""
Technical analysis indicators optimised for swing trading.
Uses the `ta` library plus numpy for advanced calculations.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import ta


def calculate_indicators(df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute all swing-trading relevant indicators from OHLCV DataFrame.
    DataFrame must have columns: Open, High, Low, Close, Volume.
    """
    if len(df) < 20:
        return {"error": "Insufficient data for indicator calculation (need >= 20 bars)"}

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    volume = df["Volume"].astype(float)

    def safe_float(series: pd.Series, idx: int = -1) -> float | None:
        try:
            val = series.iloc[idx]
            return round(float(val), 4) if not np.isnan(val) else None
        except Exception:
            return None

    # --- Momentum ---
    rsi14 = ta.momentum.RSIIndicator(close, window=14).rsi()
    rsi9 = ta.momentum.RSIIndicator(close, window=9).rsi()
    stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)

    # --- Trend ---
    macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    ema9 = ta.trend.EMAIndicator(close, window=9).ema_indicator()
    ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    ema200 = ta.trend.EMAIndicator(close, window=200).ema_indicator() if len(df) >= 200 else None
    sma50 = ta.trend.SMAIndicator(close, window=50).sma_indicator()
    sma200 = ta.trend.SMAIndicator(close, window=200).sma_indicator() if len(df) >= 200 else None
    adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)

    # --- Volatility ---
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    atr = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
    kc = ta.volatility.KeltnerChannel(high, low, close, window=20)

    # --- Volume ---
    obv = ta.volume.OnBalanceVolumeIndicator(close, volume).on_balance_volume()
    vwap_series = (close * volume).cumsum() / volume.cumsum()

    current_price = safe_float(close)
    vol_sma20 = volume.rolling(20).mean()

    # Bollinger Band position (0=lower, 1=upper)
    bb_width = safe_float(bb.bollinger_hband()) - safe_float(bb.bollinger_lband()) if safe_float(bb.bollinger_hband()) and safe_float(bb.bollinger_lband()) else None
    bb_position = None
    if bb_width and bb_width != 0:
        bb_position = round((current_price - safe_float(bb.bollinger_lband())) / bb_width, 3) if current_price and safe_float(bb.bollinger_lband()) else None

    return {
        # Price
        "current_price": current_price,
        "prev_close": safe_float(close, -2),
        # Momentum
        "rsi_14": safe_float(rsi14),
        "rsi_9": safe_float(rsi9),
        "stoch_k": safe_float(stoch.stoch()),
        "stoch_d": safe_float(stoch.stoch_signal()),
        # MACD
        "macd": safe_float(macd_ind.macd()),
        "macd_signal": safe_float(macd_ind.macd_signal()),
        "macd_histogram": safe_float(macd_ind.macd_diff()),
        "macd_prev_histogram": safe_float(macd_ind.macd_diff(), -2),
        # Trend EMAs
        "ema9": safe_float(ema9),
        "ema20": safe_float(ema20),
        "ema50": safe_float(ema50),
        "ema200": safe_float(ema200) if ema200 is not None else None,
        "sma50": safe_float(sma50),
        "sma200": safe_float(sma200) if sma200 is not None else None,
        # ADX (trend strength)
        "adx": safe_float(adx_ind.adx()),
        "adx_pos": safe_float(adx_ind.adx_pos()),
        "adx_neg": safe_float(adx_ind.adx_neg()),
        # Bollinger Bands
        "bb_upper": safe_float(bb.bollinger_hband()),
        "bb_middle": safe_float(bb.bollinger_mavg()),
        "bb_lower": safe_float(bb.bollinger_lband()),
        "bb_width": bb_width,
        "bb_position": bb_position,
        # Keltner Channel
        "kc_upper": safe_float(kc.keltner_channel_hband()),
        "kc_middle": safe_float(kc.keltner_channel_mband()),
        "kc_lower": safe_float(kc.keltner_channel_lband()),
        # Volatility
        "atr": safe_float(atr),
        "atr_pct": round(safe_float(atr) / current_price * 100, 3) if safe_float(atr) and current_price else None,
        # Volume
        "volume": int(volume.iloc[-1]),
        "volume_sma20": int(vol_sma20.iloc[-1]) if not np.isnan(vol_sma20.iloc[-1]) else None,
        "volume_ratio": round(float(volume.iloc[-1]) / float(vol_sma20.iloc[-1]), 2) if not np.isnan(vol_sma20.iloc[-1]) and vol_sma20.iloc[-1] != 0 else None,
        "obv_trend": "rising" if safe_float(obv) and safe_float(obv, -5) and safe_float(obv) > safe_float(obv, -5) else "falling",
        "vwap": round(float(vwap_series.iloc[-1]), 4),
        # Recent candle patterns
        "last_candle_body_pct": round(abs(float(close.iloc[-1]) - float(df["Open"].iloc[-1])) / float(df["Open"].iloc[-1]) * 100, 3),
        "last_candle_bullish": bool(float(close.iloc[-1]) > float(df["Open"].iloc[-1])),
    }


def find_support_resistance(df: pd.DataFrame, lookback: int = 60) -> dict[str, Any]:
    """
    Detect key support and resistance levels using swing highs/lows.
    Returns up to 3 nearest support and 3 nearest resistance levels.
    """
    if len(df) < lookback:
        lookback = len(df)

    recent = df.tail(lookback)
    close = float(recent["Close"].iloc[-1])

    swing_highs: list[float] = []
    swing_lows: list[float] = []

    highs = recent["High"].values
    lows = recent["Low"].values

    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
            swing_highs.append(round(float(highs[i]), 4))
        if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
            swing_lows.append(round(float(lows[i]), 4))

    # Cluster nearby levels (within 1%)
    def cluster(levels: list[float], threshold: float = 0.01) -> list[float]:
        if not levels:
            return []
        levels = sorted(set(levels))
        clustered: list[float] = [levels[0]]
        for lvl in levels[1:]:
            if (lvl - clustered[-1]) / clustered[-1] > threshold:
                clustered.append(lvl)
        return clustered

    resistance = [r for r in cluster(swing_highs) if r > close]
    support = [s for s in cluster(swing_lows) if s < close]

    return {
        "current_price": round(close, 4),
        "resistance_levels": sorted(resistance)[:3],
        "support_levels": sorted(support, reverse=True)[:3],
        "nearest_resistance": min(resistance) if resistance else None,
        "nearest_support": max(support) if support else None,
    }


def assess_trend(indicators: dict[str, Any]) -> dict[str, str]:
    """Determine overall trend and strength from indicator dict."""
    price = indicators.get("current_price", 0)
    ema20 = indicators.get("ema20") or 0
    ema50 = indicators.get("ema50") or 0
    ema200 = indicators.get("ema200") or 0
    adx = indicators.get("adx") or 0

    # Direction
    if ema200 and price > ema20 > ema50 > ema200:
        direction = "STRONG_UPTREND"
    elif price > ema50 and (not ema200 or ema50 > ema200):
        direction = "UPTREND"
    elif ema200 and price < ema20 < ema50 < ema200:
        direction = "STRONG_DOWNTREND"
    elif price < ema50 and (not ema200 or ema50 < ema200):
        direction = "DOWNTREND"
    else:
        direction = "SIDEWAYS"

    # Strength
    if adx >= 40:
        strength = "VERY_STRONG"
    elif adx >= 25:
        strength = "STRONG"
    elif adx >= 20:
        strength = "MODERATE"
    else:
        strength = "WEAK"

    return {"direction": direction, "strength": strength, "adx": adx}


def get_swing_signals(indicators: dict[str, Any], sr_levels: dict[str, Any]) -> dict[str, Any]:
    """
    Evaluate swing trading signals from indicators.
    Returns a scored signal dict for Claude to reason on.
    """
    signals: list[str] = []
    score = 0  # positive = bullish, negative = bearish

    rsi = indicators.get("rsi_14") or 50
    macd_hist = indicators.get("macd_histogram") or 0
    macd_prev = indicators.get("macd_prev_histogram") or 0
    stoch_k = indicators.get("stoch_k") or 50
    stoch_d = indicators.get("stoch_d") or 50
    price = indicators.get("current_price") or 0
    ema20 = indicators.get("ema20") or price
    ema50 = indicators.get("ema50") or price
    bb_pos = indicators.get("bb_position") or 0.5
    vol_ratio = indicators.get("volume_ratio") or 1.0
    adx = indicators.get("adx") or 0

    # RSI signals
    if 40 <= rsi <= 55:
        signals.append("RSI in neutral-bullish zone (healthy pullback opportunity)")
        score += 1
    elif rsi < 30:
        signals.append("RSI oversold (<30) — potential reversal")
        score += 2
    elif rsi > 70:
        signals.append("RSI overbought (>70) — caution for longs")
        score -= 2

    # MACD signals
    if macd_hist > 0 and macd_prev <= 0:
        signals.append("MACD histogram bullish crossover (fresh momentum shift)")
        score += 2
    elif macd_hist > 0 and macd_hist > macd_prev:
        signals.append("MACD histogram increasing (strengthening momentum)")
        score += 1
    elif macd_hist < 0 and macd_prev >= 0:
        signals.append("MACD histogram bearish crossover")
        score -= 2
    elif macd_hist < 0 and macd_hist < macd_prev:
        signals.append("MACD histogram decreasing (weakening)")
        score -= 1

    # EMA signals
    if price > ema20 > ema50:
        signals.append("Price above EMA20 > EMA50 (bullish stack)")
        score += 2
    elif abs(price - ema20) / ema20 < 0.01 and price > ema50:
        signals.append("Price testing EMA20 support in uptrend (pullback entry)")
        score += 2
    elif price < ema20 < ema50:
        signals.append("Price below EMA20 < EMA50 (bearish stack)")
        score -= 2

    # Stochastic signals
    if stoch_k < 25 and stoch_d < 25:
        signals.append("Stochastic oversold (<25) — reversal watch")
        score += 1
    elif stoch_k > stoch_d and stoch_k < 40:
        signals.append("Stochastic bullish crossover from low levels")
        score += 2
    elif stoch_k > 80:
        signals.append("Stochastic overbought (>80)")
        score -= 1

    # Bollinger Band signals
    if bb_pos < 0.2:
        signals.append("Price near lower Bollinger Band (mean reversion potential)")
        score += 1
    elif bb_pos > 0.8:
        signals.append("Price near upper Bollinger Band (overbought / breakout)")
        score -= 1

    # Volume confirmation
    if vol_ratio and vol_ratio > 1.5:
        signals.append(f"Volume surge ({vol_ratio:.1f}x average) — confirms move")
        score += 1
    elif vol_ratio and vol_ratio < 0.7:
        signals.append("Below-average volume — weak conviction")
        score -= 1

    # ADX trend strength
    if adx >= 25:
        signals.append(f"ADX={adx:.1f} — strong trend present")
        score += 1

    return {
        "signals": signals,
        "composite_score": score,
        "bias": "BULLISH" if score >= 3 else "BEARISH" if score <= -3 else "NEUTRAL",
        "signal_count": len(signals),
    }


def ohlcv_dataframe_from_records(records: list[dict]) -> pd.DataFrame:
    """Convert list of OHLCV records from get_stock_data back to DataFrame."""
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df.columns = [c.capitalize() for c in df.columns]
    return df
