from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *

async def open_new_position(symbol, position, trend, df, stoch_k, stoch_d, usdt_balance, support, resistance):
    if position == 0:
        # Long
        if trend == 'uptrend':
            if (
                (
                    stoch_k.iloc[-1] > stoch_d.iloc[-1] and
                    stoch_k.iloc[-2] <= stoch_d.iloc[-2] and
                    stoch_k.iloc[-1] > OVERSOLD and
                    stoch_k.iloc[-2] <= OVERSOLD
                )
            ):
                place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry with stochastic or RSI oversold", stop_loss_percentage=2)
                message = (
                    f"🔺 New Buy order placed for {symbol} ({nice_interval}): Bullish entry with stochastic or RSI oversold\n"
                    f"Support: {support}, Resistance: {resistance}\n"
                    f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                    f"RSI: {df['rsi'].iloc[-1]:.2f}, Price: {df['close'].iloc[-1]:.2f}"
                )
                await send_telegram_message(message)
                return True
            else:
                return False
        
        # Short
        if trend == 'downtrend':
            if (
                (
                    stoch_k.iloc[-1] < stoch_d.iloc[-1] and
                    stoch_k.iloc[-2] >= stoch_d.iloc[-2] and
                    stoch_k.iloc[-1] < OVERBOUGHT and
                    stoch_k.iloc[-2] >= OVERBOUGHT
                )
            ):
                place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry with stochastic or RSI overbought", stop_loss_percentage=2)
                message = (
                    f"🔻 New Sell order placed for {symbol} ({nice_interval}): Bearish entry with stochastic or RSI overbought\n"
                    f"Support: {support}, Resistance: {resistance}\n"
                    f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                    f"RSI: {df['rsi'].iloc[-1]:.2f}, Price: {df['close'].iloc[-1]:.2f}"
                )
                await send_telegram_message(message)
                return True
            else:
                return False
