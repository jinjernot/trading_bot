import matplotlib.pyplot as plt
import numpy as np

async def plot_stochastic(stoch_k, stoch_d, symbol, oversold, overbought):
    """
    Plots the stochastic oscillator for the given symbol.
    Args:
        stoch_k: %K values (Stochastic Oscillator)
        stoch_d: %D values (Stochastic Oscillator)
        symbol: The symbol (e.g., 'BTCUSDT') for the plot title
        oversold: The oversold level to plot (typically 20)
        overbought: The overbought level to plot (typically 80)
    """
    plt.figure(figsize=(10, 6))
    plt.plot(stoch_k, label='%K', color='blue', alpha=0.7)
    plt.plot(stoch_d, label='%D', color='red', alpha=0.7)
    plt.axhline(oversold, color='green', linestyle='--', label='Oversold')
    plt.axhline(overbought, color='orange', linestyle='--', label='Overbought')
    plt.title(f'Stochastic Oscillator for {symbol}')
    plt.xlabel('Time')
    plt.ylabel('Value')
    plt.legend()
    plt.savefig(f"{symbol}_stochastic.png")
    plt.clf()
    
async def plot_channel(df,symbol,resistance_slope,resistance_intercept,support_slope,support_intercept,trend):
    # Plot the data
    plt.figure(figsize=(12, 6))
    plt.plot(df['timestamp'], df['close'], label='Close Price', color='blue')
    
    # Plot resistance line (upper bound) with parallel slope
    plt.plot(df['timestamp'], resistance_slope * np.arange(len(df)) + resistance_intercept, label='Resistance (Parallel)', color='red', linestyle='--')
    
    # Plot support line (lower bound) with parallel slope
    plt.plot(df['timestamp'], support_slope * np.arange(len(df)) + support_intercept, label='Support (Parallel)', color='green', linestyle='--')
    

    trend_color = 'orange' if trend == 'uptrend' else 'purple' if trend == 'downtrend' else 'gray'
    
    plt.plot(df['timestamp'], df['close'], label=f'Trend: {trend}', color=trend_color, alpha=0.5)
    plt.legend()
    plt.title(f"{symbol} Parallel Channel with Extended Trend Lines")
    plt.xlabel("Timestamp")
    plt.ylabel("Price")
    plt.grid()
    plt.show()