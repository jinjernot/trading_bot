import threading

class BotState:
    def __init__(self):
        self._pnl_lock = threading.Lock()
        self.consecutive_losses = {}
        self.trading_paused = False
        self.global_btc_trend = 'NEUTRAL'
        self.breakeven_triggered = {}
        self.cached_data_mid = {}
        self.cached_data_long = {}
        self.last_fetch_time_mid = {}
        self.last_fetch_time_long = {}
        # Phase 1: Partial Profit Tracking
        self.partial_tp1_taken = {}  # Track if first partial profit (2R) has been taken
        self.partial_tp2_taken = {}  # Track if second partial profit (3R) has been taken
        # Tier 1 Exit Tracking
        self.entry_timestamps = {}  # Track when positions were opened
        self.last_exit_timestamps = {}  # Tracks symbol-specific cooldowns: {symbol: timestamp}
        self.unsigned_agreement_symbols = set()  # Tracks symbols requiring unsigned TradFi agreements
        
        # BOS Strategy State — Institutional Breakout Controls
        self.last_bos_entry_time = 0              # Timestamp of last BOS trade (global cooldown)
        self.bos_pending_retests = {}              # {symbol: {level, direction, timestamp, candles_waited}} — tracks BOS signals awaiting retest
        self.bos_cycle_count = 0                   # Counter for BOS trades placed in the current scan cycle

        # Daily Drawdown Circuit Breaker Tracking
        self.daily_pnl = 0.0
        self.last_pnl_reset_date = None
        self.initialize_daily_pnl()

    def initialize_daily_pnl(self):
        import pandas as pd
        import os
        self.last_pnl_reset_date = pd.Timestamp.utcnow().date()
        self.daily_pnl = 0.0
        
        log_path = 'logs/trade_log.csv'
        if os.path.exists(log_path):
            try:
                df = pd.read_csv(log_path, encoding='utf-8', encoding_errors='replace')
                df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce', utc=True)
                today = pd.Timestamp.utcnow().date()
                today_trades = df[df['Timestamp'].dt.date == today]
                if not today_trades.empty:
                    self.daily_pnl = today_trades['PnL_USDT'].sum()
            except Exception as e:
                pass

bot_state = BotState()