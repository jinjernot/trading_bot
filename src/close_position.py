from binance.enums import *
from src.telegram_bot import send_telegram_message
from src.trade import close_position, cancel_open_orders
from data.indicators import *
from config.settings import *
from src.state_manager import bot_state # Import the state manager

def update_loss_counter(roi):
    """Updates the consecutive loss counter based on trade ROI."""
    # This function is called every time a trade is closed.
    # We assume an external process (like your analysis script or manual check)
    # will be used to confirm the final PnL of bracket orders (TP/SL).
    # For discretionary closes, ROI gives us an immediate indicator.
    
    # NOTE: For full accuracy with TP/SL orders, you would need a more complex
    # system to query order history. This implementation provides a good
    # real-time approximation based on discretionary closes.
    
    if roi < 0:
        bot_state.consecutive_losses += 1
        print(f"Trade lost. Consecutive losses: {bot_state.consecutive_losses}")
    else:
        # Any winning trade resets the counter
        if bot_state.consecutive_losses > 0:
            print("Trade won. Resetting consecutive loss counter.")
        bot_state.consecutive_losses = 0

async def close_position_long(symbol, position, roi, df, stoch_k, resistance):
    """
    Handles discretionary exits for long positions and updates the loss counter.
    """
    # This logic only runs for discretionary (early) exits.
    # The main TP/SL are handled by bracket orders on the exchange.
    reason = None
    if stoch_k.iloc[-1] > OVERBOUGHT and stoch_k.iloc[-2] <= OVERBOUGHT:
        reason = "Discretionary exit: Stochastic crossed into overbought territory."
    elif df['close'].iloc[-1] >= resistance:
        reason = "Discretionary exit: Price reached a key resistance level."
    else:
        return False # No condition for early exit met.

    print(f"Closing long position for {symbol}. Reason: {reason}")
    
    # We update the counter here for discretionary closes.
    update_loss_counter(roi)
    
    await cancel_open_orders(symbol) 
    close_position(symbol, SIDE_SELL, abs(position), reason)
    return True

async def close_position_short(symbol, position, roi, df, stoch_k, support):
    """
    Handles discretionary exits for short positions and updates the loss counter.
    """
    reason = None
    if stoch_k.iloc[-1] < OVERSOLD and stoch_k.iloc[-2] >= OVERSOLD:
        reason = "Discretionary exit: Stochastic crossed into oversold territory."
    elif df['close'].iloc[-1] <= support:
        reason = "Discretionary exit: Price reached a key support level."
    else:
        return False # No condition for early exit met.

    print(f"Closing short position for {symbol}. Reason: {reason}")

    # We update the counter here for discretionary closes.
    update_loss_counter(roi)

    await cancel_open_orders(symbol)
    close_position(symbol, SIDE_BUY, abs(position), reason)
    return True