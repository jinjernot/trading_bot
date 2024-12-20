from binance.enums import *

from src.telegram_bot import send_telegram_message
from src.trade import close_position, cancel_open_orders

from data.indicators import *
from config.settings import *

async def close_position_long(symbol, position, roi, df, stoch_k, resistance):
    if roi >= 50:
        close_position(symbol, SIDE_SELL, abs(position), "ROI >= 50%")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif roi <= -10:
        close_position(symbol, SIDE_SELL, abs(position), "ROI <= -10%")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif stoch_k.iloc[-1] > OVERBOUGHT and stoch_k.iloc[-2] <= OVERBOUGHT:  # Cross above overbought
        close_position(symbol, SIDE_SELL, abs(position), "Stochastic K crossed above overbought threshold")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): Stochastic K crossed above overbought (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
        await send_telegram_message(message)
        await cancel_open_orders(symbol)
    elif stoch_k.iloc[-1] < 50 and stoch_k.iloc[-2] >= 50:  # Cross below midline
        close_position(symbol, SIDE_SELL, abs(position), "Stochastic K dropped below midline")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): Stochastic K dropped below midline (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif df['close'].iloc[-1] >= resistance:
        close_position(symbol, SIDE_SELL, abs(position), "Price reached resistance level")
        message = f"🔺 Long position closed for {symbol} ({nice_interval}): Price reached resistance level (Price: {df['close'].iloc[-1]:.2f}, Resistance: {resistance:.2f}) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    else:
        return False
    await send_telegram_message(message)
    return True

async def close_position_short(symbol, position, roi, df, stoch_k, support):
    if roi >= 50:
        close_position(symbol, SIDE_BUY, abs(position), "ROI >= 50%")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif roi <= -10:
        close_position(symbol, SIDE_BUY, abs(position), "ROI <= -10%")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif stoch_k.iloc[-1] < OVERSOLD and stoch_k.iloc[-2] >= OVERSOLD:  # Cross below oversold
        close_position(symbol, SIDE_BUY, abs(position), "Stochastic K crossed below oversold threshold")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): Stochastic K crossed below oversold (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif stoch_k.iloc[-1] > 50 and stoch_k.iloc[-2] <= 50:  # Cross above midline
        close_position(symbol, SIDE_BUY, abs(position), "Stochastic K crossed above midline")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): Stochastic K crossed above midline (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    elif df['close'].iloc[-1] <= support:
        close_position(symbol, SIDE_BUY, abs(position), "Price reached support level")
        message = f"🔻 Short position closed for {symbol} ({nice_interval}): Price reached support level (Price: {df['close'].iloc[-1]:.2f}, Support: {support:.2f}) ⭕"
        await cancel_open_orders(symbol)
        await send_telegram_message(message)
    else:
        return False
    await send_telegram_message(message)
    return True
