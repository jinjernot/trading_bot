import pandas as pd
from binance.client import Client
from config.api import API_KEY, API_SECRET

client = Client(API_KEY, API_SECRET)

# Calculate Stochastic Oscillator
def calculate_stoch(high, low, close, PERIOD, K, D):
    lowest_low = low.rolling(PERIOD).min()
    highest_high = high.rolling(PERIOD).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    stoch_d = stoch_k.rolling(D).mean()
    return stoch_k, stoch_d

# Fetch historical klines
def fetch_klines(symbol, interval, lookback='50'):
    print(f"Fetching klines for {symbol} with interval {interval} and lookback {lookback}")
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    print(f"Fetched {len(df)} rows of data.")
    return df