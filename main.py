import asyncio
import time
import sys
import io

# Force UTF-8 encoding for Windows consoles to prevent crashes on foreign tickers (e.g., Chinese meme coins)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
from config.symbols import symbols
from data.get_data import fetch_multi_timeframe_data, get_all_positions_and_balance, get_usdt_balance, get_position, get_all_funding_rates, get_global_btc_trend
from data.indicators import *
from src.close_position import close_position_long, close_position_short
from src.trade import manage_active_trades, cancel_open_orders
from src.state_manager import bot_state
from src.reconciler import reconcile_trades
from config.settings import *
from config.bot_info import get_startup_message

# --- Import All Strategy Functions ---
from src.fib_strategy import check_fib_pullback_long_entry, check_fib_retrace_short_entry
from src.open_position import open_position_long, open_position_short
from src.bos_strategy import check_bos_breakout_long, check_bos_breakout_short
from src.reversal_strategy import check_reversal_long_entry, check_reversal_short_entry


from config.client import client

trade_lock = asyncio.Lock()

async def set_leverage(symbol, leverage):
    """
    Sets the leverage for a given symbol with automatic maximum leverage fallback.
    """
    try:
        await asyncio.to_thread(client.futures_change_leverage, symbol=symbol, leverage=leverage)
    except Exception as e:
        if "No need to change leverage" in str(e):
            return
            
        # Check if user needs to sign TradFi perps agreement (Binance API Error -4411)
        if "-4411" in str(e) or "TradFi-Perps" in str(e):
            print(f"\n⚠️  [Agreement Required] {symbol} is a TradFi perp but you haven't signed the agreement on Binance!")
            print(f"   Please log in to your Binance web/app, navigate to Futures, open {symbol}, and sign the TradFi-Perps Agreement Contract.")
            print(f"   Bypassing {symbol} until the agreement is signed to prevent process crashes.\n")
            from src.state_manager import bot_state
            bot_state.unsigned_agreement_symbols.add(symbol)
            return

        # Check if leverage setting failed due to exchange limits (Binance API Error -4028)
        if "code=-4028" in str(e) or "Leverage" in str(e):
            try:
                brackets = await asyncio.to_thread(client.futures_leverage_bracket, symbol=symbol)
                if brackets:
                    bracket_list = brackets[0].get('brackets', [])
                    max_allowed = max([int(b['initialLeverage']) for b in bracket_list])
                    if max_allowed != leverage:
                        print(f"[Leverage Adjuster] {symbol} maximum leverage is {max_allowed}x. Adjusting from {leverage}x to {max_allowed}x...")
                        await asyncio.to_thread(client.futures_change_leverage, symbol=symbol, leverage=max_allowed)
                        return
            except Exception as inner_e:
                print(f"[Leverage Adjuster Error] Could not auto-adjust leverage for {symbol}: {inner_e}")
                
        # Print standard warning if it was a different error or fallback failed
        print(f"[Leverage Warning] Could not set leverage for {symbol}: {e}")

