"""
PortfolioTracker — Skill 6
Monitors all open positions and decides when to act:
  - Updates unrealized P&L for every position
  - Checks stop loss / take profit triggers
  - Initiates re-analysis (via TradeAnalyser) when price action shifts
  - Routes to TradeExecutor for any triggered orders (stop, target, time exit)
  - Generates a periodic portfolio health report
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
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
# Portfolio I/O helpers (shared with TradeExecutor)
# ---------------------------------------------------------------------------
def _load_portfolio() -> dict:
    try:
        with open(config.portfolio_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"cash": config.portfolio_cash, "total_invested": 0.0, "positions": [], "trades_history": [], "performance": {}}


def _save_portfolio(portfolio: dict) -> None:
    with open(config.portfolio_file, "w") as f:
        json.dump(portfolio, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Position update helpers
# ---------------------------------------------------------------------------
def _update_position_prices(portfolio: dict) -> dict:
    """Refresh current prices and unrealized P&L for all open positions."""
    updated = 0
    for pos in portfolio["positions"]:
        if pos.get("status") != "OPEN":
            continue
        ticker = pos["ticker"]
        data = get_stock_data(ticker, period="5d", interval="1d")
        current_price = data.get("latest_price")
        if current_price is None:
            continue
        entry = pos["entry_price"]
        shares = pos["shares"]
        direction = pos.get("direction", "LONG")
        pnl = (current_price - entry) * shares if direction == "LONG" else (entry - current_price) * shares
        pnl_pct = (current_price - entry) / entry * 100 if direction == "LONG" else (entry - current_price) / entry * 100
        pos["current_price"] = round(current_price, 4)
        pos["unrealized_pnl"] = round(pnl, 2)
        pos["unrealized_pnl_pct"] = round(pnl_pct, 2)
        pos["last_updated"] = datetime.utcnow().isoformat()
        updated += 1
    return {"updated": updated}


def _check_trigger_conditions(position: dict) -> dict:
    """Check if stop loss or take profit levels have been hit."""
    ticker = position["ticker"]
    current = position.get("current_price")
    stop = position.get("stop_loss")
    t1 = position.get("target_1")
    t2 = position.get("target_2")
    t3 = position.get("target_3")
    direction = position.get("direction", "LONG")
    entry = position["entry_price"]
    entry_date_str = position.get("entry_date", "")

    triggers: list[str] = []
    action = "HOLD"

    if current is None:
        return {"ticker": ticker, "action": "HOLD", "triggers": ["Could not fetch price"]}

    # Stop loss check
    if direction == "LONG":
        if stop and current <= stop:
            triggers.append(f"STOP LOSS HIT: ${current} <= ${stop}")
            action = "CLOSE_STOP"
        elif t2 and current >= t2:
            triggers.append(f"TARGET 2 reached: ${current} >= ${t2} (2:1 R:R)")
            action = "CLOSE_T2" if not position.get("t2_hit") else "HOLD"
        elif t1 and current >= t1:
            triggers.append(f"TARGET 1 reached: ${current} >= ${t1} (1:1 R:R)")
            action = "ALERT_T1" if not position.get("t1_hit") else "HOLD"
    else:  # SHORT
        if stop and current >= stop:
            triggers.append(f"STOP LOSS HIT: ${current} >= ${stop}")
            action = "CLOSE_STOP"
        elif t2 and current <= t2:
            triggers.append(f"TARGET 2 reached: ${current} <= ${t2}")
            action = "CLOSE_T2" if not position.get("t2_hit") else "HOLD"

    # Time-based exit check (max holding period)
    if entry_date_str:
        try:
            entry_date = datetime.fromisoformat(entry_date_str)
            days_held = (datetime.utcnow() - entry_date).days
            if days_held > 25:
                triggers.append(f"MAX HOLDING PERIOD: {days_held} days held (max 25)")
                if action == "HOLD":
                    action = "CLOSE_TIME"
        except ValueError:
            pass

    # Significant adverse move (>= 50% of risk already lost)
    pnl_pct = position.get("unrealized_pnl_pct", 0)
    risk_pct = abs(entry - (stop or entry)) / entry * 100 if stop else 5
    if pnl_pct < -risk_pct * 0.5 and action == "HOLD":
        triggers.append(f"Warning: {pnl_pct:.1f}% adverse move (50% of risk used)")

    return {
        "ticker": ticker,
        "current_price": current,
        "action": action,
        "triggers": triggers,
        "unrealized_pnl_pct": pnl_pct,
    }


def _get_position_technical_status(ticker: str, position: dict) -> dict:
    """Quick technical status check for an open position."""
    data = get_stock_data(ticker, period="3mo", interval="1d")
    if "error" in data or not data.get("data"):
        return {"ticker": ticker, "error": "No data"}
    df = ohlcv_dataframe_from_records(data["data"])
    indicators = calculate_indicators(df)
    sr = find_support_resistance(df)
    trend = assess_trend(indicators)
    signals = get_swing_signals(indicators, sr)
    direction = position.get("direction", "LONG")

    # Is trend still valid for this trade?
    trend_dir = trend.get("direction", "SIDEWAYS")
    trend_valid = (
        (direction == "LONG" and "UPTREND" in trend_dir) or
        (direction == "SHORT" and "DOWNTREND" in trend_dir)
    )
    return {
        "ticker": ticker,
        "current_price": indicators.get("current_price"),
        "trend": trend,
        "rsi": indicators.get("rsi_14"),
        "macd_histogram": indicators.get("macd_histogram"),
        "swing_signals": signals,
        "nearest_support": sr.get("nearest_support"),
        "nearest_resistance": sr.get("nearest_resistance"),
        "trend_still_valid": trend_valid,
        "signal_bias": signals.get("bias"),
    }


# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------
_TOOLS: list[dict] = [
    {
        "name": "refresh_portfolio",
        "description": "Update all open position prices and unrealized P&L from live market data.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "check_position_triggers",
        "description": "Check a specific position for stop loss / target / time exit triggers.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_position_technicals",
        "description": "Get technical indicator status for an open position to check if the trade thesis is still valid.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_portfolio_overview",
        "description": "Get the full current portfolio state: cash, positions, P&L summary.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "recommend_action",
        "description": "Recommend a specific action for a position based on technical review.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": [
                        "HOLD",
                        "CLOSE_STOP_LOSS",
                        "CLOSE_TARGET",
                        "CLOSE_TIME_EXIT",
                        "TIGHTEN_STOP",
                        "PARTIAL_CLOSE",
                        "CLOSE_THESIS_BROKEN",
                    ],
                },
                "urgency": {"type": "string", "enum": ["IMMEDIATE", "NEXT_OPEN", "MONITOR"]},
                "rationale": {"type": "string"},
                "new_stop_loss": {"type": "number", "description": "Updated stop loss if tightening"},
            },
            "required": ["ticker", "action", "urgency", "rationale"],
        },
    },
    {
        "name": "submit_tracking_report",
        "description": "Submit the complete portfolio tracking report with all position reviews and recommended actions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "portfolio_value": {"type": "number"},
                "cash": {"type": "number"},
                "total_unrealized_pnl": {"type": "number"},
                "total_unrealized_pnl_pct": {"type": "number"},
                "positions_reviewed": {"type": "integer"},
                "position_reviews": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "status": {"type": "string"},
                            "unrealized_pnl_pct": {"type": "number"},
                            "action": {"type": "string"},
                            "urgency": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                    },
                },
                "immediate_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Actions requiring immediate execution",
                },
                "alerts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Non-urgent alerts and observations",
                },
                "overall_health": {
                    "type": "string",
                    "enum": ["STRONG", "HEALTHY", "MIXED", "CAUTION", "CRITICAL"],
                },
                "report_timestamp": {"type": "string"},
            },
            "required": [
                "portfolio_value", "cash", "total_unrealized_pnl",
                "positions_reviewed", "position_reviews", "immediate_actions",
                "overall_health",
            ],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatcher
# ---------------------------------------------------------------------------
def _dispatch_tool(tool_name: str, tool_input: dict, portfolio: dict) -> Any:
    if tool_name == "refresh_portfolio":
        result = _update_position_prices(portfolio)
        _save_portfolio(portfolio)
        return result
    elif tool_name == "check_position_triggers":
        ticker = tool_input["ticker"]
        pos = next((p for p in portfolio["positions"] if p["ticker"] == ticker and p["status"] == "OPEN"), None)
        if not pos:
            return {"error": f"No open position for {ticker}"}
        return _check_trigger_conditions(pos)
    elif tool_name == "get_position_technicals":
        ticker = tool_input["ticker"]
        pos = next((p for p in portfolio["positions"] if p["ticker"] == ticker and p["status"] == "OPEN"), None)
        if not pos:
            return {"error": f"No open position for {ticker}"}
        return _get_position_technical_status(ticker, pos)
    elif tool_name == "get_portfolio_overview":
        positions = [p for p in portfolio["positions"] if p.get("status") == "OPEN"]
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
        total_invested = portfolio.get("total_invested", 0)
        portfolio_value = portfolio["cash"] + sum(p.get("position_value", 0) + p.get("unrealized_pnl", 0) for p in positions)
        return {
            "cash": portfolio["cash"],
            "total_invested": total_invested,
            "portfolio_value": round(portfolio_value, 2),
            "total_unrealized_pnl": round(total_pnl, 2),
            "open_positions": len(positions),
            "performance": portfolio.get("performance", {}),
            "positions": positions,
        }
    elif tool_name == "recommend_action":
        return tool_input
    elif tool_name == "submit_tracking_report":
        result = {**tool_input, "report_timestamp": datetime.utcnow().isoformat()}
        return result
    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------
class PortfolioTracker:
    """
    Skill 6: Portfolio Tracker
    Monitors open positions, refreshes P&L, checks triggers,
    reviews trade thesis validity, and generates action reports.
    """

    SYSTEM_PROMPT = """You are a professional portfolio risk manager monitoring swing trade positions.

