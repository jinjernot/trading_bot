from src.close_position import *
from src.open_position import *
from src.trade import *
  
from data.get_data import *
from data.indicators import *

from data.indicators import add_short_term_sma

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
EXECUTION_TIMEFRAME = '15m'
INTERMEDIATE_TIMEFRAME = '4h'
PRIMARY_TIMEFRAME = '1d'

# --- NEW: Trailing Stop Global Settings ---
TRAIL_STOP_ACTIVATE_ROI = 2.0 # ROI needed to activate the trailing stop

async def process_symbol(symbol):
    
    try:
        df_15m, support_15m, resistance_15m, \
        df_4h, support_4h, resistance_4h, stoch_k_4h, stoch_d_4h, \
        df_1d = await asyncio.to_thread(
            fetch_multi_timeframe_data, symbol, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME
        )
        
        primary_trend = detect_trend(df_1d)
        intermediate_trend = detect_trend(df_4h)
        
        if VERBOSE_LOGGING:
            print(f"Primary Trend (1D) for {symbol}: {primary_trend}")
            print(f"Intermediate Trend (4h) for {symbol}: {intermediate_trend}")

        # --- Indicator Calculations ---
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
        
        # --- Position & Account Info ---
        position, roi, unrealized_profit, margin_used, entry_price = get_position(symbol)
        usdt_balance = get_usdt_balance()
        funding_rate = get_funding_rate(symbol)
        
        # --- Breakeven Logic ---
        if position != 0 and roi >= BREAKEVEN_ROI_TARGET and not bot_state.breakeven_triggered.get(symbol):
            trade_side = SIDE_BUY if position > 0 else SIDE_SELL
            if await move_stop_to_breakeven(symbol, entry_price, trade_side):
                bot_state.breakeven_triggered[symbol] = True
        
        if position == 0:
            if bot_state.breakeven_triggered.get(symbol):
                del bot_state.breakeven_triggered[symbol]
            if bot_state.trailing_stop_activated.get(symbol):
                del bot_state.trailing_stop_activated[symbol]
            if VERBOSE_LOGGING:
                print(f"Reset flags for closed position {symbol}.")

        # --- Position Management (Closing) ---
        if position > 0:
            await close_position_long(symbol, position, roi, df_15m, stoch_k_15m, resistance_15m)
        elif position < 0:
            await close_position_short(symbol, position, roi, df_15m, stoch_k_15m, support_15m)
        
        if bot_state.trading_paused:
            return

        # --- Position Management (Opening) ---
        if position == 0:
            sma_4h = df_4h['price_sma_50'].iloc[-1]
            price_above_4h_sma = last_close > sma_4h
            price_below_4h_sma = last_close < sma_4h
            
            # --- MODIFICATION: Removed primary_trend check for more frequent signals ---
            if intermediate_trend == 'uptrend' and price_above_4h_sma:
                if VERBOSE_LOGGING:
                    print(f"CONFIRMED UPTREND (4h): Looking for LONG for {symbol}.")
                await open_position_long(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, support_15m, resistance_15m, atr_value, funding_rate, support_4h=support_4h, resistance_4h=resistance_4h)
            
            # --- MODIFICATION: Removed primary_trend check for more frequent signals ---
            elif intermediate_trend == 'downtrend' and price_below_4h_sma:
                if VERBOSE_LOGGING:
                    print(f"CONFIRMED DOWNTREND (4h): Looking for SHORT for {symbol}.")
                await open_position_short(symbol, df_15m, stoch_k_15m, stoch_d_15m, usdt_balance, support_15m, resistance_15m, atr_value, funding_rate, support_4h=support_4h, resistance_4h=resistance_4h)
    
    except Exception as e:
        print(f"Error processing {symbol}: {e}")
        await asyncio.sleep(1)

async def manage_active_trades(active_positions):
    """
    NEW: Loop through active positions to manage trailing stops.
    """
    if not active_positions:
        return

    print(f"\n--- Managing {len(active_positions)} Active Trade(s) ---")
    for position_obj in active_positions:
        symbol = position_obj['symbol']
        roi = float(position_obj.get('unrealizedProfit', 0)) / (float(position_obj.get('initialMargin', 1))) * 100
        
        # --- Activate Trailing Stop ---
        if roi >= TRAIL_STOP_ACTIVATE_ROI and not bot_state.trailing_stop_activated.get(symbol):
            print(f"✅ Activating Trailing Stop for {symbol} (ROI: {roi:.2f}%)")
            bot_state.trailing_stop_activated[symbol] = True
            # On first activation, we might just move to breakeven if not already done
            if not bot_state.breakeven_triggered.get(symbol):
                 trade_side = SIDE_BUY if float(position_obj['positionAmt']) > 0 else SIDE_SELL
                 await move_stop_to_breakeven(symbol, float(position_obj['entryPrice']), trade_side)
                 bot_state.breakeven_triggered[symbol] = True

        # --- Update Active Trailing Stop ---
        if bot_state.trailing_stop_activated.get(symbol):
            df_15m, _, _, _, _, _, _, _, _ = await asyncio.to_thread(
                fetch_multi_timeframe_data, symbol, EXECUTION_TIMEFRAME, INTERMEDIATE_TIMEFRAME, PRIMARY_TIMEFRAME
            )
            df_15m = calculate_atr(df_15m)
            atr_value = df_15m['atr'].iloc[-1]
            await manage_trailing_stop(symbol, position_obj, atr_value)


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

            # --- NEW: Manage existing trades first ---
            await manage_active_trades(active_positions)
            
            # --- Then, look for new trades ---
            if len(active_positions) >= MAX_CONCURRENT_TRADES:
                print(f"Max concurrent trade limit ({MAX_CONCURRENT_TRADES}) reached. Skipping new trades for this cycle.")
            else:
                tasks = [process_symbol(symbol) for symbol in symbols if symbol not in [p['symbol'] for p in active_positions]]
                await asyncio.gather(*tasks)

        except Exception as e:
            print(f"Error in main loop: {e}")

        print("\n--- Trading cycle complete. Waiting for 60 seconds... ---")
        await asyncio.sleep(60)

if __name__ == "__main__":
    if VERBOSE_LOGGING:
        print("Bot starting in VERBOSE mode.")
    else:
        print("Bot starting in QUIET mode.")
    asyncio.run(main())