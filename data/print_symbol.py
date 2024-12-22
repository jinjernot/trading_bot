from data.get_data import *
from data.indicators import *


def print_iteration_details(symbol, nice_interval, interval):
    # Print iteration start
    print(f"\n--- New Iteration for {symbol} ({nice_interval}) ---")
    
    # Get Candles
    df, support, resistance = fetch_klines(symbol, interval)

    # Calculate Stochastic
    stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
    print(f"Stochastic K for {symbol}: {stoch_k.iloc[-3:].values}")
    print(f"Stochastic D for {symbol}: {stoch_d.iloc[-3:].values}")

    # Calculate RSI
    df = calculate_rsi(df, period=14)
    print(f"RSI for {symbol}: {df['rsi'].iloc[-3:].values}")
    
    # Get current position and ROI
    position, roi, unrealized_profit, margin_used = get_position(symbol)
    print(f"Position for {symbol}: {position}, ROI: {roi:.2f}%, Unrealized Profit: {unrealized_profit:.2f}")
    print(f"Margin Used for {symbol}: {margin_used}")

    # Get USDT balance
    usdt_balance = get_usdt_balance()
    print(f"Available USDT balance for {symbol}: {usdt_balance}")

    # Get market trend
    trend = detect_trend(df)
    print(f"Market trend for {symbol}: {trend}")
    
    # Print iteration end
    print(f"--- End Iteration {symbol} ({nice_interval}) ---\n")

    return df, stoch_k, stoch_d, position, roi, unrealized_profit, margin_used, usdt_balance, trend
