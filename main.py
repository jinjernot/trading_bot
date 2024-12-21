from data.plot import plot_stochastic

from binance.enums import *
from src.telegram_bot import *
from data.indicators import *

from data.get_data import *
from src.trade import *
import asyncio

import matplotlib.pyplot as plt

from config.settings import *

async def cancel_open_orders(symbol):
    try:
        open_orders = client.futures_get_open_orders(symbol=symbol)
        for order in open_orders:
            if order['type'] == 'FUTURE_ORDER_TYPE_STOP' or order['type'] == 'STOP':
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                print(f"Canceled stop-loss order for {symbol}, Order ID: {order['orderId']}")
    except Exception as e:
        print(f"Error canceling open orders for {symbol}: {e}")

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
        
        # Close the trade
        if position > 0:  # Long position
            if roi >= 50:
                close_position(symbol, SIDE_SELL, abs(position), "ROI >= 50%")
                await cancel_open_orders(symbol)
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
                await send_telegram_message(message)
            elif roi <= -10:
                close_position(symbol, SIDE_SELL, abs(position), "ROI <= -10%")
                await cancel_open_orders(symbol)
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] > OVERBOUGHT and stoch_k.iloc[-2] <= OVERBOUGHT:  # Cross above overbought
                close_position(symbol, SIDE_SELL, abs(position), "Stochastic K crossed above overbought threshold")
                await cancel_open_orders(symbol)
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): Stochastic K crossed above overbought (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] < 50 and stoch_k.iloc[-2] >= 50:  # Cross below midline
                close_position(symbol, SIDE_SELL, abs(position), "Stochastic K dropped below midline")
                await cancel_open_orders(symbol)
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): Stochastic K dropped below midline (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
                await send_telegram_message(message)
            elif df['close'].iloc[-1] >= resistance:
                close_position(symbol, SIDE_SELL, abs(position), "Price reached resistance level")
                await cancel_open_orders(symbol)
                message = f"🔺 Long position closed for {symbol} ({nice_interval}): Price reached resistance level (Price: {df['close'].iloc[-1]:.2f}, Resistance: {resistance:.2f}) ⭕"
                await send_telegram_message(message)

        elif position < 0:  # Short position
            if roi >= 50:
                close_position(symbol, SIDE_BUY, abs(position), "ROI >= 50%")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI >= 50% (Current ROI: {roi:.2f}%) ⭕"
                await send_telegram_message(message)
            elif roi <= -10:
                close_position(symbol, SIDE_BUY, abs(position), "ROI <= -10%")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): ROI <= -10% (Current ROI: {roi:.2f}%) ❌"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] < OVERSOLD and stoch_k.iloc[-2] >= OVERSOLD:  # Cross below oversold
                close_position(symbol, SIDE_BUY, abs(position), "Stochastic K crossed below oversold threshold")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): Stochastic K crossed below oversold (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] > 50 and stoch_k.iloc[-2] <= 50:  # Cross above midline
                close_position(symbol, SIDE_BUY, abs(position), "Stochastic K crossed above midline")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): Stochastic K crossed above midline (Stochastic K: {stoch_k.iloc[-1]:.2f}) ⭕"
                await send_telegram_message(message)
            elif df['close'].iloc[-1] <= support:
                close_position(symbol, SIDE_BUY, abs(position), "Price reached support level")
                message = f"🔻 Short position closed for {symbol} ({nice_interval}): Price reached support level (Price: {df['close'].iloc[-1]:.2f}, Support: {support:.2f}) ⭕"
                await send_telegram_message(message)
                        
        # Open New Positions
        if position == 0:
            # Calculate ATR (Average True Range)
            atr = df['high'].rolling(window=14).max() - df['low'].rolling(window=14).min()

            # Calculate RSI 
            df = calculate_rsi(df, period=14)  # Adding RSI column to df

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
                await send_telegram_message(message)
                plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)

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
                await send_telegram_message(message)
                plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)
            
        print(f"Sleeping for 60 seconds...\n")
        await asyncio.sleep(10)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(10)

async def main():
    while True:
        for symbol in symbols:
            await process_symbol(symbol)
        print("Sleeping for 60 seconds before scanning the next symbol...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())