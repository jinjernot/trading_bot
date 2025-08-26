import os
import json
import pandas as pd
from binance.enums import *
import asyncio

from config.paths import LOG_FILE
from config.secrets import API_KEY, API_SECRET
from config.settings import VERBOSE_LOGGING, TRAILING_STOP_ATR_MULTIPLIER

from data.get_data import get_market_price, round_price, round_quantity, get_usdt_balance, fetch_multi_timeframe_data
from data.indicators import calculate_atr

from binance.client import Client

client = Client(API_KEY, API_SECRET)

async def manage_active_trades(active_positions):
    """
    Loop through active positions to manage ATR trailing stops for profitable trades.
    """
    if not active_positions:
        return

    print(f"\n--- Managing {len(active_positions)} Active Trade(s) ---")
    for position_obj in active_positions:
        symbol = position_obj['symbol']
        unrealized_profit = float(position_obj.get('unrealizedProfit', 0))

        if unrealized_profit > 0:
            print(f"✅ Position for {symbol} is profitable. Managing ATR trailing stop.")
            
            df_15m, _, _, _, _, _, _, _, _ = await asyncio.to_thread(
                fetch_multi_timeframe_data, symbol, '15m', '4h', '1d'
            )
            df_15m = calculate_atr(df_15m)
            atr_value = df_15m['atr'].iloc[-1]
            
            await manage_atr_trailing_stop(symbol, position_obj, atr_value)

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
    (Corrected Logic)
    """
    position_side = SIDE_BUY if float(position_obj['positionAmt']) > 0 else SIDE_SELL
    current_price = get_market_price(symbol)

    if not current_price:
        return

    # --- Find the current stop-loss order price ---
    open_orders = client.futures_get_open_orders(symbol=symbol)
    current_stop_price = None
    for order in open_orders:
        if order['type'] == 'STOP_MARKET':
            current_stop_price = float(order['stopPrice'])
            break
    
    if current_stop_price is None:
        if VERBOSE_LOGGING:
            print(f"Could not find an existing stop-loss for {symbol} to trail.")
        return
    
    if position_side == SIDE_BUY:
        new_stop_price = current_price - (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        # If the newly calculated stop price is higher than the current one, update it.
        if new_stop_price > current_stop_price:
            print(f"✅ Trailing stop for {symbol}. New SL: {new_stop_price:.4f} (Old: {current_stop_price:.4f})")
            await update_stop_loss(symbol, new_stop_price, position_side)
    
    elif position_side == SIDE_SELL:
        new_stop_price = current_price + (atr_value * TRAILING_STOP_ATR_MULTIPLIER)

        # If the newly calculated stop price is lower than the current one, update it.
        if new_stop_price < current_stop_price:
            print(f"✅ Trailing stop for {symbol}. New SL: {new_stop_price:.4f} (Old: {current_stop_price:.4f})")
            await update_stop_loss(symbol, new_stop_price, position_side)
            
            
async def update_stop_loss(symbol, new_stop_price, side):
    """
    Cancels the old stop loss and places a new, updated one.
    """
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        for order in open_orders:
            if order['type'] == 'STOP_MARKET':
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])

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
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        if not open_orders:
            return

        for order in open_orders:
            order_type = order['type']
            should_cancel = (cancel_sl and 'STOP' in order_type) or \
                            (cancel_tp and 'PROFIT' in order_type)
            
            if should_cancel:
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
    except Exception as e:
        print(f"Error canceling open orders for {symbol}: {e}")

async def place_order(symbol, side, usdt_balance, reason_to_open, support_4h, resistance_4h, adx_value, reduce_only=False, stop_loss_atr_multiplier=2.0, atr_value=None, df=None, stop_loss_price=None):
    """
    MODIFIED: Now accepts an optional 'stop_loss_price'. 
    If provided, it uses it. Otherwise, it calculates SL with ATR.
    """
    if adx_value > 25:
        RISK_PER_TRADE = 0.03
    elif adx_value > 18:
        RISK_PER_TRADE = 0.02
    else:
        RISK_PER_TRADE = 0.01

    RR_RATIO_TP1 = 1.5

    try:
        await cancel_open_orders(symbol, cancel_sl=True, cancel_tp=True)
        await set_margin_type(symbol, margin_type='ISOLATED')

        price = get_market_price(symbol)
        if price is None: return False
        
        limit_price = round_price(symbol, price)

        # --- MODIFIED LOGIC: Prioritize provided stop_loss_price ---
        if stop_loss_price is None:
            # Original ATR-based calculation for the trend-following bot
            if atr_value is None or df is None:
                print("Cannot calculate position size without ATR and historical data.")
                return False

            if side == SIDE_BUY:
                atr_stop_loss = limit_price - (atr_value * stop_loss_atr_multiplier)
                recent_low = df['low'].iloc[-3:].min()
                stop_loss_price = min(atr_stop_loss, recent_low)
            else: # SIDE_SELL
                atr_stop_loss = limit_price + (atr_value * stop_loss_atr_multiplier)
                recent_high = df['high'].iloc[-3:].max()
                stop_loss_price = max(atr_stop_loss, recent_high)
        
        # --- End of modified logic ---
        
        stop_loss_price = round_price(symbol, stop_loss_price)
        
        stop_loss_distance = abs(limit_price - stop_loss_price)
        if stop_loss_distance == 0:
            print("Stop loss distance is zero, cannot calculate position size.")
            return False

        if side == SIDE_BUY:
            take_profit_1_price = limit_price + (stop_loss_distance * RR_RATIO_TP1)
            take_profit_2_price = resistance_4h 
        else: # SIDE_SELL
            take_profit_1_price = limit_price - (stop_loss_distance * RR_RATIO_TP1)
            take_profit_2_price = support_4h
        
        take_profit_1_price = round_price(symbol, take_profit_1_price)
        take_profit_2_price = round_price(symbol, take_profit_2_price)

        stop_loss_distance_percent = stop_loss_distance / limit_price if limit_price > 0 else 0
        trade_amount_usdt = (usdt_balance * RISK_PER_TRADE) / stop_loss_distance_percent if stop_loss_distance_percent > 0 else 0
        total_quantity = round_quantity(symbol, trade_amount_usdt / limit_price) if limit_price > 0 else 0
        
        if total_quantity <= 0 or round(limit_price * total_quantity, 2) < 5:
            print("Calculated quantity or notional value is too small to trade.")
            return False

        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=total_quantity
        )
        log_trade({
            "symbol": symbol, "USDT_balance": usdt_balance, "side": side, 
            "quantity": total_quantity, "price": float(order['avgPrice']), "reason": reason_to_open,
            "timestamp": pd.Timestamp.now().isoformat()
        })

        stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        sl_order = client.futures_create_order(
            symbol=symbol, side=stop_loss_side, type='STOP_MARKET',
            stopPrice=stop_loss_price, closePosition=True
        )
        
        return True

    except Exception as e:
        print(f"Error placing order: {e}")
        return False

def close_position(symbol, side, quantity, reason_to_close):
    try:
        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=quantity, reduceOnly=True
        )
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
    """
    MODIFIED: Handles cases where no position info exists for a symbol.
    """
    try:
        # CORRECTED FUNCTION NAME
        position_info = client.futures_position_information(symbol=symbol)
        
        if position_info:
            current_margin_type = position_info[0]['marginType']
            if current_margin_type.lower() != margin_type.lower():
                client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
                if VERBOSE_LOGGING:
                    print(f"Margin type for {symbol} set to {margin_type}.")
        else:
            # If no position info exists, we can likely just set it.
            try:
                client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
                if VERBOSE_LOGGING:
                    print(f"Margin type for new symbol {symbol} set to {margin_type}.")
            except Exception as e:
                if "No need to change margin type" not in str(e):
                    raise e
    except Exception as e:
        if "No need to change margin type" not in str(e):
            print(f"Error setting margin type for {symbol}: {e}")