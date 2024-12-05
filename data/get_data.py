from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client

client = Client(API_KEY, API_SECRET)

def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

# Fetch available USDT balance
def get_usdt_balance():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0

# Update in the get_position function to calculate ROI and display as percentage
def get_position(symbol):
    positions = client.futures_position_information()
    for pos in positions:
        if pos['symbol'] == symbol:
            position_amt = float(pos['positionAmt'])
            entry_price = float(pos['entryPrice'])
            current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
            margin_used = abs(position_amt) * entry_price  # Adjust based on leverage
            unrealized_profit = (current_price - entry_price) * position_amt
            roi = (unrealized_profit / margin_used) * 100  # ROI as a percentage of margin used
            return position_amt, roi, unrealized_profit, margin_used
    return 0, 0, 0, 0

# Function to get the current market price of the symbol
def get_market_price(symbol):
    try:
        price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        return price
    except Exception as e:
        print(f"Error getting market price: {e}")
        return None

# Adjust quantity to match Binance rules
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
   
# Adjust price to match Binance rules
def round_price(symbol, price):
    symbol_info = get_symbol_info(symbol)
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'PRICE_FILTER':
            tick_size = float(filt['tickSize'])
            price = round(price - (price % tick_size), 8)  # Align price with tick size
            return price
    return price

def fetch_klines(symbol, interval, lookback='200'):
    print(f"Fetching klines for {symbol} with interval {interval} and lookback {lookback}")
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    
    # Calculate support and resistance levels
    support = df['low'].min()  # Lowest price in the 'low' column
    resistance = df['high'].max()  # Highest price in the 'high' column
    
    print(f"Fetched {len(df)} rows of data.")
    print(f"Support: {support}, Resistance: {resistance}")
    
    # Return the DataFrame along with support and resistance levels
    return df, support, resistance

# Function to calculate support and resistance levels
def calculate_support_resistance(df):
    support = df['low'].min()  # Lowest price in the 'low' column
    resistance = df['high'].max()  # Highest price in the 'high' column
    return support, resistance


def detect_trend(df, short_window=50, long_window=200):
    """
    Detects the trend of the market using moving averages.
    
    :param df: DataFrame containing historical candlestick data.
    :param short_window: Short-term window for moving average (default 50).
    :param long_window: Long-term window for moving average (default 200).
    :return: 'uptrend', 'downtrend', or 'sideways' based on the moving average crossover.
    """
    short_ma = df['close'].rolling(window=short_window).mean()
    long_ma = df['close'].rolling(window=long_window).mean()
    
    # Check if short MA is above long MA (uptrend) or below (downtrend)
    if short_ma.iloc[-1] > long_ma.iloc[-1]:
        return 'uptrend'
    elif short_ma.iloc[-1] < long_ma.iloc[-1]:
        return 'downtrend'
    else:
        return 'sideways'
