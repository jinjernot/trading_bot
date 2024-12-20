from binance.enums import *

from src.telegram_bot import send_telegram_message
from src.trade import place_order

from data.indicators import *
from data.plot import plot_stochastic
from config.settings import *

async def open_new_position(symbol, position, trend, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr):
    if position == 0:
        # Long
        if trend == 'uptrend' and (
            stoch_k.iloc[-1] > OVERSOLD and
            stoch_k.iloc[-2] <= OVERSOLD and
            stoch_k.iloc[-1] > stoch_d.iloc[-1] and
            abs(df['close'].iloc[-1] - support) <= atr.iloc[-1]
        ):
            place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry with stochastic leaving oversold", stop_loss_percentage=2)
            message = (
                f"🔺 New Buy order placed for {symbol} ({nice_interval}): Bullish entry with stochastic leaving oversold\n"
                f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
                f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                f"Price: {df['close'].iloc[-1]:.2f}"
            )
            #await send_telegram_message(message)
            plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)
            return message
        
        # Short
        if trend == 'downtrend' and (
            stoch_k.iloc[-1] < OVERBOUGHT and
            stoch_k.iloc[-2] >= OVERBOUGHT and
            stoch_k.iloc[-1] < stoch_d.iloc[-1] and
            abs(df['close'].iloc[-1] - resistance) <= atr.iloc[-1]
        ):
            place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry with stochastic leaving overbought", stop_loss_percentage=2)
            message = (
                f"🔻 New Sell order placed for {symbol} ({nice_interval}): Bearish entry with stochastic leaving overbought\n"
                f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
                f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                f"Price: {df['close'].iloc[-1]:.2f}"
            )
            #await send_telegram_message(message)
            plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)
            return message
    return None