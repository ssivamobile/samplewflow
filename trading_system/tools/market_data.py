"""
Market data fetching via Yahoo Finance (yfinance).
Provides OHLCV data, fundamentals, analyst recommendations, and news.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pandas as pd
import yfinance as yf


def get_stock_data(ticker: str, period: str = "6mo", interval: str = "1d") -> dict[str, Any]:
    """Fetch OHLCV price history."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            return {"ticker": ticker, "error": "No data returned", "data": []}

        records = []
        for ts, row in df.iterrows():
            records.append({
                "date": ts.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
            })

        return {
            "ticker": ticker,
            "period": period,
            "interval": interval,
            "latest_price": round(float(df["Close"].iloc[-1]), 4),
            "prev_close": round(float(df["Close"].iloc[-2]), 4) if len(df) > 1 else None,
            "day_change_pct": round(
                (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[-2]) - 1) * 100, 2
            ) if len(df) > 1 else 0.0,
            "52w_high": round(float(df["High"].max()), 4),
            "52w_low": round(float(df["Low"].min()), 4),
            "avg_volume_20d": int(df["Volume"].tail(20).mean()),
            "data": records,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "data": []}


def get_stock_info(ticker: str) -> dict[str, Any]:
    """Fetch fundamental data for a stock."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return {
            "ticker": ticker,
            "name": info.get("longName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "country": info.get("country", "Unknown"),
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "price_to_book": info.get("priceToBook"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            "ev_to_ebitda": info.get("enterpriseToEbitda"),
            "eps_trailing": info.get("trailingEps"),
            "eps_forward": info.get("forwardEps"),
            "revenue_growth_yoy": info.get("revenueGrowth"),
            "earnings_growth_yoy": info.get("earningsGrowth"),
            "gross_margins": info.get("grossMargins"),
            "profit_margins": info.get("profitMargins"),
            "operating_margins": info.get("operatingMargins"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "quick_ratio": info.get("quickRatio"),
            "free_cashflow": info.get("freeCashflow"),
            "dividend_yield": info.get("dividendYield"),
            "beta": info.get("beta"),
            "short_float_pct": info.get("shortPercentOfFloat"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "analyst_target_price": info.get("targetMeanPrice"),
            "analyst_target_high": info.get("targetHighPrice"),
            "analyst_target_low": info.get("targetLowPrice"),
            "recommendation_key": info.get("recommendationKey"),
            "number_of_analyst_opinions": info.get("numberOfAnalystOpinions"),
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def get_analyst_recommendations(ticker: str) -> dict[str, Any]:
    """Fetch recent analyst grade changes and consensus."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Grade history
        recs_df = stock.recommendations
        grade_history: list[dict] = []
        if recs_df is not None and not recs_df.empty:
            recent = recs_df.tail(30).copy()
            recent.index = recent.index.astype(str)
            for ts, row in recent.iterrows():
                grade_history.append({
                    "date": str(ts)[:10],
                    "firm": row.get("Firm", ""),
                    "to_grade": row.get("To Grade", ""),
                    "from_grade": row.get("From Grade", ""),
                    "action": row.get("Action", ""),
                })

        # Consensus breakdown
        buys = sum(1 for g in grade_history if g["to_grade"].lower() in
                   ["strong buy", "buy", "outperform", "overweight", "positive"])
        holds = sum(1 for g in grade_history if g["to_grade"].lower() in
                    ["hold", "neutral", "market perform", "equal-weight", "sector perform"])
        sells = sum(1 for g in grade_history if g["to_grade"].lower() in
                    ["sell", "underperform", "underweight", "negative", "reduce"])

        return {
            "ticker": ticker,
            "consensus": info.get("recommendationKey", "none"),
            "target_mean": info.get("targetMeanPrice"),
            "target_high": info.get("targetHighPrice"),
            "target_low": info.get("targetLowPrice"),
            "num_analysts": info.get("numberOfAnalystOpinions", 0),
            "grade_summary": {"buy": buys, "hold": holds, "sell": sells},
            "recent_grades": grade_history[:15],
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "grade_summary": {"buy": 0, "hold": 0, "sell": 0}}


def get_news(ticker: str, limit: int = 8) -> list[dict[str, Any]]:
    """Fetch recent news headlines for sentiment analysis."""
    try:
        stock = yf.Ticker(ticker)
        news = stock.news or []
        results = []
        for item in news[:limit]:
            results.append({
                "title": item.get("title", ""),
                "publisher": item.get("publisher", ""),
                "published_at": datetime.fromtimestamp(
                    item.get("providerPublishTime", 0)
                ).strftime("%Y-%m-%d %H:%M") if item.get("providerPublishTime") else "",
                "type": item.get("type", ""),
                "related_tickers": item.get("relatedTickers", []),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


def get_earnings_history(ticker: str) -> dict[str, Any]:
    """Fetch earnings surprise history."""
    try:
        stock = yf.Ticker(ticker)
        earnings = stock.quarterly_earnings
        if earnings is None or earnings.empty:
            return {"ticker": ticker, "earnings": []}

        results = []
        for date_idx, row in earnings.tail(8).iterrows():
            results.append({
                "period": str(date_idx),
                "actual": row.get("Earnings", None),
                "estimate": row.get("Estimate", None),
            })
        return {"ticker": ticker, "earnings": results}
    except Exception as e:
        return {"ticker": ticker, "error": str(e), "earnings": []}


def get_multiple_stocks_snapshot(tickers: list[str]) -> list[dict[str, Any]]:
    """Quick snapshot of multiple tickers (price, change, volume)."""
    results = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            results.append({
                "ticker": ticker,
                "name": info.get("shortName", ticker),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "change_pct": info.get("regularMarketChangePercent"),
                "volume": info.get("regularMarketVolume"),
                "avg_volume": info.get("averageVolume"),
                "market_cap": info.get("marketCap"),
                "sector": info.get("sector", "Unknown"),
                "pe_ratio": info.get("trailingPE"),
                "52w_high": info.get("fiftyTwoWeekHigh"),
                "52w_low": info.get("fiftyTwoWeekLow"),
            })
        except Exception as e:
            results.append({"ticker": ticker, "error": str(e)})
    return results
