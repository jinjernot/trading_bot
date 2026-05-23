from binance.enums import SIDE_BUY, SIDE_SELL
from src.trade import place_order
from data.indicators import (
    calculate_stoch, calculate_bollinger_bands, add_candlestick_patterns, detect_rsi_divergence
)
from config.settings import (
    REVERSAL_STOCH_THRESHOLD, REVERSAL_RSI_THRESHOLD, REVERSAL_STOP_BUFFER,
    VERBOSE_LOGGING, strategy_toggles
)
from src.state_manager import bot_state
from src.detailed_logger import log_rejected_signal, log_signal_analysis
import pandas as pd
import sys

async def check_reversal_long_entry(symbol, df_15m, df_4h, stoch_k_1h, usdt_balance, support_4h):
    """
    Mean-Reversion LONG: Catches falling knives at extreme support.
    Explicitly BYPASSES the global BTC filter and the SMA 200 Trend filter.
    """
    
    # Optional time filter
    if strategy_toggles.USE_TIME_FILTER:
        from src.time_filters import is_optimal_5m_trading_time
        is_optimal, time_reason = is_optimal_5m_trading_time()
        if not is_optimal:
            if VERBOSE_LOGGING:
                print(f"⏰ Skipping REVERSAL LONG for {symbol}: {time_reason}")
            return False

    # 1. Extreme Oversold condition on High Timeframe (1H Stochastic)
    stoch_1h_oversold = stoch_k_1h.iloc[-1] < REVERSAL_STOCH_THRESHOLD
    if not stoch_1h_oversold:
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL LONG for {symbol}: 1H Stochastic ({stoch_k_1h.iloc[-1]:.2f}) not extreme oversold (<{REVERSAL_STOCH_THRESHOLD}).")
        return False

    # 2. Extreme Oversold on Lower Timeframe (15m RSI)
    rsi_15m_oversold = df_15m['rsi'].iloc[-1] < REVERSAL_RSI_THRESHOLD
    bullish_div, _ = detect_rsi_divergence(df_15m, lookback=5)
    
    if not (rsi_15m_oversold or bullish_div):
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL LONG for {symbol}: 15m RSI ({df_15m['rsi'].iloc[-1]:.2f}) not oversold and no bullish divergence.")
        return False

    # Calculate additional indicators for entry confirmation
    df_15m = calculate_bollinger_bands(df_15m, period=20)
    df_15m = add_candlestick_patterns(df_15m)

    last_close = df_15m['close'].iloc[-1]
    
    # We now evaluate patterns and wicks on the LAST CLOSED CANDLE (-2)
    closed_low = df_15m['low'].iloc[-2]
    lower_bb = df_15m['BB_Lower'].iloc[-2]

    # 3. Structural Support / Volatility Check
    # Closed candle must be near the 4H support or piercing the Lower Bollinger Band
    near_support = False
    if support_4h is not None and support_4h > 0:
        near_support = abs(closed_low - support_4h) / support_4h < 0.015  # within 1.5% of major support
        
    piercing_bb = closed_low < lower_bb
    
    if not (near_support or piercing_bb):
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL LONG for {symbol}: Closed candle not at 4H support or piercing Lower BB.")
        return False

    # 4. Entry Trigger: Bullish Candlestick Pattern or Strong Wick Rejection (on closed candle)
    bullish_pattern = df_15m['bullish_pattern'].iloc[-2] == 1
    
    # Wick rejection logic (lower wick is >= 50% of the total candle range)
    candle_range = df_15m['high'].iloc[-2] - closed_low
    lower_wick = min(df_15m['open'].iloc[-2], df_15m['close'].iloc[-2]) - closed_low
    strong_rejection = False
    if candle_range > 0 and (lower_wick / candle_range) >= 0.5:
        strong_rejection = True
        
    if not (bullish_pattern or strong_rejection):
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL LONG for {symbol}: Waiting for bullish candlestick pattern or wick rejection on closed candle.")
        return False

    # 5. Momentum Confirmation (Trigger Pull)
    # The current live price must break ABOVE the high of the closed rejection candle
    closed_high = df_15m['high'].iloc[-2]
    if last_close <= closed_high:
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL LONG for {symbol}: Waiting for price ({last_close:.4f}) to break above closed rejection candle high ({closed_high:.4f}).")
        return False

    # ALL CONDITIONS MET FOR REVERSAL LONG
    # Stop loss goes below the wick of the confirmed closed candle
    stop_loss_price = closed_low * (1 - REVERSAL_STOP_BUFFER)
    
    # Mean reversion TP: Aim for the 50 SMA on the 15m or a 1.5 R:R
    sma_50 = df_15m['price_sma_50'].iloc[-1] if 'price_sma_50' in df_15m.columns else last_close * 1.02
    risk = last_close - stop_loss_price
    take_profit_price = max(sma_50, last_close + (risk * 1.5))
    
    atr_value = df_15m['atr'].iloc[-1]
    adx_4h = df_4h['ADX'].iloc[-1] if 'ADX' in df_4h.columns else 0

    print(f"\n{'='*70}")
    print(f"🚨 REVERSAL ENTRY SIGNAL: LONG {symbol}")
    print(f"{'='*70}")
    print(f"Entry Type: MEAN REVERSION (Counter-Trend Catch)")
    print(f"\n--- Condition Analysis ---")
    print(f"  1H Stochastic K:  {stoch_k_1h.iloc[-1]:.2f} (Extreme Oversold)")
    print(f"  15m RSI:          {df_15m['rsi'].iloc[-1]:.2f} (Divergence: {bullish_div})")
    print(f"  Trigger:          {'Bullish Pattern' if bullish_pattern else 'Wick Rejection'}")
    print(f"  Location:         {'At 4H Support' if near_support else 'Piercing Lower BB'}")
    print(f"\n--- Trade Execution ---")
    print(f"  Entry Price:      {last_close:.4f}")
    print(f"  Stop Loss:        {stop_loss_price:.4f} (Below wick)")
    print(f"  Take Profit:      {take_profit_price:.4f} (Mean Reversion Target)")
    print(f"{'='*70}\n")
    sys.stdout.flush()

    log_signal_analysis(symbol, {
        'Stoch_1H': float(stoch_k_1h.iloc[-1]),
        'RSI_15m': float(df_15m['rsi'].iloc[-1]),
        'Bullish_Div': bool(bullish_div),
        'Trigger': 'Pattern' if bullish_pattern else 'Wick',
        'Price': float(last_close)
    }, 'LONG_REVERSAL', 'Reversal conditions met')

    order_placed = await place_order(
        symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
        reason_to_open="Extreme Mean Reversion (LONG)",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        atr_value=atr_value, df=df_15m,
        support_4h=support_4h, resistance_4h=None, adx_value=adx_4h
    )
    
    return order_placed if order_placed is not None else False


