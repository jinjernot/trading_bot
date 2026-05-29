import pandas as pd
import sys
from binance.enums import SIDE_BUY, SIDE_SELL
from src.trade import place_order
from src.detailed_logger import log_rejected_signal, log_signal_analysis
from config.settings import VWAP_PULLBACK_PROXIMITY, VWAP_STOP_BUFFER, VERBOSE_LOGGING

async def check_vwap_pullback_long(symbol, df_15m, df_4h, usdt_balance, support_4h, resistance_4h):
    # Ensure VWAP is available
    if 'vwap' not in df_15m.columns:
        return False
        
    vwap = df_15m['vwap'].iloc[-1]
    last_close = df_15m['close'].iloc[-1]
    
    # 1. Trend Filter: Price must be > 4H SMA 200, ADX > 20
    sma_200_4h = df_4h['price_sma_200'].iloc[-1] if 'price_sma_200' in df_4h.columns else 0
    adx_4h = df_4h['ADX'].iloc[-1] if 'ADX' in df_4h.columns else 0
    
    if not (pd.notna(sma_200_4h) and last_close > sma_200_4h):
        return False
        
    if adx_4h < 20:
        return False

    # 2. Pullback Condition: Price must be near VWAP from above
    # Positive distance means price is above VWAP. Must be <= proximity threshold.
    distance_to_vwap = (last_close - vwap) / vwap
    if not (0 <= distance_to_vwap <= VWAP_PULLBACK_PROXIMITY):
        return False

    # 3. Confirmation: HMA slope is UP OR Bullish Candlestick Pattern
    hma_is_sloping_up = False
    if 'hma_14' in df_15m.columns:
        hma_is_sloping_up = df_15m['hma_14'].iloc[-1] > df_15m['hma_14'].iloc[-2]
        
    bullish_pattern = False
    if 'bullish_pattern' in df_15m.columns:
        bullish_pattern = bool(df_15m['bullish_pattern'].iloc[-1])
        
    if not (hma_is_sloping_up or bullish_pattern):
        if VERBOSE_LOGGING:
            print(f"Skipping VWAP LONG for {symbol}: Near VWAP but no bullish confirmation (HMA flat/down and no candle pattern).")
        log_rejected_signal(symbol, 'LONG', {'VWAP_Dist': distance_to_vwap}, "VWAP touch lacking confirmation")
        return False

    # Entry confirmed!
    print(f"\n{'='*60}")
    print(f"🚀 [VWAP Pullback] TRADE SIGNAL: LONG {symbol}")
    print(f"   VWAP: {vwap:.4f} | Entry: {last_close:.4f} | Dist: {distance_to_vwap*100:.2f}%")
    print(f"   Confirmation: HMA UP={hma_is_sloping_up}, Bull Pattern={bullish_pattern}")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    # Risk Management: Stop loss is 0.5% below VWAP or recent swing low
    vwap_sl = vwap * (1 - VWAP_STOP_BUFFER)
    recent_low = df_15m['low'].iloc[-5:].min()
    stop_price = min(vwap_sl, recent_low)
    
    log_signal_analysis(symbol, {'VWAP': vwap, 'Price': last_close, 'ADX_4H': adx_4h}, 'LONG', 'VWAP Pullback')
    
    atr_value = df_15m['atr'].iloc[-1] if 'atr' in df_15m.columns else None
    adx_value = df_15m['ADX'].iloc[-1] if 'ADX' in df_15m.columns else 20
    
    return await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance,
                             reason_to_open="VWAP Trend Pullback",
                             stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                             support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value,
                             stop_loss_price=stop_price)

async def check_vwap_pullback_short(symbol, df_15m, df_4h, usdt_balance, support_4h, resistance_4h):
    if 'vwap' not in df_15m.columns:
        return False
        
    vwap = df_15m['vwap'].iloc[-1]
    last_close = df_15m['close'].iloc[-1]
    
    # 1. Trend Filter: Price must be < 4H SMA 200, ADX > 20
    sma_200_4h = df_4h['price_sma_200'].iloc[-1] if 'price_sma_200' in df_4h.columns else 0
    adx_4h = df_4h['ADX'].iloc[-1] if 'ADX' in df_4h.columns else 0
    
    if not (pd.notna(sma_200_4h) and last_close < sma_200_4h):
        return False
        
    if adx_4h < 20:
        return False

    # 2. Pullback Condition: Price must be near VWAP from below
    # Negative distance means price is below VWAP. Absolute value must be <= proximity threshold.
    distance_to_vwap = (vwap - last_close) / vwap
    if not (0 <= distance_to_vwap <= VWAP_PULLBACK_PROXIMITY):
        return False

    # 3. Confirmation: HMA slope is DOWN OR Bearish Candlestick Pattern
    hma_is_sloping_down = False
    if 'hma_14' in df_15m.columns:
        hma_is_sloping_down = df_15m['hma_14'].iloc[-1] < df_15m['hma_14'].iloc[-2]
        
    bearish_pattern = False
    if 'bearish_pattern' in df_15m.columns:
        bearish_pattern = bool(df_15m['bearish_pattern'].iloc[-1])
        
    if not (hma_is_sloping_down or bearish_pattern):
        if VERBOSE_LOGGING:
            print(f"Skipping VWAP SHORT for {symbol}: Near VWAP but no bearish confirmation (HMA flat/up and no candle pattern).")
        log_rejected_signal(symbol, 'SHORT', {'VWAP_Dist': distance_to_vwap}, "VWAP touch lacking confirmation")
        return False

    # Entry confirmed!
    print(f"\n{'='*60}")
    print(f"🔻 [VWAP Pullback] TRADE SIGNAL: SHORT {symbol}")
    print(f"   VWAP: {vwap:.4f} | Entry: {last_close:.4f} | Dist: {distance_to_vwap*100:.2f}%")
    print(f"   Confirmation: HMA DOWN={hma_is_sloping_down}, Bear Pattern={bearish_pattern}")
    print(f"{'='*60}\n")
    sys.stdout.flush()

    # Risk Management: Stop loss is 0.5% above VWAP or recent swing high
    vwap_sl = vwap * (1 + VWAP_STOP_BUFFER)
    recent_high = df_15m['high'].iloc[-5:].max()
    stop_price = max(vwap_sl, recent_high)
    
    log_signal_analysis(symbol, {'VWAP': vwap, 'Price': last_close, 'ADX_4H': adx_4h}, 'SHORT', 'VWAP Pullback')
    
    atr_value = df_15m['atr'].iloc[-1] if 'atr' in df_15m.columns else None
    adx_value = df_15m['ADX'].iloc[-1] if 'ADX' in df_15m.columns else 20
    
    return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance,
                             reason_to_open="VWAP Trend Pullback",
                             stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df_15m,
                             support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value,
                             stop_loss_price=stop_price)
