from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *

async def open_position_long(symbol,trend, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr):
    
    # Long
    if trend == 'uptrend' and (
        stoch_k.iloc[-1] > OVERSOLD and
        stoch_k.iloc[-2] <= OVERSOLD and
        stoch_k.iloc[-1] > stoch_d.iloc[-1]
    ):
        print(f"Placing order for {symbol}")
        place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry with stochastic leaving oversold", stop_loss_percentage=2)
        message = (
            f"🔺 New Buy order placed for {symbol} ({nice_interval}): Bullish entry with stochastic leaving oversold\n"
            f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
            f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
            f"Price: {df['close'].iloc[-1]:.2f}"
        )
        await send_telegram_message(message)            
        return True
    else:
        return False
            
async def open_position_short(symbol, trend, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr):
    # Short
    if trend == 'downtrend' and (
        stoch_k.iloc[-1] < OVERBOUGHT and
        stoch_k.iloc[-2] >= OVERBOUGHT and
        stoch_k.iloc[-1] < stoch_d.iloc[-1]
    ):
        place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry with stochastic leaving overbought", stop_loss_percentage=2)
        message = (
            f"🔻 New Sell order placed for {symbol} ({nice_interval}): Bearish entry with stochastic leaving overbought\n"
            f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
            f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
            f"Price: {df['close'].iloc[-1]:.2f}"
        )
        await send_telegram_message(message)
        return True
    else:
        return False
