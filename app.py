import time
import asyncio
from threading import Lock, Thread
from flask import Flask, render_template, jsonify
from binance.client import Client
import requests

# --- Local Imports from your project ---
from data.get_data import get_usdt_balance, fetch_klines, get_position, detect_trend, get_funding_rate, get_symbol_info
from data.indicators import add_price_sma, add_volume_sma, calculate_stoch, calculate_rsi, calculate_atr, PERIOD, K, D
from analysis import analyze_trades
from config.secrets import API_KEY, API_SECRET
from config.settings import leverage, interval, VERBOSE_LOGGING
from config.symbols import symbols
from src.state_manager import bot_state
from src.close_position import close_position_long, close_position_short
from src.open_position_copy import open_position_long, open_position_short

app = Flask(__name__)

# The python-binance library handles time synchronization automatically.
# A single, shared client instance for the entire web application.
client = Client(API_KEY, API_SECRET)


# --- Server-Side Caching Mechanism ---
CACHE = {
    'active_trades': [],
    'account_balance': {'usdt_balance': 0},
    'last_fetch_timestamp': 0
}
CACHE_LIFESPAN = 20  # How long the cache is considered fresh, in seconds.
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
        
        current_active_trades = []
        for position in all_positions:
            position_amt = float(position.get('positionAmt', 0))

            if position_amt != 0:
                symbol = position['symbol']
                entry_price = float(position.get('entryPrice', 0))
                
                # --- START: Real-time PNL Calculation ---
                try:
                    mark_price = float(client.futures_mark_price(symbol=symbol)['markPrice'])
                    unrealized_profit = (mark_price - entry_price) * position_amt
                except Exception as e:
                    print(f"Could not fetch mark price for {symbol}, falling back to API value. Error: {e}")
                    unrealized_profit = float(position.get('unrealizedProfit', 0.0))
                # --- END: Real-time PNL Calculation ---

                position_leverage = int(position.get('leverage', leverage))
                margin_used = (abs(position_amt) * entry_price) / position_leverage if position_leverage != 0 else 0
                roi = (unrealized_profit / margin_used) * 100 if margin_used != 0 else 0
                
                current_active_trades.append({
                    'symbol': symbol, 'position_amt': position_amt, 'roi': roi,
                    'unrealized_profit': unrealized_profit, 'margin_used': margin_used
                })

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

# --- Trading Bot Logic (integrated from main.py) ---

async def process_symbol(symbol):
    """Processes trading logic for a single symbol."""
    try:
        # The trading logic from your main.py's process_symbol function
        df, support, resistance  = fetch_klines(symbol, interval)
        df = add_price_sma(df, period=50)
        df = add_volume_sma(df, period=20)
        stoch_k, stoch_d = calculate_stoch(df['high'], df['low'], df['close'], PERIOD, K, D)
        df = calculate_rsi(df, period=14)
        df = calculate_atr(df)
        atr_value = df['atr'].iloc[-1]
        position, roi, unrealized_profit, margin_used = get_position(symbol)
        usdt_balance = get_usdt_balance()
        trend = detect_trend(df)
        funding_rate = get_funding_rate(symbol)

        if position > 0: await close_position_long(symbol, position, roi, df, stoch_k, resistance)
        elif position < 0: await close_position_short(symbol, position, roi, df, stoch_k, support)
        
        if position == 0:
            if trend == 'uptrend': await open_position_long(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate)
            elif trend == 'downtrend': await open_position_short(symbol, df, stoch_k, stoch_d, usdt_balance, support, resistance, atr_value, funding_rate)
    except Exception as e:
        print(f"Error processing symbol {symbol}: {e}")

async def trading_bot_main_loop():
    """The main loop for the trading bot."""
    # Pre-fetch exchange info once to avoid rate limits inside the loop
    get_symbol_info('BTCUSDT') # This call will cache the info for all symbols
    
    while BOT_STATE['is_running']:
        print("\n--- Starting new trading cycle ---")
        for symbol in symbols:
            if not BOT_STATE['is_running']: break # Check again in case of stop signal
            await process_symbol(symbol)
            await asyncio.sleep(1) # Small delay between symbols
        
        if BOT_STATE['is_running']:
            print("\n--- Trading cycle complete. Waiting for 60 seconds... ---")
            await asyncio.sleep(60)
    print("--- Trading bot has been stopped. ---")

def run_async_loop():
    """Helper function to run the asyncio event loop."""
    asyncio.run(trading_bot_main_loop())

# --- API Endpoints ---

@app.route('/')
def dashboard():
    """Renders the main dashboard page."""
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
    """Starts the trading bot in a background thread."""
    with bot_control_lock:
        if not BOT_STATE['is_running']:
            BOT_STATE['is_running'] = True
            BOT_STATE['thread'] = Thread(target=run_async_loop)
            BOT_STATE['thread'].start()
            return jsonify({'status': 'success', 'message': 'Trading bot started.'})
        return jsonify({'status': 'failure', 'message': 'Bot is already running.'})

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    """Stops the trading bot."""
    with bot_control_lock:
        if BOT_STATE['is_running']:
            BOT_STATE['is_running'] = False
            # The thread will stop on its own after the current cycle
            return jsonify({'status': 'success', 'message': 'Trading bot stopping...'})
        return jsonify({'status': 'failure', 'message': 'Bot is not running.'})

@app.route('/api/bot/status', methods=['GET'])
def bot_status():
    """Returns the current status of the trading bot."""
    return jsonify({'is_running': BOT_STATE['is_running']})

if __name__ == "__main__":
    # Now, running this file starts only the web server.
    # The trading bot must be started via the API.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)

