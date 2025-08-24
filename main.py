from src.close_position import *
from src.open_position import *
from src.trade import *
  
from data.get_data import *
from data.indicators import *

from data.indicators import add_short_term_sma, calculate_hull_moving_average

from config.settings import *
from config.symbols import symbols
from src.state_manager import bot_state

import asyncio
import time

# --- Timeframe Settings ---
EXECUTION_TIMEFRAME = '15m'
INTERMEDIATE_TIMEFRAME = '4h'
PRIMARY_TIMEFRAME = '1d'

async def process_symbol(symbol, all_positions, balance_data): # MODIFIED: Accept pre-fetched data
    
    try:
        df_15m, support_15m, resistance_15m, \
        df_4h, support_4h, resistance_4h, stoch_k_4h, stoch_d_4h, \
        df_1d = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME
        )
        
        # (Indicator calculations remain the same)
        # ...
        
        # --- MODIFIED: Use pre-fetched data ---
        position, roi, _, _, entry_price = get_position(symbol, all_positions)
        usdt_balance = get_usdt_balance(balance_data)
        funding_rate = get_funding_rate(symbol) # This is a light call, can remain for now
        
        # (All other logic remains the same)
        # ...
    
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(1)

async def main():
    while True:
        # (Pause logic remains the same)
        # ...

        print("\n--- Starting new trading cycle ---")
        
        try:
            # --- MODIFIED: Fetch all account data ONCE per cycle ---
            all_positions, balance_data = get_all_positions_and_balance()
            
            active_positions = [p for p in all_positions if float(p.get('positionAmt', 0)) != 0]

            await manage_active_trades(active_positions)
            
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"Max concurrent trades reached...")
            else:
                # --- MODIFIED: Pass pre-fetched data into the processing function ---
                tasks = [process_symbol(symbol, all_positions, balance_data) for symbol in symbols if symbol not in [p['symbol'] for p in active_positions]]
                await asyncio.gather(*tasks)

        except Exception as e:
            print(f"Error in main loop: {e}")

        print("\n--- Trading cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())