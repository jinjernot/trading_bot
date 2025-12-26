class BotState:
    def __init__(self):
        self.consecutive_losses = 0
        self.trading_paused = False
        self.breakeven_triggered = {}
        self.trailing_stop_activated = {}
        self.cached_data_mid = {}
        self.cached_data_long = {}
        self.last_fetch_time_mid = {}
        self.last_fetch_time_long = {}
        # Phase 1: Partial Profit Tracking
        self.partial_tp1_taken = {}  # Track if first partial profit (2R) has been taken
        self.partial_tp2_taken = {}  # Track if second partial profit (3R) has been taken
        # Tier 1 Exit Tracking
        self.entry_timestamps = {}  # Track when positions were opened

bot_state = BotState()