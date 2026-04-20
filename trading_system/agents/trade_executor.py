"""
TradeExecutor — Skill 5
Takes trade plans from TradeAnalyser and executes them.

Modes:
  - PAPER (default): Simulates execution, records in portfolio.json
  - LIVE: Placeholder for real broker integration (Alpaca / IBKR)

Responsibilities:
  - Validate trade plan (price, size, funds available)
  - Execute entry order (market or limit)
  - Record position in portfolio with full trade metadata
  - Update cash balance and portfolio stats
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import anthropic

from ..config import config
from ..tools.market_data import get_stock_data


# ---------------------------------------------------------------------------
# Portfolio I/O helpers
# ---------------------------------------------------------------------------
def _load_portfolio() -> dict:
    try:
        with open(config.portfolio_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "cash": config.portfolio_cash,
            "total_invested": 0.0,
            "positions": [],
            "trades_history": [],
            "performance": {
                "total_return_pct": 0.0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
            },
        }


def _save_portfolio(portfolio: dict) -> None:
    with open(config.portfolio_file, "w") as f:
        json.dump(portfolio, f, indent=2, default=str)


def _get_current_price(ticker: str) -> float | None:
    data = get_stock_data(ticker, period="5d", interval="1d")
    return data.get("latest_price")


# ---------------------------------------------------------------------------
# Execution logic
# ---------------------------------------------------------------------------
def _execute_paper_trade(trade_plan: dict, portfolio: dict) -> dict:
    """Simulate order execution for paper trading."""
    ticker = trade_plan["ticker"]
    direction = trade_plan.get("direction", "LONG")
    entry_type = trade_plan.get("entry_type", "MARKET")
    target_entry = trade_plan.get("entry_price", 0)
    stop_loss = trade_plan.get("stop_loss", 0)
    target_1 = trade_plan.get("target_1")
    target_2 = trade_plan.get("target_2")
    target_3 = trade_plan.get("target_3")
    shares = int(trade_plan.get("position_size_shares", 0))
    max_risk = trade_plan.get("max_risk_amount", 0)

    # Get current market price
    current_price = _get_current_price(ticker)
    if current_price is None:
        return {"success": False, "error": f"Could not fetch current price for {ticker}"}

    # Determine fill price (paper trading: use limit if within 0.5% of current, else market)
    if entry_type == "MARKET":
        fill_price = current_price
    elif abs(current_price - target_entry) / target_entry <= 0.005:
        fill_price = target_entry  # limit filled
    else:
        fill_price = current_price  # slippage to market

    total_cost = fill_price * shares

    # Check funds
    if direction == "LONG" and total_cost > portfolio["cash"]:
        max_shares = int(portfolio["cash"] / fill_price)
        if max_shares < 1:
            return {"success": False, "error": "Insufficient cash for this position"}
        shares = max_shares
        total_cost = fill_price * shares

    # Check duplicate position
    existing = [p for p in portfolio["positions"] if p["ticker"] == ticker]
    if existing:
        return {"success": False, "error": f"Position already exists for {ticker}"}

    now = datetime.utcnow().isoformat()
    position = {
        "id": f"{ticker}_{now[:10].replace('-','')}",
        "ticker": ticker,
        "direction": direction,
        "entry_price": round(fill_price, 4),
        "shares": shares,
        "position_value": round(total_cost, 2),
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "target_3": target_3,
        "risk_reward_ratio": trade_plan.get("risk_reward_ratio"),
        "max_risk_amount": round(max_risk, 2),
        "entry_date": now,
        "status": "OPEN",
        "trade_quality": trade_plan.get("trade_quality"),
        "entry_catalyst": trade_plan.get("entry_catalyst", ""),
        "holding_period": trade_plan.get("holding_period_days", "5-15 days"),
        "current_price": round(fill_price, 4),
        "unrealized_pnl": 0.0,
        "unrealized_pnl_pct": 0.0,
        "t1_hit": False,
        "t2_hit": False,
    }

    # Update portfolio
    portfolio["positions"].append(position)
    if direction == "LONG":
        portfolio["cash"] = round(portfolio["cash"] - total_cost, 2)
        portfolio["total_invested"] = round(portfolio["total_invested"] + total_cost, 2)

    return {
        "success": True,
        "position": position,
        "fill_price": fill_price,
        "shares": shares,
        "total_cost": round(total_cost, 2),
        "remaining_cash": portfolio["cash"],
        "mode": "PAPER",
    }


def _close_position(ticker: str, portfolio: dict, reason: str = "MANUAL") -> dict:
    """Close an open position and record the trade."""
    position = next((p for p in portfolio["positions"] if p["ticker"] == ticker and p["status"] == "OPEN"), None)
    if not position:
        return {"success": False, "error": f"No open position for {ticker}"}

    current_price = _get_current_price(ticker)
    if current_price is None:
        return {"success": False, "error": f"Could not fetch price for {ticker}"}

    exit_price = current_price
    shares = position["shares"]
    entry_price = position["entry_price"]
    direction = position.get("direction", "LONG")

    pnl = (exit_price - entry_price) * shares if direction == "LONG" else (entry_price - exit_price) * shares
    pnl_pct = (exit_price - entry_price) / entry_price * 100 if direction == "LONG" else (entry_price - exit_price) / entry_price * 100

    # Record completed trade
    trade_record = {
        **position,
        "exit_price": round(exit_price, 4),
        "exit_date": datetime.utcnow().isoformat(),
        "realized_pnl": round(pnl, 2),
        "realized_pnl_pct": round(pnl_pct, 2),
        "exit_reason": reason,
        "status": "CLOSED",
    }

    # Update portfolio
    portfolio["positions"] = [p for p in portfolio["positions"] if not (p["ticker"] == ticker and p["status"] == "OPEN")]
    portfolio["trades_history"].append(trade_record)
    portfolio["cash"] = round(portfolio["cash"] + exit_price * shares, 2)
    portfolio["total_invested"] = max(0.0, round(portfolio["total_invested"] - entry_price * shares, 2))

    # Update performance stats
    perf = portfolio["performance"]
    perf["total_trades"] = perf.get("total_trades", 0) + 1
    perf["total_pnl"] = round(perf.get("total_pnl", 0) + pnl, 2)
    if pnl > 0:
        perf["winning_trades"] = perf.get("winning_trades", 0) + 1
    perf["win_rate"] = round(perf["winning_trades"] / perf["total_trades"] * 100, 1)

    return {
        "success": True,
        "ticker": ticker,
        "exit_price": exit_price,
        "realized_pnl": round(pnl, 2),
        "realized_pnl_pct": round(pnl_pct, 2),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Claude tool definitions
# ---------------------------------------------------------------------------
_TOOLS: list[dict] = [
    {
        "name": "validate_trade",
        "description": "Validate a trade plan against current portfolio state, available cash, and risk limits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "shares": {"type": "integer"},
                "entry_price": {"type": "number"},
                "stop_loss": {"type": "number"},
                "max_risk_amount": {"type": "number"},
            },
            "required": ["ticker", "shares", "entry_price", "stop_loss"],
        },
    },
    {
        "name": "execute_entry",
        "description": "Execute a trade entry for a validated trade plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trade_plan": {
                    "type": "object",
                    "description": "Complete trade plan from TradeAnalyser",
                }
            },
            "required": ["trade_plan"],
        },
    },
    {
        "name": "close_position",
        "description": "Close an existing open position.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "reason": {
                    "type": "string",
                    "enum": ["STOP_LOSS_HIT", "TARGET_HIT", "MANUAL", "TRAILING_STOP", "TIME_EXIT"],
                },
            },
            "required": ["ticker", "reason"],
        },
    },
    {
        "name": "get_portfolio_state",
        "description": "Get current portfolio summary: cash, positions, invested amount, P&L.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "submit_execution_result",
        "description": "Submit the execution result summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["ENTERED", "CLOSED", "REJECTED", "QUEUED"]},
                "ticker": {"type": "string"},
                "details": {"type": "object"},
                "reason": {"type": "string"},
                "portfolio_summary": {"type": "object"},
            },
            "required": ["action", "ticker", "details", "reason"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------
def _handle_validate_trade(portfolio: dict, ticker: str, shares: int, entry_price: float, stop_loss: float, max_risk: float | None = None) -> dict:
    total_cost = shares * entry_price
    cash = portfolio["cash"]
    positions = portfolio["positions"]
    open_tickers = [p["ticker"] for p in positions if p["status"] == "OPEN"]
    num_positions = len(positions)

    issues: list[str] = []
    if total_cost > cash:
        issues.append(f"Insufficient cash: need ${total_cost:,.2f}, have ${cash:,.2f}")
    if ticker in open_tickers:
        issues.append(f"Already have open position in {ticker}")
    if num_positions >= config.max_positions:
        issues.append(f"Max positions ({config.max_positions}) already reached")
    if entry_price <= stop_loss:
        issues.append("Entry price must be above stop loss for LONG trades")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "cash_available": cash,
        "total_cost": round(total_cost, 2),
        "open_positions": num_positions,
        "max_positions": config.max_positions,
    }


def _handle_get_portfolio_state(portfolio: dict) -> dict:
    positions = portfolio.get("positions", [])
    total_value = sum(p.get("position_value", 0) for p in positions if p.get("status") == "OPEN")
    return {
        "cash": portfolio["cash"],
        "total_invested": portfolio["total_invested"],
        "portfolio_value": round(portfolio["cash"] + total_value, 2),
        "open_positions": len([p for p in positions if p.get("status") == "OPEN"]),
        "max_positions": config.max_positions,
        "performance": portfolio.get("performance", {}),
        "positions_summary": [
            {
                "ticker": p["ticker"],
                "direction": p.get("direction"),
                "shares": p.get("shares"),
                "entry_price": p.get("entry_price"),
                "current_price": p.get("current_price"),
                "unrealized_pnl": p.get("unrealized_pnl", 0),
            }
            for p in positions
            if p.get("status") == "OPEN"
        ],
    }


def _dispatch_tool(tool_name: str, tool_input: dict, portfolio: dict) -> Any:
    if tool_name == "validate_trade":
        return _handle_validate_trade(
            portfolio,
            tool_input["ticker"],
            tool_input["shares"],
            tool_input["entry_price"],
            tool_input["stop_loss"],
            tool_input.get("max_risk_amount"),
        )
    elif tool_name == "execute_entry":
        result = _execute_paper_trade(tool_input["trade_plan"], portfolio)
        if result.get("success"):
            _save_portfolio(portfolio)
        return result
    elif tool_name == "close_position":
        result = _close_position(tool_input["ticker"], portfolio, tool_input.get("reason", "MANUAL"))
        if result.get("success"):
            _save_portfolio(portfolio)
        return result
    elif tool_name == "get_portfolio_state":
        return _handle_get_portfolio_state(portfolio)
    elif tool_name == "submit_execution_result":
        return tool_input
    return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------
class TradeExecutor:
    """
    Skill 5: Trade Executor
    Validates and executes trade plans in paper or live mode.
    Manages portfolio state (positions, cash, P&L).
    """

    SYSTEM_PROMPT = """You are a trade execution system responsible for safely executing swing trades.

