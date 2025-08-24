from src.trade import *
from data.get_data import *
from data.indicators import *
from config.settings import *
from config.symbols import symbols
from src.state_manager import bot_state
from src.fib_strategy import check_fib_pullback_entry

import asyncio

async def process_fib_symbol(symbol, all_positions, balance_data):
    """
    Processes a single symbol for the Fibonacci pullback strategy.
    """
    try:
        df_15m, _, _, df_4h, _, _, _, _, _ = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, '15m', '4h', '1d'
        )

        df_15m = calculate_atr(df_15m)
        df_4h = calculate_adx(df_4h)
        df_4h = add_price_sma(df_4h, 50)
        
        position, _, _, _, _ = get_position(symbol, all_positions)
        usdt_balance = get_usdt_balance(balance_data)

        if position == 0:
            await check_fib_pullback_entry(symbol, df_15m, df_4h, usdt_balance)

    except Exception as e:
        print(f"Error processing Fibonacci strategy for {symbol}: {e}")
        await asyncio.sleep(1)

async def fib_bot_main_loop():
    """
    The main trading loop for the Fibonacci Pullback Bot.
    """
    print("--- 🤖 Starting Fibonacci Pullback Bot (Pure Fib Strategy) ---")
    while not bot_state.trading_paused:
        print("\n---  Fibonacci Bot: Starting new cycle ---")
        
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