# -*- coding: utf-8 -*-
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
    
    # Конфигурация каналов
    CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@yourchannel')  # Основной канал для обратной совместимости
    
    # Список каналов для анализа (разделенных запятыми)
    CHANNELS_LIST = os.getenv('CHANNELS_LIST', '@yourchannel')  # Например: "@channel1,@channel2,@channel3"
    
    @classmethod
    def get_channels_list(cls):
        """Получить список каналов для анализа"""
        channels_str = cls.CHANNELS_LIST.strip()
        if not channels_str:
            return [cls.CHANNEL_USERNAME]
        
        # Разделить по запятым и очистить пробелы
        channels = [channel.strip() for channel in channels_str.split(',')]
        # Убрать пустые строки
        channels = [ch for ch in channels if ch]
        
        # Если список пуст, вернуть основной канал
        if not channels:
            return [cls.CHANNEL_USERNAME]
        
        return channels
    
    # Настройки анализа
    MAX_MESSAGES = int(os.getenv('MAX_MESSAGES', 100))
    SENTIMENT_THRESHOLD = float(os.getenv('SENTIMENT_THRESHOLD', 0.1))
    NEGATIVE_COMMENT_THRESHOLD = float(os.getenv('NEGATIVE_COMMENT_THRESHOLD', 0.3))  # 30% негативных комментариев для определения негативного поста
    
    # Настройки вывода
    OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')
    
    # Настройки логирования
    LOG_DIR = os.getenv('LOG_DIR', 'logs')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_TO_FILE = os.getenv('LOG_TO_FILE', 'true').lower() == 'true'
    LOG_TO_CONSOLE = os.getenv('LOG_TO_CONSOLE', 'true').lower() == 'true'
    
    # Темы для анализа
    TOPICS = [
        'roads', 'parks', 'playgrounds', 'healthcare', 'education', 'transport',
        'utilities', 'security', 'environment', 'housing', 'commercial', 'services'
    ]
    
    # Ключевые слова местоположений (могут быть расширены данными конкретного города)
    LOCATION_KEYWORDS = [
        'street', 'avenue', 'district', 'neighborhood', 'building', 'house',
        'plaza', 'square', 'road', 'boulevard', 'lane', 'address'
    ] 