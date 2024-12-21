from binance.enums import *
from src.telegram_bot import send_telegram_message
from src.trade import close_position, cancel_open_orders
from data.indicators import *
from config.settings import *

async def close_position_long(symbol, position, roi, df, stoch_k, resistance):
    if roi >= 50:
        close_position(symbol, SIDE_SELL, abs(position), "ROI >= 50%")
        message = f"""
🟢 *Long Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: ROI >= 50%
- *ROI*: {roi:.2f}%
- ✅ *Successful*
"""
        await cancel_open_orders(symbol)
    elif roi <= -10:
        close_position(symbol, SIDE_SELL, abs(position), "ROI <= -10%")
        message = f"""
🟢 *Long Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: ROI <= -10%
- *ROI*: {roi:.2f}%
- ❌ *Fail*
"""
        await cancel_open_orders(symbol)
    elif stoch_k.iloc[-1] > OVERBOUGHT and stoch_k.iloc[-2] <= OVERBOUGHT:  # Cross above overbought
        close_position(symbol, SIDE_SELL, abs(position), "Stochastic K crossed above overbought threshold")
        message = f"""
🟢 *Long Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: Stochastic K crossed above overbought
- *Stochastic K*: {stoch_k.iloc[-1]:.2f}
- *ROI*: {roi:.2f}%
- ✅ *Successful*
"""
        await cancel_open_orders(symbol)
    elif df['close'].iloc[-1] >= resistance:
        close_position(symbol, SIDE_SELL, abs(position), "Price reached resistance level")
        message = f"""
🟢 *Long Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: Price reached resistance level
- *Current Price*: {df['close'].iloc[-1]:.2f}
- *Resistance*: {resistance:.2f}
- *ROI*: {roi:.2f}%
- ✅ *Successful*
"""
        await cancel_open_orders(symbol)
    else:
        return False
    await send_telegram_message(message, parse_mode="Markdown")
    return True

async def close_position_short(symbol, position, roi, df, stoch_k, support):
    if roi >= 50:
        close_position(symbol, SIDE_BUY, abs(position), "ROI >= 50%")
        message = f"""
🔴 *Short Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: ROI >= 50%
- *ROI*: {roi:.2f}%
- ✅ *Successful*
"""
        await cancel_open_orders(symbol)
    elif roi <= -10:
        close_position(symbol, SIDE_BUY, abs(position), "ROI <= -10%")
        message = f"""
🔴 *Short Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: ROI <= -10%
- *ROI*: {roi:.2f}%
- ❌ *Fail*
"""
        await cancel_open_orders(symbol)
    elif stoch_k.iloc[-1] < OVERSOLD and stoch_k.iloc[-2] >= OVERSOLD:  # Cross below oversold
        close_position(symbol, SIDE_BUY, abs(position), "Stochastic K crossed below oversold threshold")
        message = f"""
🔴 *Short Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: Stochastic K crossed below oversold
- *Stochastic K*: {stoch_k.iloc[-1]:.2f}
- *ROI*: {roi:.2f}%
- ✅ *Successful*
"""
        await cancel_open_orders(symbol)
    elif df['close'].iloc[-1] <= support:
        close_position(symbol, SIDE_BUY, abs(position), "Price reached support level")
        message = f"""
🔴 *Short Position Closed* for *{symbol}* ({nice_interval}):
- *Reason*: Price reached support level
- *Current Price*: {df['close'].iloc[-1]:.2f}
- *Support*: {support:.2f}
- *ROI*: {roi:.2f}%
- ✅ *Successful Close*
"""
        await cancel_open_orders(symbol)
    else:
        return False
    await send_telegram_message(message, parse_mode="Markdown")
    return True
