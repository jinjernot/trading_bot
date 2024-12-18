from data.plot_stoch import plot_stochastic

from binance.enums import *
from src.telegram_bot import *
from data.indicators import *

from data.get_data import *
from src.trade import *
import asyncio

import matplotlib.pyplot as plt

from config.settings import *

def close_position_long(symbol, position, roi, df, stoch_k, resistance):
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

async def open_new_position(symbol, position, trend, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr):
    if position == 0:
        # Long
        if trend == 'uptrend' and (
            (
                stoch_k.iloc[-1] > stoch_d.iloc[-1] and
                stoch_k.iloc[-2] <= stoch_d.iloc[-2] and
                stoch_k.iloc[-1] > OVERSOLD and
                stoch_k.iloc[-2] <= OVERSOLD
            ) or (
                df['rsi'].iloc[-1] < 30 
            ) and abs(df['close'].iloc[-1] - support) <= atr.iloc[-1]
        ):
            place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry with stochastic or RSI oversold", stop_loss_percentage=2)
            message = (
                f"🔺 New Buy order placed for {symbol} ({nice_interval}): Bullish entry with stochastic or RSI oversold\n"
                f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
                f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                f"RSI: {df['rsi'].iloc[-1]:.2f}, Price: {df['close'].iloc[-1]:.2f}"
            )
            #await send_telegram_message(message)
            plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)

        # Short
        if trend == 'downtrend' and (
            (
                stoch_k.iloc[-1] < stoch_d.iloc[-1] and
                stoch_k.iloc[-2] >= stoch_d.iloc[-2] and
                stoch_k.iloc[-1] < OVERBOUGHT and
                stoch_k.iloc[-2] >= OVERBOUGHT
            ) or (
                df['rsi'].iloc[-1] > 70
            ) and abs(df['close'].iloc[-1] - resistance) <= atr.iloc[-1]
        ):
            place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry with stochastic or RSI overbought", stop_loss_percentage=2)
            message = (
                f"🔻 New Sell order placed for {symbol} ({nice_interval}): Bearish entry with stochastic or RSI overbought\n"
                f"Support: {support}, Resistance: {resistance}, ATR: {atr.iloc[-1]:.2f}\n"
                f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                f"RSI: {df['rsi'].iloc[-1]:.2f}, Price: {df['close'].iloc[-1]:.2f}"
            )
            #await send_telegram_message(message)
            plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)




async def process_symbol(symbol):
    print(f"Setting leverage for {symbol} to {leverage}")
    
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage set successfully for {symbol}.")
    except Exception as e:
        print(f"Error setting leverage for {symbol}: {e}")
        return
    
    try:
        print(f"\n--- New Iteration for {symbol} ({nice_interval}) ---")
        # Get Candles
        df, support, resistance, atr  = fetch_klines(symbol, interval)

        # Calculate Stochastic indicators
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        print(f"Stochastic K for {symbol}: {stoch_k.iloc[-3:].values}")
        print(f"Stochastic D for {symbol}: {stoch_d.iloc[-3:].values}")
        
        # Get current position and ROI
        position, roi, unrealized_profit, margin_used = get_position(symbol)
        print(f"Position for {symbol}: {position}, ROI: {roi:.2f}%, Unrealized Profit: {unrealized_profit:.2f}")
        print(f"Margin Used for {symbol}: {margin_used}")

        # Get USDT balance
        usdt_balance = get_usdt_balance()
        print(f"Available USDT balance for {symbol}: {usdt_balance}")

        # Get trend
        trend = detect_trend(df)
        print(f"Market trend for {symbol}: {trend}")
        
        # Close positions
        message = None
        if position > 0:
            message = close_position_long(symbol, position, roi, df, stoch_k, resistance)
        elif position < 0:
            message = close_position_short(symbol, position, roi, df, stoch_k, support)

        if message:
            print(message)
            await send_telegram_message(message)

        # Open new positions if no position is open
        if position == 0:
            df = calculate_rsi(df, period=14)
            message = open_new_position(symbol, position, trend, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr)
            if message:
                print(message)
                await send_telegram_message(message)

        print(f"Sleeping for 60 seconds...\n")
        await asyncio.sleep(60)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(60)

async def main():
    while True:
        tasks = [process_symbol(symbol) for symbol in symbols]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
