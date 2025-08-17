import time
import asyncio
from threading import Lock, Thread
from flask import Flask, render_template, jsonify
from binance.client import Client
from data.get_data import get_usdt_balance
from analysis import analyze_trades
from config.secrets import API_KEY, API_SECRET
from config.settings import leverage
from src.state_manager import bot_state

from main import main_trading_loop

app = Flask(__name__)
client = Client(API_KEY, API_SECRET)

# --- Server-Side Caching Mechanism ---
CACHE = {
    'active_trades': [],
    'account_balance': {'usdt_balance': 0},
    'last_fetch_timestamp': 0
}
CACHE_LIFESPAN = 20
cache_lock = Lock()

# --- Trading Bot State and Control ---
BOT_STATE = {
    'is_running': False,
    'thread': None
}
bot_control_lock = Lock()


def refresh_cache():
    """Fetches all necessary data from the Binance API and updates the global CACHE."""
    global CACHE
    print("CACHE STALE. Refreshing data from Binance API...")
    try:
        all_positions = client.futures_position_information()
        
        current_active_trades = [
            {
                'symbol': p['symbol'], 
                'position_amt': float(p.get('positionAmt', 0)), 
                'roi': (float(p.get('unrealizedProfit', 0)) / float(p.get('initialMargin', 1))) * 100 if float(p.get('initialMargin', 0)) != 0 else 0,
                'unrealized_profit': float(p.get('unrealizedProfit', 0.0)), 
                'margin_used': float(p.get('initialMargin', 0))
            } 
            for p in all_positions if float(p.get('positionAmt', 0)) != 0
        ]

        current_balance = get_usdt_balance()
        CACHE['active_trades'] = current_active_trades
        CACHE['account_balance'] = {'usdt_balance': current_balance}
        CACHE['last_fetch_timestamp'] = time.time()
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

# --- REMOVED: All duplicated trading logic is gone from this file ---

def run_async_loop():
    """Helper function to run the asyncio event loop in a thread."""
    asyncio.run(main_trading_loop())

# --- API Endpoints ---
@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/active-trades')
def get_active_trades_data():
    return jsonify(CACHE['active_trades'])

@app.route('/api/account-balance')
def get_account_balance():
    return jsonify(CACHE['account_balance'])
        
@app.route('/api/trade-analysis')
def get_trade_analysis():
    try:
        return jsonify(analyze_trades(return_json=True))
    except Exception as e:
        print(f"Error in /api/trade-analysis: {e}")
        return jsonify({'error': 'An internal error occurred.'}), 500

# --- Bot Control API Endpoints ---
@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    with bot_control_lock:
        if not BOT_STATE['is_running']:
            BOT_STATE['is_running'] = True
            bot_state.trading_paused = False 
            BOT_STATE['thread'] = Thread(target=run_async_loop)
            BOT_STATE['thread'].start()
            return jsonify({'status': 'success', 'message': 'Trading bot started.'})
        return jsonify({'status': 'failure', 'message': 'Bot is already running.'})

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    with bot_control_lock:
        if BOT_STATE['is_running']:
            bot_state.trading_paused = True 
            BOT_STATE['is_running'] = False 
            return jsonify({'status': 'success', 'message': 'Trading bot stopping...'})
        return jsonify({'status': 'failure', 'message': 'Bot is not running.'})

@app.route('/api/bot/status', methods=['GET'])
def bot_status():

    return jsonify({
        'is_running': BOT_STATE['is_running'],
        'is_paused': bot_state.trading_paused
    })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
