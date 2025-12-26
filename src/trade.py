import os
import json
import time
import pandas as pd
import hmac
import hashlib
import requests
from binance.enums import (
    SIDE_BUY, 
    SIDE_SELL, 
    ORDER_TYPE_MARKET
)
import asyncio

from config.paths import LOG_FILE
from config.secrets import API_KEY, API_SECRET
from config.settings import VERBOSE_LOGGING, TRAILING_STOP_ATR_MULTIPLIER, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME

from data.get_data import get_market_price, round_price, round_quantity, get_usdt_balance, fetch_multi_timeframe_data
from data.indicators import calculate_atr
from src.detailed_logger import log_trade_exit

from binance.client import Client

client = Client(API_KEY, API_SECRET)
# Sync time with Binance servers to fix timestamp errors
try:
    server_time = client.get_server_time()
    local_time = int(time.time() * 1000)
    time_offset = server_time['serverTime'] - local_time
    client.timestamp_offset = time_offset
except Exception:
    pass  # Silent fail on import


def place_algo_stop_loss(symbol, side, stop_price, quantity, working_type='CONTRACT_PRICE'):
    """
    Places a STOP_MARKET order using Binance's new Algo Order API endpoint.
    Required since December 9, 2025 when Binance migrated conditional orders.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        side: 'BUY' or 'SELL'
        stop_price: Trigger price for the stop-loss
        quantity: Position quantity to close
        working_type: 'CONTRACT_PRICE' or 'MARK_PRICE'
    
    Returns:
        dict: API response containing order details
    """
    from urllib.parse import urlencode
    
    base_url = 'https://fapi.binance.com'
    endpoint = '/fapi/v1/algoOrder'
    
    # Prepare parameters (don't include signature yet)
    timestamp = int(time.time() * 1000) + getattr(client, 'timestamp_offset', 0)
    params = {
        'symbol': symbol,
        'side': side,
        'algoType': 'CONDITIONAL',  # Required for STOP_MARKET orders
        'type': 'STOP_MARKET',
        'triggerprice': float(stop_price),  # Binance uses lowercase triggerprice
        'quantity': float(quantity),         # Ensure it's a float
        'reduceOnly': 'true',
        'workingType': working_type,
        'timestamp': timestamp
    }
    
    # Create query string for signature (parameters in original order, URL encoded)
    query_string = urlencode(params)
    
    # Generate signature
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Add signature to params
    params['signature'] = signature
    
    # Make request
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    
    response = requests.post(
        base_url + endpoint,
        params=params,
        headers=headers,
        timeout=10
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Algo Order API Error: {response.status_code} - {response.text}")


def place_algo_take_profit(symbol, side, take_profit_price, quantity, working_type='CONTRACT_PRICE'):
    """
    Places a TAKE_PROFIT_MARKET order using Binance's new Algo Order API endpoint.
    Required since December 9, 2025 when Binance migrated conditional orders.
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        side: 'BUY' or 'SELL'
        take_profit_price: Trigger price for take-profit
        quantity: Position quantity to close
        working_type: 'CONTRACT_PRICE' or 'MARK_PRICE'
    
    Returns:
        dict: API response containing order details
    """
    from urllib.parse import urlencode
    
    base_url = 'https://fapi.binance.com'
    endpoint = '/fapi/v1/algoOrder'
    
    # Prepare parameters (don't include signature yet)
    timestamp = int(time.time() * 1000) + getattr(client, 'timestamp_offset', 0)
    params = {
        'symbol': symbol,
        'side': side,
        'algoType': 'CONDITIONAL',  # Required for TAKE_PROFIT orders
        'type': 'TAKE_PROFIT_MARKET',
        'triggerprice': float(take_profit_price),  # Binance uses lowercase triggerprice
        'quantity': float(quantity),                # Ensure it's a float
        'reduceOnly': 'true',
        'workingType': working_type,
        'timestamp': timestamp
    }
    
    # Create query string for signature (parameters in original order, URL encoded)
    query_string = urlencode(params)
    
    # Generate signature
    signature = hmac.new(
        API_SECRET.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Add signature to params
    params['signature'] = signature
    
    # Make request
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    
    response = requests.post(
        base_url + endpoint,
        params=params,
        headers=headers,
        timeout=10
    )
    
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Algo Order API Error: {response.status_code} - {response.text}")


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
                fetch_multi_timeframe_data, symbol, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME
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
        
        # Get current position quantity
        position_info = client.futures_position_information(symbol=symbol)
        position_qty = 0
        for pos in position_info:
            qty = float(pos['positionAmt'])
            if qty != 0:
                position_qty = abs(qty)
                break
        
        if position_qty == 0:
            print(f"❌ No position found for {symbol}")
            return False
        
        position_qty = round_quantity(symbol, position_qty)
        
        # BREAKEVEN STOP LOSS: Use new Algo Order API
        stop_loss_placed = False
        
        # TRY #1: ALGO API with CONTRACT_PRICE
        try:
            sl_order = place_algo_stop_loss(
                symbol=symbol,
                side=stop_loss_side,
                stop_price=breakeven_price,
                quantity=position_qty,
                working_type='CONTRACT_PRICE'
            )
            stop_loss_placed = True
            print(f"✅ Breakeven stop-loss placed at {breakeven_price} (ALGO API/CONTRACT_PRICE): {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}")
        except Exception as sl_error_1:
            # TRY #2: ALGO API with MARK_PRICE
            try:
                sl_order = place_algo_stop_loss(
                    symbol=symbol,
                    side=stop_loss_side,
                    stop_price=breakeven_price,
                    quantity=position_qty,
                    working_type='MARK_PRICE'
                )
                stop_loss_placed = True
                print(f"✅ Breakeven stop-loss placed at {breakeven_price} (ALGO API/MARK_PRICE): {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}")
            except Exception as sl_error_2:
                print(f"❌ All methods failed to place breakeven stop-loss: {sl_error_2}")
                raise sl_error_2
        
        if not stop_loss_placed:
            print(f"❌ Failed to place breakeven stop-loss for {symbol}")
            return False
            
        return True
    except Exception as e:
        print(f"Error moving stop-loss to breakeven for {symbol}: {e}")
        return False

async def manage_atr_trailing_stop(symbol, position_obj, atr_value):
    """
    Manages an ATR-based trailing stop for a profitable position.
    """
    position_side = SIDE_BUY if float(position_obj['positionAmt']) > 0 else SIDE_SELL
    current_price = get_market_price(symbol)
    entry_price = float(position_obj['entryPrice']) # Get entry price for logging

    if not current_price:
        return

    open_orders = client.futures_get_open_orders(symbol=symbol)
    current_stop_price = None
    for order in open_orders:
        if order['type'] == 'STOP_MARKET':
            current_stop_price = float(order['stopPrice'])
            break

    print(f"--- Trailing Stop Debug for {symbol} ---")
    print(f"Position Side: {position_side}, Entry Price: {entry_price}")
    print(f"Current Market Price: {current_price}")
    print(f"Current Stop-Loss Price on Binance: {current_stop_price}")


    if current_stop_price is None:
        if VERBOSE_LOGGING:
            print(f"Could not find an existing stop-loss for {symbol} to trail.")
        return

    if position_side == SIDE_BUY:
        new_stop_price = current_price - (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        print(f"Calculated New Stop (Long): {new_stop_price}. Condition to trail: {new_stop_price > current_stop_price}")
        if new_stop_price > current_stop_price:
            print(f"✅ Trailing stop for {symbol}. New SL: {new_stop_price:.4f} (Old: {current_stop_price:.4f})")
            await update_stop_loss(symbol, new_stop_price, position_side)

    elif position_side == SIDE_SELL:
        new_stop_price = current_price + (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        print(f"Calculated New Stop (Short): {new_stop_price}. Condition to trail: {new_stop_price < current_stop_price}")
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
        
        # Get current position quantity
        position_info = client.futures_position_information(symbol=symbol)
        position_qty = 0
        for pos in position_info:
            qty = float(pos['positionAmt'])
            if qty != 0:
                position_qty = abs(qty)
                break
        
        if position_qty == 0:
            print(f"⚠️ No position found for {symbol}, cannot update stop-loss")
            return
        
        position_qty = round_quantity(symbol, position_qty)

        # TRAILING STOP LOSS: Use new Algo Order API
        stop_loss_placed = False
        
        # TRY #1: ALGO API with CONTRACT_PRICE
        try:
            sl_order = place_algo_stop_loss(
                symbol=symbol,
                side=stop_side,
                stop_price=new_stop_price_rounded,
                quantity=position_qty,
                working_type='CONTRACT_PRICE'
            )
            stop_loss_placed = True
            print(f"✅ Trailing stop updated for {symbol} to {new_stop_price_rounded} (ALGO API/CONTRACT_PRICE)")
        except Exception as sl_error_1:
            # TRY #2: ALGO API with MARK_PRICE
            try:
                sl_order = place_algo_stop_loss(
                    symbol=symbol,
                    side=stop_side,
                    stop_price=new_stop_price_rounded,
                    quantity=position_qty,
                    working_type='MARK_PRICE'
                )
                stop_loss_placed = True
                print(f"✅ Trailing stop updated for {symbol} to {new_stop_price_rounded} (ALGO API/MARK_PRICE)")
            except Exception as sl_error_2:
                print(f"❌ All methods failed to update trailing stop: {sl_error_2}")
                raise sl_error_2
        
        if not stop_loss_placed:
            print(f"⚠️ Failed to update trailing stop for {symbol}, keeping old stop-loss")

    except Exception as e:
        print(f"Error updating trailing stop for {symbol}: {e}")


def calculate_stop_limit_price(stop_price, side):
    """
    Calculate an appropriate limit price for stop-limit orders.
    For LONG positions: limit price = stop_price * 0.995 (0.5% lower to ensure execution)
    For SHORT positions: limit price = stop_price * 1.005 (0.5% higher to ensure execution)
    """
    if side == SIDE_BUY:  # LONG position, stop-loss below market
        return stop_price * 0.995
    else:  # SHORT position, stop-loss above market
        return stop_price * 1.005


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
    Places the main trade and then immediately places the corresponding stop-loss order.
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

        if stop_loss_price is None:
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
        
        stop_loss_price = round_price(symbol, stop_loss_price)
        
        stop_loss_distance = abs(limit_price - stop_loss_price)
        if stop_loss_distance == 0:
            print("Stop loss distance is zero, cannot calculate position size.")
            return False

        trade_amount_usdt = (usdt_balance * RISK_PER_TRADE) / (stop_loss_distance / limit_price)
        total_quantity = round_quantity(symbol, trade_amount_usdt / limit_price)
        
        if total_quantity <= 0 or (limit_price * total_quantity) < 5:
            print("Calculated quantity or notional value is too small to trade.")
            return False

        # Place the main market order
        import sys
        print(f"\n{'='*70}")
        print(f"📊 PLACING ORDER FOR {symbol}")
        print(f"   Side: {side}")
        print(f"   Entry Price: ${limit_price}")
        print(f"   Quantity: {total_quantity}")
        print(f"   Stop Loss: ${stop_loss_price}")
        print(f"   Risk: {(usdt_balance * (RISK_PER_TRADE if adx_value > 18 else 0.01)):.2f} USDT")
        print(f"{'='*70}")
        sys.stdout.flush()
        
        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=total_quantity
        )
        
        print(f"✅ Main order filled at ${float(order['avgPrice'])}")
        sys.stdout.flush()
        
        log_trade({
            "symbol": symbol, "USDT_balance": usdt_balance, "side": side, 
            "quantity": total_quantity, "price": float(order['avgPrice']), "reason": reason_to_open,
            "timestamp": pd.Timestamp.now().isoformat()
        })

        # --- Place the Stop-Loss Order Immediately After ---
        stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        
        print(f"\n🛡️ PLACING STOP LOSS...")
        print(f"   Type: STOP_MARKET (Algo Order API)")
        print(f"   Stop Price: ${stop_loss_price}")
        print(f"   Side: {stop_loss_side}")
        sys.stdout.flush()
        
        # STOP LOSS PLACEMENT: Try new Algo Order API first (required since Dec 9, 2025)
        stop_loss_placed = False
        sl_order = None
        
        # TRY #1: NEW ALGO ORDER API with CONTRACT_PRICE
        try:
            print(f"   Attempting: Algo Order API with CONTRACT_PRICE...")
            sys.stdout.flush()
            sl_order = place_algo_stop_loss(
                symbol=symbol,
                side=stop_loss_side,
                stop_price=stop_loss_price,
                quantity=total_quantity,
                working_type='CONTRACT_PRICE'
            )
            stop_loss_placed = True
            print(f"✅✅✅ STOP LOSS PLACED SUCCESSFULLY (ALGO API/CONTRACT_PRICE) ✅✅✅")
            print(f"   Order ID: {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}")
            sys.stdout.flush()
        except Exception as sl_error_1:
            print(f"   ⚠️ Failed with Algo API CONTRACT_PRICE: {sl_error_1}")
            sys.stdout.flush()
            
            # TRY #2: NEW ALGO ORDER API with MARK_PRICE
            try:
                print(f"   Attempting: Algo Order API with MARK_PRICE...")
                sys.stdout.flush()
                sl_order = place_algo_stop_loss(
                    symbol=symbol,
                    side=stop_loss_side,
                    stop_price=stop_loss_price,
                    quantity=total_quantity,
                    working_type='MARK_PRICE'
                )
                stop_loss_placed = True
                print(f"✅✅✅ STOP LOSS PLACED SUCCESSFULLY (ALGO API/MARK_PRICE) ✅✅✅")
                print(f"   Order ID: {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}")
                sys.stdout.flush()
            except Exception as sl_error_2:
                print(f"   ⚠️ Failed with Algo API MARK_PRICE: {sl_error_2}")
                print(f"   Note: Binance migrated STOP orders to Algo API on Dec 9, 2025")
                sys.stdout.flush()
        
        # If all stop-loss attempts failed, close the position immediately
        if not stop_loss_placed:
            print(f"\n❌❌❌ ALL STOP LOSS METHODS FAILED ❌❌❌")
            print(f"   Symbol: {symbol}")
            print(f"   Main order was placed but STOP LOSS FAILED!")
            print(f"\n🔄 CANCELLING MAIN ORDER TO PREVENT UNPROTECTED POSITION...")
            sys.stdout.flush()
            
            # TRANSACTION SAFETY: Cancel the main order if stop-loss failed
            try:
                # Close the position that was just opened
                close_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
                client.futures_create_order(
                    symbol=symbol,
                    side=close_side,
                    type=ORDER_TYPE_MARKET,
                    quantity=total_quantity,
                    reduceOnly=True
                )
                print(f"✅ Position closed successfully. No unprotected position.")
                print(f"{'='*70}\n")
                sys.stdout.flush()
            except Exception as cancel_error:
                print(f"❌❌❌ CRITICAL: FAILED TO CANCEL MAIN ORDER ❌❌❌")
                print(f"   You have an UNPROTECTED position for {symbol}!")
                print(f"   Please manually close or add stop-loss on Binance!")
                print(f"   Cancel Error: {cancel_error}")
                print(f"{'='*70}\n")
                sys.stdout.flush()
            
            return False  # Trade failed due to stop-loss issue

        # --- Place the Take-Profit Order ---
        take_profit_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        
        # Calculate take-profit price based on RR ratio
        if side == SIDE_BUY:
            take_profit_price = limit_price + (stop_loss_distance * RR_RATIO_TP1)
        else:  # SIDE_SELL
            take_profit_price = limit_price - (stop_loss_distance * RR_RATIO_TP1)
        
        take_profit_price = round_price(symbol, take_profit_price)
        
        print(f"\n💰 PLACING TAKE PROFIT...")
        print(f"   Type: TAKE_PROFIT_MARKET (Algo Order API)")
        print(f"   TP Price: ${take_profit_price}")
        print(f"   Side: {take_profit_side}")
        print(f"   Risk-Reward Ratio: {RR_RATIO_TP1}:1")
        sys.stdout.flush()
        
        # TAKE PROFIT PLACEMENT: Use new Algo Order API (required since Dec 9, 2025)
        try:
            print(f"   Attempting: Algo Order API with CONTRACT_PRICE...")
            sys.stdout.flush()
            tp_order = place_algo_take_profit(
                symbol=symbol,
                side=take_profit_side,
                take_profit_price=take_profit_price,
                quantity=total_quantity,
                working_type='CONTRACT_PRICE'
            )
            print(f"✅✅✅ TAKE PROFIT PLACED SUCCESSFULLY (ALGO API/CONTRACT_PRICE) ✅✅✅")
            print(f"   Order ID: {tp_order.get('orderId', tp_order.get('algoId', 'N/A'))}")
            print(f"{'='*70}\n")
            sys.stdout.flush()
        except Exception as tp_error:
            print(f"   ⚠️ Failed with Algo API CONTRACT_PRICE: {tp_error}")
            sys.stdout.flush()
            
            # TRY #2: Algo API with MARK_PRICE
            try:
                print(f"   Attempting: Algo Order API with MARK_PRICE...")
                sys.stdout.flush()
                tp_order = place_algo_take_profit(
                    symbol=symbol,
                    side=take_profit_side,
                    take_profit_price=take_profit_price,
                    quantity=total_quantity,
                    working_type='MARK_PRICE'
                )
                print(f"✅✅✅ TAKE PROFIT PLACED SUCCESSFULLY (ALGO API/MARK_PRICE) ✅✅✅")
                print(f"   Order ID: {tp_order.get('orderId', tp_order.get('algoId', 'N/A'))}")
                print(f"{'='*70}\n")
                sys.stdout.flush()
            except Exception as tp_error_2:
                print(f"⚠️⚠️⚠️ FAILED TO PLACE TAKE PROFIT ⚠️⚠️⚠️")
                print(f"   Symbol: {symbol}")
                print(f"   Stop loss is active but NO TAKE PROFIT!")
                print(f"   Error: {tp_error_2}")
                print(f"{'='*70}\n")
                sys.stdout.flush()
                # Continue anyway - stop loss is more critical
        
        return True

    except Exception as e:
        print(f"\n❌❌❌ EXCEPTION IN PLACE_ORDER ❌❌❌")
        print(f"Symbol: {symbol}")
        print(f"Error: {e}")
        print(f"Error Type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print(f"{'='*70}\n")
        sys.stdout.flush()
        return False

def close_position(symbol, side, quantity, reason_to_close):
    try:
        # First, get the position info to retrieve entry price
        position_info = client.futures_position_information(symbol=symbol)
        entry_price = 0
        
        # Find the correct position (LONG or SHORT)
        for pos in position_info:
            if float(pos['positionAmt']) != 0:
                entry_price = float(pos['entryPrice'])
                break
        
        # Execute the close order
        order = client.futures_create_order(
            symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=quantity, reduceOnly=True
        )
        
        exit_price = float(order['avgPrice'])
        new_usdt_balance = get_usdt_balance()
        
        # Calculate PnL and ROI
        # For LONG positions, we close with SELL
        # For SHORT positions, we close with BUY
        if side == SIDE_SELL:  # Closing a LONG position
            pnl = (exit_price - entry_price) * float(quantity)
            position_side = "BUY"
        else:  # Closing a SHORT position (side == SIDE_BUY)
            pnl = (entry_price - exit_price) * float(quantity)
            position_side = "SELL"
        
        # Calculate ROI (assume 10x leverage for ROI calculation)
        # ROI = (PnL / Initial Margin) * 100
        # Initial Margin = (Entry Price * Quantity) / Leverage
        leverage = 10  # You can get this from position_info if needed
        initial_margin = (entry_price * float(quantity)) / leverage
        roi = (pnl / initial_margin * 100) if initial_margin > 0 else 0
        
        # Log to JSON file (existing functionality)
        log_trade({
            "symbol": symbol, "new_USDT_balance": new_usdt_balance,
            "closing_side": side, "closing_quantity": quantity,
            "closing_price": exit_price, "reason_to_close": reason_to_close,
            "timestamp": pd.Timestamp.now().isoformat()
        })
        
        # Log to CSV file with PnL and ROI for dashboard
        log_trade_exit(
            symbol=symbol,
            side=position_side,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=float(quantity),
            pnl=pnl,
            exit_reason=reason_to_close,
            roi=roi
        )
        
        print(f"✅ Position closed for {symbol}. PnL: ${pnl:.2f}, ROI: {roi:.2f}%")
        
    except Exception as e:
        print(f"Error closing position: {e}")      
        
async def set_margin_type(symbol, margin_type='ISOLATED'):
    """
    Sets the margin type for a symbol.
    """
    try:
        position_info = client.futures_position_information(symbol=symbol)
        
        if position_info:
            current_margin_type = position_info[0]['marginType']
            if current_margin_type.lower() != margin_type.lower():
                client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
                if VERBOSE_LOGGING:
                    print(f"Margin type for {symbol} set to {margin_type}.")
        else:
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