import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.style as style

# Use a professional plot style for command-line use
style.use('seaborn-v0_8-darkgrid')

def get_zeroed_report(message=""):
    """Returns a default, zeroed-out report structure."""
    return {
        'message': message, # A new field for informational messages
        'total_trades': 0, 'win_rate': 0, 'profit_factor': 0,
        'net_pnl': 0, 'avg_win': 0, 'avg_loss': 0,
        'total_profit': 0, 'total_loss': 0,
        'equity_curve': [], 'pnl_history': []
    }

def analyze_trades(log_file='trade_logs.json', return_json=False):
    """
    Analyzes trading logs. This version is hardened against common errors
    and gracefully handles cases with no completed trades.
    """
    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if return_json:
            return get_zeroed_report('Log file not found or is empty.')
        print(f"Error: Could not read or find '{log_file}'.")
        return

    if not logs:
        if return_json:
            return get_zeroed_report('No trades logged yet.')
        print("No trades found in the log file yet.")
        return

    # --- Data Processing ---
    df = pd.DataFrame(logs)
    # Convert timestamp column, coercing errors to NaT (Not a Time)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    
    # Handle legacy 'reason' column for backward compatibility
    if 'reason' in df.columns and 'reason_to_open' not in df.columns:
        df.rename(columns={'reason': 'reason_to_open'}, inplace=True)

    # Ensure required columns exist to prevent KeyErrors
    required_cols = ['reason_to_open', 'reason_to_close', 'symbol', 'closing_price', 'price', 'quantity', 'side']
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    open_trades = df[df['reason_to_open'].notna()].copy()
    close_trades = df[df['reason_to_close'].notna()].copy()

    trades = []
    for symbol in open_trades['symbol'].unique():
        # FIX: Remove sorting by timestamp, as it can be unreliable if missing.
        # Pair trades based on their order of appearance in the log file.
        symbol_opens = open_trades[open_trades['symbol'] == symbol].reset_index(drop=True)
        symbol_closes = close_trades[close_trades['symbol'] == symbol].reset_index(drop=True)

        for i in range(min(len(symbol_opens), len(symbol_closes))):
            open_trade = symbol_opens.iloc[i]
            close_trade = symbol_closes.iloc[i]

            open_price = open_trade.get('price', 0)
            close_price = close_trade.get('closing_price', 0)
            quantity = open_trade.get('quantity', 0)
            side = open_trade.get('side', 'BUY')

            if all(pd.notna(v) for v in [open_price, close_price, quantity]):
                try:
                    pnl = (float(close_price) - float(open_price)) * float(quantity)
                    if side == 'SELL':
                        pnl = -pnl

                    trades.append({
                        'symbol': symbol,
                        'open_time': open_trade.get('timestamp'), # Use .get for safety
                        'close_time': close_trade.get('timestamp'),
                        'pnl': pnl,
                        'side': side
                    })
                except (ValueError, TypeError):
                    print(f"Skipping a trade for {symbol} due to invalid data type.")
                    continue

    if not trades:
        if return_json:
            return get_zeroed_report('No completed trades found to analyze.')
        print("No completed trades (open and close pairs) found to analyze.")
        return

    results_df = pd.DataFrame(trades).sort_values('close_time')
    
    # --- Performance Calculations ---
    wins = results_df[results_df['pnl'] > 0]
    losses = results_df[results_df['pnl'] <= 0]
    total_trades = len(results_df)
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    total_profit = wins['pnl'].sum()
    total_loss = abs(losses['pnl'].sum())
    profit_factor = total_profit / total_loss if total_loss > 0 else float('inf')
    avg_win = wins['pnl'].mean() if len(wins) > 0 else 0
    avg_loss = abs(losses['pnl'].mean()) if len(losses) > 0 else 0
    total_pnl = results_df['pnl'].sum()
    results_df['cumulative_pnl'] = results_df['pnl'].cumsum()

    # --- Return JSON data if requested ---
    if return_json:
        # Filter out any trades that might have a NaT close_time before formatting
        results_df.dropna(subset=['close_time'], inplace=True)
        results_df['close_time'] = results_df['close_time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        return {
            'total_trades': total_trades, 'win_rate': win_rate * 100, 'profit_factor': profit_factor,
            'net_pnl': total_pnl, 'avg_win': avg_win, 'avg_loss': avg_loss,
            'total_profit': total_profit, 'total_loss': total_loss,
            'equity_curve': results_df[['close_time', 'cumulative_pnl']].to_dict('records'),
            'pnl_history': results_df['pnl'].tolist()
        }

    # --- Default behavior: Print to console and plot ---
    print("\n--- Trading Performance Report ---")
    # ... (rest of your print statements)
    plt.show()

if __name__ == "__main__":
    analyze_trades()
