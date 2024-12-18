from binance.enums import *

from src.telegram_bot import send_telegram_message
from src.trade import close_position

from data.indicators import *
from config.settings import *

async def close_position_long(symbol, position, roi, df, stoch_k, resistance):
    if roi >= 50:
        close_position(symbol, SIDE_SELL, abs(position), "ROI >= 50%")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
    elif roi <= -10:
        close_position(symbol, SIDE_SELL, abs(position), "ROI <= -10%")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
    elif stoch_k.iloc[-1] > OVERBOUGHT:
        close_position(symbol, SIDE_SELL, abs(position), "Stochastic overbought threshold")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): Stochastic overbought (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
    elif df['close'].iloc[-1] >= resistance:
        close_position(symbol, SIDE_SELL, abs(position), "Price reached resistance level")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): Price reached resistance level (Price: {df['close'].iloc[-1]:.2f}, Resistance: {resistance:.2f}) ⭕"
    else:
        return False
    #await send_telegram_message(message)
    return True

async def close_position_short(symbol, position, roi, df, stoch_k, support):
    if roi >= 50:
        close_position(symbol, SIDE_BUY, abs(position), "ROI >= 50%")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
    elif roi <= -10:
        close_position(symbol, SIDE_BUY, abs(position), "ROI <= -10%")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
    elif stoch_k.iloc[-1] < OVERSOLD:
        close_position(symbol, SIDE_BUY, abs(position), "Stochastic oversold threshold")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): Stochastic oversold (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
    elif df['close'].iloc[-1] <= support:
        close_position(symbol, SIDE_BUY, abs(position), "Price reached support level")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): Price reached support level (Price: {df['close'].iloc[-1]:.2f}, Support: {support:.2f}) ⭕"
    else:
        return False
    #await send_telegram_message(message)
    return True
