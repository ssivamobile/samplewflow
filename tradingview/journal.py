"""Forward-test journal for the KOF levels / Model 1 screener (kof_levels_rr.pine).

One SQLite file, four commands:

  freeze   record the sha256 of the Pine file and the input values you will trade with. `add` warns when
           the file changes afterwards, so results from different parameter sets are not mixed.
  add      log a setup the moment it fires. Log candidates you SKIP too (--taken no --reason ...): the
           skipped ones are what show whether the filters help.
  close    record the exit for a taken trade (price or R). R is computed from entry/stop.
  stats    win rate, expectancy and splits, then a verdict against the pre-registered criteria
           (FORWARD_TEST.md): >= 100 setups logged, >= 50 closed trades, average NET R >= +0.20, stop at -10R
           drawdown. Net R subtracts an assumed round-trip cost per share (--cost, default 0.02).
  list     print the rows.

The database lives outside the repo by default (~/.kof_journal.sqlite) so trade records are not committed.
Absorption / big trade / delta are NOT detected by the Pine script; you enter them by eye (yes / no / unknown).

Examples:
  python3 tradingview/journal.py freeze --note "warm-up 30, minR 2.0, buf 0.5, 4-tick bins"
  python3 tradingview/journal.py add --symbol MNQ --side short --entry 27236 --stop 27262 \\
      --tp1 27137 --tp2 27037 --tools 2 --absorption yes --bigtrade no --delta yes --taken yes
  python3 tradingview/journal.py close 1 --exit 27137
  python3 tradingview/journal.py stats
"""
import argparse
import hashlib
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path.home() / ".kof_journal.sqlite"
PINE_FILE = Path(__file__).with_name("kof_levels_rr.pine")
YES_NO = ("yes", "no", "unknown")
DAY_TYPES = ("trend", "balance", "news", "unknown")  # judged LIVE, before the outcome is known
ENTRY_TYPES = ("reentry", "edge", "other", "unknown")

# Pre-registered criteria (see FORWARD_TEST.md). Written down before any trade was logged.
DEFAULT_COST = 0.02     # assumed round-trip cost per share in price units (spread + commission + slippage)
MIN_LOGGED = 100        # setups logged, taken or skipped
MIN_CLOSED = 50         # closed taken trades under frozen parameters
PASS_AVG_R = 0.20       # average NET R per closed taken trade
STOP_DRAWDOWN_R = -10.0 # cumulative drawdown from peak, in R, that ends the test as a fail
NEW_COLS = (("day_type", "TEXT"), ("entry_type", "TEXT"), ("tp1_hit", "TEXT"), ("tp2_hit", "TEXT"),
            ("cost", "REAL"), ("gross_r", "REAL"))  # added 2026-11-19; migrated into older databases

SCHEMA = """
CREATE TABLE IF NOT EXISTS freeze (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, pine_sha256 TEXT NOT NULL, git_head TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL CHECK (side IN ('long','short')),
    model INTEGER NOT NULL DEFAULT 1, entry REAL NOT NULL, stop REAL NOT NULL, tp1 REAL, tp2 REAL,
    risk REAL NOT NULL, r_tp1 REAL, r_tp2 REAL, tools INTEGER,
    absorption TEXT, bigtrade TEXT, delta TEXT,
    taken INTEGER NOT NULL, skip_reason TEXT, freeze_id INTEGER, pine_changed INTEGER NOT NULL DEFAULT 0,
    screenshot TEXT, notes TEXT,
    exit_price REAL, outcome_r REAL, closed_ts TEXT);
"""


def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string (seconds precision)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def pine_sha() -> str:
    """Return the sha256 hex digest of the Pine script next to this file."""
    return hashlib.sha256(PINE_FILE.read_bytes()).hexdigest()


