class BotState:
    def __init__(self):
        self.consecutive_losses = 0
        self.trading_paused = False
        self.breakeven_triggered = {}

bot_state = BotState()