"""
WatchlistScanner — Skill 1
Loads tickers from watchlist.json (or a provided file/list), fetches
quick snapshots from Yahoo Finance, applies basic filters, and returns
a ranked shortlist of stocks to analyse.
Claude is used to interpret the scan results and flag the most promising candidates.
"""
from __future__ import annotations

import json
import os
from typing import Any

import anthropic

from ..config import config
from ..tools.market_data import get_multiple_stocks_snapshot, get_stock_data


# ---------------------------------------------------------------------------
# Claude tool definitions for this agent
# ---------------------------------------------------------------------------
_TOOLS: list[dict] = [
    {
        "name": "get_watchlist",
        "description": "Load the watchlist of tickers from the configured JSON file.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "scan_tickers",
        "description": "Fetch live price, volume, market-cap snapshot for a list of tickers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols to scan.",
                }
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "get_price_history",
        "description": "Get recent price history (momentum check) for a ticker.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {"type": "string", "description": "e.g. '1mo', '3mo'"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "apply_filters",
        "description": "Apply basic quantitative filters (volume, market cap, % from 52w high) to a snapshot list and return passing tickers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "snapshot": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Snapshot list returned by scan_tickers.",
                },
                "min_volume": {"type": "number", "description": "Minimum daily volume"},
                "min_market_cap": {"type": "number", "description": "Minimum market cap in USD"},
            },
            "required": ["snapshot"],
        },
    },
    {
        "name": "finalize_shortlist",
        "description": "Return the final prioritised shortlist of tickers with scan summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Prioritised ticker list.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Brief explanation of selection criteria applied.",
                },
                "scan_summary": {
                    "type": "object",
                    "description": "Key stats about the scan (total scanned, passed filters, etc.)",
                },
            },
            "required": ["tickers", "rationale"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handler implementations
# ---------------------------------------------------------------------------
def _handle_get_watchlist() -> dict:
    try:
        with open(config.watchlist_file) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"tickers": [], "error": "Watchlist file not found"}


def _handle_scan_tickers(tickers: list[str]) -> list[dict]:
    return get_multiple_stocks_snapshot(tickers)


def _handle_get_price_history(ticker: str, period: str = "1mo") -> dict:
    result = get_stock_data(ticker, period=period, interval="1d")
    # Trim data to just recent summary to save tokens
    trimmed = {k: v for k, v in result.items() if k != "data"}
    if "data" in result:
        trimmed["last_5_closes"] = [d["close"] for d in result["data"][-5:]]
    return trimmed


def _handle_apply_filters(
    snapshot: list[dict],
    min_volume: float = 500_000,
    min_market_cap: float = 1_000_000_000,
) -> list[dict]:
    passing = []
    for s in snapshot:
        if "error" in s:
            continue
        vol = s.get("volume") or 0
        cap = s.get("market_cap") or 0
        if vol >= min_volume and cap >= min_market_cap:
            passing.append(s)
    return passing


def _dispatch_tool(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "get_watchlist":
        return _handle_get_watchlist()
    elif tool_name == "scan_tickers":
        return _handle_scan_tickers(tool_input["tickers"])
    elif tool_name == "get_price_history":
        return _handle_get_price_history(tool_input["ticker"], tool_input.get("period", "1mo"))
    elif tool_name == "apply_filters":
        return _handle_apply_filters(
            tool_input["snapshot"],
            tool_input.get("min_volume", 500_000),
            tool_input.get("min_market_cap", 1_000_000_000),
        )
    elif tool_name == "finalize_shortlist":
        return tool_input  # stored as the final result
    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------
class WatchlistScanner:
    """
    Skill 1: Watchlist Scanner
    Scans the configured watchlist, applies filters, and returns a
    prioritised list of stocks for further analysis.
    """

    SYSTEM_PROMPT = """You are a professional stock market scanner for swing trading.
Your job is to:
1. Load the watchlist of tickers.
2. Fetch live snapshots of all tickers.
3. Apply volume and market-cap filters to remove illiquid stocks.
4. Review any recent momentum data if needed.
5. Return a final shortlist of the MOST PROMISING tickers for swing trade analysis.

Focus on stocks with:
- Strong liquidity (high average volume)
- Significant market cap (reduces manipulation risk)
- Recent relative strength (not in free-fall)
- Reasonable position from their 52-week range

Use the finalize_shortlist tool as your final action."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def scan(self, custom_tickers: list[str] | None = None) -> dict[str, Any]:
        """
        Run the watchlist scan.
        Returns: {"tickers": [...], "rationale": "...", "scan_summary": {...}}
        """
        user_msg = "Scan the watchlist and return the top candidates for swing trade analysis today."
        if custom_tickers:
            tickers_str = ", ".join(custom_tickers)
            user_msg = f"Scan these specific tickers for swing trade analysis: {tickers_str}"

        messages: list[dict] = [{"role": "user", "content": user_msg}]
        final_result: dict = {}

        while True:
            response = self.client.messages.create(
                model=config.model,
                max_tokens=4096,
                system=self.SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            # Collect tool calls
            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _dispatch_tool(block.name, block.input)
                    if block.name == "finalize_shortlist":
                        final_result = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            if response.stop_reason == "end_turn" or not tool_results:
                # Extract text summary if no finalize_shortlist was called
                if not final_result:
                    for block in response.content:
                        if hasattr(block, "text"):
                            final_result = {"tickers": [], "rationale": block.text}
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if final_result:
                break

        return final_result
