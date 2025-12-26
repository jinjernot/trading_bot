from src.trade import *
from data.get_data import *
from data.indicators import *
from config.settings import *
from config.symbols import symbols
from src.state_manager import bot_state
from src.fib_strategy import check_fib_pullback_long_entry, check_fib_retrace_short_entry
from binance.client import Client
from config.secrets import API_KEY, API_SECRET

import asyncio
import time

# --- NEW: Set your desired leverage here ---
client = Client(API_KEY, API_SECRET)
# Sync time with Binance servers to fix timestamp errors
try:
    server_time = client.get_server_time()
    local_time = int(time.time() * 1000)
    time_offset = server_time['serverTime'] - local_time
    client.timestamp_offset = time_offset
except Exception:
    pass  # Silent fail on import

async def set_leverage(symbol, leverage):
    """
    Sets the leverage for a given symbol.
    """
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        if VERBOSE_LOGGING:
            print(f"Leverage for {symbol} set to {leverage}x.")
    except Exception as e:
        # We can ignore the "No need to change leverage" error from Binance
        if "No need to change leverage" not in str(e):
            print(f"Error setting leverage for {symbol}: {e}")

async def process_fib_symbol(symbol, all_positions, balance_data):
    """
    Processes a single symbol for both long and short Fibonacci strategies.
    """
    try:
        # --- NEW: Set leverage for the symbol at the start of processing ---
        await set_leverage(symbol, LEVERAGE)

        df_15m, _, _, df_4h, _, _, _, _, _ = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME
        )

        df_15m = calculate_atr(df_15m)
        df_4h = calculate_adx(df_4h)
        df_4h = add_price_sma(df_4h, 50)
        
        position, _, _, _, _ = get_position(symbol, all_positions)
        usdt_balance = get_usdt_balance(balance_data)

        if position == 0:
            long_trade_taken = await check_fib_pullback_long_entry(symbol, df_15m, df_4h, usdt_balance)
            if not long_trade_taken:
                await check_fib_retrace_short_entry(symbol, df_15m, df_4h, usdt_balance)

    except Exception as e:
        print(f"Error processing Fibonacci strategy for {symbol}: {e}")
        await asyncio.sleep(1)

async def fib_bot_main_loop():
    """
    The main trading loop for the bidirectional Fibonacci Bot.
    """
    print(f"--- 🤖 Starting Bidirectional Fibonacci Bot with {LEVERAGE}x Leverage ---")
    while not bot_state.trading_paused:
        print("\n--- Fibonacci Bot: Starting new cycle ---")
        
        try:
            all_positions, balance_data = get_all_positions_and_balance()
            active_positions = [p for p in all_positions if float(p.get('positionAmt', 0)) != 0]

            await manage_active_trades(active_positions)
            
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"Max concurrent trades reached...")
            else:
                tasks = [process_fib_symbol(symbol, all_positions, balance_data) for symbol in symbols if symbol not in [p['symbol'] for p in active_positions]]
                await asyncio.gather(*tasks)

        except Exception as e:
            print(f"Error in Fibonacci main loop: {e}")

        print("\n--- Fibonacci Bot cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(fib_bot_main_loop())