import matplotlib.pyplot as plt

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