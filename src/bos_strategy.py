"""
BOS Momentum Breakout Strategy — Brigadier Bot (Strategy #2)
=============================================================

PURPOSE:
    Captures explosive directional moves that the Pullback strategies miss.
    When a coin rockets in a straight line, there are NO pullbacks to buy.
    This strategy enters AFTER a confirmed structural break + retest,
    riding the continuation wave with institutional-grade precision.

LOGIC (v2 — Retest-Based Entry):
    LONG BREAKOUT:
        1. Price breaks ABOVE the highest high of the last 192 candles (2-day BOS).
        2. Within the next 12 candles (3h), price RETESTS the broken level.
        3. The retest candle shows a lower-wick rejection (>= 30% of candle body).
        4. Volume on the original breakout candle was >= 3x average (institutional).
        5. Price is ABOVE the 1H EMA 21 (trend alignment filter).
        6. Price is ABOVE the 24h rolling VWAP (institutional trend anchor).
        7. 4H ADX > 25 confirms a trending (not choppy) market.
        8. Stop Loss: Below the retest candle's low.
        9. Take Profit: Fibonacci 1.272 extension of the breakout range.

    SHORT BREAKDOWN:
        1. Price breaks BELOW the lowest low of the last 192 candles (2-day BOS).
        2. Within the next 12 candles (3h), price RETESTS the broken level.
        3. The retest candle shows an upper-wick rejection (>= 30% of candle body).
        4. Volume on the original breakdown candle was >= 3x average (institutional).
        5. Price is BELOW the 1H EMA 21 (trend alignment filter).
        6. Price is BELOW the 24h rolling VWAP.
        7. 4H ADX > 25 confirms trending conditions.
        8. Stop Loss: Above the retest candle's high.
        9. Take Profit: Fibonacci 1.272 extension below the breakdown.

    SAFETY CONTROLS:
        - Global 2-hour cooldown between any BOS trades (prevents cluster-bombing).
        - Max 1 BOS trade per scan cycle (opportunity throttling).
        - Hard time filter: ALWAYS blocks during Asian dead hours (01:00-07:00 UTC).
        - Stochastic exhaustion guard still active.

HIERARCHY:
    This runs AFTER the Fibonacci strategy fails to find a setup.
    It is the "rocket rider" — fewer but bigger trades with institutional timing.
"""

import sys
from binance.enums import SIDE_BUY, SIDE_SELL
from src.trade import place_order
from data.indicators import calculate_atr
from config.settings import (
    VERBOSE_LOGGING, BOS_ADX_THRESHOLD, BOS_MIN_BREAKOUT_RANGE,
    BOS_STOP_BUFFER, BOS_TP_EXTENSION, BOS_VOLUME_MULTIPLIER,
    BOS_GLOBAL_COOLDOWN_SECONDS, BOS_HARD_TIME_FILTER,
    strategy_toggles
)
from src.state_manager import bot_state
from datetime import datetime, timezone
import pandas as pd
import time


def _check_bos_global_guards(symbol, side_label):
    """
    Shared guard checks for both LONG and SHORT BOS entries.
    Returns True if the trade should be BLOCKED, False if clear to proceed.
    """
    # --- Guard 1: Global BOS Cooldown (prevents cluster-bombing) ---
    elapsed = time.time() - bot_state.last_bos_entry_time
    if elapsed < BOS_GLOBAL_COOLDOWN_SECONDS:
        remaining = int(BOS_GLOBAL_COOLDOWN_SECONDS - elapsed)
        if VERBOSE_LOGGING:
            print(f"  BOS {side_label} rejected for {symbol}: Global BOS cooldown active ({remaining}s remaining).")
        return True

    # --- Guard 2: Hard Time Filter (ALWAYS blocks Asian dead hours) ---
    if BOS_HARD_TIME_FILTER:
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= 1 and current_hour < 7:
            if VERBOSE_LOGGING:
                print(f"  BOS {side_label} rejected for {symbol}: Hard Time Filter — Asian dead hours (01:00-07:00 UTC).")
            return True

    # --- Guard 3: Soft Time Filter (Dashboard Toggle — additional sessions) ---
    if strategy_toggles.USE_TIME_FILTER:
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= 1 and current_hour < 7:
            if VERBOSE_LOGGING:
                print(f"  BOS {side_label} rejected for {symbol}: Time Filter active (Asian dead hours).")
            return True

    return False


