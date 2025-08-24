import os
import json
import pandas as pd
from binance.enums import *

from config.paths import LOG_FILE
from config.secrets import API_KEY, API_SECRET
from config.settings import VERBOSE_LOGGING

from data.get_data import get_market_price, round_price, round_quantity, get_usdt_balance

from binance.client import Client

client = Client(API_KEY, API_SECRET)

async def move_stop_to_breakeven(symbol, entry_price, side):
    """
    Cancels existing stop-loss orders and places a new one at the entry price.
    """
    print(f"--- Moving Stop-Loss to Breakeven for {symbol} ---")
    try:
        await cancel_open_orders(symbol, cancel_sl=True, cancel_tp=False)
        
        stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        breakeven_price = round_price(symbol, entry_price)
        
        sl_order = client.futures_create_order(
            symbol=symbol,
            side=stop_loss_side,
            type='STOP_MARKET',
            stopPrice=breakeven_price,
            closePosition=True
        )
        print(f"New breakeven stop-loss placed successfully at {breakeven_price}: {sl_order['orderId']}")
        return True
    except Exception as e:
        print(f"Error moving stop-loss to breakeven for {symbol}: {e}")
        return False

async def manage_atr_trailing_stop(symbol, position_obj, atr_value):
    """
    Manages an ATR-based trailing stop for a profitable position.
    This function is not dependent on a specific ROI to activate.
    """
    position_side = SIDE_BUY if float(position_obj['positionAmt']) > 0 else SIDE_SELL
    entry_price = float(position_obj['entryPrice'])
    current_price = get_market_price(symbol)
    
    if not current_price:
        return

    # --- Trailing Stop Logic ---
    # This multiplier can be adjusted to make the trail tighter or looser.
    TRAILING_STOP_ATR_MULTIPLIER = 2.5 
    
    if position_side == SIDE_BUY:
        # For a long position, the stop loss should only move up
        new_stop_price = current_price - (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        
        # We only update the stop loss if the new stop price is higher than the entry price
        if new_stop_price > entry_price:
            await update_stop_loss(symbol, new_stop_price, position_side)
    
    elif position_side == SIDE_SELL:
        # For a short position, the stop loss should only move down
        new_stop_price = current_price + (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        
        # We only update the stop loss if the new stop price is lower than the entry price
        if new_stop_price < entry_price:
            await update_stop_loss(symbol, new_stop_price, position_side)

async def update_stop_loss(symbol, new_stop_price, side):
    """
    Cancels the old stop loss and places a new, updated one.
    """
    try:
        # Cancel only the existing STOP_MARKET order
        open_orders = client.futures_get_open_orders(symbol=symbol)
        for order in open_orders:
            if order['type'] == 'STOP_MARKET':
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                if VERBOSE_LOGGING:
                    print(f"Canceled existing stop order {order['orderId']} to place new trailing stop.")

        # Place the new trailing stop loss
        stop_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        new_stop_price_rounded = round_price(symbol, new_stop_price)

        sl_order = client.futures_create_order(
            symbol=symbol,
            side=stop_side,
            type='STOP_MARKET',
            stopPrice=new_stop_price_rounded,
            closePosition=True
        )
        print(f"Successfully moved trailing stop for {symbol} to {new_stop_price_rounded}")

    except Exception as e:
        print(f"Error updating trailing stop for {symbol}: {e}")


def log_trade(data):
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            json.dump([], f) 

    with open(LOG_FILE, 'r') as f:
        logs = json.load(f)
    logs.append(data) 

    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=4)

async def cancel_open_orders(symbol, cancel_sl=True, cancel_tp=True):
    """
    Cancels specific types of open orders for a given symbol.
    """
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        if not open_orders:
            return

        print(f"Found {len(open_orders)} open order(s) for {symbol}. Evaluating for cancellation.")
        for order in open_orders:
            order_type = order['type']
            should_cancel = (cancel_sl and 'STOP' in order_type) or \
                            (cancel_tp and 'PROFIT' in order_type)
            
            if should_cancel:
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                if VERBOSE_LOGGING:
                    print(f"Canceled open order for {symbol}, Type: {order_type}, ID: {order['orderId']}")
    except Exception as e:
        print(f"Error canceling open orders for {symbol}: {e}")

# --- MODIFIED: Integrated Dynamic Position Sizing ---
async def place_order(symbol, side, usdt_balance, reason_to_open, support_4h, resistance_4h, adx_value, reduce_only=False, stop_loss_atr_multiplier=None, atr_value=None, df=None):
    """
    Places a bracket order with position size dynamically adjusted based on ADX.
    """
    # --- Dynamic Risk Calculation based on ADX ---
    if adx_value > 25: # Strong trend
        RISK_PER_TRADE = 0.03 # Risk 3%
        print(f"ADX is {adx_value:.2f} (Strong Trend). Using HIGH risk (3%).")
    elif adx_value > 18: # Healthy trend
        RISK_PER_TRADE = 0.02 # Risk 2%
        print(f"ADX is {adx_value:.2f} (Healthy Trend). Using NORMAL risk (2%).")
    else: # Weak or no trend
        RISK_PER_TRADE = 0.01 # Risk 1%
        print(f"ADX is {adx_value:.2f} (Weak Trend). Using LOW risk (1%).")

    RR_RATIO_TP1 = 1.5

    try:
        await cancel_open_orders(symbol, cancel_sl=True, cancel_tp=True)
        await set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None: return False
        
        limit_price = round_price(symbol, price)

        if stop_loss_atr_multiplier is None or atr_value is None or df is None:
            print("Cannot calculate position size without ATR, multiplier, and historical data.")
            return False

        if side == SIDE_BUY:
            atr_stop_loss = limit_price - (atr_value * stop_loss_atr_multiplier)
            recent_low = df['low'].iloc[-3:].min()
            stop_loss_price = min(atr_stop_loss, recent_low)
        else:
            atr_stop_loss = limit_price + (atr_value * stop_loss_atr_multiplier)
            recent_high = df['high'].iloc[-3:].max()
            stop_loss_price = max(atr_stop_loss, recent_high)
        
        stop_loss_price = round_price(symbol, stop_loss_price)
        
        stop_loss_distance = abs(limit_price - stop_loss_price)
        if stop_loss_distance == 0:
            print("Stop loss distance is zero, cannot calculate position size.")
            return False

        if side == SIDE_BUY:
            take_profit_1_price = limit_price + (stop_loss_distance * RR_RATIO_TP1)
            take_profit_2_price = resistance_4h 
        else:
            take_profit_1_price = limit_price - (stop_loss_distance * RR_RATIO_TP1)
            take_profit_2_price = support_4h
        
        take_profit_1_price = round_price(symbol, take_profit_1_price)
        take_profit_2_price = round_price(symbol, take_profit_2_price)

        potential_reward_final = abs(take_profit_2_price - limit_price)
        dynamic_rr_ratio = potential_reward_final / stop_loss_distance if stop_loss_distance > 0 else 0
        
        MIN_FINAL_RR = 1.0
        if dynamic_rr_ratio < MIN_FINAL_RR:
            if VERBOSE_LOGGING:
                print(f"Skipping {symbol} trade: Poor risk/reward ratio ({dynamic_rr_ratio:.2f}) to major S/R level.")
            return False

        stop_loss_distance_percent = stop_loss_distance / limit_price if limit_price > 0 else 0
        trade_amount_usdt = (usdt_balance * RISK_PER_TRADE) / stop_loss_distance_percent if stop_loss_distance_percent > 0 else 0
        total_quantity = round_quantity(symbol, trade_amount_usdt / limit_price) if limit_price > 0 else 0
        
        quantity_tp1 = round_quantity(symbol, total_quantity * 0.5) # 50% for TP1
        quantity_tp2 = round_quantity(symbol, total_quantity - quantity_tp1) # Remaining for TP2

        print(f"--- New Dynamic TP Order ---")
        print(f"Risk per trade: {RISK_PER_TRADE*100}%")
        print(f"Entry: ${limit_price:.4f}, Total Qty: {total_quantity}")
        print(f"TP1 (50%): ${take_profit_1_price:.4f} (Qty: {quantity_tp1}), R:R: {RR_RATIO_TP1}")
        print(f"TP2 (50%): ${take_profit_2_price:.4f} (Qty: {quantity_tp2}), R:R: {dynamic_rr_ratio:.2f}")
        print(f"Stop Loss: ${stop_loss_price:.4f}")

        if total_quantity <= 0 or round(limit_price * total_quantity, 2) < 5:
            print("Calculated quantity or notional value is too small to trade.")
            return False

        # --- Place Orders ---
        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_LIMIT, quantity=total_quantity,
            price=limit_price, timeInForce=TIME_IN_FORCE_GTC
        )
        print(f"Entry order placed successfully: {order['orderId']}")
        log_trade({
            "symbol": symbol, "USDT_balance": usdt_balance, "side": side, 
            "quantity": total_quantity, "price": limit_price, "reason": reason_to_open,
            "timestamp": pd.Timestamp.now().isoformat()
        })

        stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY

        sl_order = client.futures_create_order(
            symbol=symbol, side=stop_loss_side, type='STOP_MARKET',
            stopPrice=stop_loss_price, closePosition=True
        )
        print(f"Stop-Loss order placed successfully: {sl_order['orderId']}")

        if quantity_tp1 > 0:
            tp1_order = client.futures_create_order(
                symbol=symbol, side=stop_loss_side, type='TAKE_PROFIT_MARKET',
                quantity=quantity_tp1, stopPrice=take_profit_1_price, reduceOnly=True
            )
            print(f"Take-Profit 1 order placed successfully: {tp1_order['orderId']}")
        
        if quantity_tp2 > 0:
            tp2_order = client.futures_create_order(
                symbol=symbol, side=stop_loss_side, type='TAKE_PROFIT_MARKET',
                quantity=quantity_tp2, stopPrice=take_profit_2_price, reduceOnly=True
            )
            print(f"Take-Profit 2 order placed successfully: {tp2_order['orderId']}")
        
        return True

    except Exception as e:
        print(f"Error placing order: {e}")
        return False

