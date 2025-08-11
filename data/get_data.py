from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import argrelextrema

from data.plot import plot_channel

client = Client(API_KEY, API_SECRET)

def fetch_multi_timeframe_data(symbol, short_interval, long_interval):
    """
    Fetches candlestick data for both a short and a long timeframe.
    Returns both DataFrames and their respective support/resistance levels.
    """
    # --- MODIFIED: Conditional print ---
    if VERBOSE_LOGGING:
        print(f"Fetching multi-timeframe data for {symbol}: {short_interval} and {long_interval}")
    
    # Fetch and unpack short-term data (e.g., 15m)
    df_short, support_short, resistance_short = fetch_klines(symbol, short_interval, lookback='100')
    
    # Fetch and unpack long-term data (e.g., 4h)
    df_long, support_long, resistance_long = fetch_klines(symbol, long_interval, lookback='100')
    
    return df_short, support_short, resistance_short, df_long, support_long, resistance_long

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

def calculate_volatility(df):
    # Volatility calculated as standard deviation of close prices
    return df['close'].pct_change().std()

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
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    
    # Calculate support and resistance levels
    support = df['low'].min()
    resistance = df['high'].max()
        
    # Return the DataFrame along with support and resistance levels
    return df, support, resistance 

def detect_trend(df, window=4, confirm=2):
    # Check if the DataFrame is too small
    if len(df) < window:
        return 'sideways'

    # Initializations
    trend = 'sideways'
    uptrend_count = 0
    downtrend_count = 0

    # Calculate overall trend from start to end prices
    start_price = df['close'].iloc[0]
    end_price = df['close'].iloc[-1]
    overall_trend = 'uptrend' if end_price > start_price else 'downtrend' if end_price < start_price else 'sideways'

    # Loop to detect trends using rolling highs and lows
    for i in range(window, len(df)):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        high_window = df['high'].iloc[i-window:i]
        low_window = df['low'].iloc[i-window:i]

        # Check for higher high
        if current_high >= high_window.max():
            uptrend_count += 1
            downtrend_count = 0
        # Check for lower low
        elif current_low <= low_window.min():
            downtrend_count += 1
            uptrend_count = 0
        # Reset counts if no clear trend
        else:
            uptrend_count = 0
            downtrend_count = 0

        # Confirm trend based on counts
        if uptrend_count >= confirm:
            trend = 'uptrend'
        elif downtrend_count >= confirm:
            trend = 'downtrend'
        else:
            trend = 'sideways'

    # Combine overall trend with rolling trend
    if overall_trend != 'sideways' and trend == 'sideways':
        return overall_trend
    elif overall_trend == trend:
        return trend
    else:
        return 'sideways'

def get_funding_rate(symbol):
    try:
        # Fetch the most recent funding rate history (limit=1 gets the latest)
        funding_rate_history = client.futures_funding_rate(symbol=symbol, limit=1)
        if funding_rate_history:
            # The rate is a string, convert it to a float
            return float(funding_rate_history[0]['fundingRate'])
        return 0.0
    except Exception as e:
        print(f"Error getting funding rate for {symbol}: {e}")
        return 0.0