#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot for Negative Posts Analysis

Two modes:
1. On-demand: Run analysis like python main.py and send results
2. Real-time: Monitor channel every 5 minutes and send negative posts
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Set, Dict
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

from sentiment_analyzer import SentimentAnalyzer
from report_generator import ReportGenerator
from telegram_client import TelegramNewsClient
from config import Config
from logging_config import LoggingConfig

# Configure logging with file output
logger = LoggingConfig.setup_bot_logging()

def clean_text_preview(text: str, max_length: int = 200) -> str:
    """Clean and prettify text by removing newlines and normalizing whitespace"""
    if not text:
        return ""
    
    # Replace newlines and carriage returns with spaces
    clean_text = text.replace('\n', ' ').replace('\r', ' ').strip()
    # Remove multiple consecutive spaces
    clean_text = re.sub(r'\s+', ' ', clean_text)
    # Truncate if needed
    return clean_text[:max_length] + '...' if len(clean_text) > max_length else clean_text


class NegativePostsBot:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.app = Application.builder().token(bot_token).build()
        
        # Analysis components
        self.sentiment_analyzer = SentimentAnalyzer()
        self.report_generator = ReportGenerator()
        
        # Real-time monitoring state
        self.monitoring_active = False
        self.sent_message_ids: Set[int] = set()
        self.monitoring_chat_id = None
        
        # Store last generated HTML path for button access
        self.last_html_path = None
        
        # Selected channels for analysis
        self.selected_channels = Config.get_channels_list()  # Default to all configured channels
        
        # Duplicate prevention for all commands and callbacks
        self.recent_callbacks: Dict[str, float] = {}
        self.recent_commands: Dict[str, float] = {}  # Track all commands
        
        # Load sent messages from file if exists
        self._load_sent_messages()
        
        # Setup handlers
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup bot command and callback handlers"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("analyze", self.analyze_command))
        self.app.add_handler(CommandHandler("monitor", self.monitor_command))
        self.app.add_handler(CommandHandler("stop", self.stop_monitor_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
    
    def _load_sent_messages(self):
        """Load previously sent message IDs from file"""
        try:
            if os.path.exists('sent_messages.json'):
                with open('sent_messages.json', 'r') as f:
                    data = json.load(f)
                    self.sent_message_ids = set(data.get('sent_ids', []))
                    logger.info(f"Loaded {len(self.sent_message_ids)} sent message IDs")
        except Exception as e:
            logger.error(f"Error loading sent messages: {e}")
            self.sent_message_ids = set()
    
    def _save_sent_messages(self):
        """Save sent message IDs to file"""
        try:
            data = {
                'sent_ids': list(self.sent_message_ids),
                'last_updated': datetime.now().isoformat()
            }
            with open('sent_messages.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving sent messages: {e}")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        chat_id = update.effective_chat.id
        
        # Prevent duplicate start commands
        if self._is_duplicate_command(chat_id, "start"):
            return
        
        keyboard = [
            [InlineKeyboardButton("📊 Анализировать", callback_data="analyze_now")],
            [InlineKeyboardButton("📋 Выбрать каналы", callback_data="select_channels")],
            [InlineKeyboardButton("🔄 Начать мониторинг", callback_data="start_monitor")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        channels_list = Config.get_channels_list()
        channels_text = ", ".join(channels_list)
        
        welcome_text = """
🤖 **Бот для анализа негативных постов**

📋 Каналы: `{}`
🎯 Порог негативности: {}%

**Доступные действия:**
📊 **Анализировать** - анализ сообщений за выбранный период
📋 **Выбрать каналы** - настроить список каналов для анализа
🔄 **Мониторинг** - проверка новых негативных постов

Выберите действие:
        """.format(channels_text, Config.NEGATIVE_COMMENT_THRESHOLD * 100)
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    def _get_help_text(self) -> str:
        """Get help text content"""
        return """
🤖 **Команды бота**

**Основные команды:**
/start - начало работы
/help - справка бота
/analyze - анализ сообщений за выбранный период
/monitor - мониторинг новых негативных постов
/stop - остановка мониторинга
/status - текущий статус

**Режимы работы:**

📊 **Анализ**
- Выбор периода:
• 📅 Сегодня
• 📆 Вчера  
• 📊 Последние 7 дней
• 📈 Последние 30 дней
• 🔧 Выбрать период
- анализ сообщений за выбранный период
- поиск негативных постов на основе сентимента комментариев
- отправка отформатированных данных и HTML-отчета

🔄 **Мониторинг**  
- проверка канала каждые 5 минут
- отправка уведомлений о новых негативных постах
- остановка мониторинга командой /stop

**Конфигурация:**
- Канал: `{channel}`
- Порог негативности: {threshold}%
- мониторинг: каждые 5 минут
        """.format(
            channel=Config.CHANNEL_USERNAME,
            threshold=Config.NEGATIVE_COMMENT_THRESHOLD * 100
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        chat_id = update.effective_chat.id
        
        # Prevent duplicate help commands
        if self._is_duplicate_command(chat_id, "help"):
            return
            
        await update.message.reply_text(self._get_help_text(), parse_mode=ParseMode.MARKDOWN)
    
    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command - show date selection menu"""
        chat_id = update.effective_chat.id
        
        # Prevent duplicate analyze commands
        if self._is_duplicate_command(chat_id, "analyze"):
            return
            
        await self._show_date_selection_menu(chat_id, context)
    
    async def monitor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /monitor command - start real-time monitoring"""
        chat_id = update.effective_chat.id
        
        # Prevent duplicate monitor commands
        if self._is_duplicate_command(chat_id, "monitor"):
            return
            
        if self.monitoring_active:
            await update.message.reply_text("🔄 Мониторинг уже активен!")
            return
        
        self.monitoring_active = True
        self.monitoring_chat_id = update.effective_chat.id
        
        # Schedule monitoring job
        context.job_queue.run_repeating(
            self._monitor_callback,
            interval=300,  # 5 minutes
            first=10,      # Start in 10 seconds
            data=update.effective_chat.id,
            name=f"monitor_{update.effective_chat.id}"
        )
        
        # Get list of channels to display
        channels_list = Config.get_channels_list()
        channels_text = "\n".join([f"  • `{channel}`" for channel in channels_list])
        
        await update.message.reply_text(
            f"🔄 **Мониторинг запущен!**\n\n"
            f"• Проверка каждые 5 минут\n"
            f"• Каналы:\n{channels_text}\n"
            f"• Используйте /stop для остановки мониторинга",
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def stop_monitor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command - stop monitoring"""
        chat_id = update.effective_chat.id
        
        # Prevent duplicate stop commands
        if self._is_duplicate_command(chat_id, "stop"):
            return
        
        if not self.monitoring_active:
            await update.message.reply_text("❌ Мониторинг не активен")
            return
        
        # Remove job
        current_jobs = context.job_queue.get_jobs_by_name(f"monitor_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()
        
        self.monitoring_active = False
        self.monitoring_chat_id = None
        
        await update.message.reply_text("⏹️ Мониторинг остановлен")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        chat_id = update.effective_chat.id
        
        # Prevent duplicate status commands
        if self._is_duplicate_command(chat_id, "status"):
            return
            
        status_text = f"""
📊 **Статус бота**

**Конфигурация:**
• Канал: `{Config.CHANNEL_USERNAME}`
• Порог негативности: {Config.NEGATIVE_COMMENT_THRESHOLD * 100}%

**Мониторинг:**
• Статус: {'🔄 Активен' if self.monitoring_active else '⏹️ Неактивен'}
• Отслеживаемых сообщений: {len(self.sent_message_ids)}
        """
        
        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
    
    def _is_duplicate_callback(self, callback_key: str, timeout: float = 3.0) -> bool:
        """Check if this callback was recently executed to prevent duplicates"""
        current_time = time.time()
        
        if callback_key in self.recent_callbacks:
            time_diff = current_time - self.recent_callbacks[callback_key]
            if time_diff < timeout:
                logger.info(f"Ignoring duplicate callback '{callback_key}' (sent {time_diff:.1f}s ago)")
                return True
        
        # Update timestamp and clean old entries
        self.recent_callbacks[callback_key] = current_time
        self.recent_callbacks = {
            key: timestamp for key, timestamp in self.recent_callbacks.items()
            if current_time - timestamp < 10.0
        }
        return False

    def _is_duplicate_command(self, chat_id: int, command: str, timeout: float = 2.0) -> bool:
        """Check if this command was recently executed to prevent duplicates"""
        current_time = time.time()
        command_key = f"{chat_id}_{command}"
        
        if command_key in self.recent_commands:
            time_diff = current_time - self.recent_commands[command_key]
            if time_diff < timeout:
                logger.info(f"Ignoring duplicate command '{command}' from {chat_id} (sent {time_diff:.1f}s ago)")
                return True
        
        # Update timestamp and clean old entries
        self.recent_commands[command_key] = current_time
        self.recent_commands = {
            key: timestamp for key, timestamp in self.recent_commands.items()
            if current_time - timestamp < 10.0
        }
        return False

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses"""
        query = update.callback_query
        
        # Answer the callback query immediately to prevent timeout
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Failed to answer callback query (query may be too old): {e}")
        
        # Create unique callback key
        chat_id = query.message.chat_id
        callback_key = f"{chat_id}_{query.data}"
        
        # Check for duplicate callback
        if self._is_duplicate_callback(callback_key):
            return
        
        if query.data == "analyze_now":
            # Show date selection menu
            await self._show_date_selection_menu(query.message.chat_id, context)
        
        elif query.data == "select_channels":
            # Show channels selection menu
            await self._show_channels_selection_menu(query.message.chat_id, context)
        
        elif query.data.startswith("toggle_channel_"):
            # Toggle channel selection
            channel = query.data.replace("toggle_channel_", "")
            await self._toggle_channel_selection(channel, query.message.chat_id, context)
        
        elif query.data == "channels_done":
            # Finish channel selection
            await self._finish_channel_selection(query.message.chat_id, context)
        
        elif query.data == "start_monitor":
            if self.monitoring_active:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="🔄 Мониторинг уже активен!"
                )
                return
            
            # Send progress message
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🔄 Запускаем мониторинг..."
            )
            
            self.monitoring_active = True
            self.monitoring_chat_id = query.message.chat_id
            
            # Schedule monitoring job
            context.job_queue.run_repeating(
                self._monitor_callback,
                interval=300,  # 5 minutes
                first=10,      # Start in 10 seconds
                data=query.message.chat_id,
                name=f"monitor_{query.message.chat_id}"
            )
            
            # Get list of channels to display
            channels_list = Config.get_channels_list()
            channels_text = "\n".join([f"  • `{channel}`" for channel in channels_list])
            
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🔄 **Мониторинг запущен!**\n\n"
                     f"• Периодичность каждые 5 минут\n"
                     f"• Каналы:\n{channels_text}\n"
                     f"• Используйте /stop для остановки мониторинга",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif query.data == "help":
            # Send help as a new message instead of editing
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=self._get_help_text(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        elif query.data == "get_html_report":
            try:
                # Use the stored HTML file path
                if hasattr(self, 'last_html_path') and self.last_html_path:
                    html_path = self.last_html_path
                    
                    # Send HTML file only once
                    with open(html_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=query.message.chat_id,
                            document=f,
                            filename=os.path.basename(html_path),
                            caption="📊 HTML-отчет - Скачайте и откройте в вашем браузере"
                        )
                else:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text="❌ HTML-отчет недоступен. Пожалуйста, сначала запустите анализ"
                    )
                
            except Exception as e:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"❌ Ошибка отправки HTML-файла: {str(e)}"
                )
        
        # Handle quick date selections
        elif query.data.startswith("analyze_"):
            date_option = query.data.replace("analyze_", "")
            await self._handle_date_selection(query.message.chat_id, context, date_option)
        
        # Handle calendar interactions
        elif query.data.startswith("cal_"):
            await self._handle_calendar_callback(query, context)
    
    async def _show_date_selection_menu(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Show date selection menu with quick options"""
        keyboard = [
            [InlineKeyboardButton("📅 Сегодня", callback_data="analyze_today")],
            [InlineKeyboardButton("📆 Вчера", callback_data="analyze_yesterday")],
            [InlineKeyboardButton("📊 Последние 7 дней", callback_data="analyze_week")],
            [InlineKeyboardButton("📈 Последние 30 дней", callback_data="analyze_month")],
            [InlineKeyboardButton("🔧 Выбрать самостоятельно", callback_data="analyze_custom")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="📊 **Выберите период для анализа:**",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_date_selection(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, date_option: str):
        """Handle date selection and start analysis"""
        from datetime import datetime, timedelta
        
        now = datetime.now()
        
        if date_option == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now
            period_name = "сегодня"
            
        elif date_option == "yesterday":
            yesterday = now - timedelta(days=1)
            start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            period_name = "вчера"
            
        elif date_option == "week":
            start_date = now - timedelta(days=7)
            end_date = now
            period_name = "последние 7 дней"
            
        elif date_option == "month":
            start_date = now - timedelta(days=30)
            end_date = now
            period_name = "последние 30 дней"
            
        elif date_option == "custom":
            # Show calendar for custom date selection
            await self._show_custom_date_selection(chat_id, context)
            return
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Некорректный период. Попробуйте еще раз"
            )
            return
        
        # Start analysis with selected date range
        await self._run_analysis_with_dates(chat_id, context, start_date, end_date, period_name)
    
    async def _show_custom_date_selection(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Show custom date selection interface"""
        # Initialize date selection state for this user
        if not hasattr(self, 'date_selection_state'):
            self.date_selection_state = {}
        
        self.date_selection_state[chat_id] = {
            'stage': 'start_date',  # 'start_date' or 'end_date'
            'start_date': None,
            'end_date': None,
            'current_month': datetime.now().replace(day=1),
        }
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="📅 **Выберите период**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Show calendar for start date
        await self._show_calendar(chat_id, context, self.date_selection_state[chat_id]['current_month'])
    
    def _create_calendar_keyboard(self, year: int, month: int) -> InlineKeyboardMarkup:
        """Create calendar keyboard for date selection"""
        import calendar
        
        # Create calendar for the month
        cal = calendar.monthcalendar(year, month)
        
        # Month and year header
        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        keyboard = []
        
        # Header with month/year and navigation
        keyboard.append([
            InlineKeyboardButton("◀", callback_data=f"cal_prev_{year}_{month}"),
            InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="cal_ignore"),
            InlineKeyboardButton("▶", callback_data=f"cal_next_{year}_{month}")
        ])
        
        # Days of the week header
        days_header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        keyboard.append([InlineKeyboardButton(day, callback_data="cal_ignore") for day in days_header])
        
        # Calendar days
        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    # Empty cell
                    row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
                else:
                    # Date button
                    today = datetime.now()
                    button_date = datetime(year, month, day)
                    
                    # Don't allow future dates
                    if button_date > today:
                        row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
                    else:
                        row.append(InlineKeyboardButton(str(day), callback_data=f"cal_date_{year}_{month}_{day}"))
            keyboard.append(row)
        
        # Cancel button
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cal_cancel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def _show_calendar(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, date: datetime):
        """Show calendar for date selection"""
        keyboard = self._create_calendar_keyboard(date.year, date.month)
        
        state = self.date_selection_state.get(chat_id, {})
        stage = state.get('stage', 'start_date')
        
        if stage == 'start_date':
            text = "📅 **Выберите начальную дату:**"
        else:
            start_date = state.get('start_date')
            text = f"📅 **Выберите конечную дату:**\n\n" \
                   f"Начальная дата: {start_date.strftime('%d.%m.%Y')}"
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _handle_calendar_callback(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Handle calendar button callbacks"""
        chat_id = query.message.chat_id
        data = query.data
        
        # Initialize state if needed
        if not hasattr(self, 'date_selection_state'):
            self.date_selection_state = {}
        
        if chat_id not in self.date_selection_state:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Сессия истекла. Начните заново"
            )
            return
        
        state = self.date_selection_state[chat_id]
        
        if data == "cal_cancel":
            # Cancel date selection
            del self.date_selection_state[chat_id]
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Выбор периода отменен"
            )
            return
        
        elif data == "cal_ignore":
            # Do nothing for ignore buttons
            return
        
        elif data.startswith("cal_prev_") or data.startswith("cal_next_"):
            # Navigation between months
            parts = data.split("_")
            current_year = int(parts[2])
            current_month = int(parts[3])
            
            if data.startswith("cal_prev_"):
                # Previous month
                if current_month == 1:
                    new_month = 12
                    new_year = current_year - 1
                else:
                    new_month = current_month - 1
                    new_year = current_year
            else:
                # Next month
                if current_month == 12:
                    new_month = 1
                    new_year = current_year + 1
                else:
                    new_month = current_month + 1
                    new_year = current_year
            
            # Update current month
            state['current_month'] = datetime(new_year, new_month, 1)
            
            # Update calendar
            keyboard = self._create_calendar_keyboard(new_year, new_month)
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=query.message.message_id,
                reply_markup=keyboard
            )
        
        elif data.startswith("cal_date_"):
            # Date selected
            parts = data.split("_")
            selected_year = int(parts[2])
            selected_month = int(parts[3])
            selected_day = int(parts[4])
            
            selected_date = datetime(selected_year, selected_month, selected_day)
            
            if state['stage'] == 'start_date':
                # Start date selected, now select end date
                state['start_date'] = selected_date
                state['stage'] = 'end_date'
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=query.message.message_id,
                    text=f"Шаг 2: Выберите конечную дату",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Show calendar for end date
                await self._show_calendar(chat_id, context, state['current_month'])
                
            elif state['stage'] == 'end_date':
                # End date selected, validate and start analysis
                state['end_date'] = selected_date
                
                start_date = state['start_date']
                end_date = state['end_date']
                
                # Validate dates
                if end_date < start_date:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ Конечная дата не может быть раньше начальной",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    await self._show_calendar(chat_id, context, state['current_month'])
                    return
                
                # Clean up state
                del self.date_selection_state[chat_id]
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ **Период выбран:**\n\n"
                         f"📅 С: {start_date.strftime('%d.%m.%Y')}\n"
                         f"📅 По: {end_date.strftime('%d.%m.%Y')}\n\n"
                         f"🔄 Запускаем анализ...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Calculate period name
                days_diff = (end_date - start_date).days + 1
                if days_diff == 1:
                    period_name = f"{start_date.strftime('%d.%m.%Y')}"
                else:
                    period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
                
                # Start analysis
                await self._run_analysis_with_dates(chat_id, context, start_date, end_date, period_name)
    
    async def _run_analysis_with_dates(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, 
                                     start_date: datetime, end_date: datetime, period_name: str):
        """Run analysis for a specific date range"""
        from datetime import datetime
        
        # Additional duplicate prevention for analysis
        analysis_key = f"analysis_{chat_id}"
        if self._is_duplicate_callback(analysis_key, timeout=30.0):  # 30 second timeout for analysis
            logger.info(f"Analysis already running for chat {chat_id}, ignoring duplicate request")
            return
            
        try:
            # Send progress message
            progress_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔄 **Анализ за {period_name}...**",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Fetch messages by date range from selected channels
            async with TelegramNewsClient() as client:
                await client.connect(self.selected_channels)
                messages_by_channel = await client.get_recent_messages_from_all_channels(
                    limit=Config.MAX_MESSAGES,
                    days_back=(end_date - start_date).days + 1
                )
            
            # Filter messages by date range and combine all channels
            all_messages = []
            cutoff_start = start_date.replace(tzinfo=None)
            cutoff_end = end_date.replace(tzinfo=None)
            
            for channel_username, messages in messages_by_channel.items():
                filtered_messages = []
                for msg in messages:
                    msg_date = msg['date'].replace(tzinfo=None) if msg['date'].tzinfo else msg['date']
                    if cutoff_start <= msg_date <= cutoff_end:
                        filtered_messages.append(msg)
                
                messages_by_channel[channel_username] = filtered_messages
                all_messages.extend(filtered_messages)
            
            if not all_messages:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_msg.message_id,
                    text="ℹ️ **Анализ завершен**\n\n"
                         "📅 Период: {} - {}\n"
                         "📥 Сообщений не найдено за указанный период.".format(start_date.strftime('%d.%m.%Y'), end_date.strftime('%d.%m.%Y')),
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Show progress by channels
            channels_info = []
            for channel, msgs in messages_by_channel.items():
                channels_info.append("{}: {}".format(channel, len(msgs)))
            
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text="🔄 **Анализ за {}...**\n\n"
                     "📅 Период: {} - {}\n"
                     "📥 Получено {} сообщений\n"
                     "📋 По каналам: {}\n"
                     "🔍 Анализируем сентимент...".format(
                         period_name,
                         start_date.strftime('%d.%m.%Y'),
                         end_date.strftime('%d.%m.%Y'),
                         len(all_messages),
                         ", ".join(channels_info)
                     ),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Analyze messages from all channels
            all_messages = self.sentiment_analyzer.analyze_messages_sentiment(all_messages)
            
            # Generate multichannel report
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text="🔄 **Анализ за {}...**\n\n"
                     "📅 Период: {} - {}\n"
                     "📥 Обработано {} сообщений\n"
                     "📋 По каналам: {}\n"
                     "📊 Генерируем отчет...".format(
                         period_name,
                         start_date.strftime('%d.%m.%Y'),
                         end_date.strftime('%d.%m.%Y'),
                         len(all_messages),
                         ", ".join(channels_info)
                     ),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Generate multichannel report
            report_result = self.report_generator.generate_multichannel_negative_posts_report(all_messages)
            
            # Final success message
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_msg.message_id,
                text="✅ **Анализ завершен за {}!**\n\n"
                     "📅 Период: {} - {}\n"
                     "📥 Обработано {} сообщений\n"
                     "📋 По каналам: {}\n"
                     "⚠️ Негативных постов: {}\n"
                     "📊 Процент негативности: {:.1f}%".format(
                         period_name,
                         start_date.strftime('%d.%m.%Y'),
                         end_date.strftime('%d.%m.%Y'),
                         report_result['total_messages'],
                         ", ".join(channels_info),
                         report_result['total_negative'],
                         (report_result['total_negative'] / report_result['total_messages'] * 100) if report_result['total_messages'] > 0 else 0
                     ),
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Store HTML file path and create button
            self.last_html_path = report_result.get('html_file', report_result.get('html_path'))
            
            keyboard = [[InlineKeyboardButton("📊 Получить HTML-отчет", callback_data="get_html_report")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Generate detailed summary by channels
            channels_summary = []
            for channel, data in report_result['channels_data'].items():
                ch_total = len(data['messages'])
                ch_negative = len(data['negative_posts'])
                ch_pct = (ch_negative / ch_total * 100) if ch_total > 0 else 0
                channels_summary.append("• {}: {} сообщений, {} негативных ({:.1f}%)".format(
                    data['channel_title'], ch_total, ch_negative, ch_pct
                ))
            
            summary_text = """
📋 **Детализация по каналам:**

{}

📁 **Созданные файлы:**
• HTML-отчет: `{}`
• JSON-отчет: `{}`
            """.format(
                "\n".join(channels_summary),
                os.path.basename(report_result.get('html_file', report_result.get('html_path', 'unknown'))),
                os.path.basename(report_result.get('json_file', report_result.get('json_path', 'unknown')))
            )
            
            # Send detailed summary with HTML button
            await context.bot.send_message(
                chat_id=chat_id,
                text=summary_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Send formatted JSON data as text message
            json_file_path = report_result.get('json_file', report_result.get('json_path'))
            if json_file_path:
                await self._send_formatted_json_data(chat_id, json_file_path)
            
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ **Анализ не удался:** {str(e)}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _monitor_callback(self, context: ContextTypes.DEFAULT_TYPE):
        """Monitoring callback - runs every 5 minutes"""
        if not self.monitoring_active or not self.monitoring_chat_id:
            return
        
        try:
            logger.info("Running monitoring check...")
            
            # Fetch only recent messages from all channels (last 10 minutes worth)
            async with TelegramNewsClient() as client:
                all_messages_by_channel = await client.get_recent_messages_from_all_channels(limit=5, days_back=1)
                
                # Flatten messages from all channels into a single list
                messages = []
                for channel, channel_messages in all_messages_by_channel.items():
                    messages.extend(channel_messages)
            
            # Filter messages from last 60 minutes to catch new ones
            now = datetime.now()
            cutoff_time = now - timedelta(minutes=60)
            print(f"Cutoff time: {cutoff_time}")
            
            recent_messages = []
            for msg in messages:
                print(f"Message ID: {msg.get('id', 'Unknown')}")
                msg_date = msg.get('date')
                if hasattr(msg_date, 'replace'):
                    # Remove timezone info for comparison
                    msg_date = msg_date.replace(tzinfo=None)

                    print(f"Message date: {msg_date}")
                    if msg_date >= cutoff_time:
                        recent_messages.append(msg)
            
            if not recent_messages:
                logger.info("No recent messages found")
                return
            
            # Analyze recent messages
            analyzed_messages = self.sentiment_analyzer.analyze_messages_sentiment(recent_messages)
            # analyzed_messages = self.location_extractor.analyze_messages_locations(analyzed_messages)
            # analyzed_messages = self.topic_classifier.analyze_messages_topics(analyzed_messages)
            
            # Find new negative messages
            new_negative_messages = []
            for msg in analyzed_messages:
                if msg.get('is_negative', False) and msg['id'] not in self.sent_message_ids:
                    new_negative_messages.append(msg)
                    self.sent_message_ids.add(msg['id'])
            
            if new_negative_messages:
                # Save updated sent messages
                self._save_sent_messages()
                
                # Send alerts for new negative posts
                for msg in new_negative_messages:
                    await self._send_negative_post_alert(msg)
                
                logger.info(f"Sent {len(new_negative_messages)} negative post alerts")
            else:
                logger.info("No new negative posts found")
        
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
            if self.monitoring_chat_id:
                await self.app.bot.send_message(
                    chat_id=self.monitoring_chat_id,
                    text=f"⚠️ **Ошибка мониторинга:** {str(e)}",
                    parse_mode=ParseMode.MARKDOWN
                )
    
    async def _send_long_message(self, chat_id: int, message: str):
        """Send a long message, splitting it if necessary to respect Telegram's 4096 character limit"""
        MAX_MESSAGE_LENGTH = 4000  # Leave some buffer for safety
        
        if len(message) <= MAX_MESSAGE_LENGTH:
            # Message fits in one chunk
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            # Need to split the message
            chunks = []
            lines = message.split('\n')
            current_chunk = ""
            
            for line in lines:
                # Check if adding this line would exceed the limit
                if len(current_chunk) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                    # Save current chunk and start a new one
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    # Add line to current chunk
                    if current_chunk:
                        current_chunk += "\n" + line
                    else:
                        current_chunk = line
            
            # Add the last chunk
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # Send all chunks
            for i, chunk in enumerate(chunks):
                if i == 0:
                    # First chunk - send as is
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                else:
                    # Subsequent chunks - add continuation indicator
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=f"📄 Продолжение...\n\n{chunk}",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )

    async def _send_formatted_json_data(self, chat_id: int, json_path: str):
        """Send formatted JSON data as readable Telegram message"""
        try:
            # Load JSON data
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle both single-channel and multi-channel data formats
            if 'channels' in data:  # Multi-channel format
                metadata = data.get('metadata', {})
                channels_data = data.get('channels', {})
                
                # Build complete message with all content
                complete_message = "📊 Данные анализа\n\n"
                complete_message += "Метаданные:\n"
                complete_message += "• Проанализировано постов: {}\n".format(metadata.get('total_messages', 0))
                complete_message += "• Найдено негативных постов: {}\n".format(metadata.get('total_negative', 0))
                
                # Add all posts grouped by channel
                total_negative_posts = sum(len(channel_data.get('negative_posts', [])) for channel_data in channels_data.values())
                if total_negative_posts > 0:
                    complete_message += "\n\nТоп негативных постов:\n"
                    
                    for channel, channel_data in channels_data.items():
                        negative_posts = channel_data.get('negative_posts', [])
                        if not negative_posts:
                            continue
                            
                        # Add channel header
                        complete_message += f"\n• **Канал: {channel_data.get('channel_title', channel)}**\n"
                        
                        # Add top negative posts from this channel
                        for post_idx, post in enumerate(negative_posts[:3], 1):  # Show top 3 from each channel
                            # Clean and prettify text preview
                            text_preview = clean_text_preview(post.get('text', ''), 100)  # Shorter for combined message
                            
                            post_id = post.get('id', 'N/A')
                            post_date = post.get('date', 'N/A')
                            negative_score = post.get('negative_score', 0)
                            total_comments = post.get('total_comments', 0)
                            negative_comments = post.get('negative_comments', 0)
                            negative_comment_percentage = post.get('negative_comment_percentage', 0)
                            views = post.get('views', 0)
                            forwards = post.get('forwards', 0)
                            
                            # Create Telegram link - extract channel username from channel title or use generic
                            channel_username = post.get('channel', channel)
                            if channel_username.startswith('@'):
                                channel_username = channel_username[1:]
                            
                            post_link = f"https://t.me/{channel_username}/{post_id}" if channel_username else "#"
                            
                            # Format post in compact style with Telegram link
                            complete_message += f"""
{post_idx}. Пост ID {post_id}
📅 {post_date}
📊 Оценка: {negative_score:.3f}
💬 Комментарии: {negative_comments}/{total_comments} ({negative_comment_percentage:.1f}% нег.)
👀 Просмотры: {views} | ↗️ Перепосты: {forwards}

📄 {text_preview}

🔗 [Открыть в Telegram]({post_link})
"""
                else:
                    complete_message += "\n\n🎉 Негативных постов не найдено!"
                
                # Send the complete message as one, handling length limits
                await self._send_long_message(chat_id, complete_message)
                
                return  # Exit early since we've sent all messages
            else:  # Single-channel format
                metadata = data.get('metadata', {})
                negative_posts = data.get('negative_posts', [])
                
                # Build complete message with all content
                complete_message = "📊 Данные анализа\n\n"
                complete_message += "Метаданные:\n"
                complete_message += "• Проанализировано постов: {}\n".format(metadata.get('total_posts_analyzed', 0))
                complete_message += "• Найдено негативных постов: {}\n".format(metadata.get('negative_posts_found', 0))
                complete_message += "• Канал: {}\n".format(metadata.get('channel_username', 'Неизвестно'))
                
                # Add all posts
                if negative_posts:
                    complete_message += "\n\nТоп негативных постов:\n"
                    
                    for i, post in enumerate(negative_posts[:3], 1):
                        # Clean and prettify text preview
                        text_preview = clean_text_preview(post.get('text', ''), 100)  # Shorter for combined message
                        
                        # Format detailed post information
                        post_id = post.get('id', 'N/A')
                        post_date = post.get('date', 'N/A')
                        negative_score = post.get('negative_score', 0)
                        total_comments = post.get('total_comments', 0)
                        negative_comments = post.get('negative_comments', 0)
                        negative_comment_percentage = post.get('negative_comment_percentage', 0)
                        views = post.get('views', 0)
                        forwards = post.get('forwards', 0)
                        
                        # Create Telegram link
                        channel_username = metadata.get('channel_username', Config.CHANNEL_USERNAME or '')
                        if channel_username.startswith('@'):
                            channel_username = channel_username[1:]
                        
                        post_link = f"https://t.me/{channel_username}/{post_id}" if channel_username else "#"
                        
                        # Format post in compact style with Telegram link
                        complete_message += f"""
{i}. Пост ID {post_id}
📅 {post_date}
📊 Оценка: {negative_score:.3f}
💬 Комментарии: {negative_comments}/{total_comments} ({negative_comment_percentage:.1f}% нег.)
👀 Просмотры: {views} | ↗️ Перепосты: {forwards}

📄 {text_preview}

🔗 [Открыть в Telegram]({post_link})
"""
                else:
                    complete_message += "\n\n🎉 Негативных постов не найдено!"
                
                # Send the complete message as one, handling length limits
                await self._send_long_message(chat_id, complete_message)
                
                return  # Exit early since we've sent all messages
            
        except Exception as e:
            logger.error(f"Error sending formatted JSON: {e}")
            # Fallback - send the raw JSON file
            with open(json_path, 'rb') as f:
                await self.app.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=os.path.basename(json_path),
                    caption="📄 Данные анализа (ошибка отображения)"
                )
    
    async def _send_negative_post_alert(self, message: dict):
        """Send alert for a single negative post"""
        if not self.monitoring_chat_id:
            return
        
        # Format date
        msg_date = message.get('date')
        if hasattr(msg_date, 'strftime'):
            formatted_date = msg_date.strftime('%Y-%m-%d %H:%M')
        else:
            formatted_date = str(msg_date)
        
        # Get sentiment info
        sentiment_data = message.get('sentiment', {})
        negative_score = sentiment_data.get('negative', 0)
        
        # Get comment info
        comments = message.get('comments', [])
        total_comments = len(comments)
        negative_comments = sum(1 for c in comments if c.get('is_negative', False))
        negative_percentage = (negative_comments / total_comments * 100) if total_comments > 0 else 0
        
        # Create Telegram link
        channel_username = Config.CHANNEL_USERNAME.replace('@', '') if Config.CHANNEL_USERNAME.startswith('@') else Config.CHANNEL_USERNAME
        post_link = f"https://t.me/{channel_username}/{message['id']}"
        
        # Clean and prettify text preview
        text_preview = clean_text_preview(message.get('text', ''), 300)
        
        # Get views and forwards
        views = message.get('views', 0)
        forwards = message.get('forwards', 0)
        
        alert_text = f"""🚨 **Новый негативный пост**

Пост ID {message['id']}
                    📅 {formatted_date}
                    📊 Оценка: {negative_score:.3f}
                    💬 Комментарии: {negative_comments}/{total_comments} ({negative_percentage:.1f}% нег.)
                    👀 Просмотры: {views} | ↗️ Репосты: {forwards}

                    📄 **{text_preview}**

                    🔗 Открыть в Telegram"""
        
        try:
            # Create inline keyboard with link
            keyboard = [[InlineKeyboardButton("🔗 Открыть в Telegram", url=post_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.app.bot.send_message(
                chat_id=self.monitoring_chat_id,
                text=alert_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters"""
        if not text:
            return ""
        
        # Escape markdown special characters
        special_chars = ['*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, '\\' + char)
        
        return text
    
    async def _show_channels_selection_menu(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Show channels selection menu"""
        available_channels = Config.get_channels_list()
        
        if not available_channels:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Не найдено доступных каналов для выбора."
            )
            return
        
        keyboard = []
        
        # Add toggle buttons for each channel
        for channel in available_channels:
            is_selected = channel in self.selected_channels
            status_icon = "✅" if is_selected else "☐"
            button_text = "{} {}".format(status_icon, channel)
            keyboard.append([InlineKeyboardButton(button_text, callback_data="toggle_channel_{}".format(channel))])
        
        # Add done button
        keyboard.append([InlineKeyboardButton("✅ Готово", callback_data="channels_done")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        selected_text = ", ".join(self.selected_channels) if self.selected_channels else "нет"
        
        text = """
📋 **Выбор каналов для анализа**

Выбранные каналы: `{}`

Нажмите на канал, чтобы включить/отключить его:
        """.format(selected_text)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def _toggle_channel_selection(self, channel: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Toggle channel selection"""
        if channel in self.selected_channels:
            self.selected_channels.remove(channel)
        else:
            self.selected_channels.append(channel)
        
        # Update the message with new selection
        await self._show_channels_selection_menu(chat_id, context)
    
    async def _finish_channel_selection(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Finish channel selection"""
        if not self.selected_channels:
            await context.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Необходимо выбрать хотя бы один канал для анализа."
            )
            return
        
        selected_text = ", ".join(self.selected_channels)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ **Каналы обновлены!**\n\nВыбранные каналы: `{}`\n\nТеперь вы можете запустить анализ.".format(selected_text),
            parse_mode=ParseMode.MARKDOWN
        )
    
    def run(self):
        """Start the bot"""
        logger.info("Анализ негативных постов")
        self.app.run_polling()

def main():
    """Main function"""
    bot_token = os.getenv('BOT_TOKEN')
    if not bot_token:
        print("❌ Переменная окружения BOT_TOKEN не установлена")
        print("Добавьте BOT_TOKEN=your_bot_token в .env файл")
        return
    
    bot = NegativePostsBot(bot_token)
    bot.run()

if __name__ == "__main__":
    main()