async def check_reversal_short_entry(symbol, df_15m, df_4h, stoch_k_1h, usdt_balance, resistance_4h):
    """
    Mean-Reversion SHORT: Catches exhaustion spikes at extreme resistance.
    Explicitly BYPASSES the global BTC filter and the SMA 200 Trend filter.
    """
    
    # Optional time filter
    if strategy_toggles.USE_TIME_FILTER:
        from src.time_filters import is_optimal_5m_trading_time
        is_optimal, time_reason = is_optimal_5m_trading_time()
        if not is_optimal:
            if VERBOSE_LOGGING:
                print(f"⏰ Skipping REVERSAL SHORT for {symbol}: {time_reason}")
            return False

    # 1. Extreme Overbought condition on High Timeframe (1H Stochastic)
    stoch_1h_overbought = stoch_k_1h.iloc[-1] > (100 - REVERSAL_STOCH_THRESHOLD)
    if not stoch_1h_overbought:
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL SHORT for {symbol}: 1H Stochastic ({stoch_k_1h.iloc[-1]:.2f}) not extreme overbought (>{100 - REVERSAL_STOCH_THRESHOLD}).")
        return False

    # 2. Extreme Overbought on Lower Timeframe (15m RSI)
    rsi_15m_overbought = df_15m['rsi'].iloc[-1] > (100 - REVERSAL_RSI_THRESHOLD)
    _, bearish_div = detect_rsi_divergence(df_15m, lookback=5)
    
    if not (rsi_15m_overbought or bearish_div):
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL SHORT for {symbol}: 15m RSI ({df_15m['rsi'].iloc[-1]:.2f}) not overbought and no bearish divergence.")
        return False

    # Calculate additional indicators for entry confirmation
    df_15m = calculate_bollinger_bands(df_15m, period=20)
    df_15m = add_candlestick_patterns(df_15m)

    last_close = df_15m['close'].iloc[-1]
    
    # We now evaluate patterns and wicks on the LAST CLOSED CANDLE (-2)
    closed_high = df_15m['high'].iloc[-2]
    upper_bb = df_15m['BB_Upper'].iloc[-2]

    # 3. Structural Resistance / Volatility Check
    # Closed candle must be near the 4H resistance or piercing the Upper Bollinger Band
    near_resistance = False
    if resistance_4h is not None and resistance_4h > 0:
        near_resistance = abs(closed_high - resistance_4h) / resistance_4h < 0.015  # within 1.5% of major resistance
        
    piercing_bb = closed_high > upper_bb
    
    if not (near_resistance or piercing_bb):
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL SHORT for {symbol}: Closed candle not at 4H resistance or piercing Upper BB.")
        return False

    # 4. Entry Trigger: Bearish Candlestick Pattern or Strong Wick Rejection (on closed candle)
    bearish_pattern = df_15m['bearish_pattern'].iloc[-2] == 1
    
    # Wick rejection logic (upper wick is >= 50% of the total candle range)
    candle_range = closed_high - df_15m['low'].iloc[-2]
    upper_wick = closed_high - max(df_15m['open'].iloc[-2], df_15m['close'].iloc[-2])
    strong_rejection = False
    if candle_range > 0 and (upper_wick / candle_range) >= 0.5:
        strong_rejection = True
        
    if not (bearish_pattern or strong_rejection):
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL SHORT for {symbol}: Waiting for bearish candlestick pattern or wick rejection on closed candle.")
        return False

    # 5. Momentum Confirmation (Trigger Pull)
    # The current live price must break BELOW the low of the closed rejection candle
    closed_low = df_15m['low'].iloc[-2]
    if last_close >= closed_low:
        if VERBOSE_LOGGING:
            print(f"Skipping REVERSAL SHORT for {symbol}: Waiting for price ({last_close:.4f}) to break below closed rejection candle low ({closed_low:.4f}).")
        return False

    # ALL CONDITIONS MET FOR REVERSAL SHORT
    # Stop loss goes above the wick of the confirmed closed candle
    stop_loss_price = closed_high * (1 + REVERSAL_STOP_BUFFER)
    
    # Mean reversion TP: Aim for the 50 SMA on the 15m or a 1.5 R:R
    sma_50 = df_15m['price_sma_50'].iloc[-1] if 'price_sma_50' in df_15m.columns else last_close * 0.98
    risk = stop_loss_price - last_close
    take_profit_price = min(sma_50, last_close - (risk * 1.5))
    
    atr_value = df_15m['atr'].iloc[-1]
    adx_4h = df_4h['ADX'].iloc[-1] if 'ADX' in df_4h.columns else 0

    print(f"\n{'='*70}")
    print(f"🚨 REVERSAL ENTRY SIGNAL: SHORT {symbol}")
    print(f"{'='*70}")
    print(f"Entry Type: MEAN REVERSION (Counter-Trend Catch)")
    print(f"\n--- Condition Analysis ---")
    print(f"  1H Stochastic K:  {stoch_k_1h.iloc[-1]:.2f} (Extreme Overbought)")
    print(f"  15m RSI:          {df_15m['rsi'].iloc[-1]:.2f} (Divergence: {bearish_div})")
    print(f"  Trigger:          {'Bearish Pattern' if bearish_pattern else 'Wick Rejection'}")
    print(f"  Location:         {'At 4H Resistance' if near_resistance else 'Piercing Upper BB'}")
    print(f"\n--- Trade Execution ---")
    print(f"  Entry Price:      {last_close:.4f}")
    print(f"  Stop Loss:        {stop_loss_price:.4f} (Above wick)")
    print(f"  Take Profit:      {take_profit_price:.4f} (Mean Reversion Target)")
    print(f"{'='*70}\n")
    sys.stdout.flush()

    log_signal_analysis(symbol, {
        'Stoch_1H': float(stoch_k_1h.iloc[-1]),
        'RSI_15m': float(df_15m['rsi'].iloc[-1]),
        'Bearish_Div': bool(bearish_div),
        'Trigger': 'Pattern' if bearish_pattern else 'Wick',
        'Price': float(last_close)
    }, 'SHORT_REVERSAL', 'Reversal conditions met')

    order_placed = await place_order(
        symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
        reason_to_open="Extreme Mean Reversion (SHORT)",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        atr_value=atr_value, df=df_15m,
        support_4h=None, resistance_4h=resistance_4h, adx_value=adx_4h
    )
    
    return order_placed if order_placed is not None else False
