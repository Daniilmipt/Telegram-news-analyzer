import logging
import logging.handlers
import os
from datetime import datetime


class LoggingConfig:
    LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
    
    LOG_FILE = os.path.join(LOG_DIR, "news_analyzer.log")
    
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    @classmethod
    def setup_logging(cls, logger_name=None, log_to_file=True, log_to_console=True):
        """
        Настройка централизованного логирования
        
        Args:
            logger_name: Имя логгера (используется root логгер, если None)
            log_to_file: Логировать в файл
            log_to_console: Логировать в консоль
        
        Returns:
            Настроенный экземпляр логгера
        """
        # Create logs directory if it doesn't exist
        if not os.path.exists(cls.LOG_DIR):
            os.makedirs(cls.LOG_DIR)
        
        logger = logging.getLogger(logger_name)
        
        logger.handlers = []
        
        logger.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(cls.LOG_FORMAT, cls.DATE_FORMAT)
        
        if log_to_file:
            # Один файл лога с ротацией (макс. 10MB, с бекпом из 5 файлов)
            file_handler = logging.handlers.RotatingFileHandler(
                cls.LOG_FILE,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        # Пишем лог в консоль
        if log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # Предотвращаем распространение лога в root логгер, чтобы избежать дублирования сообщений
        logger.propagate = False
        
        return logger
    
    @classmethod
    def setup_bot_logging(cls):
        """
        Настройка логирования для Telegram бота
        
        Returns:
            Настроенный экземпляр логгера для бота
        """
        if not os.path.exists(cls.LOG_DIR):
            os.makedirs(cls.LOG_DIR)
        
        logger = logging.getLogger('telegram_bot')
        
        logger.handlers = []
        
        logger.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(cls.LOG_FORMAT, cls.DATE_FORMAT)
        
        # Один файл лога с ротацией (макс. 10MB, с бекпом из 5 файлов)
        file_handler = logging.handlers.RotatingFileHandler(
            cls.LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Пишем лог в консоль
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Предотвращаем распространение лога в root логгер, чтобы избежать дублирования сообщений
        logger.propagate = False
        
        return logger
    
    @classmethod
    def get_log_files_info(cls):
        """
        Получить информацию о файлах лога
        
        Returns:
            Словарь с информацией о файлах лога
        """
        info = {}
        
        log_files = [
            ('unified_log', cls.LOG_FILE)
        ]
        
        for name, file_path in log_files:
            if os.path.exists(file_path):
                stat = os.stat(file_path)
                info[name] = {
                    'path': file_path,
                    'size_mb': round(stat.st_size / (1024*1024), 2),
                    'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                }
            else:
                info[name] = {
                    'path': file_path,
                    'size_mb': 0,
                    'modified': 'Not created yet'
                }
        
        return info


def setup_logger(name=None, file_logging=True, console_logging=True):
    """
    Быстрая настройка логгера
    
    Args:
        name: Имя логгера
        file_logging: Включить логирование в файл
        console_logging: Включить логирование в консоль
    
    Returns:
        Настроенный логгер
    """
    return LoggingConfig.setup_logging(
        logger_name=name,
        log_to_file=file_logging,
        log_to_console=console_logging
    )
