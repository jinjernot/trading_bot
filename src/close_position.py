from binance.enums import *
from src.telegram_bot import send_telegram_message
from src.trade import close_position, cancel_open_orders
from data.indicators import *
from config.settings import *

async def close_position_long(symbol, position, roi, df, stoch_k, resistance):
    """
    Handles discretionary exits for long positions if momentum fades before TP/SL is hit.
    """
    reason = None
    # Condition 1: Stochastic shows momentum is reversing (crossing into overbought).
    if stoch_k.iloc[-1] > OVERBOUGHT and stoch_k.iloc[-2] <= OVERBOUGHT:
        reason = "Discretionary exit: Stochastic crossed into overbought territory."
    
    # Condition 2: Price has hit a significant resistance level.
    elif df['close'].iloc[-1] >= resistance:
        reason = "Discretionary exit: Price reached a key resistance level."
    
    # If no exit condition is met, do nothing.
    else:
        return False

    print(f"Closing long position for {symbol}. Reason: {reason}")
    # CRITICAL: Always cancel existing Stop-Loss and Take-Profit orders first.
    await cancel_open_orders(symbol) 
    
    # Now, place a market order to close the position.
    close_position(symbol, SIDE_SELL, abs(position), reason)
    
    message = f"""
🟢 *Long Position Closed Early* for *{symbol}* ({nice_interval}):
- *Reason*: {reason}
- *ROI at exit*: {roi:.2f}%
"""
    # You can re-enable this message if you wish
    # await send_telegram_message(message, parse_mode="Markdown")
    
    return True


async def close_position_short(symbol, position, roi, df, stoch_k, support):
    """
    Handles discretionary exits for short positions if momentum fades before TP/SL is hit.
    """
    reason = None
    # Condition 1: Stochastic shows momentum is reversing (crossing into oversold).
    if stoch_k.iloc[-1] < OVERSOLD and stoch_k.iloc[-2] >= OVERSOLD:
        reason = "Discretionary exit: Stochastic crossed into oversold territory."
        
    # Condition 2: Price has hit a significant support level.
    elif df['close'].iloc[-1] <= support:
        reason = "Discretionary exit: Price reached a key support level."
        
    # If no exit condition is met, do nothing.
    else:
        return False

    print(f"Closing short position for {symbol}. Reason: {reason}")
    # CRITICAL: Always cancel existing Stop-Loss and Take-Profit orders first.
    await cancel_open_orders(symbol)
    
    # Now, place a market order to close the position.
    close_position(symbol, SIDE_BUY, abs(position), reason)
    
    message = f"""
🔴 *Short Position Closed Early* for *{symbol}* ({nice_interval}):
- *Reason*: {reason}
- *ROI at exit*: {roi:.2f}%
"""
    # You can re-enable this message if you wish
    # await send_telegram_message(message, parse_mode="Markdown")
    
    return True