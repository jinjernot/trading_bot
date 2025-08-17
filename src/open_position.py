from binance.enums import *
from src.trade import place_order
from data.indicators import *
from config.settings import *

async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):
    
    adx_value = df['ADX'].iloc[-1]
    if adx_value < 20: # ADX filter to avoid choppy markets
        if VERBOSE_LOGGING:
            print(f"Skipping LONG for {symbol}: ADX is {adx_value:.2f}, indicating weak trend.")
        return False

    if AGGRESSIVE_ENTRY:
        price_sma = df['price_sma_50'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        last_volume = df['volume'].iloc[-1]
        volume_sma = df['volume_sma_20'].iloc[-1]
        last_close = df['close'].iloc[-1]
        
        stochastic_signal = (stoch_k.iloc[-1] > OVERSOLD and stoch_k.iloc[-2] <= OVERSOLD and stoch_k.iloc[-1] > stoch_d.iloc[-1])
        price_above_sma = last_close > price_sma
        rsi_is_bullish = last_rsi > 50
        volume_is_strong = last_volume > volume_sma
        funding_rate_is_healthy = funding_rate < 0.0004
        
        if (stochastic_signal and price_above_sma and rsi_is_bullish and volume_is_strong and funding_rate_is_healthy):
            print(f"Placing AGGRESSIVE order for {symbol} due to strong bullish confluence.")
            return await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance, 
                                     reason_to_open="Bullish confluence (Aggressive)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
    else:
        # Safe Mode Logic
        entry_candle_close = df['close'].iloc[-2]
        entry_candle_rsi = df['rsi'].iloc[-2]
        entry_candle_volume = df['volume'].iloc[-2]
        price_sma = df['price_sma_50'].iloc[-2]
        volume_sma = df['volume_sma_20'].iloc[-2]
        confirmation_candle_close = df['close'].iloc[-1]

        price_above_sma = entry_candle_close > price_sma
        rsi_is_bullish = entry_candle_rsi > 50
        volume_is_strong = entry_candle_volume > volume_sma
        stochastic_signal = (stoch_k.iloc[-2] > OVERSOLD and stoch_k.iloc[-3] <= OVERSOLD and stoch_k.iloc[-2] > stoch_d.iloc[-2])
        funding_rate_is_healthy = funding_rate < 0.0004
        confirmation_is_bullish = confirmation_candle_close > entry_candle_close
        
        if (stochastic_signal and price_above_sma and rsi_is_bullish and volume_is_strong and funding_rate_is_healthy and confirmation_is_bullish):
            print(f"Placing SAFE order for {symbol} due to strong bullish confluence with confirmation.")
            return await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance, 
                                     reason_to_open="Bullish confluence (Safe)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
            
    return False

async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):

    adx_value = df['ADX'].iloc[-1]
    if adx_value < 20: # ADX filter to avoid choppy markets
        if VERBOSE_LOGGING:
            print(f"Skipping SHORT for {symbol}: ADX is {adx_value:.2f}, indicating weak trend.")
        return False

    if AGGRESSIVE_ENTRY:
        price_sma = df['price_sma_50'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        last_volume = df['volume'].iloc[-1]
        volume_sma = df['volume_sma_20'].iloc[-1]
        last_close = df['close'].iloc[-1]
        
        stochastic_signal = (stoch_k.iloc[-1] < OVERBOUGHT and stoch_k.iloc[-2] >= OVERBOUGHT and stoch_k.iloc[-1] < stoch_d.iloc[-1])
        price_below_sma = last_close < price_sma
        rsi_is_bearish = last_rsi < 50
        volume_is_strong = last_volume > volume_sma
        funding_rate_is_healthy = funding_rate > -0.0004
        
        if (stochastic_signal and price_below_sma and rsi_is_bearish and volume_is_strong and funding_rate_is_healthy):
            print(f"Placing AGGRESSIVE order for {symbol} due to strong bearish confluence.")
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance, 
                                     reason_to_open="Bearish confluence (Aggressive)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
    
    else:
        # Safe Mode Logic
        entry_candle_close = df['close'].iloc[-2]
        entry_candle_rsi = df['rsi'].iloc[-2]
        entry_candle_volume = df['volume'].iloc[-2]
        price_sma = df['price_sma_50'].iloc[-2]
        volume_sma = df['volume_sma_20'].iloc[-2]
        confirmation_candle_close = df['close'].iloc[-1]

        price_below_sma = entry_candle_close < price_sma
        rsi_is_bearish = entry_candle_rsi < 50
        volume_is_strong = entry_candle_volume > volume_sma
        stochastic_signal = (stoch_k.iloc[-2] < OVERBOUGHT and stoch_k.iloc[-3] >= OVERBOUGHT and stoch_k.iloc[-2] < stoch_d.iloc[-2])
        funding_rate_is_healthy = funding_rate > -0.0004
        confirmation_is_bearish = confirmation_candle_close < entry_candle_close

        if (stochastic_signal and price_below_sma and rsi_is_bearish and volume_is_strong and funding_rate_is_healthy and confirmation_is_bearish):
            print(f"Placing SAFE order for {symbol} due to strong bearish confluence with confirmation.")
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance, 
                                     reason_to_open="Bearish confluence (Safe)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)

    return False
