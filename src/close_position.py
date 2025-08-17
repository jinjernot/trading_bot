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

    # Confluence Exit: Stochastic crossover in the overbought zone
    stoch_crossed_down = stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-2] >= stoch_d.iloc[-2]
    if roi > 0 and stoch_k.iloc[-1] > OVERBOUGHT and stoch_crossed_down:
        reason = f"Profit take: Stochastic crossed down in overbought zone ({stoch_k.iloc[-1]:.2f})."

    # Trailing Stop-Loss Logic
    if symbol in bot_state.trailing_stop_prices:
        current_trailing_stop = bot_state.trailing_stop_prices[symbol]
        new_trailing_stop = last_close - (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        
        # The trailing stop only moves up
        if new_trailing_stop > current_trailing_stop:
            bot_state.trailing_stop_prices[symbol] = new_trailing_stop
            if VERBOSE_LOGGING:
                print(f"Trailing stop for {symbol} moved up to {new_trailing_stop:.4f}")
        
        if last_close < current_trailing_stop:
            reason = f"Trailing stop-loss hit at {current_trailing_stop:.4f}."

    elif roi > 0: # If no trailing stop is set yet, set the initial one
        initial_trailing_stop = last_close - (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        bot_state.trailing_stop_prices[symbol] = initial_trailing_stop
        if VERBOSE_LOGGING:
            print(f"Initial trailing stop for {symbol} set to {initial_trailing_stop:.4f}")

    if reason:
        print(f"Closing long position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_SELL, abs(position), reason)
        if symbol in bot_state.trailing_stop_prices:
            del bot_state.trailing_stop_prices[symbol] # Clean up the state
        return True

    return False

async def close_position_short(symbol, position, roi, df, stoch_k, stoch_d, support, atr_value, entry_price):
    reason = None
    last_close = df['close'].iloc[-1]

    # Confluence Exit: Stochastic crossover in the oversold zone
    stoch_crossed_up = stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-2] <= stoch_d.iloc[-2]
    if roi > 0 and stoch_k.iloc[-1] < OVERSOLD and stoch_crossed_up:
        reason = f"Profit take: Stochastic crossed up in oversold zone ({stoch_k.iloc[-1]:.2f})."
    
    # Trailing Stop-Loss Logic
    if symbol in bot_state.trailing_stop_prices:
        current_trailing_stop = bot_state.trailing_stop_prices[symbol]
        new_trailing_stop = last_close + (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        
        # The trailing stop only moves down
        if new_trailing_stop < current_trailing_stop:
            bot_state.trailing_stop_prices[symbol] = new_trailing_stop
            if VERBOSE_LOGGING:
                print(f"Trailing stop for {symbol} moved down to {new_trailing_stop:.4f}")

        if last_close > current_trailing_stop:
            reason = f"Trailing stop-loss hit at {current_trailing_stop:.4f}."
            
    elif roi > 0: # If no trailing stop is set yet, set the initial one
        initial_trailing_stop = last_close + (atr_value * TRAILING_STOP_ATR_MULTIPLIER)
        bot_state.trailing_stop_prices[symbol] = initial_trailing_stop
        if VERBOSE_LOGGING:
            print(f"Initial trailing stop for {symbol} set to {initial_trailing_stop:.4f}")

    if reason:
        print(f"Closing short position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_BUY, abs(position), reason)
        if symbol in bot_state.trailing_stop_prices:
            del bot_state.trailing_stop_prices[symbol] # Clean up the state
        return True
        
    return False