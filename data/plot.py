import matplotlib.pyplot as plt
import mplfinance as mpf

def plot_stochastic(stoch_k, stoch_d, symbol, oversold, overbought):
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
    plt.show()
    plt.clf()
    
    
def plot_candlesticks_with_trend(df, symbol):
    # Define colors for trends
    trend_colors = {
        'uptrend': 'green',
        'downtrend': 'red',
        'sideways': 'gray'
    }

    # Create a color array for plotting
    colors = [trend_colors[trend] for trend in df['trend']]

    # Plot candlestick chart
    mpf.plot(
        df.set_index('timestamp'), 
        type='candle', 
        volume=True, 
        style='yahoo', 
        title=f"{symbol} Candlestick Chart with Trends",
        ylabel="Price",
        ylabel_lower="Volume"
    )




    # Add trend markers
    plt.scatter(df['timestamp'], df['close'], color=colors, label='Trend', zorder=3)

    plt.legend(['Uptrend', 'Downtrend', 'Sideways'])
    plt.show()