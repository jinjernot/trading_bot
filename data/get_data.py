from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *
import numpy as np
from scipy.signal import argrelextrema
import time

from data.indicators import calculate_stoch, add_price_sma, PERIOD, K, D
from src.state_manager import bot_state

client = Client(API_KEY, API_SECRET)

# --- MODIFIED: Implemented Caching Logic ---
def fetch_multi_timeframe_data(symbol, short_interval, mid_interval, long_interval):
    current_time = time.time()
    
    # Define cache duration in seconds
    CACHE_DURATION_MID = 1800  # 30 minutes for 4h data
    CACHE_DURATION_LONG = 14400 # 4 hours for 1d data

    # --- Fetch Short-Term Data (Always) ---
    if VERBOSE_LOGGING:
        print(f"Fetching 15m data for {symbol}...")
    df_short, support_short, resistance_short = fetch_klines(symbol, short_interval, lookback='100')

    # --- Fetch Mid-Term (4h) Data (from Cache or API) ---
    if (symbol not in bot_state.last_fetch_time_mid or \
        (current_time - bot_state.last_fetch_time_mid[symbol]) > CACHE_DURATION_MID):
        if VERBOSE_LOGGING:
            print(f"Cache expired. Fetching fresh 4h data for {symbol}...")
        df_mid, support_mid, resistance_mid = fetch_klines(symbol, mid_interval, lookback='100')
        stoch_k_mid, stoch_d_mid = calculate_stoch(df_mid['high'], df_mid['low'], df_mid['close'], PERIOD, K, D)
        df_mid = add_price_sma(df_mid, period=50)
        # Store in cache
        bot_state.cached_data_mid[symbol] = (df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid)
        bot_state.last_fetch_time_mid[symbol] = current_time
    else:
        if VERBOSE_LOGGING:
            print(f"Using cached 4h data for {symbol}.")
        # Retrieve from cache
        df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid = bot_state.cached_data_mid[symbol]

    # --- Fetch Long-Term (1d) Data (from Cache or API) ---
    if (symbol not in bot_state.last_fetch_time_long or \
        (current_time - bot_state.last_fetch_time_long[symbol]) > CACHE_DURATION_LONG):
        if VERBOSE_LOGGING:
            print(f"Cache expired. Fetching fresh 1d data for {symbol}...")
        df_long, _, _ = fetch_klines(symbol, long_interval, lookback='100')
        # Store in cache
        bot_state.cached_data_long[symbol] = df_long
        bot_state.last_fetch_time_long[symbol] = current_time
    else:
        if VERBOSE_LOGGING:
            print(f"Using cached 1d data for {symbol}.")
        # Retrieve from cache
        df_long = bot_state.cached_data_long[symbol]

    return df_short, support_short, resistance_short, df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid, df_long

def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

def get_usdt_balance():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0

def get_position(symbol):
    try:
        positions = client.futures_position_information()
        for pos in positions:
            if pos['symbol'] == symbol:
                position_amt = float(pos['positionAmt'])
                entry_price = float(pos['entryPrice'])
                
                if position_amt == 0:
                    return 0, 0, 0, 0, 0

                current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                unrealized_profit = (current_price - entry_price) * position_amt
                
                if leverage == 0:
                    print(f"Warning: Leverage for {symbol} is zero. Cannot calculate margin or ROI.")
                    return position_amt, 0, unrealized_profit, 0, entry_price

                order_size = abs(position_amt) * entry_price
                margin_used = order_size / leverage
                
                if margin_used == 0:
                    return position_amt, 0, unrealized_profit, 0, entry_price

                roi = (unrealized_profit / margin_used) * 100 
                
                return position_amt, roi, unrealized_profit, margin_used, entry_price
        return 0, 0, 0, 0, 0
    except Exception as e:
        print(f"Error getting position for {symbol}: {e}")
        return 0, 0, 0, 0, 0

def get_market_price(symbol):
    try:
        price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        return price
    except Exception as e:
        print(f"Error getting market price: {e}")
        return None

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
   
def round_price(symbol, price):
    symbol_info = get_symbol_info(symbol)
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'PRICE_FILTER':
            tick_size = float(filt['tickSize'])
            price = round(price - (price % tick_size), 8)
            return price
    return price

def fetch_klines(symbol, interval, lookback='100'):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    
    support = df['low'].min()
    resistance = df['high'].max()
        
    return df, support, resistance 

def detect_trend(df, window=4, confirm=2):
    if len(df) < window:
        return 'sideways'

    trend = 'sideways'
    uptrend_count = 0
    downtrend_count = 0

    start_price = df['close'].iloc[0]
    end_price = df['close'].iloc[-1]
    overall_trend = 'uptrend' if end_price > start_price else 'downtrend' if end_price < start_price else 'sideways'

    for i in range(window, len(df)):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        high_window = df['high'].iloc[i-window:i]
        low_window = df['low'].iloc[i-window:i]

        if current_high >= high_window.max():
            uptrend_count += 1
            downtrend_count = 0
        elif current_low <= low_window.min():
            downtrend_count += 1
            uptrend_count = 0
        else:
            uptrend_count = 0
            downtrend_count = 0

        if uptrend_count >= confirm:
            trend = 'uptrend'
        elif downtrend_count >= confirm:
            trend = 'downtrend'
        else:
            trend = 'sideways'

    if overall_trend != 'sideways' and trend == 'sideways':
        return overall_trend
    elif overall_trend == trend:
        return trend
    else:
        return 'sideways'

def get_funding_rate(symbol):
    try:
        funding_rate_history = client.futures_funding_rate(symbol=symbol, limit=1)
        if funding_rate_history:
            return float(funding_rate_history[0]['fundingRate'])
        return 0.0
    except Exception as e:
        print(f"Error getting funding rate for {symbol}: {e}")
        return 0.0