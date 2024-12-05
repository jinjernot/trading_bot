from binance.enums import *
from src.telegram_bot import *
from data.stochastic import *
from data.get_data import *
from src.trade import *
import asyncio

# Parameters
symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']  # Add your symbols here
interval = Client.KLINE_INTERVAL_1MINUTE
leverage = 10


async def process_symbol(symbol):
    print(f"Setting leverage for {symbol} to {leverage}")
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage set successfully for {symbol}.")
    except Exception as e:
        print(f"Error setting leverage for {symbol}: {e}")
        return
    
    try:
        print(f"\n--- New Iteration for {symbol} ---")
        # Fetch klines and calculate support and resistance
        df, support, resistance = fetch_klines(symbol, interval)
        
        # Calculate Stochastic indicators
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        print(f"Stochastic K for {symbol}: {stoch_k.iloc[-3:].values}")
        print(f"Stochastic D for {symbol}: {stoch_d.iloc[-3:].values}")
                
        # Get current position and ROI
        position, roi, unrealized_profit, margin_used = get_position(symbol)
        print(f"Position for {symbol}: {position}, ROI: {roi:.2f}%, Unrealized Profit: {unrealized_profit:.2f}") 
        print(f"Margin Used for {symbol}: {margin_used}")
        
        # Fetch available USDT balance
        usdt_balance = get_usdt_balance()
        print(f"Available USDT balance for {symbol}: {usdt_balance}")
        
        # Detect market trend using your custom function
        trend = detect_trend(df)
        print(f"Market trend for {symbol}: {trend}")
        
        # Long position logic (only in uptrend)
        if position > 0:
            if roi >= 1:  # Check ROI for long position
                close_position(symbol, SIDE_SELL, abs(position), "ROI >= 1%")
                message = f"Long position closed for {symbol}: ROI >= 1% (Current ROI: {roi:.2f}%)"
                await send_telegram_message(message)
            elif stoch_k.iloc[-1] > OVERBOUGHT:
                close_position(symbol, SIDE_SELL, abs(position), "Stochastic overbought threshold")
                message = f"Long position closed for {symbol}: Stochastic overbought (Stochastic K: {stoch_k.iloc[-1]:.2f})"
                await send_telegram_message(message)
        
        # Short position logic (only in downtrend)
        elif position < 0:
            # Close short position if ROI is greater than 2%
            if roi >= 2:  
                close_position(symbol, SIDE_BUY, abs(position), "ROI >= 2%")
                message = f"Short position closed for {symbol}: ROI >= 2% (Current ROI: {roi:.2f}%)"
                await send_telegram_message(message)
            # Close short position if Stochastic is oversold
            elif stoch_k.iloc[-1] < OVERSOLD:
                close_position(symbol, SIDE_BUY, abs(position), "Stochastic oversold threshold")
                message = f"Short position closed for {symbol}: Stochastic oversold (Stochastic K: {stoch_k.iloc[-1]:.2f})"
                await send_telegram_message(message)

        # Open New Positions
        if position == 0:
            # Long logic (only in uptrend)
            if trend == 'uptrend' and (stoch_k.iloc[-1] > stoch_d.iloc[-1] and 
                stoch_k.iloc[-2] <= stoch_d.iloc[-2] and 
                stoch_k.iloc[-1] < OVERSOLD and 
                df['close'].iloc[-1] > support):
                place_order(symbol, SIDE_BUY, usdt_balance, "Bullish crossover with support confirmation")
                message = (f"New Buy order placed for {symbol}: Bullish crossover with support confirmation\n"
                           f"Support: {support}, Resistance: {resistance}\n"
                           f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                           f"Price: {df['close'].iloc[-1]:.2f}")
                await send_telegram_message(message)
                
            # Short logic (only in downtrend)
            if trend == 'downtrend' and (stoch_k.iloc[-1] < stoch_d.iloc[-1] and 
                stoch_k.iloc[-2] >= stoch_d.iloc[-2] and 
                stoch_k.iloc[-1] > OVERBOUGHT and 
                df['close'].iloc[-1] < resistance):  # Check if price is below resistance
                place_order(symbol, SIDE_SELL, usdt_balance, "Bearish crossover with resistance confirmation")
                message = (f"New Sell order placed for {symbol}: Bearish crossover with resistance confirmation\n"
                           f"Support: {support}, Resistance: {resistance}\n"
                           f"Stochastic K: {stoch_k.iloc[-1]:.2f}, Stochastic D: {stoch_d.iloc[-1]:.2f}\n"
                           f"Price: {df['close'].iloc[-1]:.2f}")
                await send_telegram_message(message)

        print(f"Sleeping for 60 seconds...\n")
        await asyncio.sleep(10)

    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(10)

async def main():
    while True:
        for symbol in symbols:
            await process_symbol(symbol)
        # Sleep between iterations if necessary
        print("Sleeping for 10 seconds before scanning the next symbol...")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
