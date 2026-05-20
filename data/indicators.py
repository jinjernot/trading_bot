import numpy as np
import pandas as pd
from scipy.signal import find_peaks
from config.settings import VERBOSE_LOGGING

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

def calculate_hull_moving_average(df, period=10):
    """
    Calculates the Hull Moving Average (HMA).
    """
    df[f'hma_{period}'] = calculate_wma(
        2 * calculate_wma(df['close'], period // 2) - calculate_wma(df['close'], period),
        int(np.sqrt(period))
    )
    return df

def find_swing_points_and_fib(df, lookback=50, trend='long'):
    """
    Identifies swing points and calculates Fibonacci retracement levels.
    Uses ATR-relative prominence for accurate swing detection across all price levels.
    """
    subset = df.iloc[-lookback:]

    # ATR-relative prominence: adapts to each asset's volatility
    atr_rel = (df['atr'].iloc[-1] / df['close'].iloc[-1]) if ('atr' in df.columns and df['close'].iloc[-1] != 0) else 0.005
    prominence = max(atr_rel, 0.002)  # Floor at 0.2% to avoid noise on flat markets

    high_peaks, _ = find_peaks(subset['high'], distance=5, prominence=prominence)
    low_troughs, _ = find_peaks(-subset['low'], distance=5, prominence=prominence)

    if len(low_troughs) == 0 or len(high_peaks) == 0:
        return None, None, None

    last_swing_low_idx = subset.index[low_troughs[-1]]
    last_swing_high_idx = subset.index[high_peaks[-1]]

    # Determine if the swing is valid for the given trend
    if trend == 'long' and last_swing_high_idx < last_swing_low_idx:
        return None, None, None
    if trend == 'short' and last_swing_low_idx < last_swing_high_idx:
        return None, None, None

    swing_low_price = df.loc[last_swing_low_idx, 'low']
    swing_high_price = df.loc[last_swing_high_idx, 'high']
    
    diff = swing_high_price - swing_low_price
    
    fib_levels = {}
    levels = [0.236, 0.382, 0.5, 0.618, 0.786]

    for level in levels:
        if trend == 'long':
            fib_levels[str(level)] = swing_high_price - diff * level
        else: # short
            fib_levels[str(level)] = swing_low_price + diff * level
            
    return swing_low_price, swing_high_price, fib_levels

def calculate_stoch(high, low, close, PERIOD, K, D):
    lowest_low = low.rolling(PERIOD).min()
    highest_high = high.rolling(PERIOD).max()
    diff = highest_high - lowest_low
    
    # Safe division to prevent division-by-zero on flat price periods
    raw_k = 100 * (close - lowest_low) / diff.replace(0, np.nan)
    raw_k = raw_k.fillna(50.0)
    raw_k.iloc[:PERIOD-1] = np.nan  # Preserve initial window lookback NaNs
    
    smoothed_k = raw_k.rolling(K).mean()
    stoch_d = smoothed_k.rolling(D).mean()
    return smoothed_k, stoch_d

def calculate_rsi(df, period=14):
    """Standard RSI with 14-period lookback (Wilder's original setting), fortified against division by zero."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    # Safe division to prevent division-by-zero on flat periods
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs.fillna(0)))
    rsi = rsi.fillna(50.0)
    
    df['rsi'] = rsi
    return df

def calculate_atr(df, period=10):
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

def add_volume_sma(df, period=14):
    df[f'volume_sma_{period}'] = df['volume'].rolling(window=period).mean()
    return df

def add_short_term_sma(df, period=9):
    df[f'price_sma_{period}'] = df['close'].rolling(window=period).mean()
    return df

def calculate_adx(df, period=14):
    """Standard ADX with 14-period lookback (Wilder's original setting)."""
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

def calculate_bollinger_bands(df, period=14, std_dev=2):
    df['BB_Mid'] = df['close'].rolling(window=period).mean()
    df['BB_Std'] = df['close'].rolling(window=period).std()
    df['BB_Upper'] = df['BB_Mid'] + (df['BB_Std'] * std_dev)
    df['BB_Lower'] = df['BB_Mid'] - (df['BB_Std'] * std_dev)
    return df

def add_candlestick_patterns(df):
    """
    Native candlestick pattern detection — no pandas_ta dependency required.
    Detects: Hammer, Bullish Engulfing (bullish), Shooting Star, Bearish Engulfing (bearish).
    """
    o = df['open']
    h = df['high']
    l = df['low']
    c = df['close']

    body = (c - o).abs()
    # Avoid division by zero on doji/flat candles
    safe_body = body.replace(0, np.nan)

    upper_wick = h - pd.concat([c, o], axis=1).max(axis=1)
    lower_wick = pd.concat([c, o], axis=1).min(axis=1) - l

    # --- Bullish patterns ---
    # Hammer: long lower wick (>=2x body), tiny upper wick (<=50% body), bullish close
    hammer = (lower_wick >= 2 * safe_body) & (upper_wick <= 0.5 * safe_body) & (c > o)
    # Bullish engulfing: current candle completely engulfs prior bearish candle
    bull_engulf = (
        (c > o) &                        # Current is bullish
        (c.shift(1) < o.shift(1)) &      # Previous was bearish
        (c > o.shift(1)) &               # Current close above prior open
        (o < c.shift(1))                 # Current open below prior close
    )
    df['bullish_pattern'] = (hammer | bull_engulf).fillna(False).astype(int)

    # --- Bearish patterns ---
    # Shooting star: long upper wick (>=2x body), tiny lower wick (<=50% body), bearish close
    shooting_star = (upper_wick >= 2 * safe_body) & (lower_wick <= 0.5 * safe_body) & (c < o)
    # Bearish engulfing: current candle completely engulfs prior bullish candle
    bear_engulf = (
        (c < o) &                        # Current is bearish
        (c.shift(1) > o.shift(1)) &      # Previous was bullish
        (c < o.shift(1)) &               # Current close below prior open
        (o > c.shift(1))                 # Current open above prior close
    )
    df['bearish_pattern'] = (shooting_star | bear_engulf).fillna(False).astype(int)

    return df

def calculate_macd(df, fast=12, slow=26, signal=9):
    """
    Calculate MACD (Moving Average Convergence Divergence)

    Args:
        df: DataFrame with 'close' column
        fast: Fast EMA period (default 12)
        slow: Slow EMA period (default 26)
        signal: Signal line period (default 9)

    Returns:
        df with macd, macd_signal, and macd_hist columns
    """
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()

    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=signal, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    return df


def calculate_roc(df, period=10):
    """
    Rate of Change (ROC) — Institutional momentum quality filter.

    Measures the percentage change in price over N periods.
    Used to confirm that a trend still has ACTIVE momentum before entry,
    preventing entries into exhausted or reversing moves.

    ROC > 0 = upward momentum (valid for LONG entries)
    ROC < 0 = downward momentum (valid for SHORT entries)
    |ROC| < threshold = market is stalling — skip entry

    Args:
        df: DataFrame with 'close' column
        period: Lookback period (default 10 bars)

    Returns:
        df with 'roc' column (percentage)
    """
    df['roc'] = df['close'].pct_change(periods=period) * 100
    return df


def detect_rsi_divergence(df, lookback=5):
    """
    Detects bullish and bearish RSI divergence — an institutional exit filter.

    BULLISH DIVERGENCE (hold long, do not exit):
        Price made a lower low, but RSI made a higher low.
        Signals hidden strength — the trend is NOT exhausted.

    BEARISH DIVERGENCE (hold short, do not exit):
        Price made a higher high, but RSI made a lower high.
        Signals hidden weakness — the trend is NOT exhausted.

    Used in close_position to PREVENT premature exits when divergence
    indicates the move still has fuel. This is how institutional desks
    hold winners past the first exit signal.

    Args:
        df: DataFrame with 'close', 'rsi' columns
        lookback: How many bars back to compare (default 5)

    Returns:
        (bullish_divergence: bool, bearish_divergence: bool)
    """
    if 'rsi' not in df.columns or len(df) < lookback + 2:
        return False, False

    # Current vs prior candle
    cur_close = df['close'].iloc[-1]
    cur_rsi = df['rsi'].iloc[-1]
    prior_close = df['close'].iloc[-lookback]
    prior_rsi = df['rsi'].iloc[-lookback]

    # Bullish divergence: price lower low, RSI higher low
    bullish_div = (cur_close < prior_close) and (cur_rsi > prior_rsi)
    # Bearish divergence: price higher high, RSI lower high
    bearish_div = (cur_close > prior_close) and (cur_rsi < prior_rsi)

    return bullish_div, bearish_div


def calculate_fib_extensions(swing_low, swing_high, trend='long'):
    """
    Calculates Fibonacci extension levels for profit targets.

    Institutional desks (DWF Labs, GSR) use extension levels as measured
    move targets rather than arbitrary R:R multiples. The 1.272 and 1.618
    extensions are the most statistically significant targets.

    For LONG trades (pullback entry, trending up):
        Extensions are projected ABOVE the swing high.
        1.272 ext = swing_high + (range * 0.272)
        1.618 ext = swing_high + (range * 0.618)

    For SHORT trades (retracement entry, trending down):
        Extensions are projected BELOW the swing low.
        1.272 ext = swing_low - (range * 0.272)
        1.618 ext = swing_low - (range * 0.618)

    Args:
        swing_low: Price of the swing low
        swing_high: Price of the swing high
        trend: 'long' or 'short'

    Returns:
        dict with '1.272' and '1.618' extension price levels
    """
    if swing_low is None or swing_high is None:
        return {}

    diff = swing_high - swing_low

    if trend == 'long':
        return {
            '1.272': swing_high + (diff * 0.272),
            '1.618': swing_high + (diff * 0.618),
        }
    else:  # short
        return {
            '1.272': swing_low - (diff * 0.272),
            '1.618': swing_low - (diff * 0.618),
        }

def calculate_volume_profile(df, bins=50):
    """
    Calculates the Volume Profile Point of Control (POC).
    Kept for backward compatibility. Use calculate_volume_profile_full() for VAH/VAL.
    """
    poc, _, _ = calculate_volume_profile_full(df, bins=bins)
    return poc


def calculate_volume_profile_full(df, bins=50):
    """
    Institutional-grade VPVR: returns Point of Control (POC), Value Area High (VAH),
    and Value Area Low (VAL) representing the 70% volume concentration zone.
    
    Methodology: Wilder Value Area algorithm — expand symmetrically from POC until
    70% of total session volume is captured.
    """
    min_price = df['low'].min()
    max_price = df['high'].max()

    if min_price == max_price:
        return min_price, min_price, min_price

    price_bins = np.linspace(min_price, max_price, bins)
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    bin_indices = np.digitize(typical_price, price_bins)
    df_vp = pd.DataFrame({'bin': bin_indices, 'volume': df['volume']})
    volume_by_bin = df_vp.groupby('bin')['volume'].sum()

    if volume_by_bin.empty:
        p = typical_price.iloc[-1]
        return p, p, p

    poc_bin = int(volume_by_bin.idxmax())
    total_volume = volume_by_bin.sum()
    target_va_volume = total_volume * 0.70  # Value Area = 70% of total volume

    # Expand from POC outward (Wilder algorithm)
    cumulative = volume_by_bin.get(poc_bin, 0)
    upper_bin = poc_bin
    lower_bin = poc_bin

    while cumulative < target_va_volume:
        up_next = upper_bin + 1
        down_next = lower_bin - 1
        up_vol = volume_by_bin.get(up_next, 0)
        down_vol = volume_by_bin.get(down_next, 0)

        # Add the side with more volume first (Wilder rule)
        if up_vol >= down_vol and up_next in volume_by_bin.index:
            upper_bin = up_next
            cumulative += up_vol
        elif down_next in volume_by_bin.index:
            lower_bin = down_next
            cumulative += down_vol
        else:
            break  # Hit the edge of the profile

    # Clamp bin indices to valid range
    poc_bin_clamped = min(max(poc_bin - 1, 0), len(price_bins) - 1)
    vah_bin_clamped = min(max(upper_bin - 1, 0), len(price_bins) - 1)
    val_bin_clamped = min(max(lower_bin - 1, 0), len(price_bins) - 1)

    poc = price_bins[poc_bin_clamped]
    vah = price_bins[vah_bin_clamped]
    val = price_bins[val_bin_clamped]

    return poc, vah, val

def calculate_vwap(df, period=288):
    """
    Calculates a rolling Volume Weighted Average Price (VWAP).
    For a 5-minute chart, 288 periods = 24 hours.
    This acts as a continuous institutional anchor price.
    """
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    
    # Rolling Cumulative Volume * Typical Price
    cum_vol_price = (typical_price * df['volume']).rolling(window=period).sum()
    # Rolling Cumulative Volume
    cum_vol = df['volume'].rolling(window=period).sum()
    
    df['vwap'] = cum_vol_price / cum_vol
    return df

def calculate_volume_anomaly(df, period=20, multiplier=1.5):
    """
    Detects if the current candle's volume is significantly higher than the average.
    Institutional footprint tracking.
    """
    df['vol_sma'] = df['volume'].rolling(window=period).mean()
    # True if current volume is > multiplier * moving average
    df['volume_anomaly'] = df['volume'] > (df['vol_sma'] * multiplier)
    return df

def calculate_bos(df, period=50):
    """
    Break of Structure (BOS) using recent Swing Highs / Swing Lows.
    Detects if the current close breaks the highest high or lowest low of the last N periods.
    Using period=50 (approx 4 hours on a 5m chart) ensures true structural levels are respected,
    filtering out the micro-chop of 1-hour noise.
    """
    # Get highest high and lowest low of the PREVIOUS N periods
    df['recent_high'] = df['high'].shift(1).rolling(window=period).max()
    df['recent_low'] = df['low'].shift(1).rolling(window=period).min()
    
    # Bullish BOS: Close breaks above the recent high
    df['bullish_bos'] = df['close'] > df['recent_high']
    
    # Bearish BOS: Close breaks below the recent low
    df['bearish_bos'] = df['close'] < df['recent_low']
    
    return df