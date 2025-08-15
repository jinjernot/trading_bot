from binance.client import Client
from config.secrets import API_KEY, API_SECRET
import numpy as np
import pandas as pd

client = Client(API_KEY, API_SECRET)

PERIOD = 14
K = 3
D = 3
OVERSOLD = 20
OVERBOUGHT = 80

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