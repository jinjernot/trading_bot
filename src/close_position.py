from binance.enums import *
from src.telegram_bot import send_telegram_message
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

async def close_position_long(symbol, position, roi, df, stoch_k, resistance):
    reason = None
    
    if roi > 0 and stoch_k.iloc[-1] > OVERBOUGHT:
        reason = f"Profit take: Stochastic reached overbought zone ({stoch_k.iloc[-1]:.2f})."
    elif df['close'].iloc[-1] >= resistance:
        reason = "Discretionary exit: Price reached a key resistance level."
    else:
        return False

    print(f"Closing long position for {symbol}. Reason: {reason}")
    
    update_loss_counter(roi)
    
    await cancel_open_orders(symbol) 
    close_position(symbol, SIDE_SELL, abs(position), reason)
    return True

async def close_position_short(symbol, position, roi, df, stoch_k, support):
    reason = None

    if roi > 0 and stoch_k.iloc[-1] < OVERSOLD:
        reason = f"Profit take: Stochastic reached oversold zone ({stoch_k.iloc[-1]:.2f})."
    elif df['close'].iloc[-1] <= support:
        reason = "Discretionary exit: Price reached a key support level."
    else:
        return False

    print(f"Closing short position for {symbol}. Reason: {reason}")

    update_loss_counter(roi)

    await cancel_open_orders(symbol)
    close_position(symbol, SIDE_BUY, abs(position), reason)
    return True