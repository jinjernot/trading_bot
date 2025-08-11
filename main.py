from src.close_position import *
from src.open_position_copy import *
from src.trade import *
  
# --- MODIFIED: Import the new multi-timeframe function ---
from data.get_data import *
from data.indicators import *

from data.indicators import add_short_term_sma

from src.telegram_bot import *
from config.settings import *
from config.symbols import symbols
from src.state_manager import bot_state

import asyncio
import time

# --- Risk Management Settings ---
MAX_CONCURRENT_TRADES = 4
MAX_CONSECUTIVE_LOSSES = 3
COOL_DOWN_PERIOD_SECONDS = 3600 # 1 hour

# --- NEW: Timeframe Settings ---
SHORT_TERM_INTERVAL = '15m'
LONG_TERM_INTERVAL = '4h'

async def process_symbol(symbol):
    
    try:
        # --- MODIFIED: Fetch data for both timeframes ---
        df_15m, df_4h = await asyncio.to_thread(fetch_multi_timeframe_data, symbol, SHORT_TERM_INTERVAL, LONG_TERM_INTERVAL)
        
        # --- NEW: Determine the long-term trend from the 4h chart ---
        long_term_trend = detect_trend(df_4h)
        print(f"Long-term trend for {symbol} on {LONG_TERM_INTERVAL} chart: {long_term_trend}")
        
        # --- Process 15m data for entry signals ---
        df_15m = add_price_sma(df_15m, period=50)
        df_15m = add_volume_sma(df_15m, period=20)
        df_15m = add_short_term_sma(df_15m, period=9)
        stoch_k, stoch_d = calculate_stoch(df_15m['high'], df_15m['low'], df_15m['close'], PERIOD, K, D)
        df_15m = calculate_rsi(df_15m, period=14)
        df_15m = calculate_atr(df_15m)
        atr_value = df_15m['atr'].iloc[-1]
        
        # Volatility Filter
        last_close = df_15m['close'].iloc[-1]
        atr_percentage = (atr_value / last_close) * 100
        MIN_VOLATILITY = 0.2
        MAX_VOLATILITY = 2.0
        if not (MIN_VOLATILITY < atr_percentage < MAX_VOLATILITY):
            print(f"Skipping {symbol}: Volatility ({atr_percentage:.2f}%) is outside the optimal range.")
            return
        
        position, roi, unrealized_profit, margin_used = get_position(symbol)
        usdt_balance = get_usdt_balance()
        funding_rate = get_funding_rate(symbol)
        
        # For exits, we still use the 15m data
        if position > 0:
            await close_position_long(symbol, position, roi, df_15m, stoch_k, df_15m['high'].max())
        elif position < 0:
            await close_position_short(symbol, position, roi, df_15m, stoch_k, df_15m['low'].min())
        
        if bot_state.trading_paused:
            return

        # --- MODIFIED: Core logic now uses the long-term trend as a filter ---
        if position == 0:
            if long_term_trend == 'uptrend':
                print(f"4h trend is UP. Looking for a LONG entry on the 15m chart for {symbol}.")
                await open_position_long(symbol, df_15m, stoch_k, stoch_d, usdt_balance, df_15m['low'].min(), df_15m['high'].max(), atr_value, funding_rate)
            elif long_term_trend == 'downtrend':
                print(f"4h trend is DOWN. Looking for a SHORT entry on the 15m chart for {symbol}.")
                await open_position_short(symbol, df_15m, stoch_k, stoch_d, usdt_balance, df_15m['low'].min(), df_15m['high'].max(), atr_value, funding_rate)
            else:
                print(f"4h trend is SIDEWAYS for {symbol}. No new trades will be opened.")
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(1)

async def main():
    pause_until = 0
    while True:
        if bot_state.trading_paused:
            if pause_until == 0:
                pause_until = time.time() + COOL_DOWN_PERIOD_SECONDS
            
            if time.time() < pause_until:
                print(f"Trading is paused. Resuming in {int((pause_until - time.time()) / 60)} minutes.")
                await asyncio.sleep(60)
                continue
            else:
                print("Resuming trading after cool-down period.")
                bot_state.trading_paused = False
                bot_state.consecutive_losses = 0
                pause_until = 0

        print("\n--- Starting new trading cycle ---")
        
        try:
            positions = client.futures_position_information()
            active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"Max concurrent trade limit ({MAX_CONCURRENT_TRADES}) reached. Skipping new trades for this cycle.")
            else:
                tasks = [process_symbol(symbol) for symbol in symbols]
                await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error fetching position information: {e}")

        print("\n--- Trading cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    if VERBOSE_LOGGING:
        print("Bot starting in VERBOSE mode.")
    else:
        print("Bot starting in QUIET mode.")
    asyncio.run(main())