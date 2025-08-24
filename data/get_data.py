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

def get_all_positions_and_balance():
    """
    Fetches all position information and account balance in a single batch.
    """
    try:
        # CORRECTED FUNCTION NAME
        positions = client.futures_position_information()
        balance_info = client.futures_account_balance()
        return positions, balance_info
    except Exception as e:
        print(f"Error fetching account data: {e}")
        return [], []

def fetch_multi_timeframe_data(symbol, short_interval, mid_interval, long_interval):
    current_time = time.time()
    CACHE_DURATION_MID = 1800
    CACHE_DURATION_LONG = 14400

    if VERBOSE_LOGGING:
        print(f"Fetching 15m data for {symbol}...")
    df_short, support_short, resistance_short = fetch_klines(symbol, short_interval, lookback='100')

    if (symbol not in bot_state.last_fetch_time_mid or \
        (current_time - bot_state.last_fetch_time_mid[symbol]) > CACHE_DURATION_MID):
        if VERBOSE_LOGGING:
            print(f"Cache expired. Fetching fresh 4h data for {symbol}...")
        df_mid, support_mid, resistance_mid = fetch_klines(symbol, mid_interval, lookback='100')
        stoch_k_mid, stoch_d_mid = calculate_stoch(df_mid['high'], df_mid['low'], df_mid['close'], PERIOD, K, D)
        df_mid = add_price_sma(df_mid, period=50)
        bot_state.cached_data_mid[symbol] = (df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid)
        bot_state.last_fetch_time_mid[symbol] = current_time
    else:
        if VERBOSE_LOGGING:
            print(f"Using cached 4h data for {symbol}.")
        df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid = bot_state.cached_data_mid[symbol]

    if (symbol not in bot_state.last_fetch_time_long or \
        (current_time - bot_state.last_fetch_time_long[symbol]) > CACHE_DURATION_LONG):
        if VERBOSE_LOGGING:
            print(f"Cache expired. Fetching fresh 1d data for {symbol}...")
        df_long, _, _ = fetch_klines(symbol, long_interval, lookback='100')
        bot_state.cached_data_long[symbol] = df_long
        bot_state.last_fetch_time_long[symbol] = current_time
    else:
        if VERBOSE_LOGGING:
            print(f"Using cached 1d data for {symbol}.")
        df_long = bot_state.cached_data_long[symbol]

    return df_short, support_short, resistance_short, df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid, df_long

def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

def get_usdt_balance(balance_data):
    """
    MODIFIED: Extracts the AVAILABLE USDT balance.
    """
    for asset in balance_data:
        if asset['asset'] == 'USDT':
            return float(asset['availableBalance'])
    return 0.0

def get_position(symbol, all_positions):
    for pos in all_positions:
        if pos['symbol'] == symbol:
            position_amt = float(pos['positionAmt'])
            entry_price = float(pos['entryPrice'])
            
            if position_amt == 0:
                return 0, 0, 0, 0, 0

            current_price = get_market_price(symbol)
            if current_price is None: return 0, 0, 0, 0, 0

            unrealized_profit = (current_price - entry_price) * position_amt
            margin_used = abs(position_amt * entry_price) / leverage if leverage != 0 else 0
            roi = (unrealized_profit / margin_used) * 100 if margin_used != 0 else 0
            
            return position_amt, roi, unrealized_profit, margin_used, entry_price
    return 0, 0, 0, 0, 0

def get_market_price(symbol):
    try:
        price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        return price
    except Exception as e:
        if 'Too many requests' not in str(e):
            print(f"Error getting market price for {symbol}: {e}")
        return None

def round_quantity(symbol, quantity):
    symbol_info = get_symbol_info(symbol)
    if not symbol_info: return quantity
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            min_qty, step_size = float(filt['minQty']), float(filt['stepSize'])
            quantity = max(quantity, min_qty)
            return round(quantity - (quantity % step_size), 8)
    return quantity
   
def round_price(symbol, price):
    symbol_info = get_symbol_info(symbol)
    if not symbol_info: return price
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'PRICE_FILTER':
            tick_size = float(filt['tickSize'])
            return round(price - (price % tick_size), 8)
    return price

def fetch_klines(symbol, interval, lookback='100'):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    return df, df['low'].min(), df['high'].max()

def detect_trend(df, window=4, confirm=2):
    if len(df) < window:
        return 'sideways'
    return 'sideways'

def get_funding_rate(symbol):
    try:
        funding_rate_history = client.futures_funding_rate(symbol=symbol, limit=1)
        return float(funding_rate_history[0]['fundingRate']) if funding_rate_history else 0.0
    except Exception as e:
        print(f"Error getting funding rate for {symbol}: {e}")
        return 0.0