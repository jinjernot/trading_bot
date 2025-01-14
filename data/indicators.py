from binance.client import Client
from config.secrets import API_KEY, API_SECRET

client = Client(API_KEY, API_SECRET)

PERIOD = 14
K = 3
D = 3
OVERSOLD = 20
OVERBOUGHT = 80


# Calculate Stochastic Oscillator with smoothing
def calculate_stoch(high, low, close, PERIOD, K, D):
    lowest_low = low.rolling(PERIOD).min()
    highest_high = high.rolling(PERIOD).max()
    raw_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    smoothed_k = raw_k.rolling(K).mean()  # Smooth %K over K periods
    stoch_d = smoothed_k.rolling(D).mean()  # Smooth %D over D periods
    return smoothed_k, stoch_d

def calculate_rsi(df, period=14):
    """Calculate RSI using closing prices."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    df['rsi'] = rsi
    return df
