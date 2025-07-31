from src.close_position import *
from src.open_position_copy import *
from src.trade import *
  
from data.get_data import *
from data.indicators import *

from src.telegram_bot import *
from config.settings import *
from config.symbols import *
from src.state_manager import bot_state

import asyncio

MAX_CONSECUTIVE_LOSSES = 10

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
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        df = calculate_rsi(df, period=14)
        df = calculate_atr(df)
        atr_value = df['atr'].iloc[-1]
        
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
            print(f"\n!!! CIRCUIT BREAKER TRIPPED: Pausing new trades due to {bot_state.consecutive_losses} consecutive losses. !!!\n")
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
        # Add a small sleep here as well to prevent spamming on errors
        await asyncio.sleep(1)

async def main():
    while True:
        print("\n--- Starting new trading cycle ---")
        tasks = [process_symbol(symbol) for symbol in symbols]
        await asyncio.gather(*tasks)
        
        # CRITICAL FIX: Wait for a period of time before checking all symbols again.
        # 60 seconds is a reasonable starting point.
        print("\n--- Trading cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    if VERBOSE_LOGGING:
        print("Bot starting in VERBOSE mode.")
    else:
        print("Bot starting in QUIET mode.")
    asyncio.run(main())
