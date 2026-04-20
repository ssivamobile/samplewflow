"""
StockAnalyser — Skill 2
For each ticker from the WatchlistScanner, performs:
  - Fundamental analysis (valuation, growth, profitability, balance sheet)
  - Technical analysis (indicators, trend, support/resistance)
  - Market sentiment (news headlines, analyst consensus direction)
Returns a structured recommendation: BUY / SELL / HOLD with confidence and reasoning.
"""
from __future__ import annotations

import json
from typing import Any

import anthropic
import pandas as pd

from ..config import config
from ..tools.market_data import (
    get_earnings_history,
    get_news,
    get_stock_data,
    get_stock_info,
)
from ..tools.technical_indicators import (
    assess_trend,
    calculate_indicators,
    find_support_resistance,
    get_swing_signals,
    ohlcv_dataframe_from_records,
)


# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------
_TOOLS: list[dict] = [
    {
        "name": "get_fundamentals",
        "description": "Fetch fundamental financial data: P/E, EPS, revenue growth, margins, debt, ROE, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_technical_data",
        "description": "Fetch OHLCV price history and compute all technical indicators (RSI, MACD, EMAs, Bollinger Bands, ATR, ADX, Stochastic, support/resistance, swing signals).",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {"type": "string", "description": "History period e.g. '6mo', '1y'"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sentiment",
        "description": "Fetch recent news headlines and earnings surprise history for sentiment analysis.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "submit_analysis",
        "description": "Submit the completed stock analysis with recommendation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "recommendation": {
                    "type": "string",
                    "enum": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"],
                },
                "confidence": {
                    "type": "number",
                    "description": "Confidence in recommendation 0-100",
                },
                "fundamental_score": {
                    "type": "number",
                    "description": "Fundamental health score 0-100",
                },
                "technical_score": {
                    "type": "number",
                    "description": "Technical setup score 0-100",
                },
                "sentiment_score": {
                    "type": "number",
                    "description": "Sentiment score 0-100",
                },
                "overall_score": {
                    "type": "number",
                    "description": "Weighted overall score 0-100",
                },
                "key_strengths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top 3-5 bullish factors",
                },
                "key_risks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top 3-5 risk factors",
                },
                "fundamental_summary": {"type": "string"},
                "technical_summary": {"type": "string"},
                "sentiment_summary": {"type": "string"},
                "reasoning": {"type": "string", "description": "Comprehensive analysis rationale"},
                "price_at_analysis": {"type": "number"},
                "swing_bias": {
                    "type": "string",
                    "description": "BULLISH / BEARISH / NEUTRAL for swing trading",
                },
            },
            "required": [
                "ticker", "recommendation", "confidence", "fundamental_score",
                "technical_score", "sentiment_score", "overall_score",
                "key_strengths", "key_risks", "reasoning", "swing_bias",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
def _handle_get_fundamentals(ticker: str) -> dict:
    return get_stock_info(ticker)


def _handle_get_technical_data(ticker: str, period: str = "6mo") -> dict:
    price_data = get_stock_data(ticker, period=period, interval="1d")
    if "error" in price_data or not price_data.get("data"):
        return {"error": price_data.get("error", "No data")}

    df = ohlcv_dataframe_from_records(price_data["data"])
    indicators = calculate_indicators(df)
    sr_levels = find_support_resistance(df)
    trend = assess_trend(indicators)
    signals = get_swing_signals(indicators, sr_levels)

    return {
        "ticker": ticker,
        "price_summary": {
            "latest_price": price_data["latest_price"],
            "day_change_pct": price_data["day_change_pct"],
            "52w_high": price_data["52w_high"],
            "52w_low": price_data["52w_low"],
            "position_in_52w_range_pct": round(
                (price_data["latest_price"] - price_data["52w_low"]) /
                (price_data["52w_high"] - price_data["52w_low"]) * 100, 1
            ) if price_data["52w_high"] != price_data["52w_low"] else 50,
        },
        "indicators": indicators,
        "support_resistance": sr_levels,
        "trend": trend,
        "swing_signals": signals,
    }


def _handle_get_sentiment(ticker: str) -> dict:
    news = get_news(ticker, limit=8)
    earnings = get_earnings_history(ticker)
    return {
        "ticker": ticker,
        "recent_news": news,
        "earnings_history": earnings.get("earnings", []),
    }


def _dispatch_tool(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "get_fundamentals":
        return _handle_get_fundamentals(tool_input["ticker"])
    elif tool_name == "get_technical_data":
        return _handle_get_technical_data(tool_input["ticker"], tool_input.get("period", "6mo"))
    elif tool_name == "get_sentiment":
        return _handle_get_sentiment(tool_input["ticker"])
    elif tool_name == "submit_analysis":
        return tool_input
    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------
class StockAnalyser:
    """
    Skill 2: Stock Analyser
    Performs comprehensive fundamental, technical, and sentiment analysis
    for each candidate stock and produces a structured recommendation.
    """

    SYSTEM_PROMPT = """You are a professional stock analyst specialising in swing trading.
For each stock you receive, perform a thorough three-pillar analysis:

1. FUNDAMENTAL ANALYSIS — Is the business healthy and reasonably valued?
   - Assess P/E vs sector, growth rates, margins, ROE, debt load
   - Identify if the stock is undervalued, fairly valued, or overvalued
   - Check earnings trend and analyst target upside

2. TECHNICAL ANALYSIS — Is the chart set up for a swing trade?
   - Interpret RSI, MACD, Stochastic for momentum
   - Assess EMA alignment (9/20/50/200) for trend direction
   - Check Bollinger Band position and ADX for trend strength
   - Note support/resistance levels and swing signals
   - Evaluate volume confirmation

3. MARKET SENTIMENT — Is the market mood supportive?
   - Interpret news headlines (positive/negative catalyst?
   - Assess analyst recommendation direction and momentum

Weight the three pillars: 30% fundamental, 50% technical, 20% sentiment for swing trading.

Be objective and data-driven. Score each pillar 0-100, compute weighted overall, then
provide a final recommendation using submit_analysis."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def analyse(self, ticker: str) -> dict[str, Any]:
        """Analyse a single ticker. Returns structured analysis dict."""
        messages: list[dict] = [
            {
                "role": "user",
                "content": f"Perform a complete swing-trade analysis for {ticker}. "
                           f"Fetch fundamentals, technical data, and sentiment, then submit your analysis.",
            }
        ]
        final_result: dict = {}

        while True:
            response = self.client.messages.create(
                model=config.model,
                max_tokens=6144,
                system=self.SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _dispatch_tool(block.name, block.input)
                    if block.name == "submit_analysis":
                        final_result = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            if response.stop_reason == "end_turn" or not tool_results:
                if not final_result:
                    for block in response.content:
                        if hasattr(block, "text"):
                            final_result = {"ticker": ticker, "error": "No structured analysis", "text": block.text}
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if final_result:
                break

        return final_result

    def analyse_batch(self, tickers: list[str]) -> list[dict[str, Any]]:
        """Analyse multiple tickers sequentially."""
        results = []
        for ticker in tickers:
            result = self.analyse(ticker)
            results.append(result)
        return results
