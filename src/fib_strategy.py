from binance.enums import *
from src.trade import place_order
from data.indicators import *
from config.settings import *

async def check_fib_pullback_entry(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a buying opportunity based on a pullback to a Fibonacci level in an uptrend.
    This version enters the trade as soon as the price hits the target Fib level.
    """
    # --- 1. Confirm Higher Timeframe (4h) Uptrend ---
    adx_4h = df_4h['ADX'].iloc[-1]
    price_sma_4h = df_4h['price_sma_50'].iloc[-1]
    last_close_4h = df_4h['close'].iloc[-1]

    is_strong_uptrend = adx_4h > 25 and last_close_4h > price_sma_4h
    if not is_strong_uptrend:
        if VERBOSE_LOGGING:
            print(f"FibBot ({symbol}): Skipping. No strong 4h uptrend confirmed (ADX: {adx_4h:.2f}).")
        return

    # --- 2. Find Swing Points and Fibonacci Levels on 15m Chart ---
    swing_low, swing_high, fib_levels = find_swing_points_and_fib(df_15m)

    if not fib_levels:
        if VERBOSE_LOGGING:
            print(f"FibBot ({symbol}): Skipping. Could not determine valid swing points.")
        return

    # --- 3. Check if Price Has Pulled Back to the 0.618 Level ---
    last_close_15m = df_15m['close'].iloc[-1]
    target_fib_level = fib_levels['0.618']
    
    # We enter if the last close is at or below the 0.618 level, but still above the swing low.
    if last_close_15m <= target_fib_level and last_close_15m > swing_low:
        print(f"🚀🚀🚀 FIBONACCI PULLBACK SIGNAL FOR {symbol} 🚀🚀🚀")
        print(f"Price pulled back to the 0.618 level (${target_fib_level:.4f}). Entering trade.")

        # --- Place the Trade ---
        atr_value = df_15m['atr'].iloc[-1]
        
        await place_order(
            symbol=symbol,
            side=SIDE_BUY,
            usdt_balance=usdt_balance,
            reason_to_open=f"Fibonacci pullback to 0.618 level",
            stop_loss_price=swing_low * 0.995, # 0.5% buffer below the swing low
            atr_value=atr_value,
            df=df_15m,
            support_4h=swing_low, 
            resistance_4h=swing_high,
            adx_value=adx_4h
        )
        return True
    return False