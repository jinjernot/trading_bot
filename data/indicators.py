from binance.client import Client
from config.secrets import API_KEY, API_SECRET
import numpy as np
import pandas as pd
from config.settings import VERBOSE_LOGGING
import pandas_ta as ta
from scipy.signal import find_peaks

client = Client(API_KEY, API_SECRET)

PERIOD = 14
K = 3
D = 3
OVERSOLD = 20
OVERBOUGHT = 80

def calculate_wma(series, period):
    """
    Calculates the Weighted Moving Average.
    """
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda prices: np.dot(prices, weights) / weights.sum(), raw=True)

def calculate_hull_moving_average(df, period=14):
    """
    Calculates the Hull Moving Average (HMA).
    """
    df[f'hma_{period}'] = calculate_wma(
        2 * calculate_wma(df['close'], period // 2) - calculate_wma(df['close'], period),
        int(np.sqrt(period))
    )
    return df

def find_swing_points_and_fib(df, lookback=50):
    """
    Identifies swing points for an UPTREND and calculates Fibonacci retracement levels.
    """
    subset = df.iloc[-lookback:]
    high_peaks, _ = find_peaks(subset['high'], distance=5, prominence=0.001)
    low_troughs, _ = find_peaks(-subset['low'], distance=5, prominence=0.001)

    if len(low_troughs) == 0 or len(high_peaks) == 0:
        return None, None, None

    last_swing_low_idx = subset.index[low_troughs[-1]]
    last_swing_high_idx = subset.index[high_peaks[-1]]

    if last_swing_high_idx < last_swing_low_idx:
        return None, None, None

    swing_low_price = df.loc[last_swing_low_idx, 'low']
    swing_high_price = df.loc[last_swing_high_idx, 'high']
    
    diff = swing_high_price - swing_low_price
    fib_levels = {
        '0.236': swing_high_price - diff * 0.236,
        '0.382': swing_high_price - diff * 0.382,
        '0.5': swing_high_price - diff * 0.5,
        '0.618': swing_high_price - diff * 0.618,
        '0.786': swing_high_price - diff * 0.786,
    }
    return swing_low_price, swing_high_price, fib_levels

def find_swing_points_and_fib_short(df, lookback=50):
    """
    Identifies swing points for a DOWNTREND and calculates Fibonacci retracement levels.
    """
    subset = df.iloc[-lookback:]
    high_peaks, _ = find_peaks(subset['high'], distance=5, prominence=0.001)
    low_troughs, _ = find_peaks(-subset['low'], distance=5, prominence=0.001)

    if len(low_troughs) == 0 or len(high_peaks) == 0:
        return None, None, None

    last_swing_low_idx = subset.index[low_troughs[-1]]
    last_swing_high_idx = subset.index[high_peaks[-1]]

    if last_swing_low_idx < last_swing_high_idx:
        return None, None, None

    swing_low_price = df.loc[last_swing_low_idx, 'low']
    swing_high_price = df.loc[last_swing_high_idx, 'high']

    diff = swing_high_price - swing_low_price
    fib_levels = {
        '0.236': swing_low_price + diff * 0.236,
        '0.382': swing_low_price + diff * 0.382,
        '0.5': swing_low_price + diff * 0.5,
        '0.618': swing_low_price + diff * 0.618,
        '0.786': swing_low_price + diff * 0.786,
    }
    return swing_low_price, swing_high_price, fib_levels

def calculate_stoch(high, low, close, PERIOD, K, D):
    lowest_low = low.rolling(PERIOD).min()
    highest_high = high.rolling(PERIOD).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    smoothed_k = raw_k.rolling(K).mean()
    stoch_d = smoothed_k.rolling(D).mean()
    return smoothed_k, stoch_d

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    df['rsi'] = rsi
    return df

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    df['atr'] = atr
    return df

def add_price_sma(df, period=50):
    df[f'price_sma_{period}'] = df['close'].rolling(window=period).mean()
    return df

def add_volume_sma(df, period=20):
    df[f'volume_sma_{period}'] = df['volume'].rolling(window=period).mean()
    return df

def add_short_term_sma(df, period=9):
    df[f'price_sma_{period}'] = df['close'].rolling(window=period).mean()
    return df

def calculate_adx(df, period=14):
    df['H-L'] = df['high'] - df['low']
    df['H-PC'] = abs(df['high'] - df['close'].shift(1))
    df['L-PC'] = abs(df['low'] - df['close'].shift(1))
    df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
    
    df['+DM'] = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']), df['high'] - df['high'].shift(1), 0)
    df['-DM'] = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)), df['low'].shift(1) - df['low'], 0)
    
    df['+DI'] = 100 * (df['+DM'].ewm(alpha=1/period).mean() / df['TR'].ewm(alpha=1/period).mean())
    df['-DI'] = 100 * (df['-DM'].ewm(alpha=1/period).mean() / df['TR'].ewm(alpha=1/period).mean())
    
    df['DX'] = 100 * abs(df['+DI'] - df['-DI']) / (df['+DI'] + df['-DI'])
    df['ADX'] = df['DX'].ewm(alpha=1/period).mean()
    
    return df

def calculate_bollinger_bands(df, period=20, std_dev=2):
    df['BB_Mid'] = df['close'].rolling(window=period).mean()
    df['BB_Std'] = df['close'].rolling(window=period).std()
    df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * std_dev)
    df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * std_dev)
    return df

def is_market_volatile(df, atr_period=14, atr_threshold=0.05):
    if 'atr' not in df.columns:
        df = calculate_atr(df, period=atr_period)
    
    atr_percentage = (df['atr'].iloc[-1] / df['close'].iloc[-1]) * 100
    
    if VERBOSE_LOGGING:
        print(f"ATR as percentage of price: {atr_percentage:.2f}%")
        
    return atr_percentage > atr_threshold

def add_candlestick_patterns(df):
    df.ta.cdl_pattern(name="all", append=True)
    bullish_patterns = ['CDL_ENGULFING', 'CDL_HAMMER', 'CDL_MORNINGSTAR']
    bearish_patterns = ['CDL_ENGULFING', 'CDL_HANGINGMAN', 'CDL_EVENINGSTAR']
    df['bullish_pattern'] = 0
    df['bearish_pattern'] = 0
    for pattern in bullish_patterns:
        if pattern in df.columns and df[pattern].iloc[-1] == 100:
            df.loc[df.index[-1], 'bullish_pattern'] = 1
    for pattern in bearish_patterns:
        if pattern in df.columns and df[pattern].iloc[-1] == -100:
            df.loc[df.index[-1], 'bearish_pattern'] = 1
    return df