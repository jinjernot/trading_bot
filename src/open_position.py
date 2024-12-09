from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message

async def open_position_logic(symbol, usdt_balance, df, stoch_k, resistance, support, nice_interval, atr):
    """
    Logic for opening positions based on conditions like stochastic indicators, support/resistance levels, and ATR.
    
    Parameters:
        symbol (str): The trading pair (e.g., BTCUSDT).
        usdt_balance (float): Current USDT balance.
        df (DataFrame): Dataframe with historical price data.
        stoch_k (Series): Stochastic K indicator.
        resistance (float): Calculated resistance level.
        support (float): Calculated support level.
        nice_interval (str): Readable interval (e.g., '1h').
        atr (float): Average True Range (ATR) for risk management.
    """
    try:
        # Define position size based on risk management
        risk_percentage = 0.01  # Risk 1% of USDT balance per trade
        position_size_usdt = usdt_balance * risk_percentage

        # Calculate quantity to buy/sell
        price = df['close'].iloc[-1]
        quantity = round(position_size_usdt / price, 6)  # Adjust precision based on the symbol

        print(f"Opening position for {symbol}: USDT Balance = {usdt_balance:.2f}, Position Size = {position_size_usdt:.2f} USDT, Quantity = {quantity:.6f}")

        # Buy condition: Stochastic K is oversold and price near support
        if stoch_k.iloc[-1] < 20 and df['close'].iloc[-1] <= support:
            await place_order(symbol, SIDE_BUY, quantity, "Stochastic oversold and price near support")
            message = f"🟢 Opened LONG position for {symbol} ({nice_interval}): Stochastic oversold (Stochastic K: {stoch_k.iloc[-1]:.2f}) and price near support ({support:.2f})"
            await send_telegram_message(message)

        # Sell condition: Stochastic K is overbought and price near resistance
        elif stoch_k.iloc[-1] > 80 and df['close'].iloc[-1] >= resistance:
            await place_order(symbol, SIDE_SELL, quantity, "Stochastic overbought and price near resistance")
            message = f"🔴 Opened SHORT position for {symbol} ({nice_interval}): Stochastic overbought (Stochastic K: {stoch_k.iloc[-1]:.2f}) and price near resistance ({resistance:.2f})"
            await send_telegram_message(message)

        else:
            print(f"No open position conditions met for {symbol}.")
    
    except Exception as e:
        print(f"Error opening position for {symbol}: {e}")
