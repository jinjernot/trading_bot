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

bot_state = BotState()