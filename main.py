
from binance.client import Client
from binance.enums import *

from config.api import API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID
from config.stoch import PERIOD,K,D,OVERBOUGHT,OVERSOLD

from src.data.stochastic import *
from src.data.get_data import *
from src.core.trade import *

import asyncio

from telegram import Bot

client = Client(API_KEY, API_SECRET)

# Parameters
symbol = 'BTCUSDT'
interval = Client.KLINE_INTERVAL_1MINUTE
leverage = 5
bot = Bot(token=TELEGRAM_TOKEN)

async def send_telegram_message(message):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        print(f"Error sending message: {e}")

async def main():
    print(f"Setting leverage for {symbol} to {leverage}")
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print("Leverage set successfully.")
    except Exception as e:
        print(f"Error setting leverage: {e}")
        return
    
    while True:
        try:
            print(f"\n--- New Iteration ---")
            df = fetch_klines(symbol, interval)
            
            stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
            print(f"Stochastic K: {stoch_k.iloc[-3:].values}")
            print(f"Stochastic D: {stoch_d.iloc[-3:].values}")
            
            position, roi, unrealized_profit = get_position(symbol)
            print(f"Position: {position}, ROI: {roi:.2f}%, Unrealized Profit: {unrealized_profit:.2f}")  # Display ROI as %
            usdt_balance = get_usdt_balance()
            print(f"Available USDT balance: {usdt_balance}")

            # For long position
            if position > 0:
                if roi >= 1:  # Check ROI for long position
                    close_position(symbol, SIDE_SELL, abs(position), "ROI >= 1%")
                    await send_telegram_message(f"Long position closed: ROI >= 1%")
                elif stoch_k.iloc[-1] > OVERBOUGHT:
                    close_position(symbol, SIDE_SELL, abs(position), "Stochastic overbought threshold")
                    await send_telegram_message(f"Long position closed: Stochastic overbought")

            # For short position
            #elif position < 0:
            #    if roi >= 2:  # Check ROI for short position
            #        close_position(symbol, SIDE_BUY, abs(position), "ROI >= 5%")
            #        await send_telegram_message(f"Short position closed: ROI >= 5%")
            #    elif stoch_k.iloc[-1] < OVERSOLD:
            #        close_position(symbol, SIDE_BUY, abs(position), "Stochastic oversold threshold")
            #        await send_telegram_message(f"Short position closed: Stochastic oversold")
                    
            # Open New Positions
            if position == 0:
                if (stoch_k.iloc[-1] > stoch_d.iloc[-1] and 
                    stoch_k.iloc[-2] <= stoch_d.iloc[-2] and 
                    stoch_k.iloc[-1] < OVERSOLD):
                    place_order(symbol, SIDE_BUY, usdt_balance, "Bullish crossover detected")
                    await send_telegram_message(f"New Buy order placed: Bullish crossover detected")
            #    elif (stoch_k.iloc[-1] < stoch_d.iloc[-1] and 
            #          stoch_k.iloc[-2] >= stoch_d.iloc[-2] and 
            #          stoch_k.iloc[-1] > OVERBOUGHT):
            #        place_order(symbol, SIDE_SELL, usdt_balance, "Bearish crossover detected")
            #        await send_telegram_message(f"New Sell order placed: Bearish crossover detected")

            print("Sleeping for 60 seconds...\n")
            await asyncio.sleep(60)  # Use asyncio.sleep instead of time.sleep for async loop
        except Exception as e:
            print(f"Error in main loop: {e}")
            await asyncio.sleep(10)  # Use asyncio.sleep instead of time.sleep for async loop
                        
if __name__ == "__main__":
    asyncio.run(main())