from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *

async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate):
    """
    Opens a long position only if multiple conditions (Stochastic, Price SMA, RSI, Volume, Funding Rate) are met.
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
    funding_rate_is_healthy = funding_rate < 0.0004 

    # --- Final Check: All conditions must be true ---
    if stochastic_signal and price_above_sma and rsi_is_bullish and volume_is_strong and funding_rate_is_healthy:
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


async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate):
    """
    Opens a short position only if multiple conditions (Stochastic, Price SMA, RSI, Volume, Funding Rate) are met.
    """
    last_close = df['close'].iloc[-1]
    last_rsi = df['rsi'].iloc[-1]
    last_volume = df['volume'].iloc[-1]
    price_sma = df['price_sma_50'].iloc[-1]
    volume_sma = df['volume_sma_20'].iloc[-1]

    # --- Entry Conditions for a High-Quality Short Trade ---
    price_below_sma = last_close < price_sma
    rsi_is_bearish = last_rsi < 50 and last_rsi > 25
    volume_is_strong = last_volume > volume_sma
    stochastic_signal = (
        stoch_k.iloc[-1] < OVERBOUGHT and
        stoch_k.iloc[-2] >= OVERBOUGHT and
        stoch_k.iloc[-1] < stoch_d.iloc[-1]
    )
    funding_rate_is_healthy = funding_rate > -0.0004

    # --- Final Check: All conditions must be true ---
    if stochastic_signal and price_below_sma and rsi_is_bearish and volume_is_strong and funding_rate_is_healthy:
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