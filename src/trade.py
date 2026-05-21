import os
import json
import time
import pandas as pd
import hmac
import hashlib
import requests
import asyncio
import sys
from urllib.parse import urlencode
from binance.enums import (
    SIDE_BUY, 
    SIDE_SELL, 
    ORDER_TYPE_MARKET
)

from config.paths import LOG_FILE
from config.secrets import API_KEY, API_SECRET
from config.settings import VERBOSE_LOGGING, TRAILING_STOP_ATR_MULTIPLIER, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME, LEVERAGE, BINANCE_FEE_RATE

from data.get_data import get_market_price, round_price, round_quantity, get_usdt_balance, fetch_multi_timeframe_data
from data.indicators import calculate_atr
from src.detailed_logger import log_trade_exit

from config.client import client


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
        'closePosition': 'true',            # Must use closePosition for full exit to avoid matching engine cancellation
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
        'closePosition': 'true',                    # Must use closePosition for full exit to avoid matching engine cancellation
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


def cancel_algo_stop_loss_orders(symbol):
    """
    Finds and cancels only STOP_MARKET Algo Orders for a specific symbol.
    Leaves TAKE_PROFIT_MARKET Algo Orders alone.
    """
    _cancel_algo_orders_by_type(symbol, target_types=('STOP_MARKET', 'ALGO'), label='Stop Loss')

def cancel_algo_take_profit_orders(symbol):
    """
    Finds and cancels only TAKE_PROFIT_MARKET Algo Orders for a specific symbol.
    Prevents orphan TP orders from surviving after a position is closed.
    """
    _cancel_algo_orders_by_type(symbol, target_types=('TAKE_PROFIT_MARKET',), label='Take Profit')

