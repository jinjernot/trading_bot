from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import argrelextrema

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
def fetch_klines(symbol, interval, lookback='100'):
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

def detect_trend(df, window=2):
    trend = 'sideways'  # Default to sideways trend
    
    for i in range(window, len(df)):  # Start from the `window` index (since we need previous `window` data)
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        
        # Define the previous `window` number of highs and lows
        high_window = df['high'].iloc[i-window:i]
        low_window = df['low'].iloc[i-window:i]
        
        # Check for higher high (uptrend)
        if current_high == high_window.max():
            trend = 'uptrend'
        
        # Check for lower low (downtrend)
        elif current_low == low_window.min():
            trend = 'downtrend'
        
        # If neither higher high nor lower low, trend remains sideways
        elif trend == 'sideways':  # Maintain sideways if no clear trend is identified
            trend = 'sideways'

    return trend


# Function to detect local peaks (highs) and valleys (lows)
def detect_local_extrema(df):
    # Find local maxima (peaks) and local minima (valleys)
    peaks = (df['high'].shift(1) < df['high']) & (df['high'].shift(-1) < df['high'])
    valleys = (df['low'].shift(1) > df['low']) & (df['low'].shift(-1) > df['low'])

    # Extract the indices of peaks and valleys
    peak_indices = df.index[peaks]
    valley_indices = df.index[valleys]

    return peak_indices, valley_indices

# Function to fit a trend line using the given indices (peaks or valleys)
def fit_trend_line(df, indices, price_column):
    x = indices  # x values are the time indices
    y = df[price_column].iloc[indices]  # y values are the high/low prices at the peak or valley
    slope, intercept = np.polyfit(x, y, 1)  # Fit a line: y = mx + b
    return slope, intercept

# Function to detect parallel channel based on highs (resistance) and lows (support)
def detect_parallel_channel(df, symbol, threshold=0.00001):
    # Get local peaks and valleys
    peak_indices, valley_indices = detect_local_extrema(df)

    if len(peak_indices) < 4 or len(valley_indices) < 4:
        print("Not enough peaks or valleys to form a channel.")
        return None, None

    # Fit trend lines for both peaks (resistance) and valleys (support)
    resistance_slope, resistance_intercept = fit_trend_line(df, peak_indices, 'high')
    support_slope, support_intercept = fit_trend_line(df, valley_indices, 'low')

    # Ensure the slopes are the same for both resistance and support
    if abs(resistance_slope - support_slope) > threshold:
        print("Slopes are not parallel. Adjusting to make them parallel.")
        # Set both slopes to the same value (use the average slope of both)
        average_slope = (resistance_slope + support_slope) / 2
        resistance_slope = support_slope = average_slope

    # Adjust intercepts based on the new parallel slope
    resistance_intercept = np.mean(df['high'].iloc[peak_indices]) - resistance_slope * np.mean(peak_indices)
    support_intercept = np.mean(df['low'].iloc[valley_indices]) - support_slope * np.mean(valley_indices)

    # Plot the data
    plt.figure(figsize=(12, 6))
    plt.plot(df['timestamp'], df['close'], label='Close Price', color='blue')
    
    # Plot resistance line (upper bound) with parallel slope
    x_resistance = np.arange(len(df))
    y_resistance = resistance_slope * x_resistance + resistance_intercept
    plt.plot(df['timestamp'], y_resistance, label='Resistance (Parallel)', color='red', linestyle='--')
    
    # Plot support line (lower bound) with parallel slope
    x_support = np.arange(len(df))
    y_support = support_slope * x_support + support_intercept
    plt.plot(df['timestamp'], y_support, label='Support (Parallel)', color='green', linestyle='--')

    # Plot trend direction (optional)
    trend = detect_trend(df)
    trend_color = 'orange' if trend == 'uptrend' else 'purple' if trend == 'downtrend' else 'gray'
    plt.plot(df['timestamp'], df['close'], label=f'Trend: {trend}', color=trend_color, alpha=0.5)

    plt.legend()
    plt.title(f"{symbol} Parallel Channel")
    plt.xlabel("Timestamp")
    plt.ylabel("Price")
    plt.grid()
    plt.show()

    return resistance_slope, resistance_intercept, support_slope, support_intercept

def detect_multiple_parallel_channels(df, symbol, threshold=0.00001, min_channel_points=4):
    # Get local peaks and valleys
    peak_indices, valley_indices = detect_local_extrema(df)

    if len(peak_indices) < min_channel_points or len(valley_indices) < min_channel_points:
        print("Not enough peaks or valleys to form multiple channels.")
        return []

    channels = []

    # Try to form multiple channels by iterating over subsets of peaks and valleys
    for i in range(0, len(peak_indices) - min_channel_points + 1, min_channel_points):
        # Select a window of peaks and valleys to form a channel
        selected_peaks = peak_indices[i:i + min_channel_points]
        selected_valleys = valley_indices[i:i + min_channel_points]

        # Fit trend lines for both peaks (resistance) and valleys (support)
        resistance_slope, resistance_intercept = fit_trend_line(df, selected_peaks, 'high')
        support_slope, support_intercept = fit_trend_line(df, selected_valleys, 'low')

        # Ensure the slopes are the same for both resistance and support (parallelism)
        if abs(resistance_slope - support_slope) > threshold:
            print("Slopes are not parallel. Skipping this set of peaks/valleys.")
            continue  # Skip if the slopes are not parallel

        # Adjust intercepts based on the new parallel slope
        resistance_intercept = np.mean(df['high'].iloc[selected_peaks]) - resistance_slope * np.mean(selected_peaks)
        support_intercept = np.mean(df['low'].iloc[selected_valleys]) - support_slope * np.mean(selected_valleys)

        # Store the channel
        channels.append({
            'resistance_slope': resistance_slope,
            'resistance_intercept': resistance_intercept,
            'support_slope': support_slope,
            'support_intercept': support_intercept
        })

    # Plot the data and all channels
    plt.figure(figsize=(12, 6))
    plt.plot(df['timestamp'], df['close'], label='Close Price', color='blue')

    # Plot all detected channels
    for channel in channels:
        x = np.arange(len(df))
        
        # Plot resistance line (upper bound) with parallel slope
        y_resistance = channel['resistance_slope'] * x + channel['resistance_intercept']
        plt.plot(df['timestamp'], y_resistance, label='Resistance (Parallel)', linestyle='--')

        # Plot support line (lower bound) with parallel slope
        y_support = channel['support_slope'] * x + channel['support_intercept']
        plt.plot(df['timestamp'], y_support, label='Support (Parallel)', linestyle='--')

    # Plot trend direction (optional)
    trend = detect_trend(df)
    trend_color = 'orange' if trend == 'uptrend' else 'purple' if trend == 'downtrend' else 'gray'
    plt.plot(df['timestamp'], df['close'], label=f'Trend: {trend}', color=trend_color, alpha=0.5)

    plt.legend()
    plt.title(f"{symbol} Multiple Parallel Channels")
    plt.xlabel("Timestamp")
    plt.ylabel("Price")
    plt.grid()
    plt.show()

    return channels