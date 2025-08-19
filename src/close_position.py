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

    # --- REMOVED: Bollinger Band take-profit signal has been removed ---

    if roi > 0:
        stoch_crossed_down = stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-2] >= stoch_d.iloc[-2]
        if stoch_k.iloc[-1] > OVERBOUGHT and stoch_crossed_down:
            reason = f"Profit take: Stochastic crossed down in overbought zone ({stoch_k.iloc[-1]:.2f})."

        bearish_candlestick_signal = df['bearish_pattern'].iloc[-1] == 1
        if bearish_candlestick_signal and not reason:
            reason = f"Profit take: Bearish reversal pattern detected."

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

    # --- REMOVED: Bollinger Band take-profit signal has been removed ---

    if roi > 0:
        stoch_crossed_up = stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-2] <= stoch_d.iloc[-2]
        if stoch_k.iloc[-1] < OVERSOLD and stoch_crossed_up:
            reason = f"Profit take: Stochastic crossed up in oversold zone ({stoch_k.iloc[-1]:.2f})."
        
        bullish_candlestick_signal = df['bullish_pattern'].iloc[-1] == 1
        if bullish_candlestick_signal and not reason:
            reason = f"Profit take: Bullish reversal pattern detected."

    if reason:
        print(f"Closing short position for {symbol}. Reason: {reason}")
        update_loss_counter(roi)
        await cancel_open_orders(symbol)
        close_position(symbol, SIDE_BUY, abs(position), reason)
        return True
        
    return False