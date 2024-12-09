# close_positions.py
from binance.enums import *
from src.telegram_bot import send_telegram_message
from src.trade import close_position
from data.indicators import *

async def close_position_logic(symbol, position, roi, df, stoch_k, resistance, support, nice_interval, unrealized_profit, margin_used):
    try:
        if position > 0:  # Long position
            if roi >= 50:
                await close_position(symbol, SIDE_SELL, abs(position), "ROI >= 50%")
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
                await send_telegram_message(message)
            elif roi <= -10:
                await close_position(symbol, SIDE_SELL, abs(position), "ROI <= -10%")
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] > OVERBOUGHT:
                await close_position(symbol, SIDE_SELL, abs(position), "Stochastic overbought threshold")
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): Stochastic overbought (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
                await send_telegram_message(message)
            elif df['close'].iloc[-1] >= resistance:
                await close_position(symbol, SIDE_SELL, abs(position), "Price reached resistance level")
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): Price reached resistance level (Price: {df['close'].iloc[-1]:.2f}, Resistance: {resistance:.2f}) ⭕"
                await send_telegram_message(message)

        elif position < 0:  # Short position
            if roi >= 50:
                await close_position(symbol, SIDE_BUY, abs(position), "ROI >= 50%")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
                await send_telegram_message(message)
            elif roi <= -10:
                await close_position(symbol, SIDE_BUY, abs(position), "ROI <= -10%")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] < OVERSOLD:
                await close_position(symbol, SIDE_BUY, abs(position), "Stochastic oversold threshold")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): Stochastic oversold (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
                await send_telegram_message(message)
            elif df['close'].iloc[-1] <= support:
                await close_position(symbol, SIDE_BUY, abs(position), "Price reached support level")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): Price reached support level (Price: {df['close'].iloc[-1]:.2f}, Support: {support:.2f}) ⭕"
                await send_telegram_message(message)

    except Exception as e:
        print(f"Error closing positions for {symbol}: {e}")
