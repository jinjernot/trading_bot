from src.close_position import *
from src.open_position_copy import *
from src.trade import *
  
from data.get_data import *
from data.indicators import *

from src.telegram_bot import *
from config.settings import *
from config.symbols import *

import asyncio


async def process_symbol(symbol):
    
    try:
        print(f"Attempting to set leverage to {leverage} for {symbol}...")
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage for {symbol} set to {leverage}.")
    except Exception as e:
        # Check if the error is due to invalid leverage
        if 'APIError(code=-4028)' in str(e):
            print(f"Leverage {leverage} is not valid for {symbol}. Trying to set leverage to 10.")
            try:
                # Try setting a lower, safer leverage
                client.futures_change_leverage(symbol=symbol, leverage=10)
                print(f"Successfully set leverage for {symbol} to 10.")
            except Exception as e2:
                # If setting the lower leverage also fails, skip the symbol
                print(f"Failed to set leverage to 10 for {symbol}: {e2}")
                return
        else:
            # For any other errors, print the error and skip the symbol
            print(f"An unexpected error occurred while setting leverage for {symbol}: {e}")
            return

    try:
        print(f"\n--- New Iteration for {symbol} ({nice_interval}) ---")
        
        print(f"\n--- Check Daily ---")
        # **Fetch Intraday Candles for Volatility Check**
        df_intraday, _, _ = fetch_klines(symbol, intraday_interval)
        
        # Calculate Volatility using intraday data
        volatility = calculate_volatility(df_intraday) * 100
        print(f"Intraday Volatility for {symbol}: {volatility:.2f}%")

        # Only continue processing if price movement is at least 10%
        if volatility < 5:
            print(f"--- Skipping {symbol} due to low intraday volatility ---")
            return
        
        print(f"\n")
        # **Fetch Standard Candles for the Rest of the Calculations**
        df, support, resistance  = fetch_klines(symbol, interval)
        
        df = add_price_sma(df, period=50)
        df = add_volume_sma(df, period=20)

        # Calculate Stochastic
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        
        print(f"Stochastic K for {symbol}: {stoch_k.iloc[-3:].values}")
        print(f"Stochastic D for {symbol}: {stoch_d.iloc[-3:].values}")

        # Calculate RSI
        df = calculate_rsi(df, period=14)
        print(f"RSI for {symbol}: {df['rsi'].iloc[-3:].values}")
        
        # Calculate ATR
        df = calculate_atr(df)
        atr_value = df['atr'].iloc[-1]
        print(f"ATR for {symbol}: {atr_value:.4f}")
        
        # Get current position and ROI
        position, roi, unrealized_profit, margin_used = get_position(symbol)
        print(f"Position for {symbol}: {position}, ROI: {roi:.2f}%, Unrealized Profit: {unrealized_profit:.2f}")
        print(f"Margin Used for {symbol}: {margin_used}")

        # Get USDT balance
        usdt_balance = get_usdt_balance()
        print(f"Available USDT balance for {symbol}: {usdt_balance}")

        # Get trend
        trend = detect_trend(df)
        print(f"Market trend for {symbol}: {trend}")
        print(f"--- End Iteration {symbol} ({nice_interval}) ---\n")
        
        # Detect a channel
        #await detect_parallel_channel(df,symbol)

        # Close positions
        if position > 0:
            await close_position_long(symbol, position, roi, df, stoch_k, resistance)
        elif position < 0:
            await close_position_short(symbol, position, roi, df, stoch_k, support)

        # Open new positions
    
        if position == 0:
            if trend == 'uptrend':
                # Pass atr_value to the function
                await open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value)
            elif trend == 'downtrend':
                # Pass atr_value to the function
                await open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value) 
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(60)

async def main():
    while True:
        tasks = [process_symbol(symbol) for symbol in symbols]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())