#!/usr/bin/env python3
"""
Agentic Stock Trading System — Main Orchestrator
=================================================
Skills pipeline:
  1. WatchlistScanner  → scan + filter tradeable candidates
  2. StockAnalyser     → fundamental + technical + sentiment analysis
  3. Evaluator         → analyst confluence validation
  4. TradeAnalyser     → precise entry/exit/stop for swing trades
  5. TradeExecutor     → paper/live order execution + portfolio update
  6. PortfolioTracker  → continuous monitoring + alerts

Usage:
  python main.py run           # Full pipeline (scan → execute)
  python main.py scan          # Watchlist scan only
  python main.py analyse AAPL MSFT   # Analyse specific tickers
  python main.py portfolio     # Show portfolio status
  python main.py track         # Run portfolio monitor loop
  python main.py close AAPL    # Close a position manually
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from trading_system.agents.evaluator import Evaluator
from trading_system.agents.portfolio_tracker import PortfolioTracker
from trading_system.agents.stock_analyser import StockAnalyser
from trading_system.agents.trade_analyser import TradeAnalyser
from trading_system.agents.trade_executor import TradeExecutor
from trading_system.agents.watchlist_scanner import WatchlistScanner
from trading_system.config import config

console = Console()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def _rec_color(rec: str) -> str:
    rec = rec.upper()
    if rec in ("STRONG_BUY", "BUY"):
        return "bold green"
    elif rec in ("HOLD",):
        return "yellow"
    elif rec in ("SELL", "STRONG_SELL"):
        return "bold red"
    return "white"


def _quality_color(q: str) -> str:
    return {"A+": "bold green", "A": "green", "B": "yellow", "C": "red", "SKIP": "dim"}.get(q, "white")


def print_banner() -> None:
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]Agentic Stock Trading System[/bold cyan]\n"
            "[dim]Skills: WatchlistScanner → StockAnalyser → Evaluator → TradeAnalyser → TradeExecutor → PortfolioTracker[/dim]\n"
            f"[dim]Mode: [bold]{config.trading_mode.upper()}[/bold] | "
            f"Model: {config.model} | "
            f"Risk/trade: {config.risk_per_trade*100:.0f}%[/dim]"
        ),
        border_style="cyan",
    ))


def print_scan_results(scan_result: dict) -> None:
    tickers = scan_result.get("tickers", [])
    rationale = scan_result.get("rationale", "")
    summary = scan_result.get("scan_summary", {})

    table = Table(title="[bold]Watchlist Scan Results[/bold]", border_style="cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("Ticker", style="bold cyan")
    for i, ticker in enumerate(tickers, 1):
        table.add_row(str(i), ticker)

    console.print(table)
    if rationale:
        console.print(Panel(rationale, title="Scanner Rationale", border_style="dim"))


def print_analysis(analysis: dict) -> None:
    ticker = analysis.get("ticker", "?")
    rec = analysis.get("recommendation", "HOLD")
    confidence = analysis.get("confidence", 0)
    f_score = analysis.get("fundamental_score", 0)
    t_score = analysis.get("technical_score", 0)
    s_score = analysis.get("sentiment_score", 0)
    o_score = analysis.get("overall_score", 0)
    strengths = analysis.get("key_strengths", [])
    risks = analysis.get("key_risks", [])

    color = _rec_color(rec)
    table = Table(title=f"[bold]{ticker}[/bold] Analysis", border_style="blue")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Recommendation", f"[{color}]{rec}[/{color}]")
    table.add_row("Confidence", f"{confidence}/100")
    table.add_row("Fundamental Score", f"{f_score}/100")
    table.add_row("Technical Score", f"{t_score}/100")
    table.add_row("Sentiment Score", f"{s_score}/100")
    table.add_row("Overall Score", f"[bold]{o_score}/100[/bold]")
    table.add_row("Swing Bias", analysis.get("swing_bias", "N/A"))

    console.print(table)
    if strengths:
        console.print("[green]Strengths:[/green] " + " | ".join(strengths))
    if risks:
        console.print("[red]Risks:[/red] " + " | ".join(risks))


def print_evaluation(evaluation: dict) -> None:
    ticker = evaluation.get("ticker", "?")
    confluence = evaluation.get("confluence", "N/A")
    score = evaluation.get("confluence_score", 0)
    validated = evaluation.get("validated_recommendation", "HOLD")
    color = _rec_color(validated)
    proceed = evaluation.get("proceed_to_trade_analysis", False)

    console.print(
        f"  [bold]{ticker}[/bold] | Confluence: {confluence} ({score}/100) | "
        f"Validated: [{color}]{validated}[/{color}] | "
        f"Proceed: {'[green]YES[/green]' if proceed else '[red]NO[/red]'}"
    )


def print_trade_plan(plan: dict) -> None:
    ticker = plan.get("ticker", "?")
    quality = plan.get("trade_quality", "?")
    q_color = _quality_color(quality)
    direction = plan.get("direction", "?")
    entry = plan.get("entry_price", 0)
    stop = plan.get("stop_loss", 0)
    t1 = plan.get("target_1", 0)
    t2 = plan.get("target_2", 0)
    t3 = plan.get("target_3", 0)
    rr = plan.get("risk_reward_ratio", 0)
    shares = plan.get("position_size_shares", 0)
    value = plan.get("position_size_value", 0)
    risk_amt = plan.get("max_risk_amount", 0)
    alignment = plan.get("indicator_alignment_score", 0)

    table = Table(title=f"[{q_color}][{quality}][/{q_color}] {ticker} Trade Plan", border_style="green")
    table.add_column("Parameter", style="bold")
    table.add_column("Value")
    table.add_row("Direction", f"[{'green' if direction=='LONG' else 'red'}]{direction}[/]")
    table.add_row("Entry Price", f"${entry:,.4f} ({plan.get('entry_type', '')})")
    table.add_row("Stop Loss", f"${stop:,.4f} ({plan.get('stop_loss_method', '')})")
    table.add_row("Target 1 (1:1)", f"${t1:,.4f}" if t1 else "N/A")
    table.add_row("Target 2 (2:1)", f"${t2:,.4f}" if t2 else "N/A")
    table.add_row("Target 3 (3:1)", f"${t3:,.4f}" if t3 else "N/A")
    table.add_row("R:R Ratio", f"{rr:.2f}:1" if rr else "N/A")
    table.add_row("Shares", str(shares))
    table.add_row("Position Value", f"${value:,.2f}")
    table.add_row("Max Risk", f"${risk_amt:,.2f}")
    table.add_row("Indicator Alignment", f"{alignment:.1f}%")
    table.add_row("Holding Period", plan.get("holding_period_days", "N/A"))
    table.add_row("Trade Quality", f"[{q_color}]{quality}[/{q_color}]")
    console.print(table)

    if plan.get("aligned_indicators"):
        console.print("[green]Aligned:[/green] " + " | ".join(plan["aligned_indicators"][:5]))
    if plan.get("conflicting_indicators"):
        console.print("[red]Conflicting:[/red] " + " | ".join(plan["conflicting_indicators"][:3]))
    if plan.get("entry_catalyst"):
        console.print(f"[cyan]Entry catalyst:[/cyan] {plan['entry_catalyst']}")


def print_execution_result(result: dict) -> None:
    action = result.get("action", "?")
    ticker = result.get("ticker", "?")
    color = "green" if action == "ENTERED" else "red" if action == "REJECTED" else "yellow"
    console.print(f"  [{color}]{action}[/{color}] {ticker}: {result.get('reason', '')}")
    if action == "ENTERED" and result.get("details"):
        d = result["details"]
        pos = d.get("position", d)
        fill = d.get("fill_price") or pos.get("entry_price")
        shares = d.get("shares") or pos.get("shares")
        cost = d.get("total_cost") or pos.get("position_value")
        cash_left = d.get("remaining_cash")
        if fill:
            console.print(f"    Fill: ${fill:,.4f} × {shares} shares = ${cost:,.2f}")
        if cash_left:
            console.print(f"    Remaining cash: ${cash_left:,.2f}")


def print_portfolio(portfolio: dict) -> None:
    cash = portfolio.get("cash", 0)
    invested = portfolio.get("total_invested", 0)
    positions = [p for p in portfolio.get("positions", []) if p.get("status") == "OPEN"]
    perf = portfolio.get("performance", {})
    total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
    pv = cash + sum(p.get("position_value", 0) + p.get("unrealized_pnl", 0) for p in positions)

    summary_table = Table(title="[bold]Portfolio Summary[/bold]", border_style="cyan")
    summary_table.add_column("Metric")
    summary_table.add_column("Value", justify="right")
    summary_table.add_row("Portfolio Value", f"${pv:,.2f}")
    summary_table.add_row("Cash", f"${cash:,.2f}")
    summary_table.add_row("Invested", f"${invested:,.2f}")
    summary_table.add_row("Open Positions", str(len(positions)))
    summary_table.add_row("Unrealized P&L", f"${total_pnl:+,.2f}")
    summary_table.add_row("Total Realized P&L", f"${perf.get('total_pnl', 0):+,.2f}")
    summary_table.add_row("Win Rate", f"{perf.get('win_rate', 0):.1f}%")
    summary_table.add_row("Total Trades", str(perf.get("total_trades", 0)))
    console.print(summary_table)

    if positions:
        pos_table = Table(title="[bold]Open Positions[/bold]", border_style="blue")
        pos_table.add_column("Ticker", style="bold")
        pos_table.add_column("Dir")
        pos_table.add_column("Shares", justify="right")
        pos_table.add_column("Entry", justify="right")
        pos_table.add_column("Current", justify="right")
        pos_table.add_column("Stop", justify="right")
        pos_table.add_column("T2", justify="right")
        pos_table.add_column("P&L %", justify="right")
        pos_table.add_column("Quality")

        for p in positions:
            pnl_pct = p.get("unrealized_pnl_pct", 0)
            pnl_color = "green" if pnl_pct >= 0 else "red"
            pos_table.add_row(
                p["ticker"],
                p.get("direction", "LONG"),
                str(p.get("shares", 0)),
                f"${p.get('entry_price', 0):.4f}",
                f"${p.get('current_price', p.get('entry_price', 0)):.4f}",
                f"${p.get('stop_loss', 0):.4f}",
                f"${p.get('target_2', 0):.4f}" if p.get("target_2") else "—",
                f"[{pnl_color}]{pnl_pct:+.1f}%[/{pnl_color}]",
                p.get("trade_quality", "?"),
            )
        console.print(pos_table)


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------
def run_scan(custom_tickers: list[str] | None = None) -> list[str]:
    with Progress(SpinnerColumn(), TextColumn("[cyan]Running WatchlistScanner..."), console=console) as p:
        p.add_task("")
        scanner = WatchlistScanner()
        result = scanner.scan(custom_tickers)

    print_scan_results(result)
    return result.get("tickers", [])


def run_analysis(tickers: list[str]) -> list[dict]:
    analyses = []
    analyser = StockAnalyser()
    for ticker in tickers:
        with Progress(SpinnerColumn(), TextColumn(f"[blue]Analysing {ticker}..."), console=console) as p:
            p.add_task("")
            analysis = analyser.analyse(ticker)
        print_analysis(analysis)
        analyses.append(analysis)
    return analyses


def run_evaluation(analyses: list[dict]) -> list[dict]:
    console.print("\n[bold]Running Evaluator (analyst confluence check)...[/bold]")
    evaluator = Evaluator()
    evaluations = []
    for analysis in analyses:
        with Progress(SpinnerColumn(), TextColumn(f"[yellow]Evaluating {analysis.get('ticker')}..."), console=console) as p:
            p.add_task("")
            ev = evaluator.evaluate(analysis)
        print_evaluation(ev)
        evaluations.append(ev)
    return evaluations


def run_trade_analysis(evaluations: list[dict]) -> list[dict]:
    actionable = [e for e in evaluations if e.get("proceed_to_trade_analysis")]
    if not actionable:
        console.print("[yellow]No stocks passed the evaluator — no trade plans to generate.[/yellow]")
        return []

    console.print(f"\n[bold]Running TradeAnalyser for {len(actionable)} candidate(s)...[/bold]")
    analyser = TradeAnalyser()
    plans = []
    for ev in actionable:
        ticker = ev.get("ticker", "?")
        with Progress(SpinnerColumn(), TextColumn(f"[green]Trade analysis: {ticker}..."), console=console) as p:
            p.add_task("")
            plan = analyser.analyse_trade(ev)
        print_trade_plan(plan)
        plans.append(plan)
    return plans


def run_execution(trade_plans: list[dict]) -> list[dict]:
    executable = [p for p in trade_plans if p.get("trade_quality") in ("A+", "A")]
    if not executable:
        console.print("[yellow]No A/A+ grade trades to execute.[/yellow]")
        return []

    console.print(f"\n[bold]Running TradeExecutor for {len(executable)} trade(s)...[/bold]")
    executor = TradeExecutor()
    results = []
    for plan in executable:
        with Progress(SpinnerColumn(), TextColumn(f"[bold green]Executing {plan['ticker']}..."), console=console) as p:
            p.add_task("")
            result = executor.execute(plan)
        print_execution_result(result)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
def cmd_run(args: argparse.Namespace) -> None:
    """Full pipeline: scan → analyse → evaluate → trade plan → execute."""
    print_banner()
    console.print("\n[bold cyan]Starting full pipeline...[/bold cyan]\n")

    tickers = run_scan(args.tickers if hasattr(args, "tickers") and args.tickers else None)
    if not tickers:
        console.print("[red]No tickers returned from scanner.[/red]")
        return

    analyses = run_analysis(tickers)
    evaluations = run_evaluation(analyses)
    trade_plans = run_trade_analysis(evaluations)
    results = run_execution(trade_plans)

    console.print("\n[bold cyan]Pipeline complete.[/bold cyan]")
    console.print(f"  Scanned: {len(tickers)} | Analysed: {len(analyses)} | "
                  f"Passed evaluator: {sum(1 for e in evaluations if e.get('proceed_to_trade_analysis'))} | "
                  f"Trade plans: {len(trade_plans)} | Executed: {sum(1 for r in results if r.get('action') == 'ENTERED')}")

    executor = TradeExecutor()
    print_portfolio(executor.get_portfolio())


def cmd_scan(args: argparse.Namespace) -> None:
    print_banner()
    tickers = getattr(args, "tickers", None)
    run_scan(tickers if tickers else None)


def cmd_analyse(args: argparse.Namespace) -> None:
    print_banner()
    tickers = args.tickers
    if not tickers:
        console.print("[red]Provide ticker(s) to analyse: python main.py analyse AAPL MSFT[/red]")
        sys.exit(1)
    analyses = run_analysis(tickers)
    evaluations = run_evaluation(analyses)
    trade_plans = run_trade_analysis(evaluations)
    run_execution(trade_plans)
    executor = TradeExecutor()
    print_portfolio(executor.get_portfolio())


def cmd_portfolio(args: argparse.Namespace) -> None:
    print_banner()
    executor = TradeExecutor()
    portfolio = executor.get_portfolio()
    print_portfolio(portfolio)


def cmd_track(args: argparse.Namespace) -> None:
    print_banner()
    tracker = PortfolioTracker()
    interval = getattr(args, "interval", None) or config.refresh_interval
    cycles = getattr(args, "cycles", None)
    console.print(f"[cyan]Starting portfolio monitor (interval={interval}s, cycles={cycles or 'unlimited'})[/cyan]")
    tracker.monitor_loop(interval_seconds=interval, max_cycles=cycles)


def cmd_close(args: argparse.Namespace) -> None:
    print_banner()
    if not args.ticker:
        console.print("[red]Provide a ticker: python main.py close AAPL[/red]")
        sys.exit(1)
    executor = TradeExecutor()
    result = executor.close_trade(args.ticker.upper(), reason="MANUAL")
    if result.get("success"):
        console.print(f"[green]Closed {args.ticker.upper()}: P&L ${result.get('realized_pnl', 0):+,.2f} ({result.get('realized_pnl_pct', 0):+.1f}%)[/green]")
    else:
        console.print(f"[red]Failed to close: {result.get('error')}[/red]")
    print_portfolio(executor.get_portfolio())


def cmd_review(args: argparse.Namespace) -> None:
    """Single portfolio review cycle (no loop)."""
    print_banner()
    tracker = PortfolioTracker()
    with Progress(SpinnerColumn(), TextColumn("[cyan]Running portfolio review..."), console=console) as p:
        p.add_task("")
        report = tracker.review()

    health = report.get("overall_health", "UNKNOWN")
    color = {"STRONG": "green", "HEALTHY": "green", "MIXED": "yellow", "CAUTION": "yellow", "CRITICAL": "red"}.get(health, "white")
    console.print(Panel(
        f"Health: [{color}]{health}[/{color}] | "
        f"Value: ${report.get('portfolio_value', 0):,.2f} | "
        f"P&L: ${report.get('total_unrealized_pnl', 0):+,.2f}",
        title="Portfolio Review Report",
    ))
    for rev in report.get("position_reviews", []):
        console.print(f"  {rev.get('ticker')} | {rev.get('action')} | {rev.get('notes', '')}")
    for action in report.get("immediate_actions", []):
        console.print(f"[bold red]IMMEDIATE: {action}[/bold red]")
    for alert in report.get("alerts", []):
        console.print(f"[yellow]⚠ {alert}[/yellow]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        prog="trading_system",
        description="Agentic Stock Trading System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Full pipeline: scan → analyse → evaluate → trade → execute")
    p_run.add_argument("tickers", nargs="*", help="Optional specific tickers (bypasses watchlist)")
    p_run.set_defaults(func=cmd_run)

    # scan
    p_scan = sub.add_parser("scan", help="Watchlist scan only")
    p_scan.add_argument("tickers", nargs="*", help="Override watchlist with these tickers")
    p_scan.set_defaults(func=cmd_scan)

    # analyse
    p_analyse = sub.add_parser("analyse", help="Analyse specific tickers through full analysis pipeline")
    p_analyse.add_argument("tickers", nargs="+")
    p_analyse.set_defaults(func=cmd_analyse)

    # portfolio
    p_port = sub.add_parser("portfolio", help="Show current portfolio state")
    p_port.set_defaults(func=cmd_portfolio)

    # review
    p_review = sub.add_parser("review", help="Run a single portfolio review cycle")
    p_review.set_defaults(func=cmd_review)

    # track
    p_track = sub.add_parser("track", help="Start continuous portfolio monitoring loop")
    p_track.add_argument("--interval", type=int, help="Seconds between reviews (default: from .env)")
    p_track.add_argument("--cycles", type=int, help="Max review cycles (default: unlimited)")
    p_track.set_defaults(func=cmd_track)

    # close
    p_close = sub.add_parser("close", help="Manually close a position")
    p_close.add_argument("ticker", help="Ticker to close")
    p_close.set_defaults(func=cmd_close)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # Validate API key before running
    try:
        config.validate()
    except ValueError as e:
        console.print(f"[bold red]Configuration error:[/bold red] {e}")
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
