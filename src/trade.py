
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
            if order['type'] == 'FUTURE_ORDER_TYPE_STOP' or order['type'] == 'STOP':
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                print(f"Canceled stop-loss order for {symbol}, Order ID: {order['orderId']}")
    except Exception as e:
        print(f"Error canceling open orders for {symbol}: {e}")


def place_order(symbol, side, usdt_balance, reason_to_open, reduce_only=False, stop_loss_atr_multiplier=None, atr_value=None):
    trade_amount = usdt_balance * 1
    print(f"USDT balance for trade: {trade_amount}")

    try:
        set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None:
            return
        
        limit_price = round_price(symbol, price)
        quantity = trade_amount / limit_price
        quantity = round_quantity(symbol, quantity)

        notional = limit_price * quantity
        if notional < 100:
            print(f"Notional value {notional} is too small, adjusting quantity to meet minimum notional.")
            quantity = 100 / limit_price
            quantity = round_quantity(symbol, quantity)

        if quantity <= 0:
            print("Calculated quantity is too small to trade.")
            return

        print(f"Placing limit order: {side} {quantity} {symbol} at {limit_price}")
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=limit_price,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=reduce_only
        )
        print(f"Order placed successfully: {order}")

        log_trade({
            "symbol": symbol,
            "USDT_balance_before_trade": usdt_balance,
            "trade_side": side,
            "trade_quantity": quantity,
            "trade_price": limit_price,
            "reason_to_open": reason_to_open,
            "reduce_only": reduce_only,
            "timestamp": pd.Timestamp.now().isoformat()
        })

        # Place stop-loss order if an ATR multiplier is provided
        if stop_loss_atr_multiplier is not None and atr_value is not None:
            # Calculate stop-loss price using ATR
            if side == SIDE_BUY:  # Long position
                stop_loss_price = limit_price - (atr_value * stop_loss_atr_multiplier)
            elif side == SIDE_SELL:  # Short position
                stop_loss_price = limit_price + (atr_value * stop_loss_atr_multiplier)
            
            stop_loss_price = round_price(symbol, stop_loss_price)
            stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY

            print(f"Calculated ATR-based stop-loss price: {stop_loss_price}")

            if stop_loss_price <= 0 or quantity <= 0:
                print(f"Invalid stop-loss price or quantity.")
                return

            try:
                stop_loss_order = client.futures_create_order(
                    symbol=symbol,
                    side=stop_loss_side,
                    type=FUTURE_ORDER_TYPE_STOP,
                    stopPrice=stop_loss_price,
                    price=stop_loss_price,
                    quantity=quantity,
                    timeInForce=TIME_IN_FORCE_GTC
                )
                print(f"Stop-loss order placed successfully: {stop_loss_order}")
            except Exception as e:
                print(f"Error placing stop-loss order: {e}")
    except Exception as e:
        print(f"Error placing order: {e}")

def close_position(symbol, side, quantity, reason_to_close):
    print(f"Closing position: {side} {quantity} {symbol}. Reason: {reason_to_close}")
    try:
        # Ensure margin type is isolated
        set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None:
            return

        # Adjust the price slightly for limit orders
        if side == SIDE_BUY:
            limit_price = price * 1.01
        elif side == SIDE_SELL:
            limit_price = price * 0.99

        # Align limit price with the tick size
        limit_price = round_price(symbol, limit_price)

        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=limit_price,
            timeInForce=TIME_IN_FORCE_GTC,
            reduceOnly=True
        )
        print(f"Position closed successfully: {order}")

        # Fetch updated USDT balance
        new_usdt_balance = get_usdt_balance()

        # Log trade details with symbol
        log_trade({
            "symbol": symbol,  # Added symbol
            "new_USDT_balance": new_usdt_balance,
            "closing_side": side,
            "closing_quantity": quantity,
            "closing_price": limit_price,
            "reason_to_close": reason_to_close,
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