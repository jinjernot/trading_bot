from binance.enums import *
from src.trade import place_order
from data.indicators import *
from config.settings import *



async def check_fib_pullback_long_entry(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a LONG buying opportunity using a confirmation scoring system.
    """
    # --- Core Condition 1: Moderate 4-hour uptrend ---
    adx_4h = df_4h['ADX'].iloc[-1]
    price_sma_4h = df_4h['price_sma_50'].iloc[-1]
    last_close_4h = df_4h['close'].iloc[-1]
    is_strong_uptrend = adx_4h > 15 and last_close_4h > price_sma_4h
    if not is_strong_uptrend:
        return

    # --- Core Condition 2: Price at the 0.618 Fibonacci level ---
    swing_low, swing_high, fib_levels = find_swing_points_and_fib(df_15m, trend='long')
    if not fib_levels:
        return
    last_close_15m = df_15m['close'].iloc[-1]
    target_fib_level = fib_levels['0.618']
    price_at_fib_level = last_close_15m <= target_fib_level and last_close_15m > swing_low
    
    if price_at_fib_level:
        # --- Calculate all confirmation indicators ---
        df_15m = calculate_hull_moving_average(df_15m, period=14)
        df_15m = calculate_bollinger_bands(df_15m, period=20)
        df_15m = add_candlestick_patterns(df_15m)
        df_15m = add_volume_sma(df_15m, period=20)

        # --- Tally the confirmation signals ---
        confirmation_score = 0
        confirmations = []

        if df_15m['hma_14'].iloc[-1] > df_15m['hma_14'].iloc[-2]:
            confirmation_score += 1
            confirmations.append("HMA Sloping Up")
        
        lower_bb = df_15m['BB_Lower'].iloc[-1]
        if abs(last_close_15m - lower_bb) / last_close_15m < 0.005: # Price within 0.5% of lower BB
            confirmation_score += 1
            confirmations.append("Near Lower Bollinger Band")

        if df_15m['bullish_pattern'].iloc[-1] == 1:
            confirmation_score += 1
            confirmations.append("Bullish Candlestick Pattern")

        if df_15m['volume'].iloc[-1] > (df_15m['volume_sma_20'].iloc[-1] * 1.5):
            confirmation_score += 1
            confirmations.append("Volume Spike")

        # --- Check if the score meets the minimum requirement ---
        if confirmation_score >= MINIMUM_CONFIRMATIONS:
            print(f"🚀🚀🚀 LONG SIGNAL FOR {symbol} ({confirmation_score}/4 Confirmations) 🚀🚀🚀")
            print(f"Found confirmations: {', '.join(confirmations)}")
            
            atr_value = df_15m['atr'].iloc[-1]
            await place_order(
                symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
                reason_to_open=f"Fibonacci with {confirmation_score}/4 confirmations",
                stop_loss_price=swing_low * 0.995,
                atr_value=atr_value, df=df_15m,
                support_4h=swing_low, resistance_4h=swing_high, adx_value=adx_4h
            )
            return True
    return False

async def check_fib_retrace_short_entry(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a SHORT selling opportunity using a confirmation scoring system.
    """
    # --- Core Condition 1: Moderate 4-hour downtrend ---
    adx_4h = df_4h['ADX'].iloc[-1]
    price_sma_4h = df_4h['price_sma_50'].iloc[-1]
    last_close_4h = df_4h['close'].iloc[-1]
    is_strong_downtrend = adx_4h > 15 and last_close_4h < price_sma_4h
    if not is_strong_downtrend:
        return

    # --- Core Condition 2: Price at the 0.618 Fibonacci level ---
    swing_low, swing_high, fib_levels = find_swing_points_and_fib(df_15m, trend='short')
    if not fib_levels:
        return
    last_close_15m = df_15m['close'].iloc[-1]
    target_fib_level = fib_levels['0.618']
    price_at_fib_level = last_close_15m >= target_fib_level and last_close_15m < swing_high

    if price_at_fib_level:
        # --- Calculate all confirmation indicators ---
        df_15m = calculate_hull_moving_average(df_15m, period=14)
        df_15m = calculate_bollinger_bands(df_15m, period=20)
        df_15m = add_candlestick_patterns(df_15m)
        df_15m = add_volume_sma(df_15m, period=20)

        # --- Tally the confirmation signals ---
        confirmation_score = 0
        confirmations = []

        if df_15m['hma_14'].iloc[-1] < df_15m['hma_14'].iloc[-2]:
            confirmation_score += 1
            confirmations.append("HMA Sloping Down")

        upper_bb = df_15m['BB_Upper'].iloc[-1]
        if abs(last_close_15m - upper_bb) / last_close_15m < 0.005: # Price within 0.5% of upper BB
            confirmation_score += 1
            confirmations.append("Near Upper Bollinger Band")

        if df_15m['bearish_pattern'].iloc[-1] == 1:
            confirmation_score += 1
            confirmations.append("Bearish Candlestick Pattern")

        if df_15m['volume'].iloc[-1] > (df_15m['volume_sma_20'].iloc[-1] * 1.5):
            confirmation_score += 1
            confirmations.append("Volume Spike")

        # --- Check if the score meets the minimum requirement ---
        if confirmation_score >= MINIMUM_CONFIRMATIONS:
            print(f"🔥🔥🔥 SHORT SIGNAL FOR {symbol} ({confirmation_score}/4 Confirmations) 🔥🔥🔥")
            print(f"Found confirmations: {', '.join(confirmations)}")

            atr_value = df_15m['atr'].iloc[-1]
            await place_order(
                symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
                reason_to_open=f"Fibonacci with {confirmation_score}/4 confirmations",
                stop_loss_price=swing_high * 1.005,
                atr_value=atr_value, df=df_15m,
                support_4h=swing_low, resistance_4h=swing_high, adx_value=adx_4h
            )
            return True
    return False