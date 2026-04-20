"""
Evaluator — Skill 3
Takes the StockAnalyser output and cross-validates against:
  - Wall Street analyst consensus (Yahoo Finance)
  - Analyst price targets vs current price
  - Upgrade/downgrade momentum from major firms
Returns a confluence score and a final validated recommendation.
"""
from __future__ import annotations

import json
from typing import Any

import anthropic

from ..config import config
from ..tools.market_data import get_analyst_recommendations, get_stock_info


# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------
_TOOLS: list[dict] = [
    {
        "name": "get_analyst_data",
        "description": "Fetch Wall Street analyst recommendations, price targets, and recent grade changes for a stock.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_valuation_context",
        "description": "Fetch current price vs analyst target prices to assess upside/downside potential.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "submit_evaluation",
        "description": "Submit the final evaluation with confluence assessment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "our_recommendation": {
                    "type": "string",
                    "description": "StockAnalyser recommendation (e.g. BUY)",
                },
                "analyst_consensus": {
                    "type": "string",
                    "description": "Wall Street consensus (e.g. buy, hold, sell)",
                },
                "confluence": {
                    "type": "string",
                    "enum": ["STRONG_CONFLUENCE", "PARTIAL_CONFLUENCE", "NO_CONFLUENCE", "CONTRARIAN"],
                    "description": "Degree of agreement between our analysis and Wall Street",
                },
                "confluence_score": {
                    "type": "number",
                    "description": "Confluence score 0-100 (100 = perfect alignment)",
                },
                "validated_recommendation": {
                    "type": "string",
                    "enum": ["STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL", "SKIP"],
                    "description": "Final recommendation after evaluating confluence. SKIP if no confluence and contrarian risk is high.",
                },
                "analyst_upside_pct": {
                    "type": "number",
                    "description": "% upside from current price to mean analyst target",
                },
                "analyst_buy_pct": {
                    "type": "number",
                    "description": "% of analysts with buy/strong-buy ratings",
                },
                "recent_upgrades": {
                    "type": "number",
                    "description": "Number of upgrades in last 30 days",
                },
                "recent_downgrades": {
                    "type": "number",
                    "description": "Number of downgrades in last 30 days",
                },
                "upgrade_momentum": {
                    "type": "string",
                    "enum": ["POSITIVE", "NEUTRAL", "NEGATIVE"],
                },
                "evaluation_notes": {
                    "type": "string",
                    "description": "Key observations from the confluence analysis",
                },
                "proceed_to_trade_analysis": {
                    "type": "boolean",
                    "description": "True if this stock should proceed to trade analysis (BUY or STRONG_BUY with reasonable confluence)",
                },
            },
            "required": [
                "ticker", "our_recommendation", "analyst_consensus",
                "confluence", "confluence_score", "validated_recommendation",
                "evaluation_notes", "proceed_to_trade_analysis",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
def _handle_get_analyst_data(ticker: str) -> dict:
    return get_analyst_recommendations(ticker)


def _handle_get_valuation_context(ticker: str) -> dict:
    info = get_stock_info(ticker)
    current_price = info.get("analyst_target") and info  # keep full info for context
    return {
        "ticker": ticker,
        "current_price": None,  # filled from info
        "analyst_target_mean": info.get("analyst_target_price"),
        "analyst_target_high": info.get("analyst_target_high"),
        "analyst_target_low": info.get("analyst_target_low"),
        "recommendation_key": info.get("recommendation_key"),
        "num_analysts": info.get("number_of_analyst_opinions"),
        "pe_ratio": info.get("pe_ratio"),
        "52w_high": info.get("52w_high"),
        "52w_low": info.get("52w_low"),
    }


def _dispatch_tool(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "get_analyst_data":
        return _handle_get_analyst_data(tool_input["ticker"])
    elif tool_name == "get_valuation_context":
        return _handle_get_valuation_context(tool_input["ticker"])
    elif tool_name == "submit_evaluation":
        return tool_input
    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------
class Evaluator:
    """
    Skill 3: Evaluator
    Validates StockAnalyser findings against Wall Street analyst consensus
    and returns a confluence-scored final recommendation.
    """

    SYSTEM_PROMPT = """You are a senior investment analyst responsible for quality-control and validation.
You receive a stock analysis from an AI analyst and must cross-validate it against Wall Street consensus.

Your evaluation process:
1. Fetch analyst recommendations and grade history for the stock.
2. Fetch valuation context (price targets vs current price).
3. Assess the following:
   a) DIRECTION CONFLUENCE: Does our recommendation align with analyst consensus?
      - STRONG_CONFLUENCE: Both bullish (or both bearish)
      - PARTIAL_CONFLUENCE: Mildly aligned (e.g. our BUY vs their HOLD)
      - NO_CONFLUENCE: Opposite directions
      - CONTRARIAN: We are deliberately going against consensus (risky, needs justification)
   b) ANALYST MOMENTUM: Are there more recent upgrades or downgrades?
   c) UPSIDE POTENTIAL: What % upside does the mean analyst target imply?
   d) ANALYST CONVICTION: What % of analysts have buy/strong-buy ratings?

4. Compute a confluence score (0-100) and decide whether to:
   - Confirm and proceed (BUY/STRONG_BUY with adequate confluence)
   - Downgrade (reduce conviction due to analyst disagreement)
   - SKIP (no confluence + high contrarian risk + no strong catalyst)

5. Use submit_evaluation with your final verdict.

Be conservative — it is better to SKIP a questionable trade than to force a bad one."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def evaluate(self, stock_analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Evaluate a single stock analysis for confluence.
        stock_analysis: output from StockAnalyser.analyse()
        """
        ticker = stock_analysis.get("ticker", "UNKNOWN")
        our_rec = stock_analysis.get("recommendation", "HOLD")
        our_confidence = stock_analysis.get("confidence", 50)
        our_score = stock_analysis.get("overall_score", 50)
        swing_bias = stock_analysis.get("swing_bias", "NEUTRAL")

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Evaluate {ticker} for confluence with Wall Street analysts.\n\n"
                    f"Our analysis summary:\n"
                    f"- Recommendation: {our_rec}\n"
                    f"- Confidence: {our_confidence}/100\n"
                    f"- Overall score: {our_score}/100\n"
                    f"- Swing bias: {swing_bias}\n"
                    f"- Key strengths: {', '.join(stock_analysis.get('key_strengths', []))}\n"
                    f"- Key risks: {', '.join(stock_analysis.get('key_risks', []))}\n\n"
                    f"Fetch analyst data and valuation context, then submit your evaluation."
                ),
            }
        ]
        final_result: dict = {}

        while True:
            response = self.client.messages.create(
                model=config.model,
                max_tokens=4096,
                system=self.SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _dispatch_tool(block.name, block.input)
                    if block.name == "submit_evaluation":
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
                        "our_recommendation": our_rec,
                        "analyst_consensus": "unknown",
                        "confluence": "NO_CONFLUENCE",
                        "confluence_score": 0,
                        "validated_recommendation": "HOLD",
                        "evaluation_notes": "Failed to retrieve analyst data",
                        "proceed_to_trade_analysis": False,
                    }
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if final_result:
                break

        # Attach original analysis for downstream use
        final_result["original_analysis"] = stock_analysis
        return final_result

    def evaluate_batch(self, analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Evaluate multiple analyses and filter to those that proceed."""
        results = []
        for analysis in analyses:
            if "error" in analysis:
                continue
            result = self.evaluate(analysis)
            results.append(result)
        return results

    def filter_actionable(self, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return only evaluations that should proceed to trade analysis."""
        return [e for e in evaluations if e.get("proceed_to_trade_analysis", False)]
