import sys
from binance.enums import *
from src.trade import place_order
from data.indicators import *
from data.indicators import calculate_volume_profile_full, calculate_roc, calculate_fib_extensions
from config.settings import *
from config.settings import strategy_toggles



async def check_fib_pullback_long_entry(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a LONG buying opportunity using a confirmation scoring system.
    """
    # --- Global BTC Filter ---
    from src.state_manager import bot_state
    if getattr(sys.modules['config.settings'], 'ENABLE_GLOBAL_BTC_FILTER', True) and bot_state.global_btc_trend == 'BEARISH' and symbol != 'BTCUSDT':
        if VERBOSE_LOGGING:
            print(f"Skipping LONG for {symbol}: Global BTC trend is BEARISH.")
        return False

    # --- Time Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_TIME_FILTER:
        from datetime import datetime, timezone
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= 1 and current_hour < 7:
            if VERBOSE_LOGGING:
                print(f"  FIB LONG rejected for {symbol}: Time Filter active (Asian dead hours).")
            return False

    # --- SMA 200 Trend Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_SMA_200_FILTER and 'price_sma_200' in df_4h.columns:
        last_close = df_15m['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close < sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"  FIB LONG rejected for {symbol}: Price {last_close:.4f} < 4H SMA 200 {sma_200_4h:.4f}")
            return False

    # --- Core Condition 1: Moderate 4-hour uptrend ---
    adx_4h = df_4h['ADX'].iloc[-1]
    price_sma_4h = df_4h['price_sma_50'].iloc[-1]
    last_close_4h = df_4h['close'].iloc[-1]
    is_strong_uptrend = adx_4h > FIB_ADX_THRESHOLD and last_close_4h > price_sma_4h
    if not is_strong_uptrend:
        return False

    # --- Core Condition 2: Golden Pocket Fibonacci Zone (0.618 to 0.65) ---
    # The "Golden Pocket" is the institutional entry zone between 0.618 and 0.65 retracement.
    # It is a tighter, higher-probability zone than a loose ±1% band.
    # Adopted from ICT (Inner Circle Trader) methodology used by prop desk traders.
    swing_low, swing_high, fib_levels = find_swing_points_and_fib(df_15m, trend='long')
    if not fib_levels:
        return False
    last_close_15m = df_15m['close'].iloc[-1]
    fib_618 = fib_levels['0.618']
    fib_786 = fib_levels['0.786']
    # Golden Pocket: between 0.618 and midpoint of 0.618–0.786 (~0.65)
    golden_pocket_top = fib_618
    golden_pocket_bottom = fib_618 - (fib_618 - fib_786) * 0.5  # midpoint toward 0.786
    price_in_golden_pocket = golden_pocket_bottom <= last_close_15m <= golden_pocket_top

    # --- VWAP Confluence Check ---
    if 'vwap' not in df_15m.columns:
        return False
    vwap_price = df_15m['vwap'].iloc[-1]
    # VWAP must be within 0.5% of the 0.618 Fib level
    is_vwap_confluent = abs(vwap_price - fib_618) / fib_618 <= 0.005

    # --- Volume Profile (VPVR) Check — Institutional Value Area ---
    poc_price, vah_price, val_price = calculate_volume_profile_full(df_15m, bins=50)
    is_near_poc = abs(fib_618 - poc_price) / fib_618 < 0.015
    is_in_value_area_low = fib_618 <= val_price * 1.01
    is_vpvr_confluent = is_near_poc or is_in_value_area_low

    if price_in_golden_pocket and is_vwap_confluent and is_vpvr_confluent:
        # --- Calculate all confirmation indicators ---
        df_15m = add_candlestick_patterns(df_15m)
        df_15m = add_volume_sma(df_15m, period=20)

        # Strict Momentum Breakout Requirement (Trigger Pull)
        # Live price must break above the high of the previous closed candle
        if last_close_15m <= df_15m['high'].iloc[-2]:
            return False

        # --- Tally the confirmation signals ---
        confirmations = []

        if df_15m['bullish_pattern'].iloc[-2] == 1:
            confirmations.append("Bullish Candlestick Pattern (Closed)")

        if df_15m['volume'].iloc[-2] > (df_15m['volume_sma_20'].iloc[-2] * 1.5):
            confirmations.append("Volume Spike (Closed)")

        # --- Check if the score meets the minimum requirement ---
        if len(confirmations) > 0:
            # Calculate Fibonacci extension targets (institutional TP levels)
            ext_levels = calculate_fib_extensions(swing_low, swing_high, trend='long')
            tp3_price = ext_levels.get('1.272', 0)
            tp4_price = ext_levels.get('1.618', 0)

            print(f"\n{'='*70}")
            print(f"📊 FIBONACCI LONG ENTRY SIGNAL: {symbol}")
            print(f"{'='*70}")
            print(f"Entry Type: GOLDEN POCKET PULLBACK (Institutional)")
            print(f"Confirmations: {len(confirmations)} - {', '.join(confirmations)}")
            print(f"\n--- Entry Zone ---")
            print(f"  Golden Pocket: {golden_pocket_bottom:.4f} – {golden_pocket_top:.4f}")
            print(f"\n--- 4-Hour Trend ---")
            print(f"  ADX: {adx_4h:.2f}")
            print(f"  Price vs SMA50: {last_close_4h:.2f} vs {price_sma_4h:.2f}")
            print(f"\n--- Fibonacci Levels ---")
            print(f"  Swing Low: {swing_low:.4f}")
            print(f"  Swing High: {swing_high:.4f}")
            print(f"  0.618 (entry): {fib_618:.4f}")
            print(f"  TP3 (1.272 ext): {tp3_price:.4f}")
            print(f"  TP4 (1.618 ext): {tp4_price:.4f}")
            print(f"  Volume POC: {poc_price:.4f} | VAH: {vah_price:.4f} | VAL: {val_price:.4f}")
            print(f"  VPVR Confluent: {'Near POC' if is_near_poc else 'At/Below VAL'}")
            print(f"  VWAP Confluent: {vwap_price:.4f} (Matches 0.618)")
            print(f"  Current Price: {last_close_15m:.4f}")
            print(f"{'='*70}\n")

            atr_value = df_15m['atr'].iloc[-1]
            order_placed = await place_order(
                symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
                reason_to_open=f"Golden Pocket Fib ({', '.join(confirmations)}) | TP3={tp3_price:.4f} TP4={tp4_price:.4f}",
                stop_loss_price=swing_low * (1 - FIB_STOP_BUFFER),
                take_profit_price=tp3_price if tp3_price > 0 else None,
                atr_value=atr_value, df=df_15m,
                support_4h=swing_low, resistance_4h=swing_high, adx_value=adx_4h
            )
            # Return the actual result — if stop-loss failed, place_order returns False
            # and we must NOT claim the trade was placed
            return order_placed if order_placed is not None else False
    return False

async def check_fib_retrace_short_entry(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a SHORT selling opportunity using a confirmation scoring system.
    """
    # --- Global BTC Filter ---
    from src.state_manager import bot_state
    if getattr(sys.modules['config.settings'], 'ENABLE_GLOBAL_BTC_FILTER', True) and bot_state.global_btc_trend == 'BULLISH' and symbol != 'BTCUSDT':
        if VERBOSE_LOGGING:
            print(f"Skipping SHORT for {symbol}: Global BTC trend is BULLISH.")
        return False

    # --- Time Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_TIME_FILTER:
        from datetime import datetime, timezone
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= 1 and current_hour < 7:
            if VERBOSE_LOGGING:
                print(f"  FIB SHORT rejected for {symbol}: Time Filter active (Asian dead hours).")
            return False

    # --- SMA 200 Trend Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_SMA_200_FILTER and 'price_sma_200' in df_4h.columns:
        last_close = df_15m['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close > sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"  FIB SHORT rejected for {symbol}: Price {last_close:.4f} > 4H SMA 200 {sma_200_4h:.4f}")
            return False

    # --- Core Condition 1: Moderate 4-hour downtrend ---
    adx_4h = df_4h['ADX'].iloc[-1]
    price_sma_4h = df_4h['price_sma_50'].iloc[-1]
    last_close_4h = df_4h['close'].iloc[-1]
    is_strong_downtrend = adx_4h > FIB_ADX_THRESHOLD and last_close_4h < price_sma_4h
    if not is_strong_downtrend:
        return False

    # --- Core Condition 2: Golden Pocket Fibonacci Zone (0.618 to 0.65) ---
    swing_low, swing_high, fib_levels = find_swing_points_and_fib(df_15m, trend='short')
    if not fib_levels:
        return False
    last_close_15m = df_15m['close'].iloc[-1]
    fib_618 = fib_levels['0.618']
    fib_786 = fib_levels['0.786']
    # Golden Pocket for shorts: between 0.618 and midpoint of 0.618–0.786
    golden_pocket_bottom = fib_618
    golden_pocket_top = fib_618 + (fib_786 - fib_618) * 0.5  # midpoint toward 0.786
    price_in_golden_pocket = golden_pocket_bottom <= last_close_15m <= golden_pocket_top

    # --- VWAP Confluence Check ---
    if 'vwap' not in df_15m.columns:
        return False
    vwap_price = df_15m['vwap'].iloc[-1]
    # VWAP must be within 0.5% of the 0.618 Fib level
    is_vwap_confluent = abs(vwap_price - fib_618) / fib_618 <= 0.005

    # --- Volume Profile (VPVR) Check — Institutional Value Area ---
    poc_price, vah_price, val_price = calculate_volume_profile_full(df_15m, bins=50)
    is_near_poc = abs(fib_618 - poc_price) / fib_618 < 0.015
    is_in_value_area_high = fib_618 >= vah_price * 0.99
    is_vpvr_confluent = is_near_poc or is_in_value_area_high

    if price_in_golden_pocket and is_vwap_confluent and is_vpvr_confluent:
        # --- Calculate all confirmation indicators ---
        df_15m = add_candlestick_patterns(df_15m)
        df_15m = add_volume_sma(df_15m, period=20)

        # Strict Momentum Breakout Requirement (Trigger Pull)
        # Live price must break below the low of the previous closed candle
        if last_close_15m >= df_15m['low'].iloc[-2]:
            return False

        # --- Tally the confirmation signals ---
        confirmations = []

        if df_15m['bearish_pattern'].iloc[-2] == 1:
            confirmations.append("Bearish Candlestick Pattern (Closed)")

        if df_15m['volume'].iloc[-2] > (df_15m['volume_sma_20'].iloc[-2] * 1.5):
            confirmations.append("Volume Spike (Closed)")

        # --- Check if the score meets the minimum requirement ---
        if len(confirmations) > 0:
            # Fibonacci extension targets (institutional TP levels below swing low)
            ext_levels = calculate_fib_extensions(swing_low, swing_high, trend='short')
            tp3_price = ext_levels.get('1.272', 0)
            tp4_price = ext_levels.get('1.618', 0)

            print(f"\n{'='*70}")
            print(f"🔥 FIBONACCI SHORT ENTRY SIGNAL: {symbol}")
            print(f"{'='*70}")
            print(f"Entry Type: GOLDEN POCKET RETRACEMENT (Institutional)")
            print(f"Confirmations: {len(confirmations)} - {', '.join(confirmations)}")
            print(f"\n--- Entry Zone ---")
            print(f"  Golden Pocket: {golden_pocket_bottom:.4f} – {golden_pocket_top:.4f}")
            print(f"\n--- 4-Hour Trend ---")
            print(f"  ADX: {adx_4h:.2f}")
            print(f"  Price vs SMA50: {last_close_4h:.2f} vs {price_sma_4h:.2f}")
            print(f"\n--- Fibonacci Levels ---")
            print(f"  Swing High: {swing_high:.4f}")
            print(f"  Swing Low: {swing_low:.4f}")
            print(f"  0.618 (entry): {fib_618:.4f}")
            print(f"  TP3 (1.272 ext): {tp3_price:.4f}")
            print(f"  TP4 (1.618 ext): {tp4_price:.4f}")
            print(f"  Volume POC: {poc_price:.4f} | VAH: {vah_price:.4f} | VAL: {val_price:.4f}")
            print(f"  VPVR Confluent: {'Near POC' if is_near_poc else 'At/Above VAH'}")
            print(f"  VWAP Confluent: {vwap_price:.4f} (Matches 0.618)")
            print(f"  Current Price: {last_close_15m:.4f}")
            print(f"{'='*70}\n")

            atr_value = df_15m['atr'].iloc[-1]
            order_placed = await place_order(
                symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
                reason_to_open=f"Golden Pocket Fib ({', '.join(confirmations)}) | TP3={tp3_price:.4f} TP4={tp4_price:.4f}",
                stop_loss_price=swing_high * (1 + FIB_STOP_BUFFER),
                take_profit_price=tp3_price if tp3_price > 0 else None,
                atr_value=atr_value, df=df_15m,
                support_4h=swing_low, resistance_4h=swing_high, adx_value=adx_4h
            )
            return order_placed if order_placed is not None else False
    return False