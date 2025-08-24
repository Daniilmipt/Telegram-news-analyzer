import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Учетные данные Telegram API
    TELEGRAM_API_ID = os.getenv('TELEGRAM_API_ID')
    TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
    TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')
    
    # Telegram Bot Token
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # Список каналов для анализа (разделенных запятыми)
    CHANNELS_LIST = os.getenv('CHANNELS_LIST', '@yourchannel')  # Например: "@channel1,@channel2,@channel3"
    
    @classmethod
    def get_channels_list(cls):
        """Получить список каналов для анализа"""
        return [ch.strip() for ch in cls.CHANNELS_LIST.strip().split(',') if ch.strip()]
    
    # Настройки анализа
    MAX_MESSAGES = int(os.getenv('MAX_MESSAGES', 100))
    NEGATIVE_COMMENT_THRESHOLD = float(os.getenv('NEGATIVE_COMMENT_THRESHOLD', 0.3))  # 30% негативных комментариев для определения негативного поста
    
    # Настройки вывода
    OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')
