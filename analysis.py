import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.style as style

# Use a professional plot style
style.use('seaborn-v0_8-darkgrid')

def analyze_trades(log_file='trade_logs.json'):
    """
    Analyzes the trading logs and generates a visual performance report.
    """
    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"Error: Could not read or find '{log_file}'. Make sure it's in the same directory.")
        return

    if not logs:
        print("No trades found in the log file yet.")
        return

    # --- Data Processing ---
    # Convert logs to a pandas DataFrame
    df = pd.DataFrame(logs)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Separate opening and closing trades
    open_trades = df[df['reason_to_open'].notna()].copy()
    close_trades = df[df['reason_to_close'].notna()].copy()

    # We need to match open trades to their corresponding close
    # This simplified approach assumes trades are closed in order for each symbol
    trades = []
    for symbol in open_trades['symbol'].unique():
        symbol_opens = open_trades[open_trades['symbol'] == symbol].sort_values('timestamp')
        symbol_closes = close_trades[close_trades['symbol'] == symbol].sort_values('timestamp')

        # Pair them up
        for i in range(min(len(symbol_opens), len(symbol_closes))):
            open_trade = symbol_opens.iloc[i]
            close_trade = symbol_closes.iloc[i]
            
            pnl = (close_trade['closing_price'] - open_trade['trade_price']) * open_trade['trade_quantity']
            if open_trade['trade_side'] == 'SELL':
                pnl = -pnl

            trades.append({
                'symbol': symbol,
                'open_time': open_trade['timestamp'],
                'close_time': close_trade['timestamp'],
                'pnl': pnl,
                'side': open_trade['trade_side']
            })
    
    if not trades:
        print("No completed trades (open and close pairs) found to analyze.")
        return

    results_df = pd.DataFrame(trades).sort_values('close_time')
    
    # --- Performance Calculations ---
    wins = results_df[results_df['pnl'] > 0]
    losses = results_df[results_df['pnl'] <= 0]

    total_trades = len(results_df)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    total_pnl = results_df['pnl'].sum()
    
    total_profit = wins['pnl'].sum()
    total_loss = abs(losses['pnl'].sum())
    
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['pnl'].mean()) if len(losses) > 0 else 0
    
    results_df['cumulative_pnl'] = results_df['pnl'].cumsum()

    # --- Print Performance Report ---
    print("\n--- Trading Performance Report ---")
    print(f"Total Trades:      {total_trades}")
    print(f"Win Rate:          {win_rate:.2%}")
    print(f"Profit Factor:     {profit_factor:.2f}")
    print(f"Net Profit/Loss:   ${total_pnl:.2f}")
    print("-" * 35)
    print(f"Average Win:       ${avg_win:.2f}")
    print(f"Average Loss:      ${avg_loss:.2f}")
    print(f"Total Won:         ${total_profit:.2f}")
    print(f"Total Lost:        ${total_loss:.2f}")
    print("----------------------------------\n")


    # --- Plotting ---
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [2, 1]})
    fig.suptitle('Trading Bot Performance Analysis', fontsize=16)

    # 1. Equity Curve
    ax1.plot(results_df['close_time'], results_df['cumulative_pnl'], marker='o', linestyle='-', color='royalblue', label='Equity Curve')
    ax1.set_title('Equity Curve (Cumulative PnL)')
    ax1.set_ylabel('Cumulative Profit (USDT)')
    ax1.grid(True)
    ax1.legend()

    # 2. PnL per Trade
    pnl_colors = ['g' if pnl > 0 else 'r' for pnl in results_df['pnl']]
    ax2.bar(results_df.index, results_df['pnl'], color=pnl_colors)
    ax2.set_title('Profit/Loss per Trade')
    ax2.set_xlabel('Trade Number')
    ax2.set_ylabel('PnL (USDT)')
    ax2.grid(True)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.show()


if __name__ == "__main__":
    analyze_trades()