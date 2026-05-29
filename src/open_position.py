import sys
from binance.enums import *
from src.trade import place_order
from data.indicators import *
from data.indicators import calculate_roc
from config.settings import *
from config.settings import strategy_toggles, STOCH_OVERSOLD_THRESHOLD, STOCH_AGGR_PULLBACK_LEVEL, ROC_MOMENTUM_THRESHOLD, STOCH_OVERBOUGHT_THRESHOLD
from src.time_filters import is_optimal_5m_trading_time
from src.detailed_logger import log_rejected_signal, log_signal_analysis
from src.state_manager import bot_state
import pandas as pd
import time
import sys

async def open_position_long(symbol, df_15m, df_4h, stoch_k_15m, stoch_d_15m, stoch_k_1h, stoch_d_1h, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):
    
    # NOTE: Cooldown lockout is enforced in process_symbol() before this function is called.

    # --- Global BTC Filter ---
    if getattr(sys.modules['config.settings'], 'ENABLE_GLOBAL_BTC_FILTER', True) and bot_state.global_btc_trend == 'BEARISH' and symbol != 'BTCUSDT':
        if VERBOSE_LOGGING:
            print(f"Skipping LONG for {symbol}: Global BTC trend is BEARISH.")
        log_rejected_signal(symbol, 'LONG', {}, "Global BTC trend is BEARISH")
        return False

    # Time-based filter - skip low volatility periods
    if strategy_toggles.USE_TIME_FILTER:
        is_optimal, time_reason = is_optimal_5m_trading_time()
        if not is_optimal:
            if VERBOSE_LOGGING:
                print(f"⏰ Skipping LONG for {symbol}: {time_reason}")
            log_rejected_signal(symbol, 'LONG', {}, f"Time Filter: {time_reason}")
            return False
    
    adx_value = df_15m['ADX'].iloc[-1]

    # ADX threshold filter
    if adx_value < MIN_ADX_THRESHOLD:
        if VERBOSE_LOGGING:
            print(f"Skipping LONG for {symbol}: ADX is {adx_value:.2f}, below minimum threshold of {MIN_ADX_THRESHOLD}.")
        log_rejected_signal(symbol, 'LONG', {'ADX': adx_value}, f"ADX below {MIN_ADX_THRESHOLD}")
        return False

    # === PHASE 1 IMPROVEMENT: SMA 200 Trend Filter on 4H ===
    if strategy_toggles.USE_SMA_200_FILTER:
        last_close_4h = df_4h['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close_4h < sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: Price (${last_close_4h:.2f}) below 4H SMA 200 (${sma_200_4h:.2f}).")
            log_rejected_signal(symbol, 'LONG', {}, "Price below 4H SMA 200")
            return False

    # === PHASE 1 IMPROVEMENT: Multi-Timeframe Stochastic Alignment ===
    if strategy_toggles.REQUIRE_1H_STOCH_ALIGNMENT:
        # For longs: 1h stochastic should also be oversold or rising from oversold
        stoch_1h_oversold = stoch_k_1h.iloc[-1] < (STOCH_OVERSOLD_THRESHOLD + 10)  # Slightly relaxed threshold
        if not stoch_1h_oversold:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: 1H Stochastic ({stoch_k_1h.iloc[-1]:.2f}) not aligned (not oversold).")
            log_rejected_signal(symbol, 'LONG', {'Stoch_K': stoch_k_1h.iloc[-1]}, "1H Stoch not aligned")
            return False

    # === PHASE 2 IMPROVEMENT: Institutional VWAP Filter ===
    if getattr(strategy_toggles, 'REQUIRE_VWAP_ALIGNMENT', False):
        current_price = df_15m['close'].iloc[-1]
        vwap = df_15m['vwap'].iloc[-1]
        if current_price < vwap:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: Price (${current_price:.2f}) below VWAP (${vwap:.2f}).")
            log_rejected_signal(symbol, 'LONG', {'Price': current_price, 'VWAP': vwap}, "Price below VWAP")
            return False

    # === NEW: Exhaustion Guard ===
    if getattr(strategy_toggles, 'REQUIRE_ATR_EXHAUSTION_GUARD', False):
        candle_high = df_15m['high'].iloc[-1]
        candle_low = df_15m['low'].iloc[-1]
        candle_size = candle_high - candle_low
        if candle_size > atr_value * MAX_CANDLE_ATR_MULTIPLIER:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: Trigger candle size ({candle_size:.4f}) exceeds {MAX_CANDLE_ATR_MULTIPLIER}x ATR ({atr_value:.4f}). Exhaustion risk.")
            log_rejected_signal(symbol, 'LONG', {'Candle_Size': candle_size, 'ATR': atr_value}, "ATR Exhaustion Guard")
            return False

    # === NEW: Mean-Reversion Guard (Bollinger Bands) ===
    if getattr(strategy_toggles, 'REQUIRE_BB_REVERSION_GUARD', False) and 'BB_Upper' in df_15m.columns:
        current_price = df_15m['close'].iloc[-1]
        bb_upper = df_15m['BB_Upper'].iloc[-1]
        if pd.notna(bb_upper) and current_price > bb_upper:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: Price (${current_price:.4f}) is pushing above upper Bollinger Band (${bb_upper:.4f}). Mean-reversion risk.")
            log_rejected_signal(symbol, 'LONG', {'Price': current_price, 'BB_Upper': bb_upper}, "Bollinger Band Reversion Guard")
            return False

    # === PHASE 2 IMPROVEMENT: Volume Anomaly Detection ===
    if getattr(strategy_toggles, 'REQUIRE_VOLUME_ANOMALY', False):
        if not df_15m['volume_anomaly'].iloc[-1]:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: No volume anomaly detected (insufficient momentum).")
            log_rejected_signal(symbol, 'LONG', {}, "No Volume Anomaly")
            return False

    # === PHASE 2 IMPROVEMENT: Break of Structure (BOS) ===
    if getattr(strategy_toggles, 'REQUIRE_BOS', False):
        # We must verify BOS on a CLOSED candle to avoid fake wicks
        if not df_15m['bullish_bos'].iloc[-2]:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: No Bullish Break of Structure (BOS) on last closed candle.")
            log_rejected_signal(symbol, 'LONG', {}, "No Bullish BOS")
            return False

    if AGGRESSIVE_ENTRY:
        last_close = df_15m['close'].iloc[-1]

        # Stochastic signal
        if strategy_toggles.REQUIRE_STOCH_CROSSOVER:
            stoch_crossed_up = (stoch_k_15m.iloc[-1] > stoch_d_15m.iloc[-1] and
                                stoch_k_15m.iloc[-2] <= stoch_d_15m.iloc[-2])
            stochastic_signal = (stoch_k_15m.iloc[-2] < STOCH_AGGR_PULLBACK_LEVEL and stoch_crossed_up)
        else:
            stochastic_signal = (stoch_k_15m.iloc[-1] < STOCH_AGGR_PULLBACK_LEVEL and stoch_k_15m.iloc[-1] > stoch_d_15m.iloc[-1])

        # MACD confirmation
        if strategy_toggles.REQUIRE_MACD_CONFIRMATION:
            macd_bullish = (df_15m['macd'].iloc[-1] > df_15m['macd_signal'].iloc[-1] and
                            df_15m['macd_hist'].iloc[-1] > 0)
        else:
            macd_bullish = True

        # HMA slope (single most reliable trend micro-filter)
        hma_is_sloping_up = df_15m['hma_14'].iloc[-1] > df_15m['hma_14'].iloc[-2]

        # ROC momentum quality filter: trend must be actively accelerating
        df_15m = calculate_roc( df_15m, period=10)
        has_bullish_momentum = df_15m['roc'].iloc[-1] > ROC_MOMENTUM_THRESHOLD

        if (stochastic_signal and macd_bullish and hma_is_sloping_up and has_bullish_momentum):
            last_rsi = df_15m['rsi'].iloc[-1] if 'rsi' in df_15m.columns else 0
            indicators = {
                'ADX': adx_value,
                'Stoch_K': stoch_k_15m.iloc[-1],
                'Stoch_D': stoch_d_15m.iloc[-1],
                'RSI': last_rsi,
                'ROC': df_15m['roc'].iloc[-1],
                'HMA_Slope': 'UP',
                'ATR': atr_value,
                'Reason': 'Bullish confluence (Aggressive)'
            }

            print(f"\n{'='*60}")
            print(f"🚀 [Stochastic Pullback] TRADE SIGNAL: LONG {symbol}")
            print(f"   ADX: {adx_value:.1f} | Stoch: {stoch_k_15m.iloc[-1]:.1f} | ROC: {df_15m['roc'].iloc[-1]:+.2f}%")
            print(f"   MACD Hist: {df_15m['macd_hist'].iloc[-1]:.4f} | HMA: UP")
            print(f"   Entry: Bullish confluence (Aggressive)")
            print(f"{'='*60}\n")
            sys.stdout.flush()

            log_signal_analysis(symbol, {**indicators, 'Price': float(last_close), 'Bullish_BOS': bool(df_15m['bullish_bos'].iloc[-1])}, 'LONG', 'All criteria met')

            result = await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
                                     reason_to_open="Bullish confluence (Aggressive)",
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
            return result
        else:
            rejection_reasons = []
            if not stochastic_signal:
                rejection_reasons.append("Stoch not oversold/rising")
            if not macd_bullish:
                rejection_reasons.append("MACD not bullish")
            if not hma_is_sloping_up:
                rejection_reasons.append("HMA not sloping up")
            if not has_bullish_momentum:
                rejection_reasons.append(f"ROC {df_15m['roc'].iloc[-1]:.2f}% (no upward momentum)")

            log_rejected_signal(symbol, 'LONG', {
                'ADX': adx_value,
                'Stoch_K': stoch_k_15m.iloc[-1],
                'RSI': df_15m['rsi'].iloc[-1] if 'rsi' in df_15m.columns else 0,
                'HMA_Slope': 'UP' if hma_is_sloping_up else 'DOWN/FLAT',
                'Stoch_OK': stochastic_signal,
                'SMA_OK': True,
                'HMA_OK': hma_is_sloping_up,
                'Bullish_BOS': bool(df_15m['bullish_bos'].iloc[-1]),
                'VWAP': float(df_15m['vwap'].iloc[-1]),
                'Volume_Anomaly': bool(df_15m['volume_anomaly'].iloc[-1])
            }, ', '.join(rejection_reasons))
    else:
        # Safe Mode Logic
        entry_candle_close = df_15m['close'].iloc[-2]
        entry_candle_rsi = df_15m['rsi'].iloc[-2]
        price_sma = df_15m['price_sma_50'].iloc[-2]
        confirmation_candle_close = df_15m['close'].iloc[-1]

        price_above_sma = entry_candle_close > price_sma
        rsi_is_bullish = entry_candle_rsi > 50
        stochastic_signal = (stoch_k_15m.iloc[-2] > STOCH_OVERSOLD_THRESHOLD and stoch_k_15m.iloc[-3] <= STOCH_OVERSOLD_THRESHOLD and stoch_k_15m.iloc[-2] > stoch_d_15m.iloc[-2])
        confirmation_is_bullish = confirmation_candle_close > entry_candle_close
        hma_is_sloping_up = df_15m['hma_14'].iloc[-1] > df_15m['hma_14'].iloc[-2] # HMA check added
        
        if (stochastic_signal and price_above_sma and rsi_is_bullish and confirmation_is_bullish and hma_is_sloping_up):
            print(f"✅ Placing SAFE LONG for {symbol} - ADX: {adx_value:.1f}, 15m Stoch: {stoch_k_15m.iloc[-1]:.1f}, 1h Stoch: {stoch_k_1h.iloc[-1]:.1f}")
            return await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance, 
                                     reason_to_open="Bullish confluence (Safe)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
            
    return False

async def open_position_short(symbol, df_15m, df_4h, stoch_k_15m, stoch_d_15m, stoch_k_1h, stoch_d_1h, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):


    # NOTE: Cooldown lockout is enforced in process_symbol() before this function is called.

    # --- Global BTC Filter ---
    if getattr(sys.modules['config.settings'], 'ENABLE_GLOBAL_BTC_FILTER', True) and bot_state.global_btc_trend == 'BULLISH' and symbol != 'BTCUSDT':
        if VERBOSE_LOGGING:
            print(f"Skipping SHORT for {symbol}: Global BTC trend is BULLISH.")
        log_rejected_signal(symbol, 'SHORT', {}, "Global BTC trend is BULLISH")
        return False

    # Time-based filter - skip low volatility periods (mirrors long filter)
    if strategy_toggles.USE_TIME_FILTER:
        is_optimal, time_reason = is_optimal_5m_trading_time()
        if not is_optimal:
            if VERBOSE_LOGGING:
                print(f"⏰ Skipping SHORT for {symbol}: {time_reason}")
            log_rejected_signal(symbol, 'SHORT', {}, f"Time Filter: {time_reason}")
            return False

    adx_value = df_15m['ADX'].iloc[-1]

    # === PHASE 1 IMPROVEMENT: Increased MIN_ADX from 5 to 10 ===
    if adx_value < MIN_ADX_THRESHOLD:
        if VERBOSE_LOGGING:
            print(f"Skipping SHORT for {symbol}: ADX is {adx_value:.2f}, below minimum threshold of {MIN_ADX_THRESHOLD}.")
        log_rejected_signal(symbol, 'SHORT', {'ADX': adx_value}, f"ADX below {MIN_ADX_THRESHOLD}")
        return False

    # === PHASE 1 IMPROVEMENT: SMA 200 Trend Filter on 4H ===
    if strategy_toggles.USE_SMA_200_FILTER:
        last_close_4h = df_4h['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close_4h > sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: Price (${last_close_4h:.2f}) above 4H SMA 200 (${sma_200_4h:.2f}).")
            log_rejected_signal(symbol, 'SHORT', {}, "Price above 4H SMA 200")
            return False

    # === PHASE 1 IMPROVEMENT: Multi-Timeframe Stochastic Alignment ===
    if strategy_toggles.REQUIRE_1H_STOCH_ALIGNMENT:
        # For shorts: 1h stochastic should also be overbought or falling from overbought
        stoch_1h_overbought = stoch_k_1h.iloc[-1] > (STOCH_OVERBOUGHT_THRESHOLD - 10)  # Slightly relaxed threshold
        if not stoch_1h_overbought:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: 1H Stochastic ({stoch_k_1h.iloc[-1]:.2f}) not aligned (not overbought).")
            log_rejected_signal(symbol, 'SHORT', {'Stoch_K': stoch_k_1h.iloc[-1]}, "1H Stoch not aligned")
            return False

    # === PHASE 2 IMPROVEMENT: Institutional VWAP Filter ===
    if getattr(strategy_toggles, 'REQUIRE_VWAP_ALIGNMENT', False):
        current_price = df_15m['close'].iloc[-1]
        vwap = df_15m['vwap'].iloc[-1]
        if current_price > vwap:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: Price (${current_price:.2f}) above VWAP (${vwap:.2f}).")
            log_rejected_signal(symbol, 'SHORT', {'Price': current_price, 'VWAP': vwap}, "Price above VWAP")
            return False

    # === NEW: Exhaustion Guard ===
    if getattr(strategy_toggles, 'REQUIRE_ATR_EXHAUSTION_GUARD', False):
        candle_high = df_15m['high'].iloc[-1]
        candle_low = df_15m['low'].iloc[-1]
        candle_size = candle_high - candle_low
        if candle_size > atr_value * MAX_CANDLE_ATR_MULTIPLIER:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: Trigger candle size ({candle_size:.4f}) exceeds {MAX_CANDLE_ATR_MULTIPLIER}x ATR ({atr_value:.4f}). Exhaustion risk.")
            log_rejected_signal(symbol, 'SHORT', {'Candle_Size': candle_size, 'ATR': atr_value}, "ATR Exhaustion Guard")
            return False

    # === NEW: Mean-Reversion Guard (Bollinger Bands) ===
    if getattr(strategy_toggles, 'REQUIRE_BB_REVERSION_GUARD', False) and 'BB_Lower' in df_15m.columns:
        current_price = df_15m['close'].iloc[-1]
        bb_lower = df_15m['BB_Lower'].iloc[-1]
        if pd.notna(bb_lower) and current_price < bb_lower:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: Price (${current_price:.4f}) is pushing below lower Bollinger Band (${bb_lower:.4f}). Mean-reversion risk.")
            log_rejected_signal(symbol, 'SHORT', {'Price': current_price, 'BB_Lower': bb_lower}, "Bollinger Band Reversion Guard")
            return False

    # === PHASE 2 IMPROVEMENT: Volume Anomaly Detection ===
    if getattr(strategy_toggles, 'REQUIRE_VOLUME_ANOMALY', False):
        if not df_15m['volume_anomaly'].iloc[-1]:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: No volume anomaly detected (insufficient momentum).")
            log_rejected_signal(symbol, 'SHORT', {}, "No Volume Anomaly")
            return False

    # === PHASE 2 IMPROVEMENT: Break of Structure (BOS) ===
    if getattr(strategy_toggles, 'REQUIRE_BOS', False):
        # We must verify BOS on a CLOSED candle to avoid fake wicks
        if not df_15m['bearish_bos'].iloc[-2]:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: No Bearish Break of Structure (BOS) on last closed candle.")
            log_rejected_signal(symbol, 'SHORT', {}, "No Bearish BOS")
            return False

    if AGGRESSIVE_ENTRY:
        last_close = df_15m['close'].iloc[-1]

        # Stochastic signal
        if strategy_toggles.REQUIRE_STOCH_CROSSOVER:
            stoch_crossed_down = (stoch_k_15m.iloc[-1] < stoch_d_15m.iloc[-1] and
                                  stoch_k_15m.iloc[-2] >= stoch_d_15m.iloc[-2])
            stochastic_signal = (stoch_k_15m.iloc[-2] > (100 - STOCH_AGGR_PULLBACK_LEVEL) and stoch_crossed_down)
        else:
            stochastic_signal = (stoch_k_15m.iloc[-1] > (100 - STOCH_AGGR_PULLBACK_LEVEL) and stoch_k_15m.iloc[-1] < stoch_d_15m.iloc[-1])

        # MACD confirmation
        if strategy_toggles.REQUIRE_MACD_CONFIRMATION:
            macd_bearish = (df_15m['macd'].iloc[-1] < df_15m['macd_signal'].iloc[-1] and
                            df_15m['macd_hist'].iloc[-1] < 0)
        else:
            macd_bearish = True

        # HMA slope
        hma_is_sloping_down = df_15m['hma_14'].iloc[-1] < df_15m['hma_14'].iloc[-2]

        # ROC momentum quality filter: trend must be actively declining
        df_15m = calculate_roc( df_15m, period=10)
        has_bearish_momentum = df_15m['roc'].iloc[-1] < -ROC_MOMENTUM_THRESHOLD

        if (stochastic_signal and macd_bearish and hma_is_sloping_down and has_bearish_momentum):
            print(f"🚀 [Stochastic Pullback] TRADE SIGNAL: SHORT {symbol}")
            print(f"   ADX: {adx_value:.1f} | Stoch: {stoch_k_15m.iloc[-1]:.1f} | ROC: {df_15m['roc'].iloc[-1]:+.2f}%")
            print(f"   MACD Hist: {df_15m['macd_hist'].iloc[-1]:.4f} | HMA: DOWN")
            print(f"   Entry: Bearish confluence (Aggressive)")
            print(f"{'='*60}\n")
            sys.stdout.flush()
            
            log_signal_analysis(symbol, {'Price': float(last_close), 'Bearish_BOS': bool(df_15m['bearish_bos'].iloc[-1])}, 'SHORT', 'All criteria met')
            
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
                                     reason_to_open="Bearish confluence (Aggressive)",
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
        else:
            rejection_reasons = []
            if not stochastic_signal:
                rejection_reasons.append("Stoch not overbought/falling")
            if not macd_bearish:
                rejection_reasons.append("MACD not bearish")
            if not hma_is_sloping_down:
                rejection_reasons.append("HMA not sloping down")
            if not has_bearish_momentum:
                rejection_reasons.append(f"ROC {df_15m['roc'].iloc[-1]:.2f}% (no downward momentum)")

            log_rejected_signal(symbol, 'SHORT', {
                'ADX': adx_value,
                'Stoch_K': stoch_k_15m.iloc[-1],
                'RSI': df_15m['rsi'].iloc[-1] if 'rsi' in df_15m.columns else 0,
                'HMA_Slope': 'DOWN' if hma_is_sloping_down else 'UP/FLAT',
                'Stoch_OK': stochastic_signal,
                'SMA_OK': True,
                'HMA_OK': hma_is_sloping_down,
                'Bearish_BOS': bool(df_15m['bearish_bos'].iloc[-1]),
                'VWAP': float(df_15m['vwap'].iloc[-1]),
                'Volume_Anomaly': bool(df_15m['volume_anomaly'].iloc[-1])
            }, ', '.join(rejection_reasons))

    else:
        # Safe Mode Logic
        entry_candle_close = df_15m['close'].iloc[-2]
        entry_candle_rsi = df_15m['rsi'].iloc[-2]
        price_sma = df_15m['price_sma_50'].iloc[-2]
        confirmation_candle_close = df_15m['close'].iloc[-1]

        price_below_sma = entry_candle_close < price_sma
        rsi_is_bearish = entry_candle_rsi < 50
        stochastic_signal = (stoch_k_15m.iloc[-2] < STOCH_OVERBOUGHT_THRESHOLD and stoch_k_15m.iloc[-3] >= STOCH_OVERBOUGHT_THRESHOLD and stoch_k_15m.iloc[-2] < stoch_d_15m.iloc[-2])
        confirmation_is_bearish = confirmation_candle_close < entry_candle_close
        hma_is_sloping_down = df_15m['hma_14'].iloc[-1] < df_15m['hma_14'].iloc[-2]

        if (stochastic_signal and price_below_sma and rsi_is_bearish and confirmation_is_bearish and hma_is_sloping_down):
            print(f"🔻 Placing SAFE SHORT for {symbol} - ADX: {adx_value:.1f}, 15m Stoch: {stoch_k_15m.iloc[-1]:.1f}, 1h Stoch: {stoch_k_1h.iloc[-1]:.1f}")
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
                                     reason_to_open="Bearish confluence (Safe)",
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)

    return False