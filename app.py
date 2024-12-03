from flask import Flask, jsonify, render_template
import pandas as pd
from binance.client import Client
from config.api import API_KEY, API_SECRET

app = Flask(__name__)
client = Client(API_KEY, API_SECRET)

# Fetch historical klines for BTC
def fetch_klines(symbol='BTCUSDT', interval=Client.KLINE_INTERVAL_1MINUTE, lookback='50'):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 
                                       'volume', 'close_time', 'quote_volume', 
                                       'trades', 'taker_base', 'taker_quote', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].astype(float)
    return df

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/btc_data")
def btc_data():
    df = fetch_klines()
    data = {
        "timestamps": df['timestamp'].astype(str).tolist(),
        "close_prices": df['close'].tolist()
    }
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
