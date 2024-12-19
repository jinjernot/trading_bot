
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
        

def calculate_stop_loss(entry_price, position_side, stop_loss_percentage):
    """
    Calculate the stop-loss price based on the entry price and position side.
    """
    stop_loss_percentage /= 3
    
    if position_side == SIDE_BUY:  # Long position
        return entry_price * (1 - stop_loss_percentage / 100)
    elif position_side == SIDE_SELL:  # Short position
        return entry_price * (1 + stop_loss_percentage / 100)


def place_order(symbol, side, usdt_balance, reason_to_open, reduce_only=False, stop_loss_percentage=None):
    trade_amount = usdt_balance * 0.5
    print(f"34% of available USDT balance for trade: {trade_amount}")

    try:
        set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None:
            return
        # Adjust the price for limit order based on symbol precision
        limit_price = round_price(symbol, price)

        # Calculate the quantity to trade based on available balance
        quantity = trade_amount / limit_price
        quantity = round_quantity(symbol, quantity)  # Use round_quantity to adjust to symbol's step size

        notional = limit_price * quantity
        if notional < 100:
            print(f"Notional value {notional} is too small, adjusting quantity to meet minimum notional.")
            quantity = 100 / limit_price
            quantity = round_quantity(symbol, quantity)  # Ensure the adjusted quantity meets step size

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

        # Log trade details with symbol
        log_trade({
            "symbol": symbol,  # Added symbol
            "USDT_balance_before_trade": usdt_balance,
            "trade_side": side,
            "trade_quantity": quantity,
            "trade_price": limit_price,
            "reason_to_open": reason_to_open,
            "reduce_only": reduce_only,
            "timestamp": pd.Timestamp.now().isoformat()
        })

        # Place stop-loss order if stop_loss_percentage is provided
        if stop_loss_percentage is not None:
            # Calculate stop-loss price
            stop_loss_price = calculate_stop_loss(limit_price, side, stop_loss_percentage)
            stop_loss_price = round_price(symbol, stop_loss_price)

            # Ensure stop_loss_side is correctly set
            stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY

            # Log calculated stop-loss price
            print(f"Calculated stop-loss price: {stop_loss_price} (Stop Price: {stop_loss_price})")

            # Check if stop loss price is within a valid range
            if stop_loss_price <= 0:
                print(f"Invalid stop-loss price: {stop_loss_price}")
                return  # Exit if the price is invalid

            # Ensure quantity is greater than zero
            if quantity <= 0:
                print("Invalid quantity for stop-loss order.")
                return 

            try:
                # Place stop-loss limit order
                stop_loss_order = client.futures_create_order(
                    symbol=symbol,
                    side=stop_loss_side,
                    type=FUTURE_ORDER_TYPE_STOP,
                    stopPrice=stop_loss_price,
                    price=stop_loss_price,
                    quantity=quantity,
                    timeInForce=TIME_IN_FORCE_GTC  # Good Till Canceled
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