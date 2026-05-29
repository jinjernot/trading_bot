from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *
import numpy as np
from scipy.signal import argrelextrema
import time
from functools import lru_cache

from data.indicators import calculate_stoch, add_price_sma, calculate_macd, calculate_bollinger_bands, PERIOD, K, D
from src.state_manager import bot_state

from config.client import client

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

    # Use 350 bars for the short TF: enough for VWAP and BOS calculations
    df_short, support_short, resistance_short = fetch_klines(symbol, short_interval, lookback='350')
    df_short = calculate_macd(df_short)  # Add MACD for short timeframe
    df_short = calculate_bollinger_bands(df_short)  # Add Bollinger Bands for mean-reversion guard

    # Fetch 1h data for multi-timeframe stochastic confirmation
    df_1h, _, _ = fetch_klines(symbol, '1h', lookback='150')
    stoch_k_1h, stoch_d_1h = calculate_stoch(df_1h['high'], df_1h['low'], df_1h['close'], PERIOD, K, D)

    if (symbol not in bot_state.last_fetch_time_mid or \
        (current_time - bot_state.last_fetch_time_mid[symbol]) > CACHE_DURATION_MID):
        df_mid, support_mid, resistance_mid = fetch_klines(symbol, mid_interval, lookback='250')  # Increased for SMA 200 safety margin
        stoch_k_mid, stoch_d_mid = calculate_stoch(df_mid['high'], df_mid['low'], df_mid['close'], PERIOD, K, D)
        df_mid = add_price_sma(df_mid, period=50)
        df_mid = add_price_sma(df_mid, period=200)  # Add SMA 200 for trend filter
        df_mid = calculate_macd(df_mid)  # Add MACD for mid timeframe
        bot_state.cached_data_mid[symbol] = (df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid)
        bot_state.last_fetch_time_mid[symbol] = current_time
    else:
        df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid = bot_state.cached_data_mid[symbol]

    if (symbol not in bot_state.last_fetch_time_long or \
        (current_time - bot_state.last_fetch_time_long[symbol]) > CACHE_DURATION_LONG):
        df_long, support_long, resistance_long = fetch_klines(symbol, long_interval, lookback='250')
        stoch_k_long, stoch_d_long = calculate_stoch(df_long['high'], df_long['low'], df_long['close'], PERIOD, K, D)
        bot_state.cached_data_long[symbol] = (df_long, support_long, resistance_long, stoch_k_long, stoch_d_long)
        bot_state.last_fetch_time_long[symbol] = current_time
    else:
        df_long, support_long, resistance_long, stoch_k_long, stoch_d_long = bot_state.cached_data_long[symbol]

    return df_short, support_short, resistance_short, df_mid, support_mid, resistance_mid, stoch_k_mid, stoch_d_mid, df_long, support_long, resistance_long, stoch_k_1h, stoch_d_1h, df_1h

_exchange_info_cache = None
_exchange_info_cache_time = 0
_EXCHANGE_INFO_TTL = 21600  # Refresh exchange info every 6 hours

def get_symbol_info(symbol):
    """
    Returns exchange info for a symbol. Cached globally with 6-hour TTL
    to avoid repeated exchange_info() API calls.
    """
    global _exchange_info_cache, _exchange_info_cache_time
    if _exchange_info_cache is None or (time.time() - _exchange_info_cache_time) > _EXCHANGE_INFO_TTL:
        _exchange_info_cache = client.futures_exchange_info()
        _exchange_info_cache_time = time.time()
    for s in _exchange_info_cache['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

def get_usdt_balance(balance_data):
    """
    MODIFIED: Extracts the TOTAL USDT wallet balance for consistent position sizing.
    If we used availableBalance, position sizes would shrink with every concurrent trade!
    """
    for asset in balance_data:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0

def get_position(symbol, all_positions):
    for pos in all_positions:
        if pos['symbol'] == symbol:
            position_amt = float(pos['positionAmt'])
            entry_price = float(pos['entryPrice'])
            
            if position_amt == 0:
                return 0, 0, 0, 0, 0

            current_price = float(pos.get('markPrice', 0))
            if current_price == 0:
                current_price = get_market_price(symbol)
                if current_price is None: return 0, 0, 0, 0, 0

            unrealized_profit = float(pos.get('unRealizedProfit', (current_price - entry_price) * position_amt))
            margin_used = abs(position_amt * entry_price) / LEVERAGE if LEVERAGE != 0 else 0
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
    symbol_info = get_symbol_info( symbol )
    if not symbol_info: return quantity
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            min_qty, step_size = float(filt['minQty']), float(filt['stepSize'])
            quantity = max(quantity, min_qty)
            return round(quantity - (quantity % step_size), 8)
    return quantity
   
def round_price(symbol, price):
    symbol_info = get_symbol_info( symbol )
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


def get_all_funding_rates():
    """
    Fetches the latest funding rates for all symbols in a single API call.
    """
    try:
        premium_index = client.futures_mark_price()
        return {item['symbol']: float(item['lastFundingRate']) for item in premium_index if 'lastFundingRate' in item}
    except Exception as e:
        print(f"Error getting all funding rates: {e}")
        return {}

def get_funding_rate(symbol):
    """
    Returns the current funding rate for a single symbol.
    Used by close_position.py for per-trade funding rate exit checks.
    Falls back to get_all_funding_rates() to avoid extra API calls.
    """
    try:
        rates = get_all_funding_rates()
        return rates.get(symbol, 0.0)
    except Exception as e:
        print(f"Error getting funding rate for {symbol}: {e}")
        return 0.0

def get_global_btc_trend():
    try:
        from data.indicators import add_price_sma, calculate_adx
        df_btc, _, _ = fetch_klines('BTCUSDT', PRIMARY_TIMEFRAME, lookback='200')
        df_btc = add_price_sma(df_btc, period=50)
        df_btc = add_price_sma(df_btc, period=200)
        df_btc = calculate_adx(df_btc)
        
        last_close = df_btc['close'].iloc[-1]
        sma50 = df_btc['price_sma_50'].iloc[-1]
        sma200 = df_btc['price_sma_200'].iloc[-1]
        adx = df_btc['ADX'].iloc[-1]
        
        trend = 'NEUTRAL'
        if adx > 20:
            if last_close > sma50 and last_close > sma200:
                trend = 'BULLISH'
            elif last_close < sma50 and last_close < sma200:
                trend = 'BEARISH'
        
        bot_state.global_btc_trend = trend
        return trend
    except Exception as e:
        print(f"Error getting BTC trend: {e}")
        bot_state.global_btc_trend = 'NEUTRAL'
        return 'NEUTRAL'