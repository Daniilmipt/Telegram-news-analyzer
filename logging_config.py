"""
Centralized logging configuration for News Analyzer project
"""

import logging
import logging.handlers
import os
from datetime import datetime


class LoggingConfig:
    """Centralized logging configuration class - captures all log levels by default"""
    
    # Log directory
    LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
    
    # Single unified log file
    LOG_FILE = os.path.join(LOG_DIR, "news_analyzer.log")
    
    # Log format
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    
    @classmethod
    def setup_logging(cls, logger_name=None, log_to_file=True, log_to_console=True):
        """
        Setup centralized logging configuration
        
        Args:
            logger_name: Name of the logger (uses root logger if None)
            log_to_file: Whether to log to file
            log_to_console: Whether to log to console
        
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
        
        # Set logger to capture all levels
        logger.setLevel(logging.DEBUG)
        
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
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        # Add console handler
        if log_to_console:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
        
        # Prevent propagation to root logger to avoid duplicate messages
        logger.propagate = False
        
        return logger
    
    @classmethod
    def setup_bot_logging(cls):
        """
        Setup specialized logging for Telegram bot
        
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
        
        # Set logger to capture all levels
        logger.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter(cls.LOG_FORMAT, cls.DATE_FORMAT)
        
        # Unified log file with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            cls.LOG_FILE,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Console output for bot
        console_handler = logging.StreamHandler()
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
def setup_logger(name=None, file_logging=True, console_logging=True):
    """
    Quick setup function for logger
    
    Args:
        name: Logger name
        file_logging: Enable file logging
        console_logging: Enable console logging
    
    Returns:
        Configured logger
    """
    return LoggingConfig.setup_logging(
        logger_name=name,
        log_to_file=file_logging,
        log_to_console=console_logging
    )
