from binance.enums import *
from src.trade import close_position, cancel_open_orders, move_stop_to_breakeven
from data.indicators import *
from config.settings import *
from src.state_manager import bot_state

async def close_position_long(symbol, position, roi, df, stoch_k, stoch_d, resistance, atr_value, entry_price):
    reason = None
    last_close = df['close'].iloc[-1]
    
    # === PHASE 1 IMPROVEMENT: Partial Profit Taking ===
    if ENABLE_PARTIAL_PROFITS:
        # Calculate R (Risk) based on stop loss distance
        # First, we need to get the position info to calculate actual R:R
        from binance.client import Client
        from config.secrets import API_KEY, API_SECRET
        from data.get_data import round_quantity
        import time
        client = Client(API_KEY, API_SECRET)
        # Sync time with Binance servers
        try:
            server_time = client.get_server_time()
            local_time = int(time.time() * 1000)
            time_offset = server_time['serverTime'] - local_time
            client.timestamp_offset = time_offset
        except Exception:
            pass
        
        # Take 50% profit at 2R (2:1 Risk/Reward)
        if roi >= PARTIAL_TP1_RR and not bot_state.partial_tp1_taken.get(symbol, False):
            try:
                partial_size = abs(position) * PARTIAL_TP1_SIZE
                partial_size = round_quantity(symbol, partial_size)
                if partial_size > 0:
                    print(f"💰 Taking {PARTIAL_TP1_SIZE*100}% profit at {roi:.2f}% ROI ({PARTIAL_TP1_RR}R) for {symbol}")
                    client.futures_create_order(
                        symbol=symbol, 
                        side=SIDE_SELL, 
                        type=ORDER_TYPE_MARKET, 
                        quantity=partial_size, 
                        reduceOnly=True
                    )
                    bot_state.partial_tp1_taken[symbol] = True
            except Exception as e:
                print(f"Error taking partial profit 1 for {symbol}: {e}")
        
        # Take 25% of remaining (which is 25% of original) at 3R
        if roi >= PARTIAL_TP2_RR and bot_state.partial_tp1_taken.get(symbol, False) and not bot_state.partial_tp2_taken.get(symbol, False):
            try:
                # 25% of the remaining 50% = 0.25 * 0.5 = 0.125 of original position
                partial_size = abs(position) * PARTIAL_TP2_SIZE
                partial_size = round_quantity(symbol, partial_size)
                if partial_size > 0:
                    print(f"💰 Taking {PARTIAL_TP2_SIZE*100}% profit at {roi:.2f}% ROI ({PARTIAL_TP2_RR}R) for {symbol}")
                    client.futures_create_order(
                        symbol=symbol, 
                        side=SIDE_SELL, 
                        type=ORDER_TYPE_MARKET, 
                        quantity=partial_size, 
                        reduceOnly=True
                    )
                    bot_state.partial_tp2_taken[symbol] = True
            except Exception as e:
                print(f"Error taking partial profit 2 for {symbol}: {e}")
    
    # --- BREAKEVEN LOGIC ---
    BREAKEVEN_ROI_THRESHOLD = 1.5 # Move to breakeven at 1.5% ROI
    
    if roi >= BREAKEVEN_ROI_THRESHOLD and not bot_state.breakeven_triggered.get(symbol):
        print(f"✅ ROI for {symbol} hit {roi:.2f}%. Moving stop-loss to breakeven.")
        if await move_stop_to_breakeven(symbol, entry_price, SIDE_BUY):
            bot_state.breakeven_triggered[symbol] = True

    # --- TIER 1 EXIT CONDITIONS ---
    import time
    
    # 1. Time-Based Exit
    if ENABLE_TIME_BASED_EXIT:
        entry_time = bot_state.entry_timestamps.get(symbol)
        if entry_time:
            hours_held = (time.time() - entry_time) / 3600
            if hours_held >= MAX_HOLD_TIME_HOURS:
                reason = f"Time-Based Exit: Position held for {hours_held:.1f} hours (max: {MAX_HOLD_TIME_HOURS}h). Freeing up capital."
    
    # 2. Funding Rate Exit
    if not reason and ENABLE_FUNDING_RATE_EXIT:
        from data.get_data import get_funding_rate
        current_funding_rate = get_funding_rate(symbol)
        if current_funding_rate > MAX_FUNDING_RATE_LONG:
            reason = f"Funding Rate Exit: Current funding rate {current_funding_rate*100:.3f}% exceeds threshold {MAX_FUNDING_RATE_LONG*100:.3f}%. Overcrowded long position."
    
    # 3. Maximum Drawdown Limit
    if not reason and ENABLE_MAX_DRAWDOWN_EXIT:
        if roi <= EMERGENCY_EXIT_ROI:
            reason = f"Emergency Exit: ROI at {roi:.2f}% reached emergency threshold of {EMERGENCY_EXIT_ROI}%. Cutting losses early."

    # --- PRIMARY EXIT: Market Structure Break ---
    lookback_period = 10 
    recent_swing_low = df['low'].iloc[-lookback_period:-1].min()

    if last_close < recent_swing_low:
        reason = f"Exit Signal: Price broke market structure by closing below the recent swing low of ${recent_swing_low:.4f}."

    # --- SECONDARY EXIT: Profit-Taking in Extreme Conditions ---
    stoch_crossed_down = stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-2] >= stoch_d.iloc[-2]
    if stoch_k.iloc[-1] > 90 and stoch_crossed_down and not reason:
        reason = f"Profit Take: Stochastic crossed down in extreme overbought zone ({stoch_k.iloc[-1]:.2f})."

    if reason:
        print(f"Closing long position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_SELL, abs(position), reason)
        # Reset all state trackers for this symbol
        bot_state.breakeven_triggered.pop(symbol, None)
        bot_state.partial_tp1_taken.pop(symbol, None)
        bot_state.partial_tp2_taken.pop(symbol, None)
        bot_state.entry_timestamps.pop(symbol, None)
        return True

    return False

async def close_position_short(symbol, position, roi, df, stoch_k, stoch_d, support, atr_value, entry_price):
    reason = None
    last_close = df['close'].iloc[-1]

    # === PHASE 1 IMPROVEMENT: Partial Profit Taking ===
    if ENABLE_PARTIAL_PROFITS:
        from binance.client import Client
        from config.secrets import API_KEY, API_SECRET
        from data.get_data import round_quantity
        import time
        client = Client(API_KEY, API_SECRET)
        # Sync time with Binance servers
        try:
            server_time = client.get_server_time()
            local_time = int(time.time() * 1000)
            time_offset = server_time['serverTime'] - local_time
            client.timestamp_offset = time_offset
        except Exception:
            pass
        
        # Take 50% profit at 2R (2:1 Risk/Reward)
        if roi >= PARTIAL_TP1_RR and not bot_state.partial_tp1_taken.get(symbol, False):
            try:
                partial_size = abs(position) * PARTIAL_TP1_SIZE
                partial_size = round_quantity(symbol, partial_size)
                if partial_size > 0:
                    print(f"💰 Taking {PARTIAL_TP1_SIZE*100}% profit at {roi:.2f}% ROI ({PARTIAL_TP1_RR}R) for {symbol}")
                    client.futures_create_order(
                        symbol=symbol, 
                        side=SIDE_BUY, 
                        type=ORDER_TYPE_MARKET, 
                        quantity=partial_size, 
                        reduceOnly=True
                    )
                    bot_state.partial_tp1_taken[symbol] = True
            except Exception as e:
                print(f"Error taking partial profit 1 for {symbol}: {e}")
        
        # Take 25% of remaining at 3R
        if roi >= PARTIAL_TP2_RR and bot_state.partial_tp1_taken.get(symbol, False) and not bot_state.partial_tp2_taken.get(symbol, False):
            try:
                partial_size = abs(position) * PARTIAL_TP2_SIZE
                partial_size = round_quantity(symbol, partial_size)
                if partial_size > 0:
                    print(f"💰 Taking {PARTIAL_TP2_SIZE*100}% profit at {roi:.2f}% ROI ({PARTIAL_TP2_RR}R) for {symbol}")
                    client.futures_create_order(
                        symbol=symbol, 
                        side=SIDE_BUY, 
                        type=ORDER_TYPE_MARKET, 
                        quantity=partial_size, 
                        reduceOnly=True
                    )
                    bot_state.partial_tp2_taken[symbol] = True
            except Exception as e:
                print(f"Error taking partial profit 2 for {symbol}: {e}")

    # --- BREAKEVEN LOGIC ---
    BREAKEVEN_ROI_THRESHOLD = 1.5 # Move to breakeven at 1.5% ROI

    if roi >= BREAKEVEN_ROI_THRESHOLD and not bot_state.breakeven_triggered.get(symbol):
        print(f"✅ ROI for {symbol} hit {roi:.2f}%. Moving stop-loss to breakeven.")
        if await move_stop_to_breakeven(symbol, entry_price, SIDE_SELL):
            bot_state.breakeven_triggered[symbol] = True

    # --- TIER 1 EXIT CONDITIONS ---
    import time
    
    # 1. Time-Based Exit
    if ENABLE_TIME_BASED_EXIT:
        entry_time = bot_state.entry_timestamps.get(symbol)
        if entry_time:
            hours_held = (time.time() - entry_time) / 3600
            if hours_held >= MAX_HOLD_TIME_HOURS:
                reason = f"Time-Based Exit: Position held for {hours_held:.1f} hours (max: {MAX_HOLD_TIME_HOURS}h). Freeing up capital."
    
    # 2. Funding Rate Exit
    if not reason and ENABLE_FUNDING_RATE_EXIT:
        from data.get_data import get_funding_rate
        current_funding_rate = get_funding_rate(symbol)
        if current_funding_rate < MAX_FUNDING_RATE_SHORT:
            reason = f"Funding Rate Exit: Current funding rate {current_funding_rate*100:.3f}% below threshold {MAX_FUNDING_RATE_SHORT*100:.3f}%. Overcrowded short position."
    
    # 3. Maximum Drawdown Limit
    if not reason and ENABLE_MAX_DRAWDOWN_EXIT:
        if roi <= EMERGENCY_EXIT_ROI:
            reason = f"Emergency Exit: ROI at {roi:.2f}% reached emergency threshold of {EMERGENCY_EXIT_ROI}%. Cutting losses early."

    # --- PRIMARY EXIT: Market Structure Break ---
    lookback_period = 10
    recent_swing_high = df['high'].iloc[-lookback_period:-1].max()

    if last_close > recent_swing_high:
        reason = f"Exit Signal: Price broke market structure by closing above the recent swing high of ${recent_swing_high:.4f}."

    # --- SECONDARY EXIT: Profit-Taking in Extreme Conditions ---
    stoch_crossed_up = stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-2] <= stoch_d.iloc[-2]
    if stoch_k.iloc[-1] < 10 and stoch_crossed_up and not reason:
        reason = f"Profit Take: Stochastic crossed up in extreme oversold zone ({stoch_k.iloc[-1]:.2f})."

    if reason:
        print(f"Closing short position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_BUY, abs(position), reason)
        # Reset all state trackers for this symbol
        bot_state.breakeven_triggered.pop(symbol, None)
        bot_state.partial_tp1_taken.pop(symbol, None)
        bot_state.partial_tp2_taken.pop(symbol, None)
        bot_state.entry_timestamps.pop(symbol, None)
        return True
        
    return False

def update_loss_counter(roi):
    if roi < 0:
        bot_state.consecutive_losses += 1
        print(f"Trade lost. Consecutive losses: {bot_state.consecutive_losses}")
    else:
        if bot_state.consecutive_losses > 0:
            print("Trade won. Resetting consecutive loss counter.")
        bot_state.consecutive_losses = 0