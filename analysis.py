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
    Analyzes trading logs with detailed debugging print statements to pinpoint issues.
    """
    print("\n[DEBUG] --- Starting trade analysis ---")
    try:
        with open(log_file, 'r') as f:
            print(f"[DEBUG] Successfully opened '{log_file}'.")
            logs = json.load(f)
            print(f"[DEBUG] Successfully loaded JSON data. Found {len(logs)} log entries.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[DEBUG] FAILED at file reading/parsing: {e}")
        if return_json:
            return {'error': f'Log file error: {e}'}
        return

    if not logs:
        print("[DEBUG] Log file is empty. No analysis to perform.")
        if return_json:
            return get_zeroed_report('No trades logged yet.')
        return

    # --- Data Processing ---
    print("[DEBUG] Converting logs to pandas DataFrame...")
    df = pd.DataFrame(logs)
    print("[DEBUG] DataFrame created. Columns:", df.columns.tolist())
    print("[DEBUG] First 3 rows of data:\n", df.head(3))
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    
    if 'reason' in df.columns and 'reason_to_open' not in df.columns:
        print("[DEBUG] Renaming legacy 'reason' column to 'reason_to_open'.")
        df.rename(columns={'reason': 'reason_to_open'}, inplace=True)

    required_cols = ['reason_to_open', 'reason_to_close', 'symbol', 'closing_price', 'price', 'quantity', 'side']
    for col in required_cols:
        if col not in df.columns:
            print(f"[DEBUG] Column '{col}' not found. Creating it with None values.")
            df[col] = None

    open_trades = df[df['reason_to_open'].notna()].copy()
    close_trades = df[df['reason_to_close'].notna()].copy()
    print(f"[DEBUG] Found {len(open_trades)} open records and {len(close_trades)} close records.")

    trades = []
    if not open_trades.empty:
        for symbol in open_trades['symbol'].unique():
            print(f"[DEBUG] Processing symbol: {symbol}")
            symbol_opens = open_trades[open_trades['symbol'] == symbol].reset_index(drop=True)
            symbol_closes = close_trades[close_trades['symbol'] == symbol].reset_index(drop=True)

            for i in range(min(len(symbol_opens), len(symbol_closes))):
                print(f"[DEBUG] Pairing open trade #{i} with close trade #{i} for {symbol}.")
                open_trade = symbol_opens.iloc[i]
                close_trade = symbol_closes.iloc[i]

                open_price = open_trade.get('price', 0)
                close_price = close_trade.get('closing_price', 0)
                quantity = open_trade.get('quantity', 0)
                side = open_trade.get('side', 'BUY')

                if all(pd.notna(v) for v in [open_price, close_price, quantity]):
                    try:
                        pnl = (float(close_price) - float(open_price)) * float(quantity)
                        if side == 'SELL': pnl = -pnl
                        trades.append({ 'close_time': close_trade.get('timestamp'), 'pnl': pnl })
                        print(f"[DEBUG] Successfully calculated PnL for trade: {pnl}")
                    except (ValueError, TypeError) as e:
                        print(f"[DEBUG] FAILED to calculate PnL for a trade: {e}")
                        continue
                else:
                    print("[DEBUG] Skipped a trade due to missing price/quantity data.")
    
    print(f"[DEBUG] Total completed trades calculated: {len(trades)}")
    if not trades:
        if return_json:
            return get_zeroed_report('No completed trades found to analyze.')
        return

    results_df = pd.DataFrame(trades).sort_values('close_time')
    
    # --- Performance Calculations ---
    print("[DEBUG] Calculating final performance stats...")
    total_pnl = results_df['pnl'].sum()
    results_df['cumulative_pnl'] = results_df['pnl'].cumsum()
    print("[DEBUG] Calculations complete.")

    # --- Return JSON data if requested ---
    if return_json:
        results_df.dropna(subset=['close_time'], inplace=True)
        results_df['close_time'] = results_df['close_time'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        print("[DEBUG] Formatting data for JSON response. Analysis successful.")
        return {
            'total_trades': len(results_df),
            'win_rate': (results_df['pnl'] > 0).sum() / len(results_df) * 100 if len(results_df) > 0 else 0,
            'profit_factor': results_df[results_df['pnl'] > 0]['pnl'].sum() / abs(results_df[results_df['pnl'] < 0]['pnl'].sum()) if (results_df['pnl'] < 0).any() else float('inf'),
            'net_pnl': total_pnl,
            'avg_win': results_df[results_df['pnl'] > 0]['pnl'].mean() if (results_df['pnl'] > 0).any() else 0,
            'avg_loss': abs(results_df[results_df['pnl'] < 0]['pnl'].mean()) if (results_df['pnl'] < 0).any() else 0,
            'equity_curve': results_df[['close_time', 'cumulative_pnl']].to_dict('records'),
        }

    # This part only runs if you execute analysis.py directly
    plt.show()

if __name__ == "__main__":
    analyze_trades()
