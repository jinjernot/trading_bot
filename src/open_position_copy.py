from binance.enums import *
from src.trade import place_order
from data.indicators import *
from src.telegram_bot import send_telegram_message
from config.settings import *

async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate):
    """
    Opens a long position with candle confirmation and retracement entry.
    """
    # --- MODIFIED: Conditions based on the second-to-last candle ---
    entry_candle_close = df['close'].iloc[-2]
    entry_candle_rsi = df['rsi'].iloc[-2]
    entry_candle_volume = df['volume'].iloc[-2]
    price_sma = df['price_sma_50'].iloc[-2]
    volume_sma = df['volume_sma_20'].iloc[-2]
    short_term_sma = df['price_sma_9'].iloc[-1] # For retracement

    # --- MODIFIED: Confirmation from the most recent candle ---
    confirmation_candle_close = df['close'].iloc[-1]

    # --- Entry Conditions ---
    price_above_sma = entry_candle_close > price_sma
    rsi_is_bullish = entry_candle_rsi > 50 and entry_candle_rsi < 75
    volume_is_strong = entry_candle_volume > volume_sma
    stochastic_signal = (
        stoch_k.iloc[-2] > OVERSOLD and
        stoch_k.iloc[-3] <= OVERSOLD and
        stoch_k.iloc[-2] > stoch_d.iloc[-2]
    )
    funding_rate_is_healthy = funding_rate < 0.0004
    
    # --- NEW: Confirmation Conditions ---
    confirmation_is_bullish = confirmation_candle_close > entry_candle_close
    price_pulled_back = confirmation_candle_close < short_term_sma

    # --- Final Check: All conditions must be true ---
    if (stochastic_signal and 
        price_above_sma and 
        rsi_is_bullish and 
        volume_is_strong and 
        funding_rate_is_healthy and 
        confirmation_is_bullish and
        price_pulled_back):
        
        print(f"Placing order for {symbol} due to strong bullish confluence with confirmation and retracement.")
        
        place_order(
            symbol=symbol, 
            side=SIDE_BUY, 
            usdt_balance=usdt_balance, 
            reason_to_open="Bullish confluence with confirmation and retracement", 
            stop_loss_atr_multiplier=1.5, 
            atr_value=atr_value,
            df=df # Pass the dataframe for dynamic SL
        )
        return True
    else:
        return False


async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate):
    """
    Opens a short position with candle confirmation and retracement entry.
    """
    # --- MODIFIED: Conditions based on the second-to-last candle ---
    entry_candle_close = df['close'].iloc[-2]
    entry_candle_rsi = df['rsi'].iloc[-2]
    entry_candle_volume = df['volume'].iloc[-2]
    price_sma = df['price_sma_50'].iloc[-2]
    volume_sma = df['volume_sma_20'].iloc[-2]
    short_term_sma = df['price_sma_9'].iloc[-1] # For retracement

    # --- MODIFIED: Confirmation from the most recent candle ---
    confirmation_candle_close = df['close'].iloc[-1]

    # --- Entry Conditions ---
    price_below_sma = entry_candle_close < price_sma
    rsi_is_bearish = entry_candle_rsi < 50 and entry_candle_rsi > 25
    volume_is_strong = entry_candle_volume > volume_sma
    stochastic_signal = (
        stoch_k.iloc[-2] < OVERBOUGHT and
        stoch_k.iloc[-3] >= OVERBOUGHT and
        stoch_k.iloc[-2] < stoch_d.iloc[-2]
    )
    funding_rate_is_healthy = funding_rate > -0.0004

    # --- NEW: Confirmation Conditions ---
    confirmation_is_bearish = confirmation_candle_close < entry_candle_close
    price_bounced = confirmation_candle_close > short_term_sma

    # --- Final Check: All conditions must be true ---
    if (stochastic_signal and 
        price_below_sma and 
        rsi_is_bearish and 
        volume_is_strong and 
        funding_rate_is_healthy and
        confirmation_is_bearish and
        price_bounced):
        
        print(f"Placing order for {symbol} due to strong bearish confluence with confirmation and bounce.")
        
        place_order(
            symbol=symbol, 
            side=SIDE_SELL, 
            usdt_balance=usdt_balance, 
            reason_to_open="Bearish confluence with confirmation and bounce", 
            stop_loss_atr_multiplier=1.5, 
            atr_value=atr_value,
            df=df # Pass the dataframe for dynamic SL
        )
        return True
    else:
        return False