async def check_bos_breakout_long(symbol, df_15m, df_4h, df_1h, stoch_k, usdt_balance):
    """
    Checks for a LONG momentum breakout using Break of Structure + Retest.
    Requires: Bullish BOS within recent window + Retest pullback with rejection
              + 3x Volume on breakout + 1H EMA 21 trend alignment + VWAP + 4H ADX > 25.
    """
    if getattr(sys.modules['config.settings'], 'ENABLE_GLOBAL_BTC_FILTER', True) and bot_state.global_btc_trend == 'BEARISH' and symbol != 'BTCUSDT':
        return False

    # --- Global BOS Guards (cooldown, time filter) ---
    if _check_bos_global_guards(symbol, "LONG"):
        return False

    # --- SMA 200 Trend Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_SMA_200_FILTER and 'price_sma_200' in df_4h.columns:
        last_close = df_15m['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close < sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS LONG rejected for {symbol}: Price {last_close:.4f} < 4H SMA 200 {sma_200_4h:.4f}")
            return False

    # --- Core Condition 1: 4H Trending Market (ADX > 25) ---
    adx_4h = df_4h['ADX'].iloc[-1]
    if adx_4h != adx_4h or adx_4h < BOS_ADX_THRESHOLD:  # NaN check + threshold
        return False

    # --- HTF Trend Guard: 4H Price must be above 4H SMA 50 ---
    if 'price_sma_50' in df_4h.columns:
        last_4h_close = df_4h['close'].iloc[-1]
        sma_50_4h = df_4h['price_sma_50'].iloc[-1]
        if pd.notna(sma_50_4h) and last_4h_close < sma_50_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS LONG rejected for {symbol}: 4H macro trend is BEARISH (Price {last_4h_close:.4f} < SMA50 {sma_50_4h:.4f}).")
            return False

    # --- NEW: 1H EMA 21 Trend Alignment Filter ---
    # Prevents taking LONG breakouts when the 1H trend is pointing down
    if 'ema_21' in df_1h.columns:
        last_1h_close = df_1h['close'].iloc[-1]
        ema_21_1h = df_1h['ema_21'].iloc[-1]
        if pd.notna(ema_21_1h) and last_1h_close < ema_21_1h:
            if VERBOSE_LOGGING:
                print(f"  BOS LONG rejected for {symbol}: 1H trend BEARISH (Price {last_1h_close:.4f} < EMA21 {ema_21_1h:.4f}).")
            return False

    # --- Core Condition 2: Bullish BOS Retest (NOT chase entry) ---
    # Instead of entering on the breakout candle, we wait for the retest
    if 'bos_retest_long' not in df_15m.columns:
        return False

    # Ensure the retest rejection wick was printed on a fully CLOSED candle
    if not df_15m['bos_retest_long'].iloc[-2]:
        return False

    # NEW: Strict Momentum Breakout Requirement (Trigger Pull)
    # The current live price must break above the high of the closed retest candle
    last_close = df_15m['close'].iloc[-1]
    if last_close <= df_15m['high'].iloc[-2]:
        return False

    # --- Core Condition 3: Volume Anomaly on the ORIGINAL breakout candle ---
    # The retest candle doesn't need high volume — the breakout candle does.
    # We check if volume_anomaly was True at any point in the recent BOS window
    if 'volume_anomaly' not in df_15m.columns or 'vol_sma' not in df_15m.columns:
        return False

    # Check volume ratio on the current candle AND verify breakout had institutional volume
    # Use BOS_VOLUME_MULTIPLIER (3.0x) instead of the shared anomaly column
    last_vol = df_15m['volume'].iloc[-1]
    avg_vol = df_15m['vol_sma'].iloc[-1]
    
    # Look back through the retest window to find the breakout candle's volume
    from config.settings import BOS_RETEST_WINDOW
    breakout_had_volume = False
    for i in range(1, min(BOS_RETEST_WINDOW + 1, len(df_15m))):
        idx = -1 - i
        if idx < -len(df_15m):
            break
        if df_15m['bullish_bos'].iloc[idx]:
            breakout_vol = df_15m['volume'].iloc[idx]
            breakout_avg = df_15m['vol_sma'].iloc[idx]
            if breakout_avg > 0 and breakout_vol >= breakout_avg * BOS_VOLUME_MULTIPLIER:
                breakout_had_volume = True
            break
    
    if not breakout_had_volume:
        if VERBOSE_LOGGING:
            print(f"  BOS LONG rejected for {symbol}: Breakout candle lacked {BOS_VOLUME_MULTIPLIER}x volume.")
        return False

    # --- Core Condition 4: Price above VWAP (institutional trend alignment) ---
    if 'vwap' not in df_15m.columns:
        return False

    last_close = df_15m['close'].iloc[-1]
    vwap_value = df_15m['vwap'].iloc[-1]

    if last_close <= vwap_value:
        if VERBOSE_LOGGING:
            print(f"  BOS LONG rejected for {symbol}: Price {last_close:.4f} below VWAP {vwap_value:.4f}.")
        return False

    # --- Exhaustion Guard: Stochastic Overbought ---
    if stoch_k is not None and stoch_k.iloc[-1] > 80:
        if VERBOSE_LOGGING:
            print(f"  BOS LONG rejected for {symbol}: Stochastic is overbought ({stoch_k.iloc[-1]:.2f}). Exhaustion risk.")
        return False

    # --- All conditions met: Calculate trade parameters ---
    # Use the broken level from the retest detection
    broken_level = df_15m['bos_level_long'].iloc[-2]
    retest_candle_low = df_15m['low'].iloc[-2]   # Bottom of the CLOSED retest candle

    # Stop Loss: Below the retest candle's low (with buffer)
    stop_loss_price = retest_candle_low * (1 - BOS_STOP_BUFFER)

    # Take Profit: Project the breakout range as a 1.272 extension
    recent_low = df_15m['recent_low'].iloc[-1]  # True consolidation floor
    breakout_range = broken_level - recent_low

    # Sanity check: breakout range must be meaningful
    if breakout_range <= 0 or (breakout_range / last_close) < BOS_MIN_BREAKOUT_RANGE:
        if VERBOSE_LOGGING:
            print(f"  BOS LONG rejected for {symbol}: Breakout range too small ({breakout_range:.4f}).")
        return False

    take_profit_price = broken_level + (breakout_range * BOS_TP_EXTENSION)  # 1.272 extension

    atr_value = df_15m['atr'].iloc[-1]
    volume_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    ema_21_val = df_1h['ema_21'].iloc[-1] if 'ema_21' in df_1h.columns else 0

    print(f"\n{'='*70}")
    print(f"🚀 BOS RETEST BREAKOUT — LONG: {symbol}")
    print(f"{'='*70}")
    print(f"Entry Type: STRUCTURAL BREAKOUT + RETEST (Institutional)")
    print(f"\n--- Breakout Analysis ---")
    print(f"  Broken Structure Level: {broken_level:.4f}")
    print(f"  Retest Entry Price:     {last_close:.4f}")
    print(f"  1H EMA 21:              {ema_21_val:.4f}")
    print(f"  VWAP (24h):             {vwap_value:.4f}")
    print(f"  Breakout Volume:        {BOS_VOLUME_MULTIPLIER}x+ confirmed")
    print(f"  4H ADX:                 {adx_4h:.2f}")
    print(f"\n--- Trade Execution ---")
    print(f"  Stop Loss:              {stop_loss_price:.4f} (below retest candle)")
    print(f"  Take Profit (1.272):    {take_profit_price:.4f}")
    print(f"{'='*70}\n")

    order_placed = await place_order(
        symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
        reason_to_open=f"BOS Retest LONG | {BOS_VOLUME_MULTIPLIER}x Vol | ADX {adx_4h:.1f}",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price if take_profit_price > 0 else None,
        atr_value=atr_value, df=df_15m,
        support_4h=recent_low, resistance_4h=broken_level, adx_value=adx_4h
    )
    
    if order_placed:
        bot_state.last_bos_entry_time = time.time()
    
    return order_placed if order_placed is not None else False


async def check_bos_breakout_short(symbol, df_15m, df_4h, df_1h, stoch_k, usdt_balance):
    """
    Checks for a SHORT momentum breakdown using Break of Structure + Retest.
    Requires: Bearish BOS within recent window + Retest pullback with rejection
              + 3x Volume on breakdown + 1H EMA 21 trend alignment + VWAP + 4H ADX > 25.
    """
    if getattr(sys.modules['config.settings'], 'ENABLE_GLOBAL_BTC_FILTER', True) and bot_state.global_btc_trend == 'BULLISH' and symbol != 'BTCUSDT':
        return False

    # --- Global BOS Guards (cooldown, time filter) ---
    if _check_bos_global_guards(symbol, "SHORT"):
        return False

    # --- SMA 200 Trend Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_SMA_200_FILTER and 'price_sma_200' in df_4h.columns:
        last_close = df_15m['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close > sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS SHORT rejected for {symbol}: Price {last_close:.4f} > 4H SMA 200 {sma_200_4h:.4f}")
            return False

    # --- Core Condition 1: 4H Trending Market (ADX > 25) ---
    adx_4h = df_4h['ADX'].iloc[-1]
    if adx_4h != adx_4h or adx_4h < BOS_ADX_THRESHOLD:  # NaN check + threshold
        return False

    # --- HTF Trend Guard: 4H Price must be below 4H SMA 50 ---
    if 'price_sma_50' in df_4h.columns:
        last_4h_close = df_4h['close'].iloc[-1]
        sma_50_4h = df_4h['price_sma_50'].iloc[-1]
        if pd.notna(sma_50_4h) and last_4h_close > sma_50_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS SHORT rejected for {symbol}: 4H macro trend is BULLISH (Price {last_4h_close:.4f} > SMA50 {sma_50_4h:.4f}).")
            return False

    # --- NEW: 1H EMA 21 Trend Alignment Filter ---
    # Prevents taking SHORT breakdowns when the 1H trend is pointing up
    if 'ema_21' in df_1h.columns:
        last_1h_close = df_1h['close'].iloc[-1]
        ema_21_1h = df_1h['ema_21'].iloc[-1]
        if pd.notna(ema_21_1h) and last_1h_close > ema_21_1h:
            if VERBOSE_LOGGING:
                print(f"  BOS SHORT rejected for {symbol}: 1H trend BULLISH (Price {last_1h_close:.4f} > EMA21 {ema_21_1h:.4f}).")
            return False

    # --- Core Condition 2: Bearish BOS Retest (NOT chase entry) ---
    if 'bos_retest_short' not in df_15m.columns:
        return False

    # Ensure the retest rejection wick was printed on a fully CLOSED candle
    if not df_15m['bos_retest_short'].iloc[-2]:
        return False

    # NEW: Strict Momentum Breakout Requirement (Trigger Pull)
    # The current live price must break below the low of the closed retest candle
    last_close = df_15m['close'].iloc[-1]
    if last_close >= df_15m['low'].iloc[-2]:
        return False

    # --- Core Condition 3: Volume Anomaly on the ORIGINAL breakdown candle ---
    if 'volume_anomaly' not in df_15m.columns or 'vol_sma' not in df_15m.columns:
        return False

    last_vol = df_15m['volume'].iloc[-1]
    avg_vol = df_15m['vol_sma'].iloc[-1]
    
    # Look back through the retest window to find the breakdown candle's volume
    from config.settings import BOS_RETEST_WINDOW
    breakdown_had_volume = False
    for i in range(1, min(BOS_RETEST_WINDOW + 1, len(df_15m))):
        idx = -1 - i
        if idx < -len(df_15m):
            break
        if df_15m['bearish_bos'].iloc[idx]:
            breakdown_vol = df_15m['volume'].iloc[idx]
            breakdown_avg = df_15m['vol_sma'].iloc[idx]
            if breakdown_avg > 0 and breakdown_vol >= breakdown_avg * BOS_VOLUME_MULTIPLIER:
                breakdown_had_volume = True
            break
    
    if not breakdown_had_volume:
        if VERBOSE_LOGGING:
            print(f"  BOS SHORT rejected for {symbol}: Breakdown candle lacked {BOS_VOLUME_MULTIPLIER}x volume.")
        return False

    # --- Core Condition 4: Price below VWAP (institutional trend alignment) ---
    if 'vwap' not in df_15m.columns:
        return False

    last_close = df_15m['close'].iloc[-1]
    vwap_value = df_15m['vwap'].iloc[-1]

    if last_close >= vwap_value:
        if VERBOSE_LOGGING:
            print(f"  BOS SHORT rejected for {symbol}: Price {last_close:.4f} above VWAP {vwap_value:.4f}.")
        return False

    # --- Exhaustion Guard: Stochastic Oversold ---
    if stoch_k is not None and stoch_k.iloc[-1] < 20:
        if VERBOSE_LOGGING:
            print(f"  BOS SHORT rejected for {symbol}: Stochastic is oversold ({stoch_k.iloc[-1]:.2f}). Exhaustion risk.")
        return False

    # --- All conditions met: Calculate trade parameters ---
    broken_level = df_15m['bos_level_short'].iloc[-2]
    retest_candle_high = df_15m['high'].iloc[-2]  # Top of the CLOSED retest candle

    # Stop Loss: Above the retest candle's high (with buffer)
    stop_loss_price = retest_candle_high * (1 + BOS_STOP_BUFFER)

    # Take Profit: Project the breakdown range as a 1.272 extension below
    recent_high = df_15m['recent_high'].iloc[-1]  # True consolidation ceiling
    breakdown_range = recent_high - broken_level

    # Sanity check: breakdown range must be meaningful
    if breakdown_range <= 0 or (breakdown_range / last_close) < BOS_MIN_BREAKOUT_RANGE:
        if VERBOSE_LOGGING:
            print(f"  BOS SHORT rejected for {symbol}: Breakdown range too small ({breakdown_range:.4f}).")
        return False

    take_profit_price = broken_level - (breakdown_range * BOS_TP_EXTENSION)  # 1.272 extension below

    atr_value = df_15m['atr'].iloc[-1]
    volume_ratio = last_vol / avg_vol if avg_vol > 0 else 0
    ema_21_val = df_1h['ema_21'].iloc[-1] if 'ema_21' in df_1h.columns else 0

    print(f"\n{'='*70}")
    print(f"💥 BOS RETEST BREAKDOWN — SHORT: {symbol}")
    print(f"{'='*70}")
    print(f"Entry Type: STRUCTURAL BREAKDOWN + RETEST (Institutional)")
    print(f"\n--- Breakdown Analysis ---")
    print(f"  Broken Structure Level: {broken_level:.4f}")
    print(f"  Retest Entry Price:     {last_close:.4f}")
    print(f"  1H EMA 21:              {ema_21_val:.4f}")
    print(f"  VWAP (24h):             {vwap_value:.4f}")
    print(f"  Breakdown Volume:       {BOS_VOLUME_MULTIPLIER}x+ confirmed")
    print(f"  4H ADX:                 {adx_4h:.2f}")
    print(f"\n--- Trade Execution ---")
    print(f"  Stop Loss:              {stop_loss_price:.4f} (above retest candle)")
    print(f"  Take Profit (1.272):    {take_profit_price:.4f}")
    print(f"{'='*70}\n")

    order_placed = await place_order(
        symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
        reason_to_open=f"BOS Retest SHORT | {BOS_VOLUME_MULTIPLIER}x Vol | ADX {adx_4h:.1f}",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price if take_profit_price > 0 else None,
        atr_value=atr_value, df=df_15m,
        support_4h=broken_level, resistance_4h=recent_high, adx_value=adx_4h
    )
    
    if order_placed:
        bot_state.last_bos_entry_time = time.time()
    
    return order_placed if order_placed is not None else False
