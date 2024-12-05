import pandas as pd
import time
import json
import os

from binance.client import Client
from binance.enums import *

from config.api import API_KEY, API_SECRET, TELEGRAM_TOKEN, CHAT_ID
from config.paths import LOG_FILE
from config.stoch import PERIOD,K,D,OVERBOUGHT,OVERSOLD

client = Client(API_KEY, API_SECRET)

import asyncio
import time

from telegram import Bot
from telegram.ext import Updater, CommandHandler
import asyncio

# Parameters
symbol = 'BTCUSDT'
interval = Client.KLINE_INTERVAL_1MINUTE
leverage = 10
bot = Bot(token=TELEGRAM_TOKEN)

# Function to send a Telegram message
async def send_telegram_message(message):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        print(f"Error sending message: {e}")
        
# Example: Start function for your bot command
async def start(update, context):
    await send_telegram_message("Bot is up and running!")

# Your main async function
async def main():
    # You can add any code here that requires async execution
    await send_telegram_message("Bot is initializing...")

    # Simulate another action
    await asyncio.sleep(5)
    await send_telegram_message("Bot is processing data...")

# Function to log trades
def log_trade(data):

    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w') as f:
            json.dump([], f) 

    # Append new trade log to the file
    with open(LOG_FILE, 'r') as f:
        logs = json.load(f)
    logs.append(data) 

    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=4)

# Calculate Stochastic Oscillator
def calculate_stoch(high, low, close, PERIOD, K, D):
    lowest_low = low.rolling(PERIOD).min()
    highest_high = high.rolling(PERIOD).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    stoch_d = stoch_k.rolling(D).mean()
    return stoch_k, stoch_d

# Fetch historical klines
def fetch_klines(symbol, interval, lookback='50'):
    print(f"Fetching klines for {symbol} with interval {interval} and lookback {lookback}")
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].astype(float)
    print(f"Fetched {len(df)} rows of data.")
    return df

# Fetch symbol information for precision and step size
def get_symbol_info(symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            return s
    return None

# Fetch available USDT balance
def get_usdt_balance():
    balance = client.futures_account_balance()
    for asset in balance:
        if asset['asset'] == 'USDT':
            return float(asset['balance'])
    return 0.0

def calculate_roi(entry_price, current_price, position_amt, margin_used):
    if margin_used == 0:
        return 0.0
    return ((current_price - entry_price) * position_amt) / margin_used * 100

# Update in the get_position function to calculate ROI and display as percentage
def get_position(symbol):
    positions = client.futures_position_information()
    for pos in positions:
        if pos['symbol'] == symbol:
            position_amt = float(pos['positionAmt'])
            entry_price = float(pos['entryPrice'])
            current_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
            margin_used = abs(position_amt) * entry_price  # Adjust based on leverage
            unrealized_profit = (current_price - entry_price) * position_amt
            roi = (unrealized_profit / margin_used) * 100  # ROI as a percentage of margin used
            return position_amt, roi, unrealized_profit
    return 0, 0, 0

# Adjust quantity to match Binance rules
def round_quantity(symbol, quantity):
    symbol_info = get_symbol_info(symbol)
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'LOT_SIZE':
            min_qty = float(filt['minQty'])
            step_size = float(filt['stepSize'])
            quantity = max(quantity, min_qty)
            quantity = round(quantity - (quantity % step_size), 8) 
            return quantity
    return quantity

# Function to get the current market price of the symbol
def get_market_price(symbol):
    try:
        price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
        return price
    except Exception as e:
        print(f"Error getting market price: {e}")
        return None
    
# Adjust price to match Binance rules
def round_price(symbol, price):
    symbol_info = get_symbol_info(symbol)
    for filt in symbol_info['filters']:
        if filt['filterType'] == 'PRICE_FILTER':
            tick_size = float(filt['tickSize'])
            price = round(price - (price % tick_size), 8)  # Align price with tick size
            return price
    return price

def place_order(symbol, side, usdt_balance, reason_to_open):
    trade_amount = usdt_balance * 0.32  # 30% of available USDT balance
    print(f"30% of available USDT balance for trade: {trade_amount}")

    try:
        price = get_market_price(symbol)
        if price is None:
            return

        # Adjust the price for limit order
        limit_price = round_price(symbol, price)
        
        quantity = trade_amount / limit_price
        quantity = round(quantity, 3)  # Adjust to Binance's minimum step size

        notional = limit_price * quantity
        if notional < 100:
            print(f"Notional value {notional} is too small, adjusting quantity to meet minimum notional.")
            quantity = 100 / limit_price
            quantity = round(quantity, 3)

        if quantity <= 0:
            print("Calculated quantity is too small to trade.")
            return

        print(f"Placing limit order: {side} {quantity} {symbol} at {limit_price}")
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=limit_price,
            timeInForce=TIME_IN_FORCE_GTC
        )
        print(f"Order placed successfully: {order}")

        # Log trade details
        log_trade({
            "USDT_balance_before_trade": usdt_balance,
            "trade_side": side,
            "trade_quantity": quantity,
            "trade_price": limit_price,
            "reason_to_open": reason_to_open,
            "timestamp": pd.Timestamp.now().isoformat()
        })

    except Exception as e:
        print(f"Error placing order: {e}")

def close_position(symbol, side, quantity, reason_to_close):
    print(f"Closing position: {side} {quantity} {symbol}. Reason: {reason_to_close}")
    try:
        price = get_market_price(symbol)
        if price is None:
            return

        # Adjust the price slightly for limit orders
        if side == SIDE_BUY:
            limit_price = price * 1.01  # 1% above current price
        elif side == SIDE_SELL:
            limit_price = price * 0.99  # 1% below current price

        # Align limit price with the tick size
        limit_price = round_price(symbol, limit_price)

        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type=ORDER_TYPE_LIMIT,
            quantity=quantity,
            price=limit_price,  # Use the aligned price
            timeInForce=TIME_IN_FORCE_GTC  # Good Till Canceled
        )
        print(f"Position closed successfully: {order}")

        # Fetch updated USDT balance
        new_usdt_balance = get_usdt_balance()

        # Log trade details
        log_trade({
            "new_USDT_balance": new_usdt_balance,
            "closing_side": side,
            "closing_quantity": quantity,
            "closing_price": limit_price,
            "reason_to_close": reason_to_close,
            "timestamp": pd.Timestamp.now().isoformat()
        })

    except Exception as e:
        print(f"Error closing position: {e}")
                


# Main loop displaying ROI as percentage
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