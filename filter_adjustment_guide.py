# Quick Filter Adjustment for More Trades
# Use this if you're getting too few (or no) trade signals

# OPTION 1: Moderate Loosening (Recommended)
# In config/settings.py, change these settings:

"""
# Current (Very Strict):
REQUIRE_1H_STOCH_ALIGNMENT = True
MIN_ADX_THRESHOLD = 10
USE_SMA_200_FILTER = True

# Recommended Adjustment (Moderate):
REQUIRE_1H_STOCH_ALIGNMENT = False  # Disable multi-timeframe for now
MIN_ADX_THRESHOLD = 8                # Lower slightly
USE_SMA_200_FILTER = True            # Keep this - it's important
"""

# OPTION 2: Aggressive Loosening (More Trades)
"""
REQUIRE_1H_STOCH_ALIGNMENT = False
MIN_ADX_THRESHOLD = 5
USE_SMA_200_FILTER = False
"""

# OPTION 3: Ultra Conservative (Keep Original 15m Strategy)
"""
REQUIRE_1H_STOCH_ALIGNMENT = False
MIN_ADX_THRESHOLD = 5
USE_SMA_200_FILTER = False
ENABLE_PARTIAL_PROFITS = False  # Disable partial profits too
"""

# STEPS TO APPLY:
# 1. Stop the bot (Ctrl+C)
# 2. Edit config/settings.py 
# 3. Change the settings based on option above
# 4. Restart: python main.py
# 5. Monitor for 15-30 minutes

# EXPECTED TRADE FREQUENCY:
# - Very Strict (current): 0-2 trades per hour across 30 symbols
# - Moderate: 1-5 trades per hour
# - Loose: 3-10 trades per hour
