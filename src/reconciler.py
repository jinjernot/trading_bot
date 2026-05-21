"""
Trade Reconciliation Engine — Brigadier Bot
============================================

PURPOSE:
    Fills the gap when the bot was offline and trades were closed by Binance
    (TP hit, SL hit, or manual close). Those closures are never logged locally,
    causing the dashboard metrics to be incomplete.

HOW IT WORKS:
    1. Reads the local CSV log to find the most recent logged exit timestamp.
    2. Queries Binance futures trade history from that timestamp onward.
    3. For each Binance trade that represents a REDUCE (closing trade), check
       if it already exists in the local log (by matching symbol + timestamp).
    4. Any missing trades are backfilled into the CSV with source = 'BINANCE_SYNC'.

WHEN IT RUNS:
    - Called from main.py at startup (catches anything missed while offline).
    - Exposed as /api/sync-trades in app.py (manual trigger from dashboard).
    - Safe to call multiple times — deduplication prevents double-counting.

BINANCE API USED:
    client.futures_account_trades(symbol, startTime, limit=1000)
    Returns all fills for a symbol. We filter by:
        - reduceOnly = True OR positionSide indicates closing direction
        - side matches the close direction for the position
"""

import os
import csv
import time
import pandas as pd
from datetime import datetime, timezone
from binance.client import Client
from config.secrets import API_KEY, API_SECRET
from config.settings import LEVERAGE, BINANCE_FEE_RATE

# Reuse the singleton client from get_data to avoid extra connections
try:
    from data.get_data import client
except ImportError:
    client = Client(API_KEY, API_SECRET)

TRADE_LOG_CSV = 'logs/trade_log.csv'
SYNC_LOG_CSV  = 'logs/sync_log.csv'     # Audit trail of what was backfilled
os.makedirs('logs', exist_ok=True)


def _get_last_logged_timestamp_ms() -> int:
    """
    Returns the Unix timestamp (ms) of the most recently logged EXIT row in the CSV.
    If no log exists, defaults to 7 days ago so we catch a reasonable lookback window.
    """
    default_lookback_ms = int((time.time() - 7 * 86400) * 1000)  # 7 days ago

    if not os.path.exists(TRADE_LOG_CSV):
        return default_lookback_ms

    try:
        df = pd.read_csv(TRADE_LOG_CSV, encoding='utf-8', encoding_errors='replace')
        exits = df[df['Side'].str.contains('EXIT', na=False)]
        if exits.empty:
            return default_lookback_ms

        # Parse timestamps, handling mixed formats gracefully
        exits['_ts'] = pd.to_datetime(exits['Timestamp'], errors='coerce', utc=True)
        last_ts = exits['_ts'].dropna().max()
        if pd.isna(last_ts):
            return default_lookback_ms

        return int(last_ts.timestamp() * 1000)
    except Exception:
        return default_lookback_ms


def _build_logged_trade_keys() -> set:
    """
    Returns a set of (symbol, trade_time_rounded_to_minute) for all locally logged exits.
    Used for deduplication — we match at minute precision to handle minor timestamp drift.
    """
    keys = set()
    if not os.path.exists(TRADE_LOG_CSV):
        return keys

    try:
        df = pd.read_csv(TRADE_LOG_CSV, encoding='utf-8', encoding_errors='replace')
        exits = df[df['Side'].str.contains('EXIT', na=False)]
        for _, row in exits.iterrows():
            try:
                ts = pd.to_datetime(row['Timestamp'], utc=True)
                # Round to minute for fuzzy matching against Binance timestamps
                minute_key = ts.replace(second=0, microsecond=0)
                keys.add((row['Symbol'], str(minute_key)))
            except Exception:
                continue
    except Exception:
        pass

    return keys


