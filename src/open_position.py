from binance.enums import *
from src.trade import place_order
from data.indicators import *
from config.settings import *
import pandas as pd

async def open_position_long(symbol, df_15m, df_4h, stoch_k_15m, stoch_d_15m, stoch_k_1h, stoch_d_1h, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):
    
    adx_value = df_15m['ADX'].iloc[-1]

    # === PHASE 1 IMPROVEMENT: Increased MIN_ADX from 5 to 10 ===
    if adx_value < MIN_ADX_THRESHOLD:
        if VERBOSE_LOGGING:
            print(f"Skipping LONG for {symbol}: ADX is {adx_value:.2f}, below minimum threshold of {MIN_ADX_THRESHOLD}.")
        return False

    # === PHASE 1 IMPROVEMENT: SMA 200 Trend Filter on 4H ===
    if USE_SMA_200_FILTER:
        last_close_4h = df_4h['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close_4h < sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: Price (${last_close_4h:.2f}) below 4H SMA 200 (${sma_200_4h:.2f}).")
            return False

    # === PHASE 1 IMPROVEMENT: Multi-Timeframe Stochastic Alignment ===
    if REQUIRE_1H_STOCH_ALIGNMENT:
        # For longs: 1h stochastic should also be oversold or rising from oversold
        stoch_1h_oversold = stoch_k_1h.iloc[-1] < 30  # Slightly relaxed threshold
        if not stoch_1h_oversold:
            if VERBOSE_LOGGING:
                print(f"Skipping LONG for {symbol}: 1H Stochastic ({stoch_k_1h.iloc[-1]:.2f}) not aligned (not oversold).")
            return False

    if AGGRESSIVE_ENTRY:
        price_sma = df_15m['price_sma_50'].iloc[-1]
        last_rsi = df_15m['rsi'].iloc[-1]
        last_close = df_15m['close'].iloc[-1]
        
        # Relaxed: Allow entry anytime stoch is oversold and rising (not just on exact crossover)
        stochastic_signal = (stoch_k_15m.iloc[-1] < 30 and stoch_k_15m.iloc[-1] > stoch_d_15m.iloc[-1])
        price_above_sma = last_close > price_sma
        rsi_is_bullish = last_rsi > 50
        hma_is_sloping_up = df_15m['hma_14'].iloc[-1] > df_15m['hma_14'].iloc[-2]
        
        if (stochastic_signal and price_above_sma and rsi_is_bullish and hma_is_sloping_up):
            import sys
            from src.detailed_logger import log_trade_entry, log_signal_analysis
            
            # Prepare indicator data for logging
            indicators = {
                'ADX': adx_value,
                'Stoch_K': stoch_k_15m.iloc[-1],
                'Stoch_D': stoch_d_15m.iloc[-1],
                'RSI': last_rsi,
                'Price_vs_SMA50': f"{((last_close / price_sma - 1) * 100):.2f}%",
                'HMA_Slope': 'UP',
                'ATR': atr_value,
                'Reason': 'Bullish confluence (Aggressive)'
            }
            
            print(f"\n{'='*60}")
            print(f"🚀 TRADE SIGNAL: LONG {symbol}")
            print(f"   ADX: {adx_value:.1f} | Stoch: {stoch_k_15m.iloc[-1]:.1f} | RSI: {last_rsi:.1f}")
            print(f"   Entry: Bullish confluence (Aggressive)")
            print(f"{'='*60}\n")
            sys.stdout.flush()
            
            # Log the signal analysis
            log_signal_analysis(symbol, {**indicators, 'Price': last_close, 'SMA50': price_sma}, 'LONG', 'All criteria met')
            
            result = await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance, 
                                     reason_to_open="Bullish confluence (Aggressive)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
            
            return result
        else:
            # Log rejected signal for analysis
            from src.detailed_logger import log_rejected_signal
            rejection_reasons = []
            if not stochastic_signal:
                rejection_reasons.append("Stoch not oversold/rising")
            if not price_above_sma:
                rejection_reasons.append("Price below SMA50")
            if not rsi_is_bullish:
                rejection_reasons.append(f"RSI {last_rsi:.1f} < 50")
            if not hma_is_sloping_up:
                rejection_reasons.append("HMA not sloping up")
            
            log_rejected_signal(symbol, 'LONG', {
                'ADX': adx_value,
                'Stoch_K': stoch_k_15m.iloc[-1],
                'RSI': last_rsi,
                'Price_vs_SMA': 'ABOVE' if price_above_sma else 'BELOW',
                'HMA_Slope': 'UP' if hma_is_sloping_up else 'DOWN/FLAT',
                'Stoch_OK': stochastic_signal,
                'RSI_OK': rsi_is_bullish,
                'SMA_OK': price_above_sma,
                'HMA_OK': hma_is_sloping_up
            }, ', '.join(rejection_reasons))
    else:
        # Safe Mode Logic
        entry_candle_close = df_15m['close'].iloc[-2]
        entry_candle_rsi = df_15m['rsi'].iloc[-2]
        price_sma = df_15m['price_sma_50'].iloc[-2]
        confirmation_candle_close = df_15m['close'].iloc[-1]

        price_above_sma = entry_candle_close > price_sma
        rsi_is_bullish = entry_candle_rsi > 50
        stochastic_signal = (stoch_k_15m.iloc[-2] > OVERSOLD and stoch_k_15m.iloc[-3] <= OVERSOLD and stoch_k_15m.iloc[-2] > stoch_d_15m.iloc[-2])
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

    adx_value = df_15m['ADX'].iloc[-1]

    # === PHASE 1 IMPROVEMENT: Increased MIN_ADX from 5 to 10 ===
    if adx_value < MIN_ADX_THRESHOLD:
        if VERBOSE_LOGGING:
            print(f"Skipping SHORT for {symbol}: ADX is {adx_value:.2f}, below minimum threshold of {MIN_ADX_THRESHOLD}.")
        return False

    # === PHASE 1 IMPROVEMENT: SMA 200 Trend Filter on 4H ===
    if USE_SMA_200_FILTER:
        last_close_4h = df_4h['close'].iloc[-1]
        sma_200_4h = df_4h['price_sma_200'].iloc[-1]
        if pd.notna(sma_200_4h) and last_close_4h > sma_200_4h:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: Price (${last_close_4h:.2f}) above 4H SMA 200 (${sma_200_4h:.2f}).")
            return False

    # === PHASE 1 IMPROVEMENT: Multi-Timeframe Stochastic Alignment ===
    if REQUIRE_1H_STOCH_ALIGNMENT:
        # For shorts: 1h stochastic should also be overbought or falling from overbought
        stoch_1h_overbought = stoch_k_1h.iloc[-1] > 70  # Slightly relaxed threshold
        if not stoch_1h_overbought:
            if VERBOSE_LOGGING:
                print(f"Skipping SHORT for {symbol}: 1H Stochastic ({stoch_k_1h.iloc[-1]:.2f}) not aligned (not overbought).")
            return False

    if AGGRESSIVE_ENTRY:
        price_sma = df_15m['price_sma_50'].iloc[-1]
        last_rsi = df_15m['rsi'].iloc[-1]
        last_close = df_15m['close'].iloc[-1]
        
        # Relaxed: Allow entry anytime stoch is overbought and falling (not just on crossover)
        stochastic_signal = (stoch_k_15m.iloc[-1] > 70 and stoch_k_15m.iloc[-1] < stoch_d_15m.iloc[-1])
        price_below_sma = last_close < price_sma
        rsi_is_bearish = last_rsi < 50
        hma_is_sloping_down = df_15m['hma_14'].iloc[-1] < df_15m['hma_14'].iloc[-2] # HMA check added
        
        if (stochastic_signal and price_below_sma and rsi_is_bearish and hma_is_sloping_down):
            import sys
            print(f"\n{'='*60}")
            print(f"🚀 TRADE SIGNAL: SHORT {symbol}")
            print(f"   ADX: {adx_value:.1f} | Stoch: {stoch_k_15m.iloc[-1]:.1f} | RSI: {last_rsi:.1f}")
            print(f"   Entry: Bearish confluence (Aggressive)")
            print(f"{'='*60}\n")
            sys.stdout.flush()
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance, 
                                     reason_to_open="Bearish confluence (Aggressive)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
    
    else:
        # Safe Mode Logic
        entry_candle_close = df_15m['close'].iloc[-2]
        entry_candle_rsi = df_15m['rsi'].iloc[-2]
        price_sma = df_15m['price_sma_50'].iloc[-2]
        confirmation_candle_close = df_15m['close'].iloc[-1]

        price_below_sma = entry_candle_close < price_sma
        rsi_is_bearish = entry_candle_rsi < 50
        stochastic_signal = (stoch_k_15m.iloc[-2] < OVERBOUGHT and stoch_k_15m.iloc[-3] >= OVERBOUGHT and stoch_k_15m.iloc[-2] < stoch_d_15m.iloc[-2])
        confirmation_is_bearish = confirmation_candle_close < entry_candle_close
        hma_is_sloping_down = df_15m['hma_14'].iloc[-1] < df_15m['hma_14'].iloc[-2] # HMA check added

        if (stochastic_signal and price_below_sma and rsi_is_bearish and confirmation_is_bearish and hma_is_sloping_down):
            print(f"🔻 Placing SAFE SHORT for {symbol} - ADX: {adx_value:.1f}, 15m Stoch: {stoch_k_15m.iloc[-1]:.1f}, 1h Stoch: {stoch_k_1h.iloc[-1]:.1f}")
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance, 
                                     reason_to_open="Bearish confluence (Safe)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)

    return False