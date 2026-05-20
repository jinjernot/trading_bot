import sys
import os
import asyncio
import pandas as pd
from datetime import datetime, timedelta

# Add parent directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.symbols import symbols
from config.settings import EXECUTION_TIMEFRAME
from data.get_data import fetch_klines
from data.indicators import (
    calculate_adx, calculate_stoch, add_price_sma, calculate_hull_moving_average,
    calculate_vwap, calculate_volume_anomaly, calculate_bos, calculate_macd, calculate_roc
)

# Limit to 1500 because that's the max Binance allows in a single API call.
# 1500 candles * 5 minutes = 125 hours = ~5.2 days of data.
MAX_LIMIT = '1500'

async def mine_historical_data():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting Historical Data Miner...")
    print(f"Downloading the last 5.2 days of 5-minute data for {len(symbols)} symbols...")
    
    os.makedirs('logs', exist_ok=True)
    all_data = []

    for idx, symbol in enumerate(symbols):
        print(f"[{idx+1}/{len(symbols)}] 📊 Mining {symbol}...")
        try:
            # Fetch max allowed 5m data
            df_15m, _, _ = await asyncio.to_thread(fetch_klines, symbol, EXECUTION_TIMEFRAME, lookback=MAX_LIMIT)
            
            # Run all our institutional indicators
            df_15m = calculate_adx(df_15m)
            df_15m = add_price_sma(df_15m, 50)
            df_15m = calculate_hull_moving_average(df_15m, 14)
            df_15m = calculate_macd(df_15m)
            df_15m = calculate_roc(df_15m, period=10)
            df_15m = calculate_vwap(df_15m, period=288)
            df_15m = calculate_volume_anomaly(df_15m, period=20, multiplier=1.5)
            df_15m = calculate_bos(df_15m, period=20)
            
            stoch_k, stoch_d = calculate_stoch(df_15m['high'], df_15m['low'], df_15m['close'], 14, 3, 3)
            df_15m['Stoch_K'] = stoch_k
            df_15m['Stoch_D'] = stoch_d
            
            # Add symbol column
            df_15m['symbol'] = symbol
            
            # We drop the first 300 rows because they are "tainted" by indicator warmup periods (like VWAP 288)
            valid_data = df_15m.iloc[300:].copy()
            
            all_data.append(valid_data)
            
        except Exception as e:
            print(f"❌ Error mining {symbol}: {e}")

    print("\n💾 Aggregating and saving massive dataset...")
    final_df = pd.concat(all_data, ignore_index=True)
    
    # Reorder columns to make it readable
    cols = ['timestamp', 'symbol', 'close', 'volume', 'ADX', 'Stoch_K', 'Stoch_D', 'macd', 'macd_hist', 'roc', 'vwap', 'volume_anomaly', 'bullish_bos', 'bearish_bos']
    final_df = final_df[cols]
    
    # Save to CSV
    export_path = 'logs/historical_miner_export.csv'
    final_df.to_csv(export_path, index=False)
    
    print(f"✅ DONE! Successfully mined {len(final_df)} rows of advanced market data!")
    print(f"📁 Saved to: {export_path}")

if __name__ == "__main__":
    asyncio.run(mine_historical_data())
