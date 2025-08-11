from src.close_position import *
from src.open_position_copy import *
from src.trade import *
  
from data.get_data import *
from data.indicators import *

from data.indicators import add_short_term_sma

from src.telegram_bot import *
from config.settings import *
# --- MODIFIED: Ensure we're importing from our new curated list ---
from config.symbols import symbols
from src.state_manager import bot_state

import asyncio
import time

# --- Risk Management Settings ---
MAX_CONCURRENT_TRADES = 4
MAX_CONSECUTIVE_LOSSES = 3
COOL_DOWN_PERIOD_SECONDS = 3600 # 1 hour

async def process_symbol(symbol):
    
    try:
        print(f"Processing symbol: {symbol}...")
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except Exception as e:
        if 'APIError(code=-4028)' in str(e):
            print(f"Leverage {leverage} is not valid for {symbol}. Trying to set leverage to 10.")
            try:
                client.futures_change_leverage(symbol=symbol, leverage=10)
            except Exception as e2:
                print(f"Failed to set leverage to 10 for {symbol}: {e2}")
                return
        else:
            print(f"An unexpected error occurred while setting leverage for {symbol}: {e}")
            return

    try:
        df, support, resistance  = fetch_klines(symbol, interval)
        df = add_price_sma(df, period=50)
        df = add_volume_sma(df, period=20)
        df = add_short_term_sma(df, period=9)
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        df = calculate_rsi(df, period=14)
        df = calculate_atr(df)
        atr_value = df['atr'].iloc[-1]
        
        # --- NEW: Volatility Filter ---
        last_close = df['close'].iloc[-1]
        # Calculate ATR as a percentage of the closing price
        atr_percentage = (atr_value / last_close) * 100
        # Define your optimal volatility range. For a 15m chart, a good range is often between 0.2% and 2.0%.
        # This avoids trading when the market is too flat (less than 0.2% movement per candle)
        # or too volatile (more than 2.0% movement per candle).
        MIN_VOLATILITY = 0.2
        MAX_VOLATILITY = 2.0
        if not (MIN_VOLATILITY < atr_percentage < MAX_VOLATILITY):
            print(f"Skipping {symbol}: Volatility ({atr_percentage:.2f}%) is outside the optimal range.")
            return
        
        position, roi, unrealized_profit, margin_used = get_position(symbol)
        usdt_balance = get_usdt_balance()
        trend = detect_trend(df)
        funding_rate = get_funding_rate(symbol)

        if VERBOSE_LOGGING:
            print(f"\n--- Verbose Log for {symbol} ({nice_interval}) ---")
            print(f"Stochastic K: {stoch_k.iloc[-3:].values}")
            print(f"Stochastic D: {stoch_d.iloc[-3:].values}")
            print(f"RSI: {df['rsi'].iloc[-3:].values}")
            print(f"Position: {position}, ROI: {roi:.2f}%")
            print(f"--- End Log ---\n")
        
        if position > 0:
            await close_position_long(symbol, position, roi, df, stoch_k, resistance)
        elif position < 0:
            await close_position_short(symbol, position, roi, df, stoch_k, support)
        
        if bot_state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES and not bot_state.trading_paused:
            print(f"\n!!! CIRCUIT BREAKER: Pausing new trades for 1 hour due to {bot_state.consecutive_losses} consecutive losses. !!!\n")
            bot_state.trading_paused = True

        if bot_state.trading_paused:
            return

        if position == 0:
            if trend == 'uptrend':
                await open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate)
            elif trend == 'downtrend':
                await open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate)     
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