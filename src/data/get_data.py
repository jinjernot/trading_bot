from config.api import API_KEY, API_SECRET

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
            return position_amt, roi, unrealized_profit
    return 0, 0, 0

# Function to get the current market price of the symbol
def get_market_price(symbol):
    try:
        price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        return price
    except Exception as e:
        print(f"Error getting market price: {e}")
        return None
    
def calculate_roi(entry_price, current_price, position_amt, margin_used):
    if margin_used == 0:
        return 0.0
    return ((current_price - entry_price) * position_amt) / margin_used * 100

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