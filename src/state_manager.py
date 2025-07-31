class BotState:
    """A simple class to hold the bot's state across different modules."""
    def __init__(self):
        self.consecutive_losses = 0
        self.trading_paused = False

# Create a single instance that will be imported by other modules
bot_state = BotState()