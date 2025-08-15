class BotState:
    def __init__(self):
        self.consecutive_losses = 0
        self.trading_paused = False
        self.breakeven_triggered = {}
        self.cached_data_mid = {} # For 4h data
        self.cached_data_long = {} # For 1d data
        self.last_fetch_time_mid = {}
        self.last_fetch_time_long = {}

bot_state = BotState()