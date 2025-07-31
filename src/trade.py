import os
import json
import pandas as pd
from binance.enums import *

from config.paths import LOG_FILE
from config.secrets import API_KEY, API_SECRET

from data.get_data import *

from binance.client import Client

client = Client(API_KEY, API_SECRET)

# Function to log trades
def log_trade(data):

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            json.dump([], f) 

    with open(LOG_FILE, 'r') as f:
        logs = json.load(f)
    logs.append(data) 

    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=4)


async def cancel_open_orders(symbol):
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        for order in open_orders:
            # Check for both Stop and Take Profit order types
            if order['type'] in ['STOP', 'TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'STOP_MARKET']:
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                print(f"Canceled open order for {symbol}, Type: {order['type']}, ID: {order['orderId']}")
    except Exception as e:
        print(f"Error canceling open orders for {symbol}: {e}")


def place_order(symbol, side, usdt_balance, reason_to_open, reduce_only=False, stop_loss_atr_multiplier=None, atr_value=None):
    
    RISK_PER_TRADE = 0.02  # Risking 2% of the account per trade.
    RISK_REWARD_RATIO = 2 # Aiming for 1.5x our risk

    try:
        set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None: return
        
        limit_price = round_price(symbol, price)

        # --- POSITION SIZING AND TP/SL CALCULATION ---
        if stop_loss_atr_multiplier is None or atr_value is None:
            print("Cannot calculate position size without ATR and multiplier.")
            return

        # 1. Calculate Stop-Loss Price and Distance
        if side == SIDE_BUY:
            stop_loss_price = limit_price - (atr_value * stop_loss_atr_multiplier)
        else: # SIDE_SELL
            stop_loss_price = limit_price + (atr_value * stop_loss_atr_multiplier)
        stop_loss_price = round_price(symbol, stop_loss_price)
        
        stop_loss_distance = abs(limit_price - stop_loss_price)
        if stop_loss_distance == 0:
            print("Stop loss distance is zero, cannot calculate position size.")
            return

        # 2. Calculate Take-Profit Price
        if side == SIDE_BUY:
            take_profit_price = limit_price + (stop_loss_distance * RISK_REWARD_RATIO)
        else: # SIDE_SELL
            take_profit_price = limit_price - (stop_loss_distance * RISK_REWARD_RATIO)
        take_profit_price = round_price(symbol, take_profit_price)

        # 3. Calculate Position Size
        stop_loss_distance_percent = stop_loss_distance / limit_price
        trade_amount_usdt = (usdt_balance * RISK_PER_TRADE) / stop_loss_distance_percent
        quantity = round_quantity(symbol, trade_amount_usdt / limit_price)
        # --- END OF CALCULATIONS ---

        print(f"--- New Order ---")
        print(f"Risk per trade: {RISK_PER_TRADE*100}%, R:R Ratio: {RISK_REWARD_RATIO}")
        print(f"Entry: ${limit_price:.4f}, Qty: {quantity}")
        print(f"Take Profit: ${take_profit_price:.4f}")
        print(f"Stop Loss: ${stop_loss_price:.4f}")

        if quantity <= 0 or round(limit_price * quantity, 2) < 5: # Binance minimum notional value is ~$5
            print("Calculated quantity or notional value is too small to trade.")
            return

        # --- PLACING ORDERS ---
        # 1. Entry Order
        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_LIMIT, quantity=quantity,
            price=limit_price, timeInForce=TIME_IN_FORCE_GTC, reduceOnly=reduce_only
        )
        print(f"Entry order placed successfully: {order['orderId']}")
        log_trade({
            "symbol": symbol, "USDT_balance": usdt_balance, "side": side, 
            "quantity": quantity, "price": limit_price, "reason": reason_to_open
        })

        # 2. Stop-Loss Order
        stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        sl_order = client.futures_create_order(
            symbol=symbol, side=stop_loss_side, type='STOP_MARKET',
            stopPrice=stop_loss_price, closePosition=True, timeInForce='GTC'
        )
        print(f"Stop-Loss order placed successfully: {sl_order['orderId']}")

        # 3. Take-Profit Order
        tp_order = client.futures_create_order(
            symbol=symbol, side=stop_loss_side, type='TAKE_PROFIT_MARKET',
            stopPrice=take_profit_price, closePosition=True, timeInForce='GTC'
        )
        print(f"Take-Profit order placed successfully: {tp_order['orderId']}")

    except Exception as e:
        print(f"Error placing order: {e}")
        

def close_position(symbol, side, quantity, reason_to_close):
    print(f"Closing position: {side} {quantity} {symbol}. Reason: {reason_to_close}")
    try:
        set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None:
            return

        if side == SIDE_BUY:
            limit_price = price * 1.01
        elif side == SIDE_SELL:
            limit_price = price * 0.99

        limit_price = round_price(symbol, limit_price)

        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_LIMIT, quantity=quantity,
            price=limit_price, timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
        )
        print(f"Position closed successfully: {order}")

        new_usdt_balance = get_usdt_balance()

        log_trade({
            "symbol": symbol, "new_USDT_balance": new_usdt_balance,
            "closing_side": side, "closing_quantity": quantity,
            "closing_price": limit_price, "reason_to_close": reason_to_close,
            "timestamp": pd.Timestamp.now().isoformat()
        })

    except Exception as e:
        print(f"Error closing position: {e}")      
        

def set_margin_type(symbol, margin_type='ISOLATED'):
    try:
        response = client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
        print(f"Margin type for {symbol} set to {margin_type}: {response}")
    except Exception as e:
        if "No need to change margin type" in str(e):
            print(f"Margin type for {symbol} is already {margin_type}.")
        else:
            print(f"Error setting margin type for {symbol}: {e}")