Your monitoring process:
1. Refresh all position prices (get latest market data)
2. For each open position:
   a) Check stop loss / target / time-exit triggers
   b) Review technical status (is the trend still valid?)
   c) Recommend action: HOLD, CLOSE (various reasons), TIGHTEN_STOP, or PARTIAL_CLOSE
3. Generate a comprehensive portfolio health report

Decision rules:
- CLOSE_STOP_LOSS: Stop price breached — IMMEDIATE action
- CLOSE_TARGET: T2 or T3 reached — book profits
- CLOSE_THESIS_BROKEN: Trend reversed, MACD bearish crossover, price below EMA50 for long — trade thesis no longer valid
- TIGHTEN_STOP: Position moved significantly in favour (>1.5:1) — trail the stop
- PARTIAL_CLOSE: At T1 (1:1 R:R) — consider closing 33% to reduce risk
- HOLD: Thesis intact, within expected parameters
- CLOSE_TIME_EXIT: Position held > 25 trading days

Be decisive — a good portfolio manager acts promptly on clear signals."""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def review(self) -> dict[str, Any]:
        """
        Run a full portfolio review cycle.
        Returns: tracking report with actions and alerts.
        """
        portfolio = _load_portfolio()
        open_positions = [p for p in portfolio["positions"] if p.get("status") == "OPEN"]

        if not open_positions:
            return {
                "message": "No open positions to track",
                "portfolio_value": portfolio["cash"],
                "cash": portfolio["cash"],
                "total_unrealized_pnl": 0,
                "positions_reviewed": 0,
                "position_reviews": [],
                "immediate_actions": [],
                "alerts": ["Portfolio is all-cash — ready to deploy"],
                "overall_health": "HEALTHY",
                "report_timestamp": datetime.utcnow().isoformat(),
            }

        positions_info = json.dumps(open_positions, indent=2, default=str)
        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Review the portfolio. Currently {len(open_positions)} open positions:\n\n"
                    f"{positions_info}\n\n"
                    f"Refresh prices, check each position for triggers and technical validity, "
                    f"then submit a complete tracking report."
                ),
            }
        ]
        final_report: dict = {}

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
                    result = _dispatch_tool(block.name, block.input, portfolio)
                    if block.name == "submit_tracking_report":
                        final_report = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            if response.stop_reason == "end_turn" or not tool_results:
                if not final_report:
                    for block in response.content:
                        if hasattr(block, "text"):
                            final_report = {"message": block.text, "immediate_actions": [], "overall_health": "UNKNOWN"}
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if final_report:
                break

        return final_report

    def monitor_loop(self, interval_seconds: int | None = None, max_cycles: int | None = None) -> None:
        """
        Run continuous monitoring loop.
        interval_seconds: time between reviews (default from config)
        max_cycles: maximum review cycles (None = run forever)
        """
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        interval = interval_seconds or config.refresh_interval
        cycle = 0

        console.print(Panel(
            f"[bold green]Portfolio Tracker Started[/bold green]\n"
            f"Review interval: {interval}s | Max cycles: {max_cycles or 'unlimited'}",
            title="Portfolio Monitor"
        ))

        while True:
            cycle += 1
            console.print(f"\n[cyan]--- Review Cycle {cycle} @ {datetime.utcnow().strftime('%H:%M:%S')} UTC ---[/cyan]")

            try:
                report = self.review()
                _print_tracking_report(report, console)

                # Route immediate actions back to executor
                if report.get("immediate_actions"):
                    console.print(f"[bold red]IMMEDIATE ACTIONS REQUIRED:[/bold red]")
                    for action in report["immediate_actions"]:
                        console.print(f"  [red]• {action}[/red]")
            except Exception as e:
                console.print(f"[red]Error during review: {e}[/red]")

            if max_cycles and cycle >= max_cycles:
                break

            console.print(f"[dim]Next review in {interval}s...[/dim]")
            time.sleep(interval)


def _print_tracking_report(report: dict, console: Any) -> None:
    """Pretty print a tracking report using Rich."""
    health_colors = {
        "STRONG": "bold green", "HEALTHY": "green", "MIXED": "yellow",
        "CAUTION": "bold yellow", "CRITICAL": "bold red",
    }
    health = report.get("overall_health", "UNKNOWN")
    color = health_colors.get(health, "white")

    console.print(f"Portfolio Health: [{color}]{health}[/{color}]")
    console.print(f"  Value: ${report.get('portfolio_value', 0):,.2f} | "
                  f"Cash: ${report.get('cash', 0):,.2f} | "
                  f"Unrealized P&L: ${report.get('total_unrealized_pnl', 0):+,.2f}")

    for rev in report.get("position_reviews", []):
        pnl = rev.get("unrealized_pnl_pct", 0)
        pnl_color = "green" if pnl >= 0 else "red"
        console.print(
            f"  [{pnl_color}]{rev['ticker']}[/{pnl_color}] "
            f"P&L: [{pnl_color}]{pnl:+.1f}%[/{pnl_color}] | "
            f"Action: {rev.get('action', 'HOLD')} ({rev.get('urgency', '')})"
        )

    for alert in report.get("alerts", []):
        console.print(f"  [yellow]⚠ {alert}[/yellow]")