def close_position(symbol, side, quantity, reason_to_close):
    print(f"Closing position: {side} {quantity} {symbol}. Reason: {reason_to_close}")
    try:
        price = get_market_price(symbol)
        if price is None:
            return

        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=quantity, reduceOnly=True
        )
        print(f"Position closed successfully via MARKET order: {order}")

        new_usdt_balance = get_usdt_balance()

        log_trade({
            "symbol": symbol, "new_USDT_balance": new_usdt_balance,
            "closing_side": side, "closing_quantity": quantity,
            "closing_price": float(order['avgPrice']), "reason_to_close": reason_to_close,
            "timestamp": pd.Timestamp.now().isoformat()
        })

    except Exception as e:
        print(f"Error closing position: {e}")      
        
async def set_margin_type(symbol, margin_type='ISOLATED'):
    try:
        current_margin_type = client.futures_get_position_information(symbol=symbol)[0]['marginType']
        if current_margin_type.lower() != margin_type.lower():
            response = client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
            if VERBOSE_LOGGING:
                print(f"Margin type for {symbol} set to {margin_type}: {response}")
        elif VERBOSE_LOGGING:
             print(f"Margin type for {symbol} is already {margin_type}.")
    except Exception as e:
        if "No need to change margin type" in str(e):
            if VERBOSE_LOGGING:
                print(f"Margin type for {symbol} is already {margin_type}.")
        else:
            print(f"Error setting margin type for {symbol}: {e}")