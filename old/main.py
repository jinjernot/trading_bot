import time
import numpy as np
import pandas as pd
from binance.client import Client
from binance.enums import *
from config.api import API_KEY, API_SECRET

client = Client(API_KEY, API_SECRET)

# Parameters
symbol = 'BTCUSDT'
interval = Client.KLINE_INTERVAL_1MINUTE
stoch_period = 14
k_period = 3
d_period = 3
leverage = 10
oversold_threshold = 20
overbought_threshold = 80

# Calculate Stochastic Oscillator
def calculate_stoch(high, low, close, stoch_period, k_period, d_period):
    lowest_low = low.rolling(stoch_period).min()
    highest_high = high.rolling(stoch_period).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    stoch_d = stoch_k.rolling(d_period).mean()
    return stoch_k, stoch_d

# Fetch historical klines
def fetch_klines(symbol, interval, lookback='50'):
    print(f"Fetching klines for {symbol} with interval {interval} and lookback {lookback}")
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    print(f"Fetched {len(df)} rows of data.")
    return df

# Detect engulfing pattern
def is_engulfing(df):
    last = df.iloc[-1]
    second_last = df.iloc[-2]
    if last['close'] > last['open'] and last['open'] < second_last['close'] and last['close'] > second_last['open']:
        return "bullish"
    elif last['close'] < last['open'] and last['open'] > second_last['close'] and last['close'] < second_last['open']:
        return "bearish"
    return None

# Place order
def place_order(symbol, side, quantity):
    print(f"Placing order: {side} {quantity} {symbol}")
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        print(f"Order placed successfully: {order}")
    except Exception as e:
        print(f"Error placing order: {e}")

# Fetch open position
def get_position(symbol):
    positions = client.futures_position_information()
    for pos in positions:
        if pos['symbol'] == symbol:
            return float(pos['positionAmt']), float(pos['unrealizedProfit'])
    return 0, 0  # No open position

# Close position
def close_position(symbol, side, quantity):
    print(f"Closing position: {side} {quantity} {symbol}")
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_MARKET,
            quantity=quantity
        )
        print(f"Position closed successfully: {order}")
    except Exception as e:
        print(f"Error closing position: {e}")

# Main trading loop
def main():
    print(f"Setting leverage for {symbol} to {leverage}")
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print("Leverage set successfully.")
    except Exception as e:
        print(f"Error setting leverage: {e}")
        return
    
    while True:
        try:
            print(f"\n--- New Iteration ---")
            df = fetch_klines(symbol, interval)
            
            stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], stoch_period, k_period, d_period)
            print(f"Stochastic K: {stoch_k.iloc[-3:].values}")
            print(f"Stochastic D: {stoch_d.iloc[-3:].values}")
            
            engulfing = is_engulfing(df)
            print(f"Engulfing pattern detected: {engulfing}")
            
            position, unrealized_profit = get_position(symbol)
            print(f"Current position: {position}, Unrealized Profit: {unrealized_profit}")

            # Close Positions
            if position > 0:  # Long position open
                if (stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-2] >= stoch_d.iloc[-2]) or unrealized_profit >= 10:
                    print("Closing LONG position")
                    close_position(symbol, SIDE_SELL, abs(position))
            
            elif position < 0:  # Short position open
                if (stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-2] <= stoch_d.iloc[-2]) or unrealized_profit >= 10:
                    print("Closing SHORT position")
                    close_position(symbol, SIDE_BUY, abs(position))

            # Open New Positions
            if position == 0:
                if (stoch_k.iloc[-1] > stoch_d.iloc[-1] and 
                    stoch_k.iloc[-2] <= stoch_d.iloc[-2] and 
                    stoch_k.iloc[-1] < oversold_threshold and 
                    engulfing == "bullish"):
                    print("Bullish crossover with bullish engulfing detected - Going LONG")
                    place_order(symbol, SIDE_BUY, quantity=0.001)
                elif (stoch_k.iloc[-1] < stoch_d.iloc[-1] and 
                      stoch_k.iloc[-2] >= stoch_d.iloc[-2] and 
                      stoch_k.iloc[-1] > overbought_threshold and 
                      engulfing == "bearish"):
                    print("Bearish crossover with bearish engulfing detected - Going SHORT")
                    place_order(symbol, SIDE_SELL, quantity=0.001)  
            
            print("Sleeping for 10 seconds...\n")
            time.sleep(10) 
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
