import asyncio
from config.secrets import TELEGRAM_TOKEN, CHAT_ID
from telegram import Bot

bot = Bot(token=TELEGRAM_TOKEN)

semaphore = asyncio.Semaphore(5) 

async def send_telegram_message(message, parse_mode="Markdown"):
    async with semaphore:
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=message,
                parse_mode=parse_mode
            )
            await asyncio.sleep(0.5)
        except Exception as e:
            print(f"Error sending message: {e}")