def _cancel_algo_orders_by_type(symbol, target_types, label=''):
    """
    Internal helper: fetches open Algo Orders and cancels those matching target_types.
    """
    
    base_url = 'https://fapi.binance.com'
    endpoint = '/fapi/v1/openAlgoOrders'
    
    timestamp = int(time.time() * 1000) + getattr(client, 'timestamp_offset', 0)
    params = {'symbol': symbol, 'timestamp': timestamp}
    query_string = urlencode(params)
    signature = hmac.new(API_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    params['signature'] = signature
    headers = {'X-MBX-APIKEY': API_KEY}
    
    # 1. Get all open Algo Orders
    try:
        response = requests.get(base_url + endpoint, params=params, headers=headers, timeout=10)
        if response.status_code == 200:
            algo_orders = response.json()
            if 'orders' in algo_orders:
                algo_orders = algo_orders['orders'] # Depending on Binance API version wrapper
            elif isinstance(algo_orders, dict) and 'items' in algo_orders:
                algo_orders = algo_orders['items']
                
            if not isinstance(algo_orders, list):
                # Safe fallback if format is unexpected
                return
                
            # 2. Cancel only the matching types
            cancel_endpoint = '/fapi/v1/algoOrder'
            for order in algo_orders:
                if order.get('type') in target_types:
                    cancel_params = {
                        'symbol': symbol,
                        'algoId': order.get('algoId'),
                        'timestamp': int(time.time() * 1000) + getattr(client, 'timestamp_offset', 0)
                    }
                    cancel_qs = urlencode(cancel_params)
                    cancel_sig = hmac.new(API_SECRET.encode('utf-8'), cancel_qs.encode('utf-8'), hashlib.sha256).hexdigest()
                    cancel_params['signature'] = cancel_sig
                    
                    requests.delete(base_url + cancel_endpoint, params=cancel_params, headers=headers, timeout=10)
    except Exception as e:
        print(f"Error checking/canceling Algo {label} for {symbol}: {e}")

async def manage_active_trades(active_positions):
    """
    Loop through active positions to manage ATR trailing stops for profitable trades.
    """
    if len(active_positions) > 0 and VERBOSE_LOGGING:
        # Avoid duplicate console logging (main.py already prints this)
        pass
    for position_obj in active_positions:
        symbol = position_obj['symbol']
        unrealized_profit = float(position_obj.get('unrealizedProfit', 0))

        if unrealized_profit > 0:
            print(f"✅ Position for {symbol} is profitable. Managing ATR trailing stop.")
            
            # fetch_multi_timeframe_data returns 11 values — unpack all of them
            df_15m, _, _, _, _, _, _, _, _, _, _ = await asyncio.to_thread(
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
        position_info = await asyncio.to_thread(client.futures_position_information, symbol=symbol)
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
            sl_order = await asyncio.to_thread(
                place_algo_stop_loss,
                symbol,
                stop_loss_side,
                breakeven_price,
                position_qty,
                'CONTRACT_PRICE'
            )
            stop_loss_placed = True
            print(f"✅ Breakeven stop-loss placed at {breakeven_price} (ALGO API/CONTRACT_PRICE): {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}")
        except Exception as sl_error_1:
            # TRY #2: ALGO API with MARK_PRICE
            try:
                sl_order = await asyncio.to_thread(
                    place_algo_stop_loss,
                    symbol,
                    stop_loss_side,
                    breakeven_price,
                    position_qty,
                    'MARK_PRICE'
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
    current_price = await asyncio.to_thread(get_market_price, symbol)
    entry_price = float(position_obj['entryPrice']) # Get entry price for logging

    if not current_price:
        return

    open_orders = await asyncio.to_thread(client.futures_get_open_orders, symbol=symbol)
    current_stop_price = None
    for order in open_orders:
        if order['type'] in ('STOP_MARKET', 'ALGO'):
            current_stop_price = float(order['stopPrice'])
            break
            
    # If not found in standard orders, check Algo Orders
    if current_stop_price is None:
        from config.settings import API_KEY, API_SECRET
        
        base_url = 'https://fapi.binance.com'
        endpoint = '/fapi/v1/openAlgoOrders'
        
        timestamp = int(time.time() * 1000) + getattr(client, 'timestamp_offset', 0)
        params = {'symbol': symbol, 'timestamp': timestamp}
        query_string = urlencode(params)
        signature = hmac.new(API_SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
        params['signature'] = signature
        headers = {'X-MBX-APIKEY': API_KEY}
        
        def fetch_algo():
            return requests.get(base_url + endpoint, params=params, headers=headers, timeout=10)
            
        try:
            response = await asyncio.to_thread(fetch_algo)
            if response.status_code == 200:
                algo_orders = response.json()
                if 'orders' in algo_orders:
                    algo_orders = algo_orders['orders']
                elif isinstance(algo_orders, dict) and 'items' in algo_orders:
                    algo_orders = algo_orders['items']
                    
                if isinstance(algo_orders, list):
                    for order in algo_orders:
                        order_type = order.get('type', '')
                        if order_type in ('STOP_MARKET', 'ALGO') or 'STOP' in order_type:
                            # Try all known field names for the trigger price
                            current_stop_price = float(
                                order.get('stopPrice',
                                order.get('triggerprice',
                                order.get('triggerPrice',
                                order.get('price', 0))))
                            )
                            break
        except Exception as e:
            if VERBOSE_LOGGING:
                print(f"Could not fetch algo orders for trailing stop on {symbol}: {e}")

    if current_stop_price is None or current_stop_price == 0:
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
        # 1. Cancel standard stop market orders (legacy)
        open_orders = await asyncio.to_thread(client.futures_get_open_orders, symbol=symbol)
        for order in open_orders:
            if order['type'] in ('STOP_MARKET', 'ALGO'):
                await asyncio.to_thread(client.futures_cancel_order, symbol=symbol, orderId=order['orderId'])

        # 2. Cancel ALGO stop market orders (new Binance logic)
        # MUST wrap in to_thread because cancel_algo_stop_loss_orders uses blocking requests
        await asyncio.to_thread(cancel_algo_stop_loss_orders, symbol)
        stop_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        new_stop_price_rounded = round_price(symbol, new_stop_price)
        
        # Get current position quantity
        position_info = await asyncio.to_thread(client.futures_position_information, symbol=symbol)
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
            sl_order = await asyncio.to_thread(
                place_algo_stop_loss,
                symbol,
                stop_side,
                new_stop_price_rounded,
                position_qty,
                'CONTRACT_PRICE'
            )
            stop_loss_placed = True
            print(f"✅ Trailing stop updated for {symbol} to {new_stop_price_rounded} (ALGO API/CONTRACT_PRICE)")
        except Exception as sl_error_1:
            # TRY #2: ALGO API with MARK_PRICE
            try:
                sl_order = await asyncio.to_thread(
                    place_algo_stop_loss,
                    symbol,
                    stop_side,
                    new_stop_price_rounded,
                    position_qty,
                    'MARK_PRICE'
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


import threading
_log_trade_lock = threading.Lock()

def log_trade(data):
    with _log_trade_lock:
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
        # If we need to cancel both, use the official Binance "nuke" command 
        # which guarantees removal of ALL standard and ALGO orders.
        if cancel_sl and cancel_tp:
            await asyncio.to_thread(client.futures_cancel_all_open_orders, symbol=symbol)
            return

        # Fallback for partial cancellation (used only during breakeven adjustment)
        open_orders = await asyncio.to_thread(client.futures_get_open_orders, symbol=symbol)
        
        if open_orders:
            for order in open_orders:
                order_type = order['type']
                should_cancel = (cancel_sl and 'STOP' in order_type) or \
                                (cancel_tp and 'PROFIT' in order_type)
                
                if should_cancel:
                    await asyncio.to_thread(client.futures_cancel_order, symbol=symbol, orderId=order['orderId'])
                    
        # ALGO ORDERS FALLBACK: Since the above API does not see ALGO orders, we must manually query and cancel them
        if cancel_sl:
            await asyncio.to_thread(cancel_algo_stop_loss_orders, symbol)
        if cancel_tp:
            await asyncio.to_thread(cancel_algo_take_profit_orders, symbol)
            
    except Exception as e:
        print(f"Error canceling open orders for {symbol}: {e}")

async def place_order(symbol, side, usdt_balance, reason_to_open, support_4h, resistance_4h, adx_value, reduce_only=False, stop_loss_atr_multiplier=2.0, atr_value=None, df=None, stop_loss_price=None, take_profit_price=None):
    """
    Places the main trade and then immediately places the corresponding stop-loss order.
    """
    # Check Order Book Imbalance before proceeding
    try:
        order_book = await asyncio.to_thread(client.futures_order_book, symbol=symbol, limit=50)
        current_price = await asyncio.to_thread(get_market_price, symbol)
        if current_price:
            bids = sum(float(qty) for price, qty in order_book['bids'] if float(price) >= current_price * 0.99)
            asks = sum(float(qty) for price, qty in order_book['asks'] if float(price) <= current_price * 1.01)
            
            if bids > 0 and asks > 0:
                from src.detailed_logger import log_rejected_signal
                if side == SIDE_BUY and asks > bids * 3:
                    print(f"\n⛔ Trade aborted for {symbol}: Massive Sell Wall detected (Asks: {asks:.2f} vs Bids: {bids:.2f})")
                    log_rejected_signal(symbol, side, {}, f"Order Book: Sell Wall (Asks: {asks:.2f} > Bids: {bids:.2f})")
                    return False
                elif side == SIDE_SELL and bids > asks * 3:
                    print(f"\n⛔ Trade aborted for {symbol}: Massive Buy Wall detected (Bids: {bids:.2f} vs Asks: {asks:.2f})")
                    log_rejected_signal(symbol, side, {}, f"Order Book: Buy Wall (Bids: {bids:.2f} > Asks: {asks:.2f})")
                    return False
    except Exception as ob_error:
        print(f"Order book check failed, proceeding anyway. Error: {ob_error}")

    from config.settings import BASE_RISK_PER_TRADE, MED_RISK_PER_TRADE, HIGH_RISK_PER_TRADE, DEFAULT_RR_RATIO_TP1, MIN_NOTIONAL
    if adx_value > 25:
        RISK_PER_TRADE = HIGH_RISK_PER_TRADE
    elif adx_value > 18:
        RISK_PER_TRADE = MED_RISK_PER_TRADE
    else:
        RISK_PER_TRADE = BASE_RISK_PER_TRADE

    RR_RATIO_TP1 = DEFAULT_RR_RATIO_TP1

    try:
        # set_margin_type will cancel all open orders to avoid -4067 error
        await set_margin_type(symbol, margin_type='ISOLATED')

        price = await asyncio.to_thread(get_market_price, symbol)
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
        
        # --- NEW: Max Margin Allocation Cap ---
        # The maximum allowed base margin collateral for this single trade
        from config.settings import MAX_MARGIN_PER_TRADE_PERCENT
        max_allowed_margin = usdt_balance * MAX_MARGIN_PER_TRADE_PERCENT
        max_allowed_notional = max_allowed_margin * LEVERAGE
        
        if trade_amount_usdt > max_allowed_notional:
            print(f"⚠️  ATR sizing demands ${trade_amount_usdt/LEVERAGE:.2f} in margin, capping to max allowed (${max_allowed_margin:.2f}).")
            trade_amount_usdt = max_allowed_notional
            
        total_quantity = round_quantity(symbol, trade_amount_usdt / limit_price)
        
        # Binance Futures minimum notional is generally $5, setting to MIN_NOTIONAL to be safe for slippage
        notional_value = limit_price * total_quantity

        if total_quantity <= 0 or notional_value < MIN_NOTIONAL:
            print(f"❌ Calculated notional value (${notional_value:.2f}) is below Binance minimum (${MIN_NOTIONAL})")
            print(f"   Quantity: {total_quantity}, Price: ${limit_price}")
            print(f"   Increase account balance or risk percentage to meet minimum order size.")
            from src.detailed_logger import log_rejected_signal
            log_rejected_signal(symbol, side, {'Price': limit_price, 'Quantity': total_quantity}, f"Insufficient Funds (Notional ${notional_value:.2f} < Min ${MIN_NOTIONAL})")
            return False

        # --- Pre-flight: Check if we have enough available margin ---
        # Required margin = notional_value / leverage
        # This prevents the -2019 "Margin is insufficient" crash
        required_margin = notional_value / LEVERAGE
        available_balance = usdt_balance  # This is the available (free) balance
        if required_margin > available_balance * 0.90:  # Leave 10% buffer for fees + slippage
            print(f"❌ Insufficient margin for {symbol}: Need ${required_margin:.2f}, Available: ${available_balance:.2f}")
            from src.detailed_logger import log_rejected_signal
            log_rejected_signal(symbol, side, {'Price': limit_price, 'Required_Margin': required_margin, 'Available': available_balance}, f"Insufficient Margin (${required_margin:.2f} > 90% of ${available_balance:.2f})")
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
        
        order = await asyncio.to_thread(
            client.futures_create_order,
            symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=total_quantity
        )
        
        print(f"✅ Main order filled at ${float(order['avgPrice'])}")
        sys.stdout.flush()
        
        # Use limit_price as fallback when Binance returns avgPrice='0' for async market fills
        logged_price = float(order.get('avgPrice', 0)) or limit_price
        log_trade({
            "symbol": symbol, "USDT_balance": usdt_balance, "side": side, 
            "quantity": total_quantity, "price": logged_price, "reason": reason_to_open,
            "timestamp": pd.Timestamp.now().isoformat()
        })
        
        # Track entry timestamp for time-based exits
        from src.state_manager import bot_state
        bot_state.entry_timestamps[symbol] = time.time()

        # --- Place the Stop-Loss Order Immediately After ---
        stop_loss_side = SIDE_SELL if side == SIDE_BUY else SIDE_BUY
        
        print(f"\n╭───────────────────────────────────────────────────╮")
        print(f"│ 🛡️  SECURING CAPITAL: STOP LOSS DEPLOYMENT        │")
        print(f"╰───────────────────────────────────────────────────╯")
        print(f"  ▶ Engine:   Algo Order API (STOP_MARKET)")
        print(f"  ▶ Target:   ${stop_loss_price}")
        print(f"  ▶ Action:   {stop_loss_side}")
        sys.stdout.flush()
        
        # STOP LOSS PLACEMENT: Try new Algo Order API first (required since Dec 9, 2025)
        stop_loss_placed = False
        sl_order = None
        
        # TRY #1: NEW ALGO ORDER API with CONTRACT_PRICE
        try:
            print(f"   Attempting: Algo Order API with CONTRACT_PRICE...")
            sys.stdout.flush()
            sl_order = await asyncio.to_thread(
                place_algo_stop_loss,
                symbol,
                stop_loss_side,
                stop_loss_price,
                total_quantity,
                'CONTRACT_PRICE'
            )
            stop_loss_placed = True
            print(f"  ───────────────────────────────────────────────────")
            print(f"  ✅ STOP LOSS DEPLOYED [CONTRACT_PRICE | ID: {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}]")
            sys.stdout.flush()
        except Exception as sl_error_1:
            print(f"   ⚠️ Failed with Algo API CONTRACT_PRICE: {sl_error_1}")
            sys.stdout.flush()
            
            # TRY #2: NEW ALGO ORDER API with MARK_PRICE
            try:
                print(f"   Attempting: Algo Order API with MARK_PRICE...")
                sys.stdout.flush()
                sl_order = await asyncio.to_thread(
                    place_algo_stop_loss,
                    symbol,
                    stop_loss_side,
                    stop_loss_price,
                    total_quantity,
                    'MARK_PRICE'
                )
                stop_loss_placed = True
                print(f"  ───────────────────────────────────────────────────")
                print(f"  ✅ STOP LOSS DEPLOYED [MARK_PRICE | ID: {sl_order.get('orderId', sl_order.get('algoId', 'N/A'))}]")
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
                await asyncio.to_thread(
                    client.futures_create_order,
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
        
        # Calculate take-profit price based on RR ratio if not provided dynamically
        if take_profit_price is None:
            if side == SIDE_BUY:
                take_profit_price = limit_price + (stop_loss_distance * RR_RATIO_TP1)
            else:  # SIDE_SELL
                take_profit_price = limit_price - (stop_loss_distance * RR_RATIO_TP1)
                
            print(f"   Risk-Reward Ratio: {RR_RATIO_TP1}:1")
        else:
            # --- Safety check: Dynamic TP must deliver at least 1:1 R:R ---
            # If the Fibonacci target is too close to entry, the fees alone
            # will wipe out the profit. Override with 1.5x R:R fallback.
            tp_distance = abs(take_profit_price - limit_price)
            if tp_distance < stop_loss_distance:
                print(f"   \u26a0\ufe0f Dynamic TP ${take_profit_price} is too close (R:R < 1:1) — overriding with 1.5x R:R")
                if side == SIDE_BUY:
                    take_profit_price = limit_price + (stop_loss_distance * RR_RATIO_TP1)
                else:
                    take_profit_price = limit_price - (stop_loss_distance * RR_RATIO_TP1)
                print(f"   \u2705 Safe TP: ${take_profit_price}")
            else:
                print(f"   Target: Dynamic Institutional Level")
        
        take_profit_price = round_price(symbol, take_profit_price)
        
        # --- Pre-flight check: Prevent "Order would immediately trigger" (-2021) ---
        # If the market already blew past the TP target before we placed it,
        # Binance will reject with -2021. Detect this and recalculate a safe TP.
        current_market = await asyncio.to_thread(get_market_price, symbol)
        if current_market:
            tp_would_trigger = False
            if side == SIDE_BUY and take_profit_price <= current_market:
                tp_would_trigger = True
            elif side == SIDE_SELL and take_profit_price >= current_market:
                tp_would_trigger = True
            
            if tp_would_trigger:
                print(f"   ⚠️ TP ${take_profit_price} already past market ${current_market} — recalculating...")
                # Fallback: use 1.5x R:R from current price instead
                if side == SIDE_BUY:
                    take_profit_price = round_price(symbol, current_market + (stop_loss_distance * RR_RATIO_TP1))
                else:
                    take_profit_price = round_price(symbol, current_market - (stop_loss_distance * RR_RATIO_TP1))
                print(f"   ✅ Recalculated TP: ${take_profit_price}")
                sys.stdout.flush()
        
        print(f"\n╭───────────────────────────────────────────────────╮")
        print(f"│ 🎯 LOCKING TARGET: TAKE PROFIT DEPLOYMENT         │")
        print(f"╰───────────────────────────────────────────────────╯")
        print(f"  ▶ Engine:   Algo Order API (TAKE_PROFIT_MARKET)")
        print(f"  ▶ Target:   ${take_profit_price}")
        print(f"  ▶ Action:   {take_profit_side}")
        sys.stdout.flush()
        
        # TAKE PROFIT PLACEMENT: Use new Algo Order API (required since Dec 9, 2025)
        try:
            print(f"   Attempting: Algo Order API with CONTRACT_PRICE...")
            sys.stdout.flush()
            tp_order = await asyncio.to_thread(
                place_algo_take_profit,
                symbol,
                take_profit_side,
                take_profit_price,
                total_quantity,
                'CONTRACT_PRICE'
            )
            print(f"  ───────────────────────────────────────────────────")
            print(f"  ✅ TAKE PROFIT DEPLOYED [CONTRACT_PRICE | ID: {tp_order.get('orderId', tp_order.get('algoId', 'N/A'))}]")
            print(f"\n🚀 TRADE FULLY SECURED AND LIVE. AWAITING MARKET REACTION.")
            print(f"{'='*70}\n")
            sys.stdout.flush()
        except Exception as tp_error:
            print(f"   ⚠️ Failed with Algo API CONTRACT_PRICE: {tp_error}")
            sys.stdout.flush()
            
            # TRY #2: Algo API with MARK_PRICE
            try:
                print(f"   Attempting: Algo Order API with MARK_PRICE...")
                sys.stdout.flush()
                tp_order = await asyncio.to_thread(
                    place_algo_take_profit,
                    symbol,
                    take_profit_side,
                    take_profit_price,
                    total_quantity,
                    'MARK_PRICE'
                )
                print(f"  ───────────────────────────────────────────────────")
                print(f"  ✅ TAKE PROFIT DEPLOYED [MARK_PRICE | ID: {tp_order.get('orderId', tp_order.get('algoId', 'N/A'))}]")
                print(f"\n🚀 TRADE FULLY SECURED AND LIVE. AWAITING MARKET REACTION.")
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
        # Fetch a fresh balance after closing — get_usdt_balance requires balance_data arg
        _balance_data = client.futures_account_balance()
        new_usdt_balance = get_usdt_balance(_balance_data)
        
        # Calculate PnL and ROI
        # For LONG positions, we close with SELL
        # For SHORT positions, we close with BUY
        if side == SIDE_SELL:  # Closing a LONG position
            gross_pnl = (exit_price - entry_price) * float(quantity)
            position_side = "LONG"
        else:  # Closing a SHORT position (side == SIDE_BUY)
            gross_pnl = (entry_price - exit_price) * float(quantity)
            position_side = "SHORT"
            
        # Binance Futures Market Taker Fee — configured in settings.py
        # We pay this twice (once to open, once to close) because we use Market Orders.
        # NOTE (Fix #3): Even on partial closes, we calculate the entry fee based on the 
        # *closing* quantity. This correctly apportions the entry fee across the partial exits.
        total_fees = (entry_price * float(quantity) * BINANCE_FEE_RATE) + (exit_price * float(quantity) * BINANCE_FEE_RATE)
        
        pnl = gross_pnl - total_fees
        
        # Update Daily PnL Tracker (thread-safe: close_position runs via asyncio.to_thread)
        from src.state_manager import bot_state
        with bot_state._pnl_lock:
            bot_state.daily_pnl += pnl
        
        # Calculate ROI using the configured LEVERAGE (imported from settings)
        # ROI = (PnL / Initial Margin) * 100
        # Initial Margin = (Entry Price * Quantity) / Leverage
        initial_margin = (entry_price * float(quantity)) / LEVERAGE
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
        
        print(f"✅ Position closed for {symbol}. Gross: ${gross_pnl:.2f} | Fees: ${total_fees:.2f} | Net PnL: ${pnl:.2f} | ROI: {roi:.2f}%")
        
    except Exception as e:
        print(f"Error closing position: {e}")      
        
async def set_margin_type(symbol, margin_type='ISOLATED'):
    """
    Sets the margin type for a symbol.
    Only cancels open orders if a margin type change is actually required,
    to avoid wiping stop-losses on other positions (API error -4067 only
    occurs when orders exist and margin type is being changed).
    """
    try:
        position_info = await asyncio.to_thread(client.futures_position_information, symbol=symbol)
        
        if position_info:
            current_margin_type = position_info[0]['marginType']
            if current_margin_type.lower() == margin_type.lower():
                # Already correct — do NOT cancel orders
                return
        
        # Margin type change is needed — cancel orders first to avoid -4067
        open_orders = await asyncio.to_thread(client.futures_get_open_orders, symbol=symbol)
        if open_orders:
            print(f"⚠️ Margin type change needed for {symbol}. Cancelling {len(open_orders)} order(s)...")
            for order in open_orders:
                try:
                    await asyncio.to_thread(client.futures_cancel_order, symbol=symbol, orderId=order['orderId'])
                except Exception as cancel_error:
                    print(f"   ⚠️ Failed to cancel order {order.get('orderId', 'N/A')}: {cancel_error}")
        
        await asyncio.to_thread(client.futures_change_margin_type, symbol=symbol, marginType=margin_type)
        if VERBOSE_LOGGING:
            print(f"Margin type for {symbol} set to {margin_type}.")

    except Exception as e:
        if "No need to change margin type" not in str(e):
            print(f"Error setting margin type for {symbol}: {e}")