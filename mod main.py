from data.plot_stoch import plot_stochastic

from binance.enums import *
from src.telegram_bot import *
from data.indicators import *

from data.get_data import *
from src.trade import *
import asyncio

import matplotlib.pyplot as plt

from config.settings import *

async def set_leverage(symbol):
    """Set leverage for the given symbol."""
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage set successfully for {symbol}.")
    except Exception as e:
        print(f"Error setting leverage for {symbol}: {e}")

def should_close_position(position, roi, stoch_k, price, support, resistance, symbol):
    """Determine if the position should be closed."""
    if position > 0:  # Long position
        return (
            (roi >= 50, "ROI >= 50%"),
            (roi <= -10, "ROI <= -10%"),
            (stoch_k.iloc[-1] > OVERBOUGHT, "Stochastic overbought threshold"),
            (price >= resistance, "Price reached resistance level")
        )
    elif position < 0:  # Short position
        return (
            (roi >= 50, "ROI >= 50%"),
            (roi <= -10, "ROI <= -10%"),
            (stoch_k.iloc[-1] < OVERSOLD, "Stochastic oversold threshold"),
            (price <= support, "Price reached support level")
        )
    return []

async def process_position(symbol, position, roi, stoch_k, price, support, resistance):
    """Handle closing an open position."""
    close_reasons = should_close_position(position, roi, stoch_k, price, support, resistance, symbol)
    for should_close, reason in close_reasons:
        if should_close:
            side = SIDE_SELL if position > 0 else SIDE_BUY
            close_position(symbol, side, abs(position), reason)
            await send_telegram_message(f"Position closed for {symbol}: {reason} (ROI: {roi:.2f}%)")
            return True
    return False

async def open_position(symbol, trend, stoch_k, stoch_d, atr, price, support, resistance, usdt_balance):
    """Open a new position based on trend and stochastic indicators."""
    if trend == 'uptrend':
        if (
            (stoch_k.iloc[-1] > stoch_d.iloc[-1] and stoch_k.iloc[-1] > OVERSOLD) or
            (price <= support + atr)
        ):
            place_order(symbol, SIDE_BUY, usdt_balance, "Bullish entry detected", stop_loss_percentage=2)
            await send_telegram_message(f"New long position opened for {symbol}.")
            return True
    elif trend == 'downtrend':
        if (
            (stoch_k.iloc[-1] < stoch_d.iloc[-1] and stoch_k.iloc[-1] < OVERBOUGHT) or
            (price >= resistance - atr)
        ):
            place_order(symbol, SIDE_SELL, usdt_balance, "Bearish entry detected", stop_loss_percentage=2)
            await send_telegram_message(f"New short position opened for {symbol}.")
            return True
    return False

async def process_symbol(symbol):
    """Main processing logic for a single symbol."""
    print(f"Setting leverage for {symbol} to {leverage}")
    await set_leverage(symbol)

    print(f"\n--- New Iteration for {symbol} ({nice_interval}) ---")
    try:
        # Fetch data
        df, support, resistance, atr = fetch_klines(symbol, interval)
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        position, roi, _, _ = get_position(symbol)
        usdt_balance = get_usdt_balance()
        trend = detect_trend(df)

        # Close existing position
        if await process_position(symbol, position, roi, stoch_k, df['close'].iloc[-1], support, resistance):
            return

        # Open a new position if none exist
        if position == 0:
            await open_position(symbol, trend, stoch_k, stoch_d, atr, df['close'].iloc[-1], support, resistance, usdt_balance)

        plot_stochastic(stoch_k, stoch_d, symbol, OVERSOLD, OVERBOUGHT)
        print(f"Sleeping for 60 seconds...\n")
        await asyncio.sleep(60)
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(20)

async def main():
    """Main function to process all symbols."""
    while True:
        for symbol in symbols:
            await process_symbol(symbol)
        print("Sleeping for 60 seconds before scanning the next symbol...")
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())