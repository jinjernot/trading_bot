import time
import os
import logging
import pandas as pd
from threading import Lock
from flask import Flask, render_template, jsonify, request
from data.get_data import get_usdt_balance
from config.settings import strategy_toggles, VERBOSE_LOGGING
from src.state_manager import bot_state
from src.reconciler import reconcile_trades
from config.symbols import symbols
from config.client import client

# Silence Werkzeug/Flask HTTP request logs to keep terminal quiet
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__)

# --- Server-Side Caching Mechanism ---
CACHE = {
    'active_trades': [],
    'account_balance': {'usdt_balance': 0},
    'last_fetch_timestamp': 0
}
CACHE_LIFESPAN = 20
cache_lock = Lock()

# CSV Log Paths
TRADE_LOG = 'logs/trade_log.csv'
SIGNAL_LOG = 'logs/signal_log.csv'
REJECTED_LOG = 'logs/rejected_signals.csv'

def refresh_cache():
    """Fetches all necessary data from the Binance API and updates the global CACHE."""
    global CACHE
    if VERBOSE_LOGGING:
        print("CACHE STALE. Refreshing data from Binance API...")
    try:
        all_positions = client.futures_position_information()
        
        current_active_trades = [
            {
                'symbol': p['symbol'], 
                'position_amt': float(p.get('positionAmt', 0)), 
                'entry_price': float(p.get('entryPrice', 0)),
                'mark_price': float(p.get('markPrice', 0)),
                'roi': (float(p.get('unrealizedProfit', 0)) / float(p.get('initialMargin', 1))) * 100 if float(p.get('initialMargin', 0)) != 0 else 0,
                'unrealized_profit': float(p.get('unrealizedProfit', 0.0)), 
                'margin_used': float(p.get('initialMargin', 0)),
                'leverage': float(p.get('leverage', 1))
            } 
            for p in all_positions if float(p.get('positionAmt', 0)) != 0
        ]

        balance_data = client.futures_account_balance()
        current_balance = get_usdt_balance(balance_data)
        CACHE['active_trades'] = current_active_trades
        CACHE['account_balance'] = {'usdt_balance': current_balance}
        CACHE['last_fetch_timestamp'] = time.time()
        if VERBOSE_LOGGING:
            print("Cache refreshed successfully.")
    except Exception as e:
        print(f"!!! CRITICAL: FAILED to refresh cache from Binance API: {e}")
        CACHE['last_fetch_timestamp'] = time.time() - CACHE_LIFESPAN + 5

@app.before_request
def check_cache_freshness():
    """Runs before each request to check and refresh the cache if stale."""
    if (time.time() - CACHE['last_fetch_timestamp']) > CACHE_LIFESPAN:
        if cache_lock.acquire(blocking=False):
            try:
                refresh_cache()
            finally:
                cache_lock.release()

# --- API Endpoints ---
@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        return jsonify({'status': 'ok'})  # Handle POST gracefully to prevent 405 errors
    return render_template('index.html')

@app.route('/api/active-trades')
def get_active_trades_data():
    return jsonify(CACHE['active_trades'])

@app.route('/api/account-balance')
def get_account_balance():
    return jsonify(CACHE['account_balance'])

@app.route('/api/bot-state')
def get_bot_state():
    return jsonify({
        'global_btc_trend': getattr(bot_state, 'global_btc_trend', 'NEUTRAL')
    })

@app.route('/api/trade-history')
def get_trade_history():
    """Get completed trades from CSV log"""
    try:
        if not os.path.exists(TRADE_LOG):
            return jsonify({'trades': [], 'message': 'No trade history found'})
        
        df = pd.read_csv(TRADE_LOG, encoding_errors='replace', low_memory=False)
        df = df.drop_duplicates(subset=['Timestamp', 'Symbol', 'Side'])
        exits = df[df['Side'].str.contains('EXIT', na=False)]
        
        trades = []
        for _, row in exits.iterrows():
            trades.append({
                'timestamp': row['Timestamp'],
                'symbol': row['Symbol'],
                'side': row['Side'].replace('_EXIT', ''),
                'entry_price': row.get('Entry_Price', 0),
                'exit_price': row.get('Exit_Price', 0),
                'pnl': row.get('PnL_USDT', 0),
                'roi': row.get('ROI_Percent', 0),
                'exit_reason': row.get('Exit_Reason', 'Unknown')
            })
        
        return jsonify({'trades': trades})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/performance')