def git_head() -> str:
    """Return the short git HEAD of the repo holding this file, or '' if unavailable."""
    try:
        out = subprocess.run(["git", "-C", str(PINE_FILE.parent), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def connect(path: Path) -> sqlite3.Connection:
    """Open (and create if needed) the journal database."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    have = {r["name"] for r in con.execute("PRAGMA table_info(trades)")}
    for name, typ in NEW_COLS:  # constants above, not user input
        if name not in have:
            con.execute(f"ALTER TABLE trades ADD COLUMN {name} {typ}")
    con.commit()
    return con


def cmd_freeze(con: sqlite3.Connection, a: argparse.Namespace) -> None:
    """Record the Pine file hash and your input values as the frozen parameter set."""
    cur = con.execute("INSERT INTO freeze (ts, pine_sha256, git_head, note) VALUES (?,?,?,?)",
                      (now_utc(), pine_sha(), git_head(), a.note))
    con.commit()
    print(f"freeze #{cur.lastrowid} recorded (pine sha256 {pine_sha()[:12]}, git {git_head() or 'n/a'}).")


def cmd_add(con: sqlite3.Connection, a: argparse.Namespace) -> None:
    """Log a setup (taken or skipped) with its levels, R multiples and the by-eye confirmations."""
    risk = abs(a.entry - a.stop)
    if risk == 0 or (a.side == "long") != (a.stop < a.entry):
        sys.exit("stop must be below entry for a long and above entry for a short")
    r1 = abs(a.tp1 - a.entry) / risk if a.tp1 else None
    r2 = abs(a.tp2 - a.entry) / risk if a.tp2 else None
    fz = con.execute("SELECT id, pine_sha256 FROM freeze ORDER BY id DESC LIMIT 1").fetchone()
    changed = 0
    if fz is None:
        print("note: no freeze recorded yet; run `freeze` before the test window starts.")
    elif fz["pine_sha256"] != pine_sha():
        changed = 1
        print("WARNING: kof_levels_rr.pine differs from the frozen version; this row is flagged pine_changed.")
    taken = 1 if a.taken == "yes" else 0
    if not taken and not a.reason:
        sys.exit("a skipped setup needs --reason (that is what makes the skipped rows useful)")
    cur = con.execute(
        "INSERT INTO trades (ts,symbol,side,model,entry,stop,tp1,tp2,risk,r_tp1,r_tp2,tools,absorption,bigtrade,delta,"
        "taken,skip_reason,freeze_id,pine_changed,screenshot,notes,day_type,entry_type)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now_utc(), a.symbol, a.side, a.model, a.entry, a.stop, a.tp1, a.tp2, risk, r1, r2, a.tools,
         a.absorption, a.bigtrade, a.delta, taken, a.reason, fz["id"] if fz else None, changed, a.screenshot, a.notes,
         a.day_type, a.entry_type))
    con.commit()
    print(f"trade #{cur.lastrowid} logged: {a.side} risk {risk:g}"
          + (f", R to TP1 {r1:.2f}" if r1 else "") + (f", R to TP2 {r2:.2f}" if r2 else ""))


def cmd_close(con: sqlite3.Connection, a: argparse.Namespace) -> None:
    """Close a trade from an exit price (R computed) or an explicit R multiple."""
    t = con.execute("SELECT * FROM trades WHERE id=?", (a.id,)).fetchone()
    if t is None:
        sys.exit(f"no trade #{a.id}")
    if (a.exit is None) == (a.r is None):
        sys.exit("give exactly one of --exit PRICE or --r MULTIPLE")
    sign = 1 if t["side"] == "long" else -1
    gross = a.r if a.r is not None else sign * (a.exit - t["entry"]) / t["risk"]
    net = gross - a.cost / t["risk"]  # outcome_r is NET of the assumed round-trip cost
    con.execute("UPDATE trades SET exit_price=?, gross_r=?, cost=?, outcome_r=?, tp1_hit=?, tp2_hit=?, closed_ts=? WHERE id=?",
                (a.exit, gross, a.cost, net, a.tp1_hit, a.tp2_hit, now_utc(), a.id))
    con.commit()
    print(f"trade #{a.id} closed: gross {gross:+.2f}R, cost {a.cost / t['risk']:.2f}R, net {net:+.2f}R")


def _summary(rows: list) -> str:
    """One-line summary of closed trades: count, win rate, average R, total R."""
    rs = [r["outcome_r"] for r in rows]
    if not rs:
        return "n=0"
    wins = sum(1 for r in rs if r > 0)
    return f"n={len(rs)}  win {wins / len(rs):.0%}  avg {sum(rs) / len(rs):+.2f}R  total {sum(rs):+.2f}R"


def cmd_stats(con: sqlite3.Connection, a: argparse.Namespace) -> None:
    """Print results for closed, taken trades, split by confirmation and by frozen/changed parameters."""
    allrows = con.execute("SELECT * FROM trades").fetchall()
    closed = [r for r in allrows if r["taken"] and r["outcome_r"] is not None]
    skipped = [r for r in allrows if not r["taken"]]
    open_n = sum(1 for r in allrows if r["taken"] and r["outcome_r"] is None)
    print(f"logged {len(allrows)}  taken-closed {len(closed)}  open {open_n}  skipped {len(skipped)}")
    print("all taken      :", _summary(closed))
    clean = [r for r in closed if r["freeze_id"] is not None and not r["pine_changed"]]
    print("frozen params  :", _summary(clean), f"({len(closed) - len(clean)} excluded: logged before a freeze, or Pine changed)")
    conf = [r for r in clean if (r["absorption"], r["bigtrade"], r["delta"]) == ("yes", "yes", "yes")]
    some = [r for r in clean if r not in conf]
    print("all 3 confirmed:", _summary(conf))
    print("not confirmed  :", _summary(some))
    for side in ("long", "short"):
        print(f"{side:15}:", _summary([r for r in clean if r["side"] == side]))
    if skipped:
        print("skipped by reason:")
        for reason in sorted({r["skip_reason"] for r in skipped}):
            print(f"  {sum(1 for r in skipped if r['skip_reason'] == reason):3}  {reason}")
    for dt in DAY_TYPES:
        sub = [r for r in clean if r["day_type"] == dt]
        if sub:
            print(f"day {dt:11}:", _summary(sub))
    print("\n" + _verdict(len(allrows), clean))


def _verdict(logged: int, clean: list) -> str:
    """Compare the frozen-parameter results with the pre-registered criteria (net R, drawdown, sample size)."""
    rs = [r["outcome_r"] for r in sorted(clean, key=lambda r: r["closed_ts"])]
    peak = cum = worst = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    n = len(rs)
    avg = cum / n if n else 0.0
    se = (sum((r - avg) ** 2 for r in rs) / (n - 1)) ** 0.5 / n ** 0.5 if n > 1 else float("nan")
    head = f"criteria: logged {logged}/{MIN_LOGGED}, closed {n}/{MIN_CLOSED}, avg net R {avg:+.2f} (need >= {PASS_AVG_R:+.2f}), " \
           f"max drawdown {worst:+.1f}R (stop at {STOP_DRAWDOWN_R:+.1f}R), std error of avg R {se:.2f}"
    if worst <= STOP_DRAWDOWN_R:
        return head + "\nVERDICT: FAIL - drawdown stop hit. Stop the test."
    if logged < MIN_LOGGED or n < MIN_CLOSED:
        return head + "\nVERDICT: IN PROGRESS - sample too small, treat the numbers as noise."
    if avg >= PASS_AVG_R:
        return head + (f"\nVERDICT: PROMISING, not proven - average is {avg / se:.1f} standard errors above zero (rough guide only: "
                       "setups on the same day are not independent, and one symbol over a few weeks is one market regime).")
    return head + "\nVERDICT: FAIL - average net R below the threshold."


def cmd_list(con: sqlite3.Connection, a: argparse.Namespace) -> None:
    """Print every row in order, with open trades marked."""
    for r in con.execute("SELECT * FROM trades ORDER BY id"):
        res = "open" if r["taken"] and r["outcome_r"] is None else ("skipped" if not r["taken"] else f"{r['outcome_r']:+.2f}R")
        print(f"#{r['id']:<3} {r['ts']} {r['symbol']} {r['side']:5} entry {r['entry']:g} stop {r['stop']:g} "
              f"conf {r['absorption']}/{r['bigtrade']}/{r['delta']} day {r['day_type']} entry-type {r['entry_type']} "
              f"tp1/tp2 {r['tp1_hit']}/{r['tp2_hit']} {res}")


def main() -> None:
    """Parse the command line and dispatch to the sub-command."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"database path (default {DEFAULT_DB})")
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--note", default="")
    ad = sub.add_parser("add")
    ad.add_argument("--symbol", required=True); ad.add_argument("--side", required=True, choices=("long", "short"))
    ad.add_argument("--entry", type=float, required=True); ad.add_argument("--stop", type=float, required=True)
    ad.add_argument("--tp1", type=float); ad.add_argument("--tp2", type=float)
    ad.add_argument("--model", type=int, default=1, choices=(1, 2)); ad.add_argument("--tools", type=int)
    for k in ("absorption", "bigtrade", "delta"):
        ad.add_argument(f"--{k}", choices=YES_NO, default="unknown")
    ad.add_argument("--taken", choices=("yes", "no"), required=True); ad.add_argument("--reason")
    ad.add_argument("--screenshot"); ad.add_argument("--notes")
    ad.add_argument("--day-type", choices=DAY_TYPES, default="unknown", help="judged live, before the outcome")
    ad.add_argument("--entry-type", choices=ENTRY_TYPES, default="unknown")
    c = sub.add_parser("close"); c.add_argument("id", type=int)
    c.add_argument("--exit", type=float); c.add_argument("--r", type=float, help="gross R multiple instead of --exit")
    c.add_argument("--cost", type=float, default=DEFAULT_COST, help=f"round-trip cost per share, price units (default {DEFAULT_COST})")
    c.add_argument("--tp1-hit", choices=YES_NO, default="unknown"); c.add_argument("--tp2-hit", choices=YES_NO, default="unknown")
    sub.add_parser("stats")
    sub.add_parser("list")
    a = p.parse_args()
    con = connect(a.db)
    {"freeze": cmd_freeze, "add": cmd_add, "close": cmd_close, "stats": cmd_stats, "list": cmd_list}[a.cmd](con, a)


if __name__ == "__main__":
    main()
