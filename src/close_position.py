from binance.enums import *
from src.trade import close_position, cancel_open_orders
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
    
    # Define the lookback period to find the most recent swing low.
    lookback_period = 10 
    
    # Find the lowest low in the recent past (our swing low).
    recent_swing_low = df['low'].iloc[-lookback_period:-1].min()

    # If the price closes below this recent swing low, it's a sign the uptrend is broken.
    if last_close < recent_swing_low:
        reason = f"Exit Signal: Price broke market structure by closing below the recent swing low of ${recent_swing_low:.4f}."

    # We can still keep the stochastic as a secondary, profit-taking signal for very overextended moves.
    stoch_crossed_down = stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-2] >= stoch_d.iloc[-2]
    if stoch_k.iloc[-1] > 90 and stoch_crossed_down and not reason: # Using a higher threshold (e.g., 90) for this exit.
        reason = f"Profit Take: Stochastic crossed down in extreme overbought zone ({stoch_k.iloc[-1]:.2f})."

    if reason:
        print(f"Closing long position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_SELL, abs(position), reason)
        return True

    return False

async def close_position_short(symbol, position, roi, df, stoch_k, stoch_d, support, atr_value, entry_price):
    reason = None
    last_close = df['close'].iloc[-1]

    # Define the lookback period to find the most recent swing high.
    lookback_period = 10

    # Find the highest high in the recent past (our swing high).
    recent_swing_high = df['high'].iloc[-lookback_period:-1].max()

    # If the price closes above this recent swing high, it's a sign the downtrend is broken.
    if last_close > recent_swing_high:
        reason = f"Exit Signal: Price broke market structure by closing above the recent swing high of ${recent_swing_high:.4f}."

    # Secondary profit-taking signal for extreme oversold conditions.
    stoch_crossed_up = stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-2] <= stoch_d.iloc[-2]
    if stoch_k.iloc[-1] < 10 and stoch_crossed_up and not reason: # Using a lower threshold (e.g., 10) for this exit.
        reason = f"Profit Take: Stochastic crossed up in extreme oversold zone ({stoch_k.iloc[-1]:.2f})."

    if reason:
        print(f"Closing short position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_BUY, abs(position), reason)
        return True
        
    return False