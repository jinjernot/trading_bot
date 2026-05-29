import csv
import os
from datetime import datetime
import pandas as pd
import json
from src.state_manager import bot_state

def _make_serializable(v):
    if isinstance(v, (pd.Series, pd.DataFrame)):
        return str(v)
    if hasattr(v, 'item'):
        return v.item()
    return v

# Define log file paths
TRADE_LOG_CSV = 'logs/trade_log.csv'
SIGNAL_LOG_CSV = 'logs/signal_log.csv'
REJECTED_LOG_CSV = 'logs/rejected_signals.csv'

# Ensure logs directory exists
os.makedirs('logs', exist_ok=True)

def log_trade_entry(symbol, side, entry_price, quantity, stop_loss, indicators, balance):
    """
    Log detailed trade entry information to CSV
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    
    with open(TRADE_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        
        # Write header if file doesn't exist
        if not file_exists:
            writer.writerow([
                'Timestamp', 'Symbol', 'Side', 'Entry_Price', 'Quantity', 'Stop_Loss',
                'ADX', 'Stoch_K', 'Stoch_D', 'RSI', 'Price_vs_SMA50', 'HMA_Slope',
                'ATR', 'Balance_USDT', 'Risk_Percent', 'Global_BTC_Trend', 'Notes', 'Full_Indicators_JSON'
            ])
        
        # Write trade data
        writer.writerow([
            datetime.now().isoformat(),
            symbol,
            side,
            entry_price,
            quantity,
            stop_loss,
            indicators.get('ADX', 'N/A'),
            indicators.get('Stoch_K', 'N/A'),
            indicators.get('Stoch_D', 'N/A'),
            indicators.get('RSI', 'N/A'),
            indicators.get('Price_vs_SMA50', 'N/A'),
            indicators.get('HMA_Slope', 'N/A'),
            indicators.get('ATR', 'N/A'),
            balance,
            '2%',  # Your risk setting
            getattr(bot_state, 'global_btc_trend', 'UNKNOWN'),
            indicators.get('Reason', 'Bullish/Bearish confluence'),
            json.dumps({k: _make_serializable(v) for k, v in indicators.items()})
        ])

def log_trade_exit(symbol, side, entry_price, exit_price, quantity, pnl, exit_reason, roi, exit_type='UNKNOWN'):
    """
    Log detailed trade exit information to CSV.
    exit_type: machine-readable tag — one of:
        TIME_BASED | FUNDING_RATE | MARKET_STRUCTURE_BREAK | STOCH_EXTREME
        EMERGENCY | TRAILING_STOP | EXCHANGE_SL_TP | MANUAL | UNKNOWN
    """
    file_exists = os.path.isfile(TRADE_LOG_CSV)
    
    with open(TRADE_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        
        # Write header if file doesn't exist
        if not file_exists:
            writer.writerow([
                'Timestamp', 'Symbol', 'Side', 'Entry_Price', 'Exit_Price', 'Quantity',
                'PnL_USDT', 'ROI_Percent', 'Exit_Reason', 'Exit_Type', 'Notes'
            ])
        
        # Write exit data
        writer.writerow([
            datetime.now().isoformat(),
            symbol,
            f"{side}_EXIT",
            entry_price,
            exit_price,
            quantity,
            pnl,
            roi,
            exit_reason,
            exit_type,
            f"Trade closed: {exit_reason}"
        ])

def log_signal_analysis(symbol, indicators, decision, reason):
    """
    Log every symbol analysis with full indicator data (for later backtesting)
    """
    file_exists = os.path.isfile(SIGNAL_LOG_CSV)
    
    with open(SIGNAL_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        
        # Write header if file doesn't exist
        if not file_exists:
            writer.writerow([
                'Timestamp', 'Symbol', 'Decision', 'Reason',
                'ADX', 'Stoch_K_15m', 'Stoch_D_15m', 'Stoch_K_1h', 'Stoch_D_1h',
                'RSI', 'Price', 'SMA50', 'HMA_14', 'HMA_Slope', 'ATR',
                'SMA200_4h', 'Price_vs_SMA200', 'Global_BTC_Trend', 'Full_Indicators_JSON'
            ])
        
        # Write signal data
        writer.writerow([
            datetime.now().isoformat(),
            symbol,
            decision,  # 'LONG', 'SHORT', 'SKIP'
            reason,
            indicators.get('ADX', 0),
            indicators.get('Stoch_K_15m', 0),
            indicators.get('Stoch_D_15m', 0),
            indicators.get('Stoch_K_1h', 0),
            indicators.get('Stoch_D_1h', 0),
            indicators.get('RSI', 0),
            indicators.get('Price', 0),
            indicators.get('SMA50', 0),
            indicators.get('HMA_14', 0),
            indicators.get('HMA_Slope', 'FLAT'),
            indicators.get('ATR', 0),
            indicators.get('SMA200_4h', 0),
            indicators.get('Price_vs_SMA200', 'BELOW'),
            getattr(bot_state, 'global_btc_trend', 'UNKNOWN'),
            json.dumps({k: _make_serializable(v) for k, v in indicators.items()})
        ])

def log_rejected_signal(symbol, side, indicators, rejection_reason):
    """
    Log signals that were rejected (didn't meet all criteria)
    This is crucial for understanding missed opportunities
    """
    file_exists = os.path.isfile(REJECTED_LOG_CSV)
    
    with open(REJECTED_LOG_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        
        # Write header if file doesn't exist
        if not file_exists:
            writer.writerow([
                'Timestamp', 'Symbol', 'Attempted_Side', 'Rejection_Reason',
                'ADX', 'Stoch_K', 'RSI', 'Price_vs_SMA', 'HMA_Slope',
                'Stoch_Signal', 'RSI_Signal', 'SMA_Signal', 'HMA_Signal', 'Global_BTC_Trend', 'Full_Indicators_JSON'
            ])
        
        # Write rejected signal
        writer.writerow([
            datetime.now().isoformat(),
            symbol,
            side,
            rejection_reason,
            indicators.get('ADX', 0),
            indicators.get('Stoch_K', 0),
            indicators.get('RSI', 0),
            indicators.get('Price_vs_SMA', 'N/A'),
            indicators.get('HMA_Slope', 'N/A'),
            indicators.get('Stoch_OK', False),
            indicators.get('RSI_OK', False),
            indicators.get('SMA_OK', False),
            indicators.get('HMA_OK', False),
            getattr(bot_state, 'global_btc_trend', 'UNKNOWN'),
            json.dumps({k: _make_serializable(v) for k, v in indicators.items()})
        ])

