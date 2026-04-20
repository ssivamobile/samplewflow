"""
TradeAnalyser — Skill 4
Takes evaluated stocks (from Evaluator) and computes precise swing-trade plans:
  - Entry price (limit/market) and entry zone
  - Stop loss (ATR-based or below swing low)
  - Take profit targets (T1 = 1:1, T2 = 2:1, T3 = 3:1 R:R)
  - Position size based on risk management
  - Technical alignment check across ALL major indicators
  - Trade validity timeframe (swing = 3–25 trading days)
"""
from __future__ import annotations

import json
from typing import Any

import anthropic

from ..config import config
from ..tools.market_data import get_stock_data
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
        "name": "get_chart_data",
        "description": "Fetch OHLCV chart data and compute ALL technical indicators for trade analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {"type": "string", "description": "e.g. '6mo' for swing context"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_weekly_chart",
        "description": "Fetch weekly OHLCV data to confirm the higher-timeframe trend.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "calculate_position_size",
        "description": "Calculate position size based on portfolio value, risk %, entry price, and stop loss.",
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_value": {"type": "number"},
                "risk_pct": {"type": "number", "description": "Risk as decimal e.g. 0.02 for 2%"},
                "entry_price": {"type": "number"},
                "stop_loss": {"type": "number"},
            },
            "required": ["portfolio_value", "risk_pct", "entry_price", "stop_loss"],
        },
    },
    {
        "name": "check_indicator_alignment",
        "description": "Check how many key swing-trade indicators are aligned for a bullish or bearish trade. Returns an alignment checklist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "indicators": {"type": "object", "description": "Indicators dict from get_chart_data"},
                "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
            },
            "required": ["indicators", "direction"],
        },
    },
    {
        "name": "submit_trade_plan",
        "description": "Submit the final swing trade plan with precise entry, stop, and target prices.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "direction": {"type": "string", "enum": ["LONG", "SHORT"]},
                "trade_type": {"type": "string", "enum": ["SWING"]},
                "entry_type": {
                    "type": "string",
                    "enum": ["MARKET", "LIMIT", "STOP_LIMIT"],
                    "description": "Order type for entry",
                },
                "entry_price": {"type": "number", "description": "Ideal entry price"},
                "entry_zone_low": {"type": "number", "description": "Lower bound of acceptable entry zone"},
                "entry_zone_high": {"type": "number", "description": "Upper bound of acceptable entry zone"},
                "stop_loss": {"type": "number", "description": "Hard stop loss price"},
                "stop_loss_method": {
                    "type": "string",
                    "description": "e.g. 'Below swing low', 'ATR x2 stop', 'Below EMA50'",
                },
                "target_1": {"type": "number", "description": "First take profit (1:1 R:R)"},
                "target_2": {"type": "number", "description": "Second take profit (2:1 R:R)"},
                "target_3": {"type": "number", "description": "Third take profit (3:1 R:R)"},
                "risk_reward_ratio": {"type": "number", "description": "R:R ratio to T2"},
                "risk_per_share": {"type": "number"},
                "reward_per_share": {"type": "number"},
                "position_size_shares": {"type": "integer", "description": "Number of shares to buy"},
                "position_size_value": {"type": "number", "description": "Total position value in USD"},
                "max_risk_amount": {"type": "number", "description": "Max $ at risk for this trade"},
                "holding_period_days": {
                    "type": "string",
                    "description": "Expected swing duration e.g. '5-15 trading days'",
                },
                "invalidation_level": {
                    "type": "number",
                    "description": "Price at which the trade thesis is invalidated (usually = stop loss or tighter)",
                },
                "indicator_alignment_score": {
                    "type": "number",
                    "description": "0-100 score of how many indicators align",
                },
                "aligned_indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of indicators confirming the trade",
                },
                "conflicting_indicators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of indicators NOT confirming (risks)",
                },
                "entry_catalyst": {
                    "type": "string",
                    "description": "What specific price action to look for before entering",
                },
                "trade_notes": {"type": "string"},
                "trade_quality": {
                    "type": "string",
                    "enum": ["A+", "A", "B", "C", "SKIP"],
                    "description": "Grade of this trade setup",
                },
            },
            "required": [
                "ticker", "direction", "trade_type", "entry_type", "entry_price",
                "stop_loss", "stop_loss_method", "target_1", "target_2", "target_3",
                "risk_reward_ratio", "position_size_shares", "position_size_value",
                "max_risk_amount", "indicator_alignment_score", "aligned_indicators",
                "conflicting_indicators", "entry_catalyst", "trade_quality",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
def _handle_get_chart_data(ticker: str, period: str = "6mo") -> dict:
    data = get_stock_data(ticker, period=period, interval="1d")
    if "error" in data or not data.get("data"):
        return {"error": data.get("error", "No data")}
    df = ohlcv_dataframe_from_records(data["data"])
    indicators = calculate_indicators(df)
    sr = find_support_resistance(df)
    trend = assess_trend(indicators)
    signals = get_swing_signals(indicators, sr)
    return {
        "ticker": ticker,
        "current_price": indicators["current_price"],
        "indicators": indicators,
        "support_resistance": sr,
        "trend": trend,
        "signals": signals,
        "recent_candles": data["data"][-10:],
    }


def _handle_get_weekly_chart(ticker: str) -> dict:
    data = get_stock_data(ticker, period="1y", interval="1wk")
    if "error" in data or not data.get("data"):
        return {"error": data.get("error", "No data")}
    df = ohlcv_dataframe_from_records(data["data"])
    if len(df) < 10:
        return {"error": "Not enough weekly bars"}
    indicators = calculate_indicators(df)
    trend = assess_trend(indicators)
    return {
        "ticker": ticker,
        "weekly_trend": trend,
        "weekly_rsi": indicators.get("rsi_14"),
        "weekly_macd_histogram": indicators.get("macd_histogram"),
        "weekly_ema20": indicators.get("ema20"),
        "weekly_ema50": indicators.get("ema50"),
        "weekly_current_price": indicators.get("current_price"),
    }


def _handle_calculate_position_size(
    portfolio_value: float,
    risk_pct: float,
    entry_price: float,
    stop_loss: float,
) -> dict:
    risk_amount = portfolio_value * risk_pct
    risk_per_share = abs(entry_price - stop_loss)
    if risk_per_share == 0:
        return {"error": "Entry and stop loss cannot be equal"}
    shares = int(risk_amount / risk_per_share)
    position_value = shares * entry_price
    return {
        "portfolio_value": portfolio_value,
        "risk_pct": risk_pct,
        "max_risk_amount": round(risk_amount, 2),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "risk_per_share": round(risk_per_share, 4),
        "shares": shares,
        "position_value": round(position_value, 2),
        "position_pct_of_portfolio": round(position_value / portfolio_value * 100, 2),
    }


def _handle_check_indicator_alignment(indicators: dict, direction: str) -> dict:
    checklist: list[dict] = []
    score = 0
    max_score = 0

    price = indicators.get("current_price", 0)
    ema20 = indicators.get("ema20") or price
    ema50 = indicators.get("ema50") or price
    ema200 = indicators.get("ema200")
    rsi = indicators.get("rsi_14") or 50
    macd_hist = indicators.get("macd_histogram") or 0
    macd_prev = indicators.get("macd_prev_histogram") or 0
    stoch_k = indicators.get("stoch_k") or 50
    stoch_d = indicators.get("stoch_d") or 50
    adx = indicators.get("adx") or 0
    adx_pos = indicators.get("adx_pos") or 0
    adx_neg = indicators.get("adx_neg") or 0
    bb_pos = indicators.get("bb_position") or 0.5
    vol_ratio = indicators.get("volume_ratio") or 1.0
    obv_trend = indicators.get("obv_trend", "falling")

    def check(name: str, condition: bool, weight: int = 1) -> None:
        nonlocal score, max_score
        max_score += weight
        if condition:
            score += weight
        checklist.append({"indicator": name, "aligned": condition, "weight": weight})

    if direction == "LONG":
        check("Price > EMA20", price > ema20, 2)
        check("Price > EMA50", price > ema50, 2)
        check("EMA20 > EMA50 (bullish stack)", ema20 > ema50, 2)
        check("EMA200 support" if ema200 else "EMA200 N/A", price > ema200 if ema200 else True, 1)
        check("RSI 40-65 (healthy zone)", 40 <= rsi <= 65, 2)
        check("RSI not overbought (<70)", rsi < 70, 1)
        check("MACD histogram positive", macd_hist > 0, 2)
        check("MACD histogram rising", macd_hist > macd_prev, 1)
        check("Stochastic not overbought (<80)", stoch_k < 80, 1)
        check("Stochastic bullish (K>D)", stoch_k > stoch_d, 1)
        check("ADX trend strength (>20)", adx > 20, 1)
        check("+DI > -DI (buyers in control)", adx_pos > adx_neg, 2)
        check("BB position < 0.7 (room to run)", bb_pos < 0.7, 1)
        check("Volume > average", vol_ratio >= 1.0, 1)
        check("OBV rising", obv_trend == "rising", 1)
    else:  # SHORT
        check("Price < EMA20", price < ema20, 2)
        check("Price < EMA50", price < ema50, 2)
        check("EMA20 < EMA50 (bearish stack)", ema20 < ema50, 2)
        check("EMA200 resistance" if ema200 else "EMA200 N/A", price < ema200 if ema200 else True, 1)
        check("RSI 35-60 (bearish zone)", 35 <= rsi <= 60, 2)
        check("RSI not oversold (>30)", rsi > 30, 1)
        check("MACD histogram negative", macd_hist < 0, 2)
        check("MACD histogram falling", macd_hist < macd_prev, 1)
        check("Stochastic not oversold (>20)", stoch_k > 20, 1)
        check("Stochastic bearish (K<D)", stoch_k < stoch_d, 1)
        check("ADX trend strength (>20)", adx > 20, 1)
        check("-DI > +DI (sellers in control)", adx_neg > adx_pos, 2)
        check("BB position > 0.3 (room to fall)", bb_pos > 0.3, 1)
        check("Volume > average", vol_ratio >= 1.0, 1)
        check("OBV falling", obv_trend == "falling", 1)

    alignment_score = round(score / max_score * 100, 1) if max_score > 0 else 0
    return {
        "direction": direction,
        "alignment_score": alignment_score,
        "checklist": checklist,
        "aligned_count": score,
        "total_checks": max_score,
        "aligned_indicators": [c["indicator"] for c in checklist if c["aligned"]],
        "conflicting_indicators": [c["indicator"] for c in checklist if not c["aligned"]],
    }


def _dispatch_tool(tool_name: str, tool_input: dict, portfolio_value: float) -> Any:
    if tool_name == "get_chart_data":
        return _handle_get_chart_data(tool_input["ticker"], tool_input.get("period", "6mo"))
    elif tool_name == "get_weekly_chart":
        return _handle_get_weekly_chart(tool_input["ticker"])
    elif tool_name == "calculate_position_size":
        return _handle_calculate_position_size(
            tool_input.get("portfolio_value", portfolio_value),
            tool_input.get("risk_pct", config.risk_per_trade),
            tool_input["entry_price"],
            tool_input["stop_loss"],
        )
    elif tool_name == "check_indicator_alignment":
        return _handle_check_indicator_alignment(
            tool_input["indicators"], tool_input["direction"]
        )
    elif tool_name == "submit_trade_plan":
        return tool_input
    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------
class TradeAnalyser:
    """
    Skill 4: Trade Analyser
    Determines precise entry/exit/stop levels for validated swing trade candidates.
    All major technical indicators must be checked for alignment.
    """

    SYSTEM_PROMPT = """You are an expert swing trader and technical analyst.
Your job is to determine precise trade entry/exit parameters for stocks approved by the Evaluator.

Swing trading rules:
- Holding period: 3–25 trading days
- Only trade with the higher-timeframe (weekly) trend
- Require at least 2:1 risk-to-reward minimum (prefer 3:1)
- Require >= 60% indicator alignment score for A/B grade setups
- Only issue SKIP for C-grade or worse setups

Entry strategies (choose based on setup):
1. PULLBACK ENTRY: Price pulled back to EMA20/EMA50 in uptrend — best entry
2. BREAKOUT ENTRY: Price breaking above key resistance with volume
3. REVERSAL ENTRY: Oversold bounce with multiple momentum indicators turning up

Stop loss methodology (use best fit):
1. ATR-based: Entry - (2.0 × ATR14) for longs
2. Swing low: Below the most recent significant swing low
3. EMA50: Below EMA50 for trend-following trades

Take profit levels:
- T1 (partial exit, 33% of position): 1:1 R:R from entry
- T2 (partial exit, 33% of position): 2:1 R:R from entry
- T3 (trail remaining, 34%): 3:1 R:R or trailing stop

Process:
1. Get daily chart data and indicators
2. Get weekly chart for higher-timeframe trend confirmation
3. Check full indicator alignment (use check_indicator_alignment tool)
4. Calculate position size (use 2% portfolio risk)
5. Submit trade plan with submit_trade_plan

IMPORTANT: Only grade A+ or A if alignment score >= 70%. Grade B for 55-70%. SKIP below 55%."""

    def __init__(self, portfolio_value: float | None = None) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        self.portfolio_value = portfolio_value

    def _get_portfolio_value(self) -> float:
        if self.portfolio_value:
            return self.portfolio_value
        try:
            import json as _json
            with open(config.portfolio_file) as f:
                portfolio = _json.load(f)
            cash = portfolio.get("cash", config.portfolio_cash)
            invested = portfolio.get("total_invested", 0)
            return cash + invested
        except Exception:
            return config.portfolio_cash

    def analyse_trade(self, evaluation: dict[str, Any]) -> dict[str, Any]:
        """
        Determine precise swing trade parameters for an evaluated stock.
        evaluation: output from Evaluator.evaluate()
        """
        ticker = evaluation.get("ticker", "UNKNOWN")
        validated_rec = evaluation.get("validated_recommendation", "HOLD")
        confluence = evaluation.get("confluence", "NO_CONFLUENCE")
        confluence_score = evaluation.get("confluence_score", 0)
        original = evaluation.get("original_analysis", {})
        portfolio_value = self._get_portfolio_value()

        direction = "LONG" if validated_rec in ("BUY", "STRONG_BUY") else "SHORT"

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Analyse the swing trade setup for {ticker}.\n\n"
                    f"Validated recommendation: {validated_rec} ({direction})\n"
                    f"Analyst confluence: {confluence} (score: {confluence_score}/100)\n"
                    f"Technical summary: {original.get('technical_summary', 'N/A')}\n"
                    f"Key strengths: {', '.join(original.get('key_strengths', []))}\n"
                    f"Key risks: {', '.join(original.get('key_risks', []))}\n"
                    f"Portfolio value: ${portfolio_value:,.2f}\n"
                    f"Risk per trade: {config.risk_per_trade*100:.1f}%\n\n"
                    f"Get chart data, check weekly trend, verify indicator alignment, "
                    f"calculate position size, then submit the complete trade plan."
                ),
            }
        ]
        final_result: dict = {}
        pv = portfolio_value

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
                    result = _dispatch_tool(block.name, block.input, pv)
                    if block.name == "submit_trade_plan":
                        final_result = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            if response.stop_reason == "end_turn" or not tool_results:
                if not final_result:
                    final_result = {
                        "ticker": ticker,
                        "direction": direction,
                        "trade_quality": "SKIP",
                        "trade_notes": "Failed to complete trade analysis",
                    }
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if final_result:
                break

        return final_result

    def analyse_batch(self, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Analyse trade setups for multiple evaluated stocks."""
        results = []
        for evaluation in evaluations:
            if not evaluation.get("proceed_to_trade_analysis", False):
                continue
            result = self.analyse_trade(evaluation)
            results.append(result)
        return results

    def filter_executable(self, trade_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only A+ and A grade setups ready for execution."""
        return [p for p in trade_plans if p.get("trade_quality") in ("A+", "A")]
