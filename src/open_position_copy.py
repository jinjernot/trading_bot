from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *

async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr):
    
    if (
        (
            stoch_k.iloc[-1] > stoch_d.iloc[-1] and
            stoch_k.iloc[-2] <= stoch_d.iloc[-2] and
            stoch_k.iloc[-1] > OVERSOLD and
            stoch_k.iloc[-2] <= OVERSOLD
        ) or (df['rsi'].iloc[-1] < 30) and abs(df['close'].iloc[-1] - support) <= atr.iloc[-1]
        ):
        message = (
            f"🔺 New Buy order placed for {symbol} ({nice_interval}): Bullish entry with stochastic or RSI oversold\n"
            f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
            f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
            f"RSI: {df['rsi'].iloc[-1]:.2f}, Price: {df['close'].iloc[-1]:.2f}"
        )
        await send_telegram_message(message)    
            
        place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry with stochastic or RSI oversold", stop_loss_percentage=2)

        return True
    else:
        return False
            
async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr):
        
    if (
        (
            stoch_k.iloc[-1] < stoch_d.iloc[-1] and
            stoch_k.iloc[-2] >= stoch_d.iloc[-2] and
            stoch_k.iloc[-1] < OVERBOUGHT and
            stoch_k.iloc[-2] >= OVERBOUGHT
        ) or (df['rsi'].iloc[-1] > 70) and abs(df['close'].iloc[-1] - resistance) <= atr.iloc[-1]
        ):
        message = (
            f"🔻 New Sell order placed for {symbol} ({nice_interval}): Bearish entry with stochastic or RSI overbought\n"
            f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
            f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
            f"RSI: {df['rsi'].iloc[-1]:.2f}, Price: {df['close'].iloc[-1]:.2f}"
        )
        await send_telegram_message(message)

        place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry with stochastic or RSI overbought", stop_loss_percentage=2)
        return True
    else:
        return False
