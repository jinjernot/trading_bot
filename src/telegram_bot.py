
from config.secrets import TELEGRAM_TOKEN, CHAT_ID
from telegram import Bot


bot = Bot(token=TELEGRAM_TOKEN)
async def send_telegram_message(message):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        print(f"Error sending message: {e}")
