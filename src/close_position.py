from binance.enums import *
from src.trade import close_position, cancel_open_orders, move_stop_to_breakeven
from data.indicators import *
from config.settings import *
from src.state_manager import bot_state

def update_loss_counter(roi):
    if roi < 0:
        bot_state.consecutive_losses += 1
        print(f"Trade lost. Consecutive losses: {bot_state.consecutive_losses}")
    else:
        if bot_state.consecutive_losses > 0:
            print("Trade won. Resetting consecutive loss counter.")
        bot_state.consecutive_losses = 0

async def close_position_long(symbol, position, roi, df, stoch_k, stoch_d, resistance, atr_value, entry_price):
    reason = None
    last_close = df['close'].iloc[-1]
    
    # --- BREAKEVEN LOGIC ---
    BREAKEVEN_ROI_THRESHOLD = 1.5 # Move to breakeven at 1.5% ROI
    
    if roi >= BREAKEVEN_ROI_THRESHOLD and not bot_state.breakeven_triggered.get(symbol):
        print(f"✅ ROI for {symbol} hit {roi:.2f}%. Moving stop-loss to breakeven.")
        if await move_stop_to_breakeven(symbol, entry_price, SIDE_BUY):
            bot_state.breakeven_triggered[symbol] = True

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
        bot_state.breakeven_triggered.pop(symbol, None) # Reset state after closing
        return True

    return False

async def close_position_short(symbol, position, roi, df, stoch_k, stoch_d, support, atr_value, entry_price):
    reason = None
    last_close = df['close'].iloc[-1]

    # --- BREAKEVEN LOGIC ---
    BREAKEVEN_ROI_THRESHOLD = 1.5 # Move to breakeven at 1.5% ROI

    if roi >= BREAKEVEN_ROI_THRESHOLD and not bot_state.breakeven_triggered.get(symbol):
        print(f"✅ ROI for {symbol} hit {roi:.2f}%. Moving stop-loss to breakeven.")
        if await move_stop_to_breakeven(symbol, entry_price, SIDE_SELL):
            bot_state.breakeven_triggered[symbol] = True

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
        bot_state.breakeven_triggered.pop(symbol, None) # Reset state after closing
        return True
        
    return False