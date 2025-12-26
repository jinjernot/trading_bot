from datetime import datetime, timezone

def is_optimal_5m_trading_time():
    """
    Filters out low-volatility periods for 5m trading
    Returns: (is_optimal, reason_message)
    """
    utc_hour = datetime.now(timezone.utc).hour
    
    # Dead zones (very low volatility - avoid these)
    if utc_hour in [1, 2, 3, 4, 5, 6]:
        return False, f"Low volatility period ({utc_hour}:00 UTC - Asian dead hours)"
    
    # Optimal zones
    if 8 <= utc_hour <= 11:
        return True, "European session (high volatility)"
    elif 13 <= utc_hour <= 17:
        return True, "US market hours (high volatility)"
    elif 20 <= utc_hour <= 23:
        return True, "Asian-US overlap (good momentum)"
    
    # Moderate zones (acceptable but not optimal)
    return True, "Moderate trading hours"


def get_current_utc_hour():
    """Helper to get current UTC hour for logging"""
    return datetime.now(timezone.utc).hour