def get_performance():
    """Get performance metrics from CSV logs"""
    try:
        if not os.path.exists(TRADE_LOG):
            return jsonify({'message': 'No trades logged yet'})
        
        df = pd.read_csv(TRADE_LOG, encoding_errors='replace', low_memory=False)
        df = df.drop_duplicates(subset=['Timestamp', 'Symbol', 'Side'])
        exits = df[df['Side'].str.contains('EXIT', na=False)]
        
        if len(exits) == 0:
            return jsonify({'message': 'No completed trades yet'})
        
        total_pnl = exits['PnL_USDT'].sum()
        winners = exits[exits['PnL_USDT'] > 0]
        losers = exits[exits['PnL_USDT'] <= 0]
        
        win_rate = (len(winners) / len(exits)) * 100 if len(exits) > 0 else 0
        avg_win = winners['PnL_USDT'].mean() if len(winners) > 0 else 0
        avg_loss = abs(losers['PnL_USDT'].mean()) if len(losers) > 0 else 0
        profit_factor = (winners['PnL_USDT'].sum() / abs(losers['PnL_USDT'].sum())) if len(losers) > 0 and losers['PnL_USDT'].sum() != 0 else 0
        
        # Equity curve
        exits['cumulative_pnl'] = exits['PnL_USDT'].cumsum()
        equity_curve = exits[['Timestamp', 'cumulative_pnl']].to_dict('records')
        
        return jsonify({
            'total_pnl': round(total_pnl, 2),
            'total_trades': len(exits),
            'winners': len(winners),
            'losers': len(losers),
            'win_rate': round(win_rate, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'equity_curve': equity_curve
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/rejected-signals')
def get_rejected_signals():
    """Get rejected signals for analysis"""
    try:
        if not os.path.exists(REJECTED_LOG):
            return jsonify({'signals': []})
        
        df = pd.read_csv(REJECTED_LOG, encoding_errors='replace', on_bad_lines='skip', low_memory=False)
        # Get last 50 rejected signals
        recent = df.tail(50).fillna('N/A')
        
        signals = recent.to_dict('records')
        
        # Get rejection reason counts
        reason_counts = df['Rejection_Reason'].value_counts().to_dict()
        
        return jsonify({
            'signals': signals,
            'reason_counts': reason_counts
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/strategy-toggles', methods=['GET'])
def get_strategy_toggles():
    """Get current strategy toggle states"""
    return jsonify({
        'require_macd': strategy_toggles.REQUIRE_MACD_CONFIRMATION,
        'require_stoch_crossover': strategy_toggles.REQUIRE_STOCH_CROSSOVER,
        'require_1h_alignment': strategy_toggles.REQUIRE_1H_STOCH_ALIGNMENT,
        'use_sma_200': strategy_toggles.USE_SMA_200_FILTER,
        'use_time_filter': strategy_toggles.USE_TIME_FILTER
    })

@app.route('/api/strategy-toggles', methods=['POST'])
def update_strategy_toggles():
    """Update strategy toggle states"""
    try:
        data = request.json
        
        if 'require_macd' in data:
            strategy_toggles.REQUIRE_MACD_CONFIRMATION = bool(data['require_macd'])
            print(f"📊 Toggle: MACD confirmation = {strategy_toggles.REQUIRE_MACD_CONFIRMATION}")
        
        if 'require_stoch_crossover' in data:
            strategy_toggles.REQUIRE_STOCH_CROSSOVER = bool(data['require_stoch_crossover'])
            print(f"📊 Toggle: Stochastic crossover = {strategy_toggles.REQUIRE_STOCH_CROSSOVER}")
        
        if 'require_1h_alignment' in data:
            strategy_toggles.REQUIRE_1H_STOCH_ALIGNMENT = bool(data['require_1h_alignment'])
            print(f"📊 Toggle: 1H alignment = {strategy_toggles.REQUIRE_1H_STOCH_ALIGNMENT}")
        
        if 'use_sma_200' in data:
            strategy_toggles.USE_SMA_200_FILTER = bool(data['use_sma_200'])
            print(f"📊 Toggle: SMA 200 filter = {strategy_toggles.USE_SMA_200_FILTER}")
        
        if 'use_time_filter' in data:
            strategy_toggles.USE_TIME_FILTER = bool(data['use_time_filter'])
            print(f"📊 Toggle: Time filter = {strategy_toggles.USE_TIME_FILTER}")
        
        return jsonify({'status': 'success', 'message': 'Toggles updated'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/sync-trades', methods=['POST'])
def sync_trades():
    """
    Manually trigger a Binance trade history sync.
    Backfills any trades that closed while the bot was offline
    (e.g. TP or SL hit, or manual close on Binance).
    Safe to call multiple times — deduplication prevents double-counting.
    """
    try:
        result = reconcile_trades(symbols, verbose=True)
        return jsonify({
            'status':           'success',
            'backfilled_count': result['backfilled_count'],
            'skipped_count':    result['skipped_count'],
            'scan_from':        result['scan_from'],
            'details':          result['details'],
            'errors':           result['errors']
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)