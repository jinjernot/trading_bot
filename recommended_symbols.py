# Recommended Symbol List for Small Account (46 USDT)
# These are the most liquid and reliable pairs on Binance Futures

recommended_symbols = [
    # === Tier 1: Major Pairs (Highest Liquidity) ===
    'BTCUSDT',      # Bitcoin - Most liquid
    'ETHUSDT',      # Ethereum - Second most liquid
    'BNBUSDT',      # Binance Coin - High liquidity
    
    # === Tier 2: Large Caps (Very Good Liquidity) ===
    'SOLUSDT',      # Solana
    'XRPUSDT',      # Ripple
    'DOGEUSDT',     # Dogecoin
    'ADAUSDT',      # Cardano
    'LINKUSDT',     # Chainlink
    'DOTUSDT',      # Polkadot
    'AVAXUSDT',     # Avalanche
    
    # === Tier 3: Mid Caps (Good Liquidity) ===
    'MATICUSDT',    # Polygon (if available)
    'LTCUSDT',      # Litecoin
    'UNIUSDT',      # Uniswap
    'ATOMUSDT',     # Cosmos
    'NEARUSDT',     # Near Protocol
    'AAVEUSDT',     # Aave
    'SUSHIUSDT',    # SushiSwap
    'SANDUSDT',     # Sandbox
    'MANAUSDT',     # Decentraland
    'AXSUSDT',      # Axie Infinity
    
    # === Tier 4: Trending Meme/Alt Coins (Higher Volatility) ===
    '1000PEPEUSDT', # Pepe (good for volatility)
    '1000SHIBUSDT', # Shiba Inu
    'WIFUSDT',      # Dogwifhat (trending)
    'ORDIUSDT',     # Ordinals
    'ARBUSDT',      # Arbitrum
    'OPUSDT',       # Optimism
    'SUIUSDT',      # Sui
    'APTUSDT',      # Aptos
    'INJUSDT',      # Injective
    'SEIUSDT',      # Sei
]

# For even safer start with tiny balance, use just these:
conservative_symbols = [
    'BTCUSDT',
    'ETHUSDT',
    'BNBUSDT',
    'SOLUSDT',
    'XRPUSDT',
    'DOGEUSDT',
    'ADAUSDT',
    'AVAXUSDT',
    'LINKUSDT',
    'DOTUSDT',
]

# To use this list instead of the full 558 symbols:
# 1. Open config/symbols.py
# 2. Comment out (or delete) the huge list
# 3. Add: from recommended_symbols import recommended_symbols as symbols
# OR just copy-paste the recommended_symbols list into symbols.py
