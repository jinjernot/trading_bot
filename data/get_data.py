from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *
import numpy as np
from numpy import polyfit
import matplotlib.pyplot as plt


client = Client(API_KEY, API_SECRET)

# Get Token
def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

# Get USDT balance
def get_usdt_balance():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0

# Get Position
def get_position(symbol):
    try:
        positions = client.futures_position_information()
        for pos in positions:
            if pos['symbol'] == symbol:
                position_amt = float(pos['positionAmt'])
                entry_price = float(pos['entryPrice'])
                current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                order_size = abs(position_amt) * entry_price
                margin_used = order_size / leverage
                unrealized_profit = (current_price - entry_price) * position_amt
                roi = (unrealized_profit / margin_used) * 100 
                
                return position_amt, roi, unrealized_profit, margin_used
        return 0, 0, 0, 0
    except Exception as e:
        print(f"Error getting position for {symbol}: {e}")
        return 0, 0, 0, 0
    
# Get price
def get_market_price(symbol):
    try:
        price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        return price
    except Exception as e:
        print(f"Error getting market price: {e}")
        return None

# Adjust quantity to match Binance rules
def round_quantity(symbol, quantity):
    symbol_info = get_symbol_info(symbol)
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            min_qty = float(filt['minQty'])
            step_size = float(filt['stepSize'])
            quantity = max(quantity, min_qty)
            quantity = round(quantity - (quantity % step_size), 8) 
            return quantity
    return quantity
   
# Adjust price to match Binance rules
def round_price(symbol, price):
    symbol_info = get_symbol_info(symbol)
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'PRICE_FILTER':
            tick_size = float(filt['tickSize'])
            price = round(price - (price % tick_size), 8)
            return price
    return price

# Get candles
def fetch_klines(symbol, interval, lookback='60'):
    print(f"Fetching candles for {symbol} with interval {interval} and lookback {lookback}")
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    
    # Calculate support and resistance levels
    support = df['low'].min()
    resistance = df['high'].max()
        
    print(f"Support: {support}, Resistance: {resistance}")
    
    # Return the DataFrame along with support and resistance levels
    return df, support, resistance 

# Get trend
def detect_trend(df):
    trend = 'sideways'
    
    # Use 'close' prices instead of 'high' and 'low'
    for i in range(2, len(df)):
        current_close = df['close'].iloc[i]
        previous_close = df['close'].iloc[i-1]
        
        # Check if we have a higher close (uptrend)
        if current_close > previous_close:
            trend = 'uptrend'
        
        # Check if we have a lower close (downtrend)
        elif current_close < previous_close:
            trend = 'downtrend'
        
        # If neither higher close nor lower close is found
        elif trend == 'sideways':  # Maintain sideways if no clear trend is identified
            trend = 'sideways'

    return trend

def detect_local_extrema(df):
    # Find local maxima (peaks) and local minima (valleys)
    peaks = (df['high'].shift(1) < df['high']) & (df['high'].shift(-1) < df['high'])
    valleys = (df['low'].shift(1) > df['low']) & (df['low'].shift(-1) > df['low'])

    # Extract the indices of peaks and valleys
    peak_indices = df.index[peaks]
    valley_indices = df.index[valleys]

    return peak_indices, valley_indices

def fit_trend_line(df, indices, price_column):
    x = indices  # x values are the time indices
    y = df[price_column].iloc[indices]  # y values are the high/low prices at the peak or valley
    slope, intercept = polyfit(x, y, 1)  # Fit a line: y = mx + b
    
    return slope, intercept

def detect_channel_with_plot(df, symbol, threshold=0.001):
    # Get local peaks and valleys
    peak_indices, valley_indices = detect_local_extrema(df)

    if len(peak_indices) < 2 or len(valley_indices) < 2:
        print("Not enough peaks or valleys to form a channel.")
        return None, None

    # Fit trend lines for peaks (resistance) and valleys (support) using outer bounds
    resistance_slope, resistance_intercept = fit_trend_line(df, peak_indices, 'high')
    support_slope, support_intercept = fit_trend_line(df, valley_indices, 'low')

    # Check if the slopes are close (within a certain threshold)
    if abs(resistance_slope - support_slope) <= threshold * 10: 
        print("Detected a channel!")

        # Plot the data
        plt.figure(figsize=(12, 6))
        plt.plot(df['timestamp'], df['close'], label='Close Price', color='blue')
        
        # Plot resistance line (outer bounds - high prices)
        x_resistance = np.arange(len(df))
        y_resistance = resistance_slope * x_resistance + resistance_intercept
        plt.plot(df['timestamp'], y_resistance, label='Resistance', color='red', linestyle='--')
        
        # Plot support line (outer bounds - low prices)
        x_support = np.arange(len(df))
        y_support = support_slope * x_support + support_intercept
        plt.plot(df['timestamp'], y_support, label='Support', color='green', linestyle='--')

        # Plot trend direction
        trend = detect_trend(df)
        trend_color = 'orange' if trend == 'uptrend' else 'purple' if trend == 'downtrend' else 'gray'
        plt.plot(df['timestamp'], df['close'], label=f'Trend: {trend}', color=trend_color, alpha=0.5)

        plt.legend()
        plt.title(f"{symbol}")
        plt.xlabel("Timestamp")
        plt.ylabel("Price")
        plt.grid()
        plt.show()

        return resistance_slope, support_slope
    else:
        print("No channel detected.")
        return None, None