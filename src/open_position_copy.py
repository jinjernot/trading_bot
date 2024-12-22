from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *

async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance):
    # Long
    if (
        stoch_k.iloc[-1] > OVERSOLD and
        stoch_k.iloc[-2] <= OVERSOLD and
        stoch_k.iloc[-1] > stoch_d.iloc[-1]
    ):
        print(f"Placing order for {symbol}")
        message = f"""
🟢 *New Buy Order Placed* for *{symbol}* ({nice_interval}):
- *Reason*: Bullish entry with stochastic leaving oversold
- *Support*: {support:.2f}  |  *Resistance*: {resistance:.2f}
- *Stochastic K*: {stoch_k.iloc[-1]:.2f}  |  *Stochastic D*: {stoch_d.iloc[-1]:.2f}
- *Current Price*: {df['close'].iloc[-1]:.2f}
"""
        await send_telegram_message(message, parse_mode="Markdown")
        place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry with stochastic leaving oversold", stop_loss_percentage=2)

        return True
    else:
        return False

async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance):
    # Short
    if (
        stoch_k.iloc[-1] < OVERBOUGHT and
        stoch_k.iloc[-2] >= OVERBOUGHT and
        stoch_k.iloc[-1] < stoch_d.iloc[-1]
    ):
        print(f"Placing order for {symbol}")
        message = f"""
🔴 *New Sell Order Placed* for *{symbol}* ({nice_interval}):
- *Reason*: Bearish entry with stochastic leaving overbought
- *Support*: {support:.2f}  |  *Resistance*: {resistance:.2f}
- *Stochastic K*: {stoch_k.iloc[-1]:.2f}  |  *Stochastic D*: {stoch_d.iloc[-1]:.2f}
- *Current Price*: {df['close'].iloc[-1]:.2f}
"""
        await send_telegram_message(message, parse_mode="Markdown")
        place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry with stochastic leaving overbought", stop_loss_percentage=2)
        return True
    else:
        return False
