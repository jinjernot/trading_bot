from binance.enums import *
from src.trade import place_order
from data.indicators import *
from config.settings import *

async def open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):
    
    adx_value = df['ADX'].iloc[-1]

    if adx_value < 5:
        if VERBOSE_LOGGING:
            print(f"Skipping LONG for {symbol}: ADX is {adx_value:.2f}, indicating weak trend.")
        return False

    if AGGRESSIVE_ENTRY:
        price_sma = df['price_sma_50'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        last_close = df['close'].iloc[-1]
        
        stochastic_signal = (stoch_k.iloc[-1] > OVERSOLD and stoch_k.iloc[-2] <= OVERSOLD and stoch_k.iloc[-1] > stoch_d.iloc[-1])
        price_above_sma = last_close > price_sma
        rsi_is_bullish = last_rsi > 50
        hma_is_sloping_up = df['hma_14'].iloc[-1] > df['hma_14'].iloc[-2] # HMA check added
        
        if (stochastic_signal and price_above_sma and rsi_is_bullish and hma_is_sloping_up):
            print(f"Placing AGGRESSIVE order for {symbol} due to strong bullish confluence.")
            return await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance, 
                                     reason_to_open="Bullish confluence (Aggressive)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
    else:
        # Safe Mode Logic
        entry_candle_close = df['close'].iloc[-2]
        entry_candle_rsi = df['rsi'].iloc[-2]
        price_sma = df['price_sma_50'].iloc[-2]
        confirmation_candle_close = df['close'].iloc[-1]

        price_above_sma = entry_candle_close > price_sma
        rsi_is_bullish = entry_candle_rsi > 50
        stochastic_signal = (stoch_k.iloc[-2] > OVERSOLD and stoch_k.iloc[-3] <= OVERSOLD and stoch_k.iloc[-2] > stoch_d.iloc[-2])
        confirmation_is_bullish = confirmation_candle_close > entry_candle_close
        hma_is_sloping_up = df['hma_14'].iloc[-1] > df['hma_14'].iloc[-2] # HMA check added
        
        if (stochastic_signal and price_above_sma and rsi_is_bullish and confirmation_is_bullish and hma_is_sloping_up):
            print(f"Placing SAFE order for {symbol} due to strong bullish confluence with confirmation.")
            return await place_order(symbol=symbol, side=SIDE_BUY, usdt_balance=usdt_balance, 
                                     reason_to_open="Bullish confluence (Safe)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
            
    return False

async def open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate, support_4h, resistance_4h):

    adx_value = df['ADX'].iloc[-1]

    if adx_value < 5:
        if VERBOSE_LOGGING:
            print(f"Skipping SHORT for {symbol}: ADX is {adx_value:.2f}, indicating weak trend.")
        return False

    if AGGRESSIVE_ENTRY:
        price_sma = df['price_sma_50'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        last_close = df['close'].iloc[-1]
        
        stochastic_signal = (stoch_k.iloc[-1] < OVERBOUGHT and stoch_k.iloc[-2] >= OVERBOUGHT and stoch_k.iloc[-1] < stoch_d.iloc[-1])
        price_below_sma = last_close < price_sma
        rsi_is_bearish = last_rsi < 50
        hma_is_sloping_down = df['hma_14'].iloc[-1] < df['hma_14'].iloc[-2] # HMA check added
        
        if (stochastic_signal and price_below_sma and rsi_is_bearish and hma_is_sloping_down):
            print(f"Placing AGGRESSIVE order for {symbol} due to strong bearish confluence.")
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance, 
                                     reason_to_open="Bearish confluence (Aggressive)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)
    
    else:
        # Safe Mode Logic
        entry_candle_close = df['close'].iloc[-2]
        entry_candle_rsi = df['rsi'].iloc[-2]
        price_sma = df['price_sma_50'].iloc[-2]
        confirmation_candle_close = df['close'].iloc[-1]

        price_below_sma = entry_candle_close < price_sma
        rsi_is_bearish = entry_candle_rsi < 50
        stochastic_signal = (stoch_k.iloc[-2] < OVERBOUGHT and stoch_k.iloc[-3] >= OVERBOUGHT and stoch_k.iloc[-2] < stoch_d.iloc[-2])
        confirmation_is_bearish = confirmation_candle_close < entry_candle_close
        hma_is_sloping_down = df['hma_14'].iloc[-1] < df['hma_14'].iloc[-2] # HMA check added

        if (stochastic_signal and price_below_sma and rsi_is_bearish and confirmation_is_bearish and hma_is_sloping_down):
            print(f"Placing SAFE order for {symbol} due to strong bearish confluence with confirmation.")
            return await place_order(symbol=symbol, side=SIDE_SELL, usdt_balance=usdt_balance, 
                                     reason_to_open="Bearish confluence (Safe)", 
                                     stop_loss_atr_multiplier=2.0, atr_value=atr_value, df=df,
                                     support_4h=support_4h, resistance_4h=resistance_4h, adx_value=adx_value)

    return False