Your process for ENTERING a trade:
1. Get the current portfolio state (check cash, open positions count)
2. Validate the trade against: available cash, max positions, no duplicate tickers, sensible prices
3. If validation passes, execute the entry order
4. Submit execution result

Your process for CLOSING a position:
1. Confirm the position exists
2. Execute the close
3. Report realized P&L

Rules:
- NEVER execute a trade that fails validation
- In PAPER mode, fills are simulated at limit/market price
- Always confirm remaining cash and portfolio value after execution
- Be precise with position sizing — never exceed the max risk amount"""

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def execute(self, trade_plan: dict[str, Any]) -> dict[str, Any]:
        """Execute a single trade plan."""
        ticker = trade_plan.get("ticker", "UNKNOWN")
        quality = trade_plan.get("trade_quality", "C")
        portfolio = _load_portfolio()

        if quality == "SKIP":
            return {
                "action": "REJECTED",
                "ticker": ticker,
                "reason": f"Trade quality is SKIP — not executing",
                "details": {},
            }

        messages: list[dict] = [
            {
                "role": "user",
                "content": (
                    f"Execute the following swing trade for {ticker} in {config.trading_mode.upper()} mode:\n\n"
                    f"Direction: {trade_plan.get('direction')}\n"
                    f"Entry price: ${trade_plan.get('entry_price', 0):,.4f}\n"
                    f"Entry type: {trade_plan.get('entry_type')}\n"
                    f"Shares: {trade_plan.get('position_size_shares')}\n"
                    f"Stop loss: ${trade_plan.get('stop_loss', 0):,.4f}\n"
                    f"Target 1: ${trade_plan.get('target_1', 0):,.4f}\n"
                    f"Target 2: ${trade_plan.get('target_2', 0):,.4f}\n"
                    f"Target 3: ${trade_plan.get('target_3', 0):,.4f}\n"
                    f"Max risk: ${trade_plan.get('max_risk_amount', 0):,.2f}\n"
                    f"Trade quality: {quality}\n\n"
                    f"Check portfolio state, validate, then execute if valid."
                ),
            }
        ]
        final_result: dict = {}

        while True:
            response = self.client.messages.create(
                model=config.model,
                max_tokens=3072,
                system=self.SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = _dispatch_tool(block.name, block.input, portfolio)
                    if block.name == "submit_execution_result":
                        final_result = result
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            if response.stop_reason == "end_turn" or not tool_results:
                if not final_result:
                    final_result = {"action": "REJECTED", "ticker": ticker, "reason": "Execution agent ended without result", "details": {}}
                break

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

            if final_result:
                break

        return final_result

    def close_trade(self, ticker: str, reason: str = "MANUAL") -> dict[str, Any]:
        """Manually close a position."""
        portfolio = _load_portfolio()
        result = _close_position(ticker, portfolio, reason)
        if result.get("success"):
            _save_portfolio(portfolio)
        return result

    def get_portfolio(self) -> dict[str, Any]:
        """Return current portfolio state."""
        return _load_portfolio()

    def execute_batch(self, trade_plans: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Execute multiple trade plans."""
        results = []
        for plan in trade_plans:
            result = self.execute(plan)
            results.append(result)
        return results
