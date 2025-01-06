import requests

def fetch_binance_futures_pairs():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    pairs = [symbol['symbol'] for symbol in data['symbols'] if symbol['contractType'] == 'PERPETUAL']
    return pairs

# Fetch pairs
symbols = fetch_binance_futures_pairs()

# Save pairs to a Python file as a list
with open("binance_futures_pairs.py", "w") as file:
    file.write("symbols = [\n")
    for pair in symbols:
        file.write(f"    '{pair}',\n")
    file.write("]\n")

print(f"{len(symbols)} Binance Futures pairs saved to 'binance_futures_pairs.py'")