def _write_backfill_row(symbol: str, side: str, entry_price: float,
                         exit_price: float, quantity: float,
                         pnl: float, roi: float, exit_time_ms: int,
                         exit_reason: str = 'BINANCE_SYNC'):
    """
    Appends a single backfilled trade row to the CSV log.
    Marks source as BINANCE_SYNC so it's distinguishable from bot-logged trades.
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    exit_time_str = datetime.fromtimestamp(exit_time_ms / 1000, tz=timezone.utc).isoformat()

    with open(TRADE_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'Timestamp', 'Symbol', 'Side', 'Entry_Price', 'Exit_Price',
                'Quantity', 'PnL_USDT', 'ROI_Percent', 'Exit_Reason', 'Notes'
            ])
        writer.writerow([
            exit_time_str,
            symbol,
            f'{side}_EXIT',
            round(entry_price, 8),
            round(exit_price, 8),
            round(quantity, 8),
            round(pnl, 4),
            round(roi, 4),
            exit_reason,
            'Backfilled from Binance history — bot was offline'
        ])

    # Also write to audit log
    with open(SYNC_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([exit_time_str, symbol, side, exit_price, quantity, pnl, roi, exit_reason])


def reconcile_trades(symbols: list, verbose: bool = True) -> dict:
    """
    Main reconciliation function. Queries Binance for each symbol's trade history
    and backfills any closes that were missed while the bot was offline.

    Args:
        symbols: List of trading pair symbols (e.g. ['BTCUSDT', 'ETHUSDT'])
        verbose:  Print progress to console

    Returns:
        dict with keys: backfilled_count, skipped_count, errors, details
    """
    start_time_ms = _get_last_logged_timestamp_ms()
    logged_keys   = _build_logged_trade_keys()

    start_dt = datetime.fromtimestamp(start_time_ms / 1000, tz=timezone.utc)
    if verbose:
        print(f"\n{'='*60}")
        print(f"TRADE RECONCILIATION — Syncing with Binance")
        print(f"   Scanning from: {start_dt.strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"   Symbols:       {len(symbols)}")
        print(f"{'='*60}")

    backfilled = 0
    skipped    = 0
    errors     = []
    details    = []

    for symbol in symbols:
        try:
            # Fetch trade history for this symbol from Binance
            # Binance returns fills (partial or full), not position-level closes,
            # so we need to aggregate fills into position-close events.
            raw_trades = client.futures_account_trades(
                symbol=symbol,
                startTime=start_time_ms,
                limit=1000   # Max allowed per Binance API
            )

            if not raw_trades:
                continue

            # Filter to only CLOSING trades (reduceOnly=True)
            closing_trades = [t for t in raw_trades if t.get('buyer') is not None
                              and t.get('realizedPnl') is not None
                              and float(t.get('realizedPnl', 0)) != 0]

            # Group fills by time proximity (within 2 seconds = same close event)
            # This handles partial fills being multiple rows for one TP order
            if not closing_trades:
                continue

            # Sort by time
            closing_trades.sort(key=lambda x: int(x['time']))

            # Aggregate into close events
            events = []
            current_event = None

            for trade in closing_trades:
                trade_time = int(trade['time'])
                qty   = float(trade['qty'])
                price = float(trade['price'])
                pnl   = float(trade.get('realizedPnl', 0))
                side  = trade['side']  # 'BUY' (closing short) or 'SELL' (closing long)

                if current_event is None or (trade_time - current_event['time']) > 2000:
                    # New close event
                    current_event = {
                        'time':     trade_time,
                        'side':     side,
                        'qty':      qty,
                        'pnl':      pnl,
                        'prices':   [price],
                        'symbol':   symbol,
                    }
                    events.append(current_event)
                else:
                    # Same close event — aggregate
                    current_event['qty']    += qty
                    current_event['pnl']    += pnl
                    current_event['prices'].append(price)

            # Process each aggregated close event
            for event in events:
                exit_price  = sum(event['prices']) / len(event['prices'])  # VWAP approx
                total_qty   = event['qty']
                total_pnl   = event['pnl']
                position_side = 'LONG' if event['side'] == 'SELL' else 'SHORT'

                # Dedup check — is this already in our local log?
                event_dt     = datetime.fromtimestamp(event['time'] / 1000, tz=timezone.utc)
                minute_key   = str(event_dt.replace(second=0, microsecond=0))
                dedupe_key   = (symbol, minute_key)

                if dedupe_key in logged_keys:
                    skipped += 1
                    continue

                # We don't have the entry price from fills directly —
                # compute it from PnL: entry = exit - (pnl / qty) for LONG
                # For LONG: pnl = (exit - entry) * qty  → entry = exit - pnl/qty
                # For SHORT: pnl = (entry - exit) * qty → entry = exit + pnl/qty
                if position_side == 'LONG':
                    entry_price = exit_price - (total_pnl / total_qty) if total_qty > 0 else 0
                else:
                    entry_price = exit_price + (total_pnl / total_qty) if total_qty > 0 else 0

                # Binance Futures Market Taker Fee — configured in settings.py
                # We pay this twice (once to open, once to close) because we use Market Orders
                total_fees = (entry_price * total_qty * BINANCE_FEE_RATE) + (exit_price * total_qty * BINANCE_FEE_RATE)
                net_pnl = total_pnl - total_fees

                # ROI calculation: same formula as close_position() in trade.py
                initial_margin = (entry_price * total_qty) / LEVERAGE if LEVERAGE > 0 else 1
                roi = (net_pnl / initial_margin * 100) if initial_margin > 0 else 0

                _write_backfill_row(
                    symbol=symbol,
                    side=position_side,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    quantity=total_qty,
                    pnl=net_pnl,
                    roi=roi,
                    exit_time_ms=event['time'],
                    exit_reason=f"BINANCE_SYNC (offline TP/SL)"
                )

                logged_keys.add(dedupe_key)  # Prevent double-write in same run
                backfilled += 1
                details.append({
                    'symbol':     symbol,
                    'side':       position_side,
                    'exit_price': round(exit_price, 6),
                    'qty':        round(total_qty, 6),
                    'pnl':        round(net_pnl, 4),
                    'roi':        round(roi, 2),
                    'time':       event_dt.strftime('%Y-%m-%d %H:%M UTC')
                })

                if verbose:
                    status_marker = 'OK' if net_pnl > 0 else 'LOSS'
                    print(f"  [{status_marker}] BACKFILLED: {symbol} {position_side} | "
                          f"Net PnL: ${net_pnl:.4f} (Fees: ${total_fees:.4f}) | ROI: {roi:.2f}% | {event_dt.strftime('%H:%M %b %d')}")

        except Exception as e:
            error_msg = f"{symbol}: {e}"
            errors.append(error_msg)
            if verbose:
                print(f"  WARNING: Error syncing {symbol}: {e}")

        # Small delay to avoid rate limiting on 25+ symbols
        time.sleep(0.1)

    result = {
        'backfilled_count': backfilled,
        'skipped_count':    skipped,
        'errors':           errors,
        'details':          details,
        'scan_from':        start_dt.strftime('%Y-%m-%d %H:%M UTC')
    }

    if verbose:
        print(f"\n{'='*60}")
        print(f"Sync complete — Backfilled: {backfilled} | Skipped (already logged): {skipped}")
        if errors:
            print(f"WARNING: Errors on {len(errors)} symbol(s): {', '.join(e.split(':')[0] for e in errors)}")
        print(f"{'='*60}\n")

    return result


if __name__ == '__main__':
    # Run standalone to manually trigger a full sync
    from config.symbols import symbols
    result = reconcile_trades(symbols, verbose=True)
