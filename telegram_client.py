import asyncio
from typing import List, Dict
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.types import MessageService
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from config import Config
from logging_config import setup_logger

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
                    
                    # Извлекаем текст из сообщения, обрабатывая медиа сообщения
                    message_text = ''
                    if message.text:
                        message_text = message.text
                    elif hasattr(message, 'message') and message.message:
                        message_text = message.message
                    elif message.media and hasattr(message.media, 'caption') and message.media.caption:
                        message_text = message.media.caption # TODO: add media text
                    
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
                
                # Безопасно извлекаем user_id
                user_id = None
                if comment.from_id:
                    if hasattr(comment.from_id, 'user_id'):
                        user_id = comment.from_id.user_id
                    elif hasattr(comment.from_id, 'channel_id'):
                        user_id = comment.from_id.channel_id
                    else:
                        user_id = str(comment.from_id)
                
                # Извлекаем текст из комментария, обрабатывая медиа комментарии
                comment_text = ''
                if comment.text:
                    comment_text = comment.text
                elif hasattr(comment, 'message') and comment.message:
                    comment_text = comment.message
                elif comment.media and hasattr(comment.media, 'caption') and comment.media.caption:
                    comment_text = comment.media.caption # TODO: add media text
                
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
        await self.client.disconnect()
        logger.info("Disconnected from Telegram")
    
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect() 