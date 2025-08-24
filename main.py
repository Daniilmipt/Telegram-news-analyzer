import os
from telegram_bot import NegativePostsBot

if __name__ == "__main__":
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        print("❌ Переменная окружения BOT_TOKEN не установлена")
        print("Добавьте BOT_TOKEN=your_bot_token в .env файл")
        exit(1)
    
    bot = NegativePostsBot(bot_token)
    bot.run()
