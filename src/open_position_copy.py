from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *


async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value):
    """
    Opens a long position only if multiple conditions (Stochastic, Price SMA, RSI, Volume) are met.
    """
    last_close = df['close'].iloc[-1]
    last_rsi = df['rsi'].iloc[-1]
    last_volume = df['volume'].iloc[-1]
    price_sma = df['price_sma_50'].iloc[-1]
    volume_sma = df['volume_sma_20'].iloc[-1]

    # --- Entry Conditions for a High-Quality Long Trade ---
    price_above_sma = last_close > price_sma
    rsi_is_bullish = last_rsi > 50 and last_rsi < 75
    volume_is_strong = last_volume > volume_sma
    stochastic_signal = (
        stoch_k.iloc[-1] > OVERSOLD and
        stoch_k.iloc[-2] <= OVERSOLD and
        stoch_k.iloc[-1] > stoch_d.iloc[-1]
    )

    # --- Final Check: All conditions must be true ---
    if stochastic_signal and price_above_sma and rsi_is_bullish and volume_is_strong:
        print(f"Placing order for {symbol} due to strong bullish confluence.")
        
        place_order(
            symbol=symbol, 
            side=SIDE_BUY, 
            usdt_balance=usdt_balance, 
            reason_to_open="Bullish confluence entry", 
            stop_loss_atr_multiplier=1.5, 
            atr_value=atr_value
        )
        return True
    else:
        return False


async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value):
    """
    Opens a short position only if multiple conditions (Stochastic, Price SMA, RSI, Volume) are met.
    """
    # Define the values from the last row of the DataFrame for easy access
    last_close = df['close'].iloc[-1]
    last_rsi = df['rsi'].iloc[-1]
    last_volume = df['volume'].iloc[-1]
    price_sma = df['price_sma_50'].iloc[-1]
    volume_sma = df['volume_sma_20'].iloc[-1]

    # --- Entry Conditions for a High-Quality Short Trade ---

    # 1. Price Trend Filter: The closing price must be below the 50-period moving average.
    price_below_sma = last_close < price_sma

    # 2. Momentum Filter: The RSI must show bearish momentum (below 50) but not be oversold (e.g., above 25).
    rsi_is_bearish = last_rsi < 50 and last_rsi > 25

    # 3. Volume Confirmation: The volume of the last candle must be greater than the average volume.
    volume_is_strong = last_volume > volume_sma

    # 4. Stochastic Oscillator Signal: The original entry trigger, crossing down from overbought.
    stochastic_signal = (
        stoch_k.iloc[-1] < OVERBOUGHT and
        stoch_k.iloc[-2] >= OVERBOUGHT and
        stoch_k.iloc[-1] < stoch_d.iloc[-1]
    )

    # --- Final Check: All conditions must be true ---
    if stochastic_signal and price_below_sma and rsi_is_bearish and volume_is_strong:
        print(f"Placing order for {symbol} due to strong bearish confluence.")
        
        place_order(
            symbol=symbol, 
            side=SIDE_SELL, 
            usdt_balance=usdt_balance, 
            reason_to_open="Bearish confluence entry", 
            stop_loss_atr_multiplier=1.5, 
            atr_value=atr_value
        )
        return True
    else:
        return False