from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *
import numpy as np
from scipy.signal import argrelextrema

from data.indicators import calculate_stoch, add_price_sma, PERIOD, K, D

client = Client(API_KEY, API_SECRET)

def fetch_multi_timeframe_data(symbol, short_interval, long_interval):
    if VERBOSE_LOGGING:
        print(f"Fetching multi-timeframe data for {symbol}: {short_interval} and {long_interval}")
    
    df_short, support_short, resistance_short = fetch_klines(symbol, short_interval, lookback='100')
    df_long, support_long, resistance_long = fetch_klines(symbol, long_interval, lookback='100')
    
    stoch_k_long, stoch_d_long = calculate_stoch(df_long['high'], df_long['low'], df_long['close'], PERIOD, K, D)
    
    # --- NEW: Calculate 50-period SMA for the long-term timeframe ---
    df_long = add_price_sma(df_long, period=50)
    
    return df_short, support_short, resistance_short, df_long, support_long, resistance_long, stoch_k_long, stoch_d_long

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