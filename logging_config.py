"""
Centralized logging configuration for News Analyzer project
"""

import logging
import logging.handlers
import os
from datetime import datetime


class LoggingConfig:
    """Centralized logging configuration class"""
    
    # Log directory
    LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
    
    # Single unified log file
    LOG_FILE = os.path.join(LOG_DIR, "news_analyzer.log")
    
    # Log format
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    # Log levels
    DEFAULT_LEVEL = logging.INFO
    
    @classmethod
    def setup_logging(cls, logger_name=None, log_to_file=True, 
                     log_to_console=True, log_level=None):
        """
        Setup centralized logging configuration
        
        Args:
            logger_name: Name of the logger (uses root logger if None)
            log_to_file: Whether to log to file
            log_to_console: Whether to log to console
            log_level: Logging level (uses DEFAULT_LEVEL if None)
        
        Returns:
            Configured logger instance
        """
        # Create logs directory if it doesn't exist
        if not os.path.exists(cls.LOG_DIR):
            os.makedirs(cls.LOG_DIR)
        
        # Get logger
        logger = logging.getLogger(logger_name)
        
        # Clear existing handlers to avoid duplicates
        logger.handlers = []
        
        # Set log level
        level = log_level or cls.DEFAULT_LEVEL
        logger.setLevel(level)
        
        # Create formatter
        formatter = logging.Formatter(cls.LOG_FORMAT, cls.DATE_FORMAT)
        
        # Add file handler with rotation
        if log_to_file:
            # Single unified log file with rotation (max 10MB, keep 5 files)
            file_handler = logging.handlers.RotatingFileHandler(
                cls.LOG_FILE,
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        # Add console handler
        if log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # Prevent propagation to root logger to avoid duplicate messages
        logger.propagate = False
        
        return logger
    
    @classmethod
    def setup_bot_logging(cls, log_level=None):
        """
        Setup specialized logging for Telegram bot
        
        Args:
            log_level: Logging level (uses DEFAULT_LEVEL if None)
        
        Returns:
            Configured logger instance for bot
        """
        # Create logs directory if it doesn't exist
        if not os.path.exists(cls.LOG_DIR):
            os.makedirs(cls.LOG_DIR)
        
        # Get bot logger
        logger = logging.getLogger('telegram_bot')
        
        # Clear existing handlers
        logger.handlers = []
        
        # Set log level
        level = log_level or cls.DEFAULT_LEVEL
        logger.setLevel(level)
        
        # Create formatter
        formatter = logging.Formatter(cls.LOG_FORMAT, cls.DATE_FORMAT)
        
        # Unified log file with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            cls.LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Console output for bot
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Prevent propagation to avoid duplicates
        logger.propagate = False
        
        return logger
    
    @classmethod
    def get_log_files_info(cls):
        """
        Get information about log files
        
        Returns:
            Dict with log files information
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


# Convenience function for quick setup
def setup_logger(name=None, level=logging.INFO, 
                file_logging=True, console_logging=True):
    """
    Quick setup function for logger
    
    Args:
        name: Logger name
        level: Log level
        file_logging: Enable file logging
        console_logging: Enable console logging
    
    Returns:
        Configured logger
    """
    return LoggingConfig.setup_logging(
        logger_name=name,
        log_to_file=file_logging,
        log_to_console=console_logging,
        log_level=level
    )