async def process_symbol(symbol, all_positions, balance_data, funding_rates_map):
    """
    Processes a single symbol by checking for trade signals in a hierarchical order.
    1. First, check for the high-probability Fibonacci setup.
    2. If no Fib setup is found, then check for the general trend-following setup.
    """
    try:
        # --- Pre-flight: Skip symbols requiring unsigned agreements ---
        if symbol in bot_state.unsigned_agreement_symbols:
            if VERBOSE_LOGGING:
                print(f"⚠️ Skipping {symbol}: TradFi-Perps Agreement required.")
            return

        df_15m, _, _, _, _, _, _, _, df_4h, support_4h, resistance_4h, stoch_k_1h, stoch_d_1h, df_1h = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME
        )

        # --- Prepare Data and Indicators ---
        df_15m = calculate_atr(df_15m)
        df_15m = calculate_rsi(df_15m)
        df_15m = add_price_sma(df_15m, 50)
        df_15m = calculate_hull_moving_average(df_15m, 14)
        df_15m = calculate_adx(df_15m)
        df_15m = calculate_vwap(df_15m, period=288)
        from config.settings import VOLUME_ANOMALY_PERIOD, VOLUME_ANOMALY_MULTIPLIER
        df_15m = calculate_volume_anomaly(df_15m, period=VOLUME_ANOMALY_PERIOD, multiplier=VOLUME_ANOMALY_MULTIPLIER)
        from config.settings import BOS_LOOKBACK_PERIOD, BOS_RETEST_WINDOW, BOS_RETEST_PROXIMITY_PCT, BOS_RETEST_WICK_REJECTION
        df_15m = calculate_bos(df_15m, period=BOS_LOOKBACK_PERIOD, retest_window=BOS_RETEST_WINDOW, retest_proximity=BOS_RETEST_PROXIMITY_PCT, retest_wick_threshold=BOS_RETEST_WICK_REJECTION)
        stoch_k_15m, stoch_d_15m = calculate_stoch(df_15m['high'], df_15m['low'], df_15m['close'], 14, 3, 3)
        
        df_4h = calculate_adx(df_4h)
        df_4h = add_price_sma(df_4h, 50)
        df_4h = add_price_sma(df_4h, 200)  # Required by SMA200 trend filter in open_position.py
        
        # --- 1H EMA 21 for BOS Trend Filter ---
        df_1h['ema_21'] = df_1h['close'].ewm(span=21, adjust=False).mean()
        
        position, roi, _, _, entry_price = get_position(symbol, all_positions)
        usdt_balance = get_usdt_balance(balance_data)
        funding_rate = funding_rates_map.get(symbol, 0.0)
        atr_value_15m = df_15m['atr'].iloc[-1]

        # --- Position Management Logic (for open trades) ---
        # NOTE (Fix #1): position/roi data is from the cycle-start snapshot. Each symbol is
        # processed independently so cross-symbol staleness is not an issue. The only risk is
        # an exchange-level SL/TP firing mid-cycle for THIS symbol, which is a rare edge case.
        if position > 0: # Active Long Position
            await close_position_long(symbol, position, roi, df_15m, stoch_k_15m, stoch_d_15m, None, atr_value_15m, entry_price, funding_rate=funding_rate)
        elif position < 0: # Active Short Position
            await close_position_short(symbol, position, roi, df_15m, stoch_k_15m, stoch_d_15m, None, atr_value_15m, entry_price, funding_rate=funding_rate)
        
        # --- Entry Logic (for new trades) ---
        if position == 0:
            # Global Daily Drawdown Circuit Breaker
            current_date = pd.Timestamp.utcnow().date()
            if current_date != bot_state.last_pnl_reset_date:
                bot_state.daily_pnl = 0.0
                bot_state.last_pnl_reset_date = current_date
                print(f"🌅 New trading day! Daily PnL reset to 0.0")

            if bot_state.daily_pnl <= MAX_DAILY_LOSS_USDT:
                if VERBOSE_LOGGING:
                    print(f"🚨 DAILY DRAWDOWN HALT: Daily PnL ({bot_state.daily_pnl:.2f} USDT) hit limit ({MAX_DAILY_LOSS_USDT}). Skipping new entries.")
                return

            # Circuit breaker: pause new entries after too many consecutive losses
            consecutive_losses = bot_state.consecutive_losses.get(symbol, 0) if isinstance(bot_state.consecutive_losses, dict) else bot_state.consecutive_losses
            if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
                if VERBOSE_LOGGING:
                    print(f"⚠️  Circuit breaker active for {symbol}: {consecutive_losses} consecutive losses. Skipping new entries.")
                return

            # Cooldown lockout filter
            last_exit = bot_state.last_exit_timestamps.get(symbol, 0)
            cooldown_elapsed = time.time() - last_exit
            if cooldown_elapsed < COOL_DOWN_PERIOD_SECONDS:
                remaining = int(COOL_DOWN_PERIOD_SECONDS - cooldown_elapsed)
                if VERBOSE_LOGGING:
                    print(f"❄️  Skipping scanning for {symbol}: Symbol is in a cooldown lockout period. {remaining}s remaining.")
                return

            # 1. Check for Fibonacci Strategy First (A+ precision sniper)
            async with trade_lock:
                # Re-fetch active positions and balance dynamically to avoid race conditions in concurrent tasks
                current_positions, current_balance_data = await asyncio.to_thread(get_all_positions_and_balance)
                current_active = [p for p in current_positions if float(p.get('positionAmt', 0)) != 0]
                
                if len(current_active) >= MAX_CONCURRENT_TRADES:
                    if VERBOSE_LOGGING:
                        print(f"⏸️  Max concurrent trades reached ({len(current_active)}/{MAX_CONCURRENT_TRADES}) while evaluating {symbol}. Skipping entry.")
                    return
                
                current_usdt_balance = get_usdt_balance(current_balance_data)

                fib_trade_taken = False
                if ENABLE_FIB_STRATEGY:
                    fib_trade_taken = await check_fib_pullback_long_entry(symbol, df_15m, df_4h, current_usdt_balance)
                    if not fib_trade_taken:
                        fib_trade_taken = await check_fib_retrace_short_entry(symbol, df_15m, df_4h, current_usdt_balance)

                # 2. If no Fib, check for BOS Momentum Breakout (rocket rider)
                bos_trade_taken = False
                from config.settings import BOS_MAX_TRADES_PER_CYCLE
                if ENABLE_BOS_STRATEGY and not fib_trade_taken and bot_state.bos_cycle_count < BOS_MAX_TRADES_PER_CYCLE:
                    bos_trade_taken = await check_bos_breakout_long(symbol, df_15m, df_4h, df_1h, stoch_k_15m, current_usdt_balance)
                    if not bos_trade_taken:
                        bos_trade_taken = await check_bos_breakout_short(symbol, df_15m, df_4h, df_1h, stoch_k_15m, current_usdt_balance)
                    if bos_trade_taken:
                        bot_state.bos_cycle_count += 1

                # 3. If no Fib or BOS, check for Mean Reversion / Support Catch
                reversal_trade_taken = False
                if ENABLE_REVERSAL_STRATEGY and not fib_trade_taken and not bos_trade_taken:
                    reversal_trade_taken = await check_reversal_long_entry(symbol, df_15m, df_4h, stoch_k_1h, current_usdt_balance, support_4h)
                    if not reversal_trade_taken:
                        reversal_trade_taken = await check_reversal_short_entry(symbol, df_15m, df_4h, stoch_k_1h, current_usdt_balance, resistance_4h)

                # 4. If no Fib, BOS, or Reversal, fall back to Stochastic Pullback (B+ everyday grinder)
                if ENABLE_STOCH_STRATEGY and not fib_trade_taken and not bos_trade_taken and not reversal_trade_taken:
                    general_trade_taken = await open_position_long(symbol, df_15m, df_4h, stoch_k_15m, stoch_d_15m, stoch_k_1h, stoch_d_1h, current_usdt_balance, None, None, atr_value_15m, funding_rate, support_4h, resistance_4h)
                    if not general_trade_taken:
                        await open_position_short(symbol, df_15m, df_4h, stoch_k_15m, stoch_d_15m, stoch_k_1h, stoch_d_1h, current_usdt_balance, None, None, atr_value_15m, funding_rate, support_4h, resistance_4h)

    except Exception as e:
        import traceback
        error_msg = f"Error processing {symbol}: {e}\n{traceback.format_exc()}"
        print(error_msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'))

async def main_trading_loop():
    """
    The unified main trading loop for the bot.
    """
    # Display startup configuration
    print(get_startup_message())

    # --- STARTUP: Sync any trades closed while bot was offline ---
    print("🔄 Running trade reconciliation against Binance history...")
    try:
        sync_result = await asyncio.to_thread(reconcile_trades, symbols, True)
        if sync_result['backfilled_count'] > 0:
            print(f"✅ Reconciliation complete: {sync_result['backfilled_count']} missed trade(s) backfilled into logs.")
        else:
            print("✅ Reconciliation complete: No missed trades found — logs are up to date.")
    except Exception as sync_err:
        print(f"⚠️  Reconciliation failed (non-critical): {sync_err}")
    
    print("⚙️ Initializing leverage for all symbols...")
    leverage_tasks = [set_leverage(symbol, LEVERAGE) for symbol in symbols]
    await asyncio.gather(*leverage_tasks)
    print("✅ Leverage initialization complete.")
    
    cycle_count = 0
    previously_active_symbols = set()
    while not bot_state.trading_paused:
        cycle_count += 1
        print(f"\n{'='*60}")
        print(f"🔄 Cycle #{cycle_count} - {pd.Timestamp.now().strftime('%H:%M:%S')}")
        print(f"{'='*60}")
        
        try:
            # Reset BOS cycle throttle at the start of each scan cycle
            bot_state.bos_cycle_count = 0
            
            all_positions, balance_data = await asyncio.to_thread(get_all_positions_and_balance)
            active_positions = [p for p in all_positions if float(p.get('positionAmt', 0)) != 0]
            current_active_symbols = {p['symbol'] for p in active_positions}
            
            # Detect any positions closed on exchange/offline since the last cycle
            for symbol in previously_active_symbols:
                if symbol not in current_active_symbols:
                    print(f"❄️ [Exchange Exit Detected] {symbol} position closed. Applying symbol cooldown lockout and nuking orphan orders.")
                    await cancel_open_orders(symbol)
                    bot_state.last_exit_timestamps[symbol] = time.time()
                    
            previously_active_symbols = current_active_symbols

            # Fetch funding rates once per cycle — used by both close and entry logic
            funding_rates_map = await asyncio.to_thread(get_all_funding_rates)

            if len(active_positions) > 0:
                print(f"📊 Managing {len(active_positions)} active trade(s)")
                await manage_active_trades(active_positions)
            
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"⏸️  Max concurrent trades reached ({len(active_positions)}/{MAX_CONCURRENT_TRADES})")
            else:
                available_slots = MAX_CONCURRENT_TRADES - len(active_positions)
                active_symbols = {p['symbol'] for p in active_positions}
                symbols_to_check = [s for s in symbols if s not in active_symbols]
                
                print(f"🔍 Scanning {len(symbols_to_check)} symbols for entry signals...")
                await asyncio.to_thread(get_global_btc_trend)
                prev_trend = getattr(bot_state, '_prev_btc_trend', None)
                if prev_trend != bot_state.global_btc_trend:
                    print(f"🌍 Global BTC Trend CHANGED: {prev_trend} → {bot_state.global_btc_trend}")
                    bot_state._prev_btc_trend = bot_state.global_btc_trend
                else:
                    print(f"🌍 Global BTC Trend: {bot_state.global_btc_trend}")
                tasks = [process_symbol(symbol, all_positions, balance_data, funding_rates_map) for symbol in symbols_to_check]
                await asyncio.gather(*tasks)

        except Exception as e:
            error_msg = f"Error in main loop: {e}"
            print(error_msg.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8'))

        print(f"\n{'='*60}")
        print(f"✅ Cycle #{cycle_count} complete - Next cycle in 60s")
        print(f"{'='*60}\n")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_trading_loop())