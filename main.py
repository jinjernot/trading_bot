import asyncio
from binance.client import Client
from config.secrets import API_KEY, API_SECRET
from config.symbols import symbols
from data.get_data import fetch_multi_timeframe_data, get_all_positions_and_balance, get_usdt_balance, get_position, get_funding_rate
from data.indicators import *
from src.close_position import close_position_long, close_position_short
from src.trade import manage_active_trades
from src.state_manager import bot_state
from config.settings import *

# --- Import Both Strategy Functions ---
from src.fib_strategy import check_fib_pullback_long_entry, check_fib_retrace_short_entry
from src.open_position import open_position_long, open_position_short


client = Client(API_KEY, API_SECRET)

async def set_leverage(symbol, leverage):
    """
    Sets the leverage for a given symbol.
    """
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        if VERBOSE_LOGGING:
            print(f"Leverage for {symbol} set to {leverage}x.")
    except Exception as e:
        if "No need to change leverage" not in str(e):
            print(f"Error setting leverage for {symbol}: {e}")

async def process_symbol(symbol, all_positions, balance_data):
    """
    Processes a single symbol by checking for trade signals in a hierarchical order.
    1. First, check for the high-probability Fibonacci setup.
    2. If no Fib setup is found, then check for the general trend-following setup.
    """
    try:
        # --- Set leverage for the symbol at the start of processing ---
        await set_leverage(symbol, LEVERAGE)

        df_15m, _, _, df_4h, support_4h, resistance_4h, _, _, _ = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, '15m', '4h', '1d'
        )

        # --- Prepare Data and Indicators ---
        df_15m = calculate_atr(df_15m)
        df_15m = calculate_rsi(df_15m)
        df_15m = add_price_sma(df_15m, 50)
        df_15m = calculate_hull_moving_average(df_15m, 14)
        stoch_k_15m, stoch_d_15m = calculate_stoch(df_15m['high'], df_15m['low'], df_15m['close'], 14, 3, 3)
        df_4h = calculate_adx(df_4h)
        df_4h = add_price_sma(df_4h, 50)
        
        position, roi, _, _, entry_price = get_position(symbol, all_positions)
        usdt_balance = get_usdt_balance(balance_data)
        funding_rate = get_funding_rate(symbol)
        atr_value_15m = df_15m['atr'].iloc[-1]

        # --- Position Management Logic (for open trades) ---
        if position > 0: # Active Long Position
            await close_position_long(symbol, position, roi, df_15m, stoch_k_15m, stoch_d_15m, None, atr_value_15m, entry_price)
        elif position < 0: # Active Short Position
            await close_position_short(symbol, position, roi, df_15m, stoch_k_15m, stoch_d_15m, None, atr_value_15m, entry_price)
        
        # --- Entry Logic (for new trades) ---
        if position == 0:
            # 1. Check for Fibonacci Strategy First
            fib_trade_taken = await check_fib_pullback_long_entry(symbol, df_15m, df_4h, usdt_balance)
            if not fib_trade_taken:
                fib_trade_taken = await check_fib_retrace_short_entry(symbol, df_15m, df_4h, usdt_balance)

            # 2. If no Fibonacci trade was taken, check for the General Trend Strategy
            if not fib_trade_taken:
                general_trade_taken = await open_position_long(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, None, None, atr_value_15m, funding_rate, support_4h, resistance_4h)
                if not general_trade_taken:
                    await open_position_short(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, None, None, atr_value_15m, funding_rate, support_4h, resistance_4h)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")

async def main_trading_loop():
    """
    The unified main trading loop for the bot.
    """
    print(f"--- 🤖 Starting Unified Trading Bot with {LEVERAGE}x Leverage ---")
    while not bot_state.trading_paused:
        print("\n--- Unified Bot: Starting new cycle ---")
        
        try:
            all_positions, balance_data = get_all_positions_and_balance()
            active_positions = [p for p in all_positions if float(p.get('positionAmt', 0)) != 0]

            await manage_active_trades(active_positions)
            
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"Max concurrent trades reached ({len(active_positions)}/{MAX_CONCURRENT_TRADES})...")
            else:
                tasks = [process_symbol(symbol, all_positions, balance_data) for symbol in symbols if symbol not in [p['symbol'] for p in active_positions]]
                await asyncio.gather(*tasks)

        except Exception as e:
            print(f"Error in main loop: {e}")

        print("\n--- Unified Bot cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main_trading_loop())