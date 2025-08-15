from src.close_position import *
from src.open_position_copy import *
from src.trade import *
  
from data.get_data import *
from data.indicators import *

from data.indicators import add_short_term_sma

from src.telegram_bot import *
from config.settings import *
from config.symbols import symbols
from src.state_manager import bot_state

import asyncio
import time

# --- Risk Management Settings ---
MAX_CONCURRENT_TRADES = 4
MAX_CONSECUTIVE_LOSSES = 3
COOL_DOWN_PERIOD_SECONDS = 3600 # 1 hour

# --- Timeframe Settings ---
SHORT_TERM_INTERVAL = '15m'
LONG_TERM_INTERVAL = '4h'

async def process_symbol(symbol):
    
    try:
        df_15m, support_15m, resistance_15m, df_4h, support_4h, resistance_4h, stoch_k_4h, stoch_d_4h = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, SHORT_TERM_INTERVAL, LONG_TERM_INTERVAL
        )
        
        long_term_trend = detect_trend(df_4h)
        if VERBOSE_LOGGING:
            print(f"Long-term trend for {symbol} on {LONG_TERM_INTERVAL} chart: {long_term_trend}")
        
        df_15m = add_price_sma(df_15m, period=50)
        df_15m = add_volume_sma(df_15m, period=20)
        df_15m = add_short_term_sma(df_15m, period=9)
        stoch_k_15m, stoch_d_15m = calculate_stoch(df_15m['high'], df_15m['low'], df_15m['close'], PERIOD, K, D)
        df_15m = calculate_rsi(df_15m, period=14)
        df_15m = calculate_atr(df_15m)
        df_15m = calculate_adx(df_15m)
        df_15m = calculate_bollinger_bands(df_15m)
        atr_value = df_15m['atr'].iloc[-1]
        
        last_close = df_15m['close'].iloc[-1]
        atr_percentage = (atr_value / last_close) * 100
        MIN_VOLATILITY = 0.2
        MAX_VOLATILITY = 2.0
        if not (MIN_VOLATILITY < atr_percentage < MAX_VOLATILITY):
            if VERBOSE_LOGGING:
                print(f"Skipping {symbol}: Volatility ({atr_percentage:.2f}%) is outside the optimal range.")
            return
        
        position, roi, unrealized_profit, margin_used, entry_price = get_position(symbol)
        usdt_balance = get_usdt_balance()
        funding_rate = get_funding_rate(symbol)
        
        if position != 0 and roi >= BREAKEVEN_ROI_TARGET and not bot_state.breakeven_triggered.get(symbol):
            trade_side = SIDE_BUY if position > 0 else SIDE_SELL
            if await move_stop_to_breakeven(symbol, entry_price, trade_side):
                bot_state.breakeven_triggered[symbol] = True
        
        if position == 0 and bot_state.breakeven_triggered.get(symbol):
            del bot_state.breakeven_triggered[symbol]
            if VERBOSE_LOGGING:
                print(f"Reset breakeven flag for closed position {symbol}.")

        adx_value = df_15m['ADX'].iloc[-1]
        last_volume = df_15m['volume'].iloc[-1]
        volume_sma = df_15m['volume_sma_20'].iloc[-1]
        
        if adx_value < 20 and last_volume < volume_sma:
            if VERBOSE_LOGGING:
                print(f"Skipping {symbol}: Market is too quiet (ADX: {adx_value:.2f}, Volume is below average).")
            return

        bb_upper = df_15m['BB_Upper'].iloc[-1]
        bb_lower = df_15m['BB_Lower'].iloc[-1]
        bb_mid = df_15m['BB_Mid'].iloc[-1]
        bb_width = ((bb_upper - bb_lower) / bb_mid) * 100
        MIN_BB_WIDTH = 1.5
        
        if bb_width < MIN_BB_WIDTH:
            if VERBOSE_LOGGING:
                print(f"Skipping {symbol}: Market is too choppy (Bollinger Band Width: {bb_width:.2f}%).")
            return
        
        if (long_term_trend == 'uptrend' and funding_rate > 0.001) or \
           (long_term_trend == 'downtrend' and funding_rate < -0.001):
            if VERBOSE_LOGGING:
                print(f"Skipping {symbol}: Unfavorable funding rate ({funding_rate:.4f}) for the current trend.")
            return

        if position > 0:
            await close_position_long(symbol, position, roi, df_15m, stoch_k_15m, resistance_15m)
        elif position < 0:
            await close_position_short(symbol, position, roi, df_15m, stoch_k_15m, support_15m)
        
        if bot_state.trading_paused:
            return

        if position == 0:
            trade_opened = False
            
            stoch_4h_oversold = stoch_k_4h.iloc[-1] < OVERSOLD
            stoch_4h_overbought = stoch_k_4h.iloc[-1] > OVERBOUGHT
            
            # --- NEW: Get 4-Hour Moving Average ---
            sma_4h = df_4h['price_sma_50'].iloc[-1]
            price_above_4h_sma = last_close > sma_4h
            price_below_4h_sma = last_close < sma_4h
            
            # Override 1: LONG reversal
            if long_term_trend == 'downtrend' and stoch_4h_oversold:
                if VERBOSE_LOGGING:
                    print(f"OVERRIDE: 4h trend is DOWN but Stoch is OVERSOLD. Prioritizing LONG.")
                trade_opened = await open_position_long(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, support_15m, resistance_15m, atr_value, funding_rate, support_4h=support_4h, resistance_4h=resistance_4h)
            
            # Override 2: SHORT reversal
            elif long_term_trend == 'uptrend' and stoch_4h_overbought:
                if VERBOSE_LOGGING:
                    print(f"OVERRIDE: 4h trend is UP but Stoch is OVERBOUGHT. Prioritizing SHORT.")
                trade_opened = await open_position_short(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, support_15m, resistance_15m, atr_value, funding_rate, support_4h=support_4h, resistance_4h=resistance_4h)
            
            if not trade_opened:
                # --- MODIFIED: Added 4h SMA check to trend-following logic ---
                if long_term_trend == 'uptrend' and price_above_4h_sma:
                    if VERBOSE_LOGGING:
                        print(f"CONFIRMED UPTREND: 4h trend is UP and price is above 4h SMA for {symbol}.")
                    trade_opened = await open_position_long(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, support_15m, resistance_15m, atr_value, funding_rate, support_4h=support_4h, resistance_4h=resistance_4h)
                
                elif long_term_trend == 'downtrend' and price_below_4h_sma:
                    if VERBOSE_LOGGING:
                        print(f"CONFIRMED DOWNTREND: 4h trend is DOWN and price is below 4h SMA for {symbol}.")
                    trade_opened = await open_position_short(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, support_15m, resistance_15m, atr_value, funding_rate, support_4h=support_4h, resistance_4h=resistance_4h)
    
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(1)

async def main():
    pause_until = 0
    while True:
        if bot_state.trading_paused:
            if pause_until == 0:
                pause_until = time.time() + COOL_DOWN_PERIOD_SECONDS
            
            if time.time() < pause_until:
                print(f"Trading is paused. Resuming in {int((pause_until - time.time()) / 60)} minutes.")
                await asyncio.sleep(60)
                continue
            else:
                print("Resuming trading after cool-down period.")
                bot_state.trading_paused = False
                bot_state.consecutive_losses = 0
                pause_until = 0

        print("\n--- Starting new trading cycle ---")
        
        try:
            positions = client.futures_position_information()
            active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"Max concurrent trade limit ({MAX_CONCURRENT_TRADES}) reached. Skipping new trades for this cycle.")
            else:
                tasks = [process_symbol(symbol) for symbol in symbols]
                await asyncio.gather(*tasks)
        except Exception as e:
            print(f"Error fetching position information: {e}")

        print("\n--- Trading cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    if VERBOSE_LOGGING:
        print("Bot starting in VERBOSE mode.")
    else:
        print("Bot starting in QUIET mode.")
    asyncio.run(main())