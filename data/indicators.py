from binance.client import Client
from config.secrets import API_KEY, API_SECRET
import numpy as np
import pandas as pd
from config.settings import VERBOSE_LOGGING
import pandas_ta as ta

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
    """
    Checks if the market is volatile based on the ATR percentage.
    """
    if 'atr' not in df.columns:
        df = calculate_atr(df, period=atr_period)
    
    atr_percentage = (df['atr'].iloc[-1] / df['close'].iloc[-1]) * 100
    
    if VERBOSE_LOGGING:
        print(f"ATR as percentage of price: {atr_percentage:.2f}%")
        
    return atr_percentage > atr_threshold

def add_candlestick_patterns(df):
    """
    Scans for multiple candlestick patterns using pandas-ta and adds
    consolidated bullish/bearish signal columns to the DataFrame.
    """
    # Scan for all candlestick patterns
    df.ta.cdl_pattern(name="all", append=True)

    bullish_patterns = [
        'CDL_ENGULFING', 'CDL_HAMMER', 'CDL_MORNINGSTAR',
        'CDL_PIERCING', 'CDL_3WHITESOLDIERS'
    ]
    bearish_patterns = [
        'CDL_ENGULFING', 'CDL_HANGINGMAN', 'CDL_EVENINGSTAR',
        'CDL_SHOOTINGSTAR', 'CDL_3BLACKCROWS'
    ]

    df['bullish_pattern'] = 0
    df['bearish_pattern'] = 0

    # Consolidate bullish signals and log them
    for pattern in bullish_patterns:
        if pattern in df.columns and df[pattern].iloc[-1] == 100:
            df.loc[df.index[-1], 'bullish_pattern'] = 1
            if VERBOSE_LOGGING:
                print(f"🕯️ Bullish Pattern Detected: {pattern} on the last candle.")

    # Consolidate bearish signals and log them
    for pattern in bearish_patterns:
        if pattern in bearish_patterns:
            if pattern in df.columns and df[pattern].iloc[-1] == -100:
                df.loc[df.index[-1], 'bearish_pattern'] = 1
                if VERBOSE_LOGGING:
                    print(f"🕯️ Bearish Pattern Detected: {pattern} on the last candle.")
    
    return df