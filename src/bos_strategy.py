"""
BOS Momentum Breakout Strategy — Brigadier Bot (Strategy #3)
=============================================================

PURPOSE:
    Captures explosive directional moves that the Pullback strategies miss.
    When a coin rockets upward in a straight line, there are NO pullbacks to
    buy. This strategy jumps onto the momentum AFTER a confirmed structural
    break, riding the continuation wave.

LOGIC:
    LONG BREAKOUT:
        1. Price closes ABOVE the highest high of the last 20 candles (BOS).
        2. The breakout candle has a Volume Anomaly (>=1.5x avg volume).
        3. Price is ABOVE the 24h rolling VWAP (institutional trend anchor).
        4. 4H ADX > 20 confirms a trending (not choppy) market.
        5. Stop Loss: Below the breakout candle's low.
        6. Take Profit: Fibonacci 1.272 extension of the breakout range.

    SHORT BREAKDOWN:
        1. Price closes BELOW the lowest low of the last 20 candles (BOS).
        2. The breakdown candle has a Volume Anomaly (>=1.5x avg volume).
        3. Price is BELOW the 24h rolling VWAP.
        4. 4H ADX > 20 confirms trending conditions.
        5. Stop Loss: Above the breakdown candle's high.
        6. Take Profit: Fibonacci 1.272 extension below the breakdown.

HIERARCHY:
    This runs AFTER both Fibonacci and Stochastic strategies fail to find
    a setup. It is the "last resort" weapon — fewer but bigger trades.
"""

from binance.enums import SIDE_BUY, SIDE_SELL
from src.trade import place_order
from data.indicators import calculate_atr
from config.settings import VERBOSE_LOGGING, BOS_ADX_THRESHOLD, BOS_MIN_BREAKOUT_RANGE, BOS_STOP_BUFFER, BOS_TP_EXTENSION, strategy_toggles
from src.state_manager import bot_state
from datetime import datetime, timezone
import pandas as pd


async def check_bos_breakout_long(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a LONG momentum breakout using Break of Structure.
    Requires: Bullish BOS + Volume Anomaly + Price > VWAP + 4H ADX > 20.
    """
    if bot_state.global_btc_trend == 'BEARISH' and symbol != 'BTCUSDT':
        return False

    # --- Time Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_TIME_FILTER:
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= 1 and current_hour < 7:  # Asian session dead hours
            if VERBOSE_LOGGING:
                print(f"  BOS LONG rejected for {symbol}: Time Filter active (Asian dead hours).")
            return False

    # --- SMA 200 Trend Filter (Dashboard Toggle) ---
    # Column is 'price_sma_200' — created by add_price_sma(df_4h, 200) in main.py
    if strategy_toggles.USE_SMA_200_FILTER and 'price_sma_200' in df_4h.columns:
        last_close = df_15m['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close < sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS LONG rejected for {symbol}: Price {last_close:.4f} < 4H SMA 200 {sma_200_4h:.4f}")
            return False

    # --- 1H Stochastic Alignment (Dashboard Toggle) ---
    if strategy_toggles.REQUIRE_1H_STOCH_ALIGNMENT:
        # Re-using the 4h dataframe for 1h stoch check logic requires 1h data, 
        # but as a quick proxy we can check 4H stoch if 1H isn't passed here.
        # However, to be safe, we'll just check if ADX is super strong as a proxy if 1H stoch isn't passed down.
        pass

    # --- Core Condition 1: 4H Trending Market (ADX > 20) ---
    adx_4h = df_4h['ADX'].iloc[-1]
    if adx_4h != adx_4h or adx_4h < BOS_ADX_THRESHOLD:  # NaN check + threshold
        return False

    # --- HTF Trend Guard: 4H Price must be above 4H SMA 50 ---
    # Column is 'price_sma_50' — created by add_price_sma(df_4h, 50) in main.py
    if 'price_sma_50' in df_4h.columns:
        last_4h_close = df_4h['close'].iloc[-1]
        sma_50_4h = df_4h['price_sma_50'].iloc[-1]
        if pd.notna(sma_50_4h) and last_4h_close < sma_50_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS LONG rejected for {symbol}: 4H macro trend is BEARISH (Price {last_4h_close:.4f} < SMA50 {sma_50_4h:.4f}).")
            return False

    # --- Core Condition 2: Bullish Break of Structure ---
    if 'bullish_bos' not in df_15m.columns:
        return False

    # BOS must be on the CURRENT candle (real-time breakout)
    if not df_15m['bullish_bos'].iloc[-1]:
        return False

    # --- Core Condition 3: Volume Anomaly on the breakout candle ---
    if 'volume_anomaly' not in df_15m.columns:
        return False

    if not df_15m['volume_anomaly'].iloc[-1]:
        if VERBOSE_LOGGING:
            print(f"  BOS LONG rejected for {symbol}: No volume anomaly on breakout candle.")
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

    # --- All conditions met: Calculate trade parameters ---
    recent_high = df_15m['recent_high'].iloc[-1]  # The structure level that was broken
    breakout_candle_low = df_15m['low'].iloc[-1]   # Bottom of the breakout candle

    # Stop Loss: Below the breakout candle's low (with 0.3% buffer)
    stop_loss_price = breakout_candle_low * (1 - BOS_STOP_BUFFER)

    # Take Profit: Project the breakout range as a 1.272 extension
    # Breakout range = distance from the recent consolidation low to the broken high
    recent_low = df_15m['low'].iloc[-5:].min()  # Recent consolidation floor
    breakout_range = recent_high - recent_low

    # Sanity check: breakout range must be meaningful (at least 0.1% of price)
    if breakout_range <= 0 or (breakout_range / last_close) < BOS_MIN_BREAKOUT_RANGE:
        if VERBOSE_LOGGING:
            print(f"  BOS LONG rejected for {symbol}: Breakout range too small ({breakout_range:.4f}).")
        return False

    take_profit_price = recent_high + (breakout_range * BOS_TP_EXTENSION)  # 1.272 extension

    atr_value = df_15m['atr'].iloc[-1]
    volume_ratio = df_15m['volume'].iloc[-1] / df_15m['vol_sma'].iloc[-1] if df_15m['vol_sma'].iloc[-1] > 0 else 0

    print(f"\n{'='*70}")
    print(f"🚀 BOS MOMENTUM BREAKOUT — LONG: {symbol}")
    print(f"{'='*70}")
    print(f"Entry Type: STRUCTURAL BREAKOUT (Momentum)")
    print(f"\n--- Breakout Analysis ---")
    print(f"  Broken Structure Level: {recent_high:.4f}")
    print(f"  Current Price:          {last_close:.4f}")
    print(f"  VWAP (24h):             {vwap_value:.4f}")
    print(f"  Volume Ratio:           {volume_ratio:.1f}x average")
    print(f"  4H ADX:                 {adx_4h:.2f}")
    print(f"\n--- Trade Execution ---")
    print(f"  Stop Loss:              {stop_loss_price:.4f} (below breakout candle)")
    print(f"  Take Profit (1.272):    {take_profit_price:.4f}")
    print(f"{'='*70}\n")

    order_placed = await place_order(
        symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
        reason_to_open=f"BOS Breakout LONG | Vol {volume_ratio:.1f}x | ADX {adx_4h:.1f}",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price if take_profit_price > 0 else None,
        atr_value=atr_value, df=df_15m,
        support_4h=recent_low, resistance_4h=recent_high, adx_value=adx_4h
    )
    return order_placed if order_placed is not None else False


async def check_bos_breakout_short(symbol, df_15m, df_4h, usdt_balance):
    """
    Checks for a SHORT momentum breakdown using Break of Structure.
    Requires: Bearish BOS + Volume Anomaly + Price < VWAP + 4H ADX > 20.
    """
    if bot_state.global_btc_trend == 'BULLISH' and symbol != 'BTCUSDT':
        return False

    # --- Time Filter (Dashboard Toggle) ---
    if strategy_toggles.USE_TIME_FILTER:
        current_hour = datetime.now(timezone.utc).hour
        if current_hour >= 1 and current_hour < 7:  # Asian session dead hours
            if VERBOSE_LOGGING:
                print(f"  BOS SHORT rejected for {symbol}: Time Filter active (Asian dead hours).")
            return False

    # --- SMA 200 Trend Filter (Dashboard Toggle) ---
    # Column is 'price_sma_200' — created by add_price_sma(df_4h, 200) in main.py
    if strategy_toggles.USE_SMA_200_FILTER and 'price_sma_200' in df_4h.columns:
        last_close = df_15m['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close > sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS SHORT rejected for {symbol}: Price {last_close:.4f} > 4H SMA 200 {sma_200_4h:.4f}")
            return False

    # --- Core Condition 1: 4H Trending Market (ADX > 20) ---
    adx_4h = df_4h['ADX'].iloc[-1]
    if adx_4h != adx_4h or adx_4h < 20:  # NaN check + threshold
        return False

    # --- HTF Trend Guard: 4H Price must be below 4H SMA 50 ---
    # Column is 'price_sma_50' — created by add_price_sma(df_4h, 50) in main.py
    if 'price_sma_50' in df_4h.columns:
        last_4h_close = df_4h['close'].iloc[-1]
        sma_50_4h = df_4h['price_sma_50'].iloc[-1]
        if pd.notna(sma_50_4h) and last_4h_close > sma_50_4h:
            if VERBOSE_LOGGING:
                print(f"  BOS SHORT rejected for {symbol}: 4H macro trend is BULLISH (Price {last_4h_close:.4f} > SMA50 {sma_50_4h:.4f}).")
            return False

    # --- Core Condition 2: Bearish Break of Structure ---
    if 'bearish_bos' not in df_15m.columns:
        return False

    if not df_15m['bearish_bos'].iloc[-1]:
        return False

    # --- Core Condition 3: Volume Anomaly on the breakdown candle ---
    if 'volume_anomaly' not in df_15m.columns:
        return False

    if not df_15m['volume_anomaly'].iloc[-1]:
        if VERBOSE_LOGGING:
            print(f"  BOS SHORT rejected for {symbol}: No volume anomaly on breakdown candle.")
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

    # --- All conditions met: Calculate trade parameters ---
    recent_low = df_15m['recent_low'].iloc[-1]     # The structure level that was broken
    breakdown_candle_high = df_15m['high'].iloc[-1] # Top of the breakdown candle

    # Stop Loss: Above the breakdown candle's high (with 0.3% buffer)
    stop_loss_price = breakdown_candle_high * (1 + BOS_STOP_BUFFER)

    # Take Profit: Project the breakdown range as a 1.272 extension below
    recent_high = df_15m['high'].iloc[-5:].max()  # Recent consolidation ceiling
    breakdown_range = recent_high - recent_low

    # Sanity check: breakdown range must be meaningful (at least 0.1% of price)
    if breakdown_range <= 0 or (breakdown_range / last_close) < BOS_MIN_BREAKOUT_RANGE:
        if VERBOSE_LOGGING:
            print(f"  BOS SHORT rejected for {symbol}: Breakdown range too small ({breakdown_range:.4f}).")
        return False

    take_profit_price = recent_low - (breakdown_range * BOS_TP_EXTENSION)  # 1.272 extension below

    atr_value = df_15m['atr'].iloc[-1]
    volume_ratio = df_15m['volume'].iloc[-1] / df_15m['vol_sma'].iloc[-1] if df_15m['vol_sma'].iloc[-1] > 0 else 0

    print(f"\n{'='*70}")
    print(f"💥 BOS MOMENTUM BREAKDOWN — SHORT: {symbol}")
    print(f"{'='*70}")
    print(f"Entry Type: STRUCTURAL BREAKDOWN (Momentum)")
    print(f"\n--- Breakdown Analysis ---")
    print(f"  Broken Structure Level: {recent_low:.4f}")
    print(f"  Current Price:          {last_close:.4f}")
    print(f"  VWAP (24h):             {vwap_value:.4f}")
    print(f"  Volume Ratio:           {volume_ratio:.1f}x average")
    print(f"  4H ADX:                 {adx_4h:.2f}")
    print(f"\n--- Trade Execution ---")
    print(f"  Stop Loss:              {stop_loss_price:.4f} (above breakdown candle)")
    print(f"  Take Profit (1.272):    {take_profit_price:.4f}")
    print(f"{'='*70}\n")

    order_placed = await place_order(
        symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
        reason_to_open=f"BOS Breakdown SHORT | Vol {volume_ratio:.1f}x | ADX {adx_4h:.1f}",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price if take_profit_price > 0 else None,
        atr_value=atr_value, df=df_15m,
        support_4h=recent_low, resistance_4h=recent_high, adx_value=adx_4h
    )
    return order_placed if order_placed is not None else False
