from config.secrets import API_KEY, API_SECRET
import pandas as pd
from binance.client import Client
from config.settings import *

client = Client(API_KEY, API_SECRET)

# Get Token
def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

# Get USDT balance
def get_usdt_balance():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0

# Get Position
def get_position(symbol):
    try:
        positions = client.futures_position_information()
        for pos in positions:
            if pos['symbol'] == symbol:
                position_amt = float(pos['positionAmt'])
                entry_price = float(pos['entryPrice'])
                current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                order_size = abs(position_amt) * entry_price
                margin_used = order_size / leverage
                unrealized_profit = (current_price - entry_price) * position_amt
                roi = (unrealized_profit / margin_used) * 100 
                
                return position_amt, roi, unrealized_profit, margin_used
        return 0, 0, 0, 0
    except Exception as e:
        print(f"Error getting position for {symbol}: {e}")
        return 0, 0, 0, 0
    
# Get price
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

# Get candles
def fetch_klines(symbol, interval, lookback='100'):
    print(f"Fetching candles for {symbol} with interval {interval} and lookback {lookback}")
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    
    # Calculate support and resistance levels
    support = df['low'].min()
    resistance = df['high'].max()
        
    print(f"Support: {support}, Resistance: {resistance}")
    
    # Return the DataFrame along with support and resistance levels
    return df, support, resistance 

# Function to calculate support and resistance levels
def calculate_support_resistance(df):
    support = df['low'].min()
    resistance = df['high'].max()
    return support, resistance

# Get trend
def detect_trend(df):
    trend = 'sideways'
    
    # Loop through the DataFrame starting from the second index
    for i in range(2, len(df)):
        current_high = df['high'].iloc[i]
        previous_high = df['high'].iloc[i-1]
        current_low = df['low'].iloc[i]
        previous_low = df['low'].iloc[i-1]
        
        # Check if we have a higher high and higher low (uptrend)
        if current_high > previous_high and current_low > previous_low:
            trend = 'uptrend'
        
        # Check if we have a lower high and lower low (downtrend)
        elif current_high < previous_high and current_low < previous_low:
            trend = 'downtrend'
        
        # If neither higher highs and higher lows nor lower highs and lower lows are found
        elif trend == 'sideways':  # Maintain sideways if no clear trend is identified
            trend = 'sideways'

    return trend
