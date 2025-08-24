import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.types import Message, MessageService
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from config import Config
from logging_config import setup_logger

# Configure logging with file output
logger = setup_logger(__name__)

class TelegramNewsClient:
    def __init__(self):
        self.client = TelegramClient(
            'news_analyzer_session',
            Config.TELEGRAM_API_ID,
            Config.TELEGRAM_API_HASH
        )
        self.channel_entities = {}  # Словарь: username -> entity
    
    async def connect(self, channels=None):
        """Подключение к Telegram и аутентификация"""
        try:
            await self.client.start(phone=Config.TELEGRAM_PHONE)
            logger.info("Successfully connected to Telegram")
            
            # Получение списка каналов
            if channels is None:
                channels = Config.get_channels_list()
            
            # Подключение к каждому каналу
            for channel_username in channels:
                try:
                    entity = await self.client.get_entity(channel_username)
                    self.channel_entities[channel_username] = entity
                    logger.info("Connected to channel: {} ({})".format(channel_username, entity.title))
                except Exception as e:
                    logger.error("Failed to connect to channel {}: {}".format(channel_username, e))
            
            if not self.channel_entities:
                raise ValueError("Не удалось подключиться ни к одному каналу")
                
        except SessionPasswordNeededError:
            logger.error("Two-factor authentication required. Please configure app password.")
            raise
        except Exception as e:
            logger.error("Failed to connect to Telegram: {}".format(e))
            raise
    
    async def get_recent_messages_from_all_channels(self, limit: int = None, days_back: int = 1) -> Dict[str, List[Dict]]:
        """Получение последних сообщений из всех каналов с группировкой по каналам"""
        if not self.channel_entities:
            raise ValueError("Не подключен ни к одному каналу. Сначала вызовите connect().")
        
        limit = limit or Config.MAX_MESSAGES
        results = {}
        
        for channel_username, channel_entity in self.channel_entities.items():
            logger.info("Fetching messages from channel: {}".format(channel_username))
            messages_data = []
            
            try:
                # Определяем дату начала для фильтрации
                cutoff_date = datetime.now() - timedelta(days=days_back)
                
                async for message in self.client.iter_messages(
                    channel_entity, 
                    limit=limit
                ):
                    if isinstance(message, MessageService):
                        continue
                    
                    # Фильтрация по дате
                    if message.date and message.date.replace(tzinfo=None) < cutoff_date:
                        break
                    
                    # Extract text from message, handling media messages
                    message_text = ''
                    if message.text:
                        message_text = message.text
                    elif hasattr(message, 'message') and message.message:
                        message_text = message.message
                    elif message.media and hasattr(message.media, 'caption') and message.media.caption:
                        message_text = message.media.caption
                    
                    message_data = {
                        'id': message.id,
                        'date': message.date,
                        'text': message_text,
                        'views': getattr(message, 'views', 0),
                        'forwards': getattr(message, 'forwards', 0),
                        'replies': getattr(message.replies, 'replies', 0) if message.replies else 0,
                        'comments': [],
                        'channel': channel_username,
                        'channel_title': channel_entity.title
                    }
                    
                    # Получение комментариев/ответов, если доступны
                    if message.replies and message.replies.replies > 0:
                        comments = await self.get_message_comments(message.id, channel_entity)
                        message_data['comments'] = comments
                    
                    messages_data.append(message_data)
                    
                    # Добавление задержки для избежания ограничений скорости
                    await asyncio.sleep(0.1)
                    
            except FloodWaitError as e:
                logger.warning("Rate limit for {}: waiting {} seconds...".format(channel_username, e.seconds))
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error("Error fetching messages from {}: {}".format(channel_username, e))
                messages_data = []
            
            results[channel_username] = messages_data
            logger.info("Fetched {} messages from {}".format(len(messages_data), channel_username))
        
        return results
    
    async def get_recent_messages(self, limit: int = None, channel_username: str = None) -> List[Dict]:
        """Получение последних сообщений из канала (для обратной совместимости)"""
        if channel_username and channel_username in self.channel_entities:
            channel_entity = self.channel_entities[channel_username]
        elif len(self.channel_entities) == 1:
            channel_entity = list(self.channel_entities.values())[0]
            channel_username = list(self.channel_entities.keys())[0]
        else:
            # Используем первый доступный канал
            channel_username = list(self.channel_entities.keys())[0]
            channel_entity = self.channel_entities[channel_username]
        
        limit = limit or Config.MAX_MESSAGES
        messages_data = []
        
        try:
            async for message in self.client.iter_messages(
                channel_entity, 
                limit=limit
            ):
                if isinstance(message, MessageService):
                    continue
                
                # Extract text from message, handling media messages
                message_text = ''
                if message.text:
                    message_text = message.text
                elif hasattr(message, 'message') and message.message:
                    message_text = message.message
                elif message.media and hasattr(message.media, 'caption') and message.media.caption:
                    message_text = message.media.caption
                
                message_data = {
                    'id': message.id,
                    'date': message.date,
                    'text': message_text,
                    'views': getattr(message, 'views', 0),
                    'forwards': getattr(message, 'forwards', 0),
                    'replies': getattr(message.replies, 'replies', 0) if message.replies else 0,
                    'comments': [],
                    'channel': channel_username,
                    'channel_title': channel_entity.title
                }
                
                # Получение комментариев/ответов, если доступны
                if message.replies and message.replies.replies > 0:
                    comments = await self.get_message_comments(message.id, channel_entity)
                    message_data['comments'] = comments
                
                messages_data.append(message_data)
                
                # Добавление задержки для избежания ограничений скорости
                await asyncio.sleep(0.5)
                
        except FloodWaitError as e:
            logger.warning("Rate limit. Waiting {} seconds...".format(e.seconds))
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error("Error fetching messages: {}".format(e))
            raise
        
        logger.info("Fetched {} messages from {}".format(len(messages_data), channel_username))
        return messages_data
    
    async def get_messages_by_date_range(self, start_date: datetime, end_date: datetime, channel_username: str = None) -> List[Dict]:
        """Получение сообщений из канала за определенный период"""
        if not self.channel_entities:
            raise ValueError("Не подключен ни к одному каналу. Сначала вызовите connect().")
        
        # Выбираем канал
        if channel_username and channel_username in self.channel_entities:
            channel_entity = self.channel_entities[channel_username]
        else:
            # Используем первый доступный канал
            channel_username = list(self.channel_entities.keys())[0]
            channel_entity = self.channel_entities[channel_username]
        
        # Приводим к naive datetime для сравнения
        start_check = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
        end_check = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
        
        if start_check > end_check:
            raise ValueError("Начальная дата не может быть позже конечной даты.")
        
        messages_data = []
        
        try:
            # Приводим входящие даты к naive datetime и добавляем время для полного покрытия дней
            start_naive = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
            end_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
            
            start_datetime = start_naive.replace(hour=0, minute=0, second=0, microsecond=0)
            end_datetime = end_naive.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            logger.info(f"Fetching messages from {start_datetime} to {end_datetime}")
            
            async for message in self.client.iter_messages(
                channel_entity,
                offset_date=end_datetime,  # Начинаем с конца периода
                reverse=False  # Идем от новых к старым
            ):
                if isinstance(message, MessageService):
                    continue
                
                # Приводим дату сообщения к naive datetime для сравнения
                message_date_naive = message.date.replace(tzinfo=None) if message.date.tzinfo else message.date
                
                # Проверяем, что сообщение в нужном диапазоне дат
                if message_date_naive < start_datetime:
                    # Достигли начала периода, прекращаем поиск
                    break
                
                if message_date_naive > end_datetime:
                    # Еще не дошли до нужного периода, продолжаем
                    continue
                
                # Extract text from message, handling media messages
                message_text = ''
                if message.text:
                    message_text = message.text
                elif hasattr(message, 'message') and message.message:
                    message_text = message.message
                elif message.media and hasattr(message.media, 'caption') and message.media.caption:
                    message_text = message.media.caption
                
                message_data = {
                    'id': message.id,
                    'date': message.date,
                    'text': message_text,
                    'views': getattr(message, 'views', 0),
                    'forwards': getattr(message, 'forwards', 0),
                    'replies': getattr(message.replies, 'replies', 0) if message.replies else 0,
                    'comments': []
                }
                
                # Получение комментариев/ответов, если доступны
                if message.replies and message.replies.replies > 0:
                    # Используем первый доступный канал для обратной совместимости
                    if self.channel_entities:
                        channel_entity = list(self.channel_entities.values())[0]
                        comments = await self.get_message_comments(message.id, channel_entity)
                        message_data['comments'] = comments
                
                messages_data.append(message_data)
                
                # Добавление задержки для избежания ограничений скорости
                await asyncio.sleep(0.5)
                
        except FloodWaitError as e:
            logger.warning(f"Rate limit. Waiting {e.seconds} seconds...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error fetching messages by date range: {e}")
            raise
        
        # Сортируем сообщения по дате (от новых к старым)
        messages_data.sort(key=lambda x: x['date'], reverse=True)
        
        logger.info(f"Fetched {len(messages_data)} messages for period from {start_date.date()} to {end_date.date()}")
        return messages_data
    
    async def get_message_comments(self, message_id: int, channel_entity=None, limit: int = 50) -> List[Dict]:
        """Получение комментариев для конкретного сообщения"""
        if channel_entity is None:
            # Для обратной совместимости используем первый доступный канал
            if self.channel_entities:
                channel_entity = list(self.channel_entities.values())[0]
            else:
                raise ValueError("Не подключен ни к одному каналу")
        
        comments = []
        
        try:
            async for comment in self.client.iter_messages(
                channel_entity,
                reply_to=message_id,
                limit=limit
            ):
                if isinstance(comment, MessageService):
                    continue
                
                # Safely extract user_id from different peer types
                user_id = None
                if comment.from_id:
                    if hasattr(comment.from_id, 'user_id'):
                        user_id = comment.from_id.user_id
                    elif hasattr(comment.from_id, 'channel_id'):
                        user_id = comment.from_id.channel_id
                    else:
                        user_id = str(comment.from_id)
                
                # Extract text from comment, handling media comments
                comment_text = ''
                if comment.text:
                    comment_text = comment.text
                elif hasattr(comment, 'message') and comment.message:
                    comment_text = comment.message
                elif comment.media and hasattr(comment.media, 'caption') and comment.media.caption:
                    comment_text = comment.media.caption
                
                comment_data = {
                    'id': comment.id,
                    'date': comment.date,
                    'text': comment_text,
                    'user_id': user_id,
                    'reply_to': comment.reply_to.reply_to_msg_id if comment.reply_to else None
                }
                comments.append(comment_data)
                
        except Exception as e:
            logger.error(f"Error fetching comments for message {message_id}: {e}")
        
        return comments
    
    async def disconnect(self):
        """Отключение от Telegram"""
        await self.client.disconnect()
        logger.info("Disconnected from Telegram")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect() 