import json
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

logger = LoggingConfig.setup_bot_logging()

def clean_text_preview(text: str, max_length: int = 200) -> str:
    """Очищаем и форматируем текст, удаляя переносы строк и нормализуя пробелы"""
    if not text:
        return ""
    
    clean_text = text.replace('\n', ' ').replace('\r', ' ').strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return clean_text[:max_length] + '...' if len(clean_text) > max_length else clean_text


class NegativePostsBot:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.app = Application.builder().token(bot_token).build()
        
        # Компоненты анализа
        self.sentiment_analyzer = SentimentAnalyzer()
        self.report_generator = ReportGenerator()
        
        # Состояние мониторинга
        self.monitoring_active = False
        self.sent_message_ids: Set[int] = set()
        self.monitoring_chat_id = None
        
        # Последний сгенерированный путь HTML
        self.last_html_path = None
        
        # Выбранные каналы для анализа
        self.selected_channels = Config.get_channels_list()  # Default to all configured channels
        
        # Предотвращение дублирования для всех команд и обратных вызовов
        self.recent_callbacks: Dict[str, float] = {}
        self.recent_commands: Dict[str, float] = {}  # Отслеживаем все команды
        
        # Загружаем отправленные сообщения из файла, если существует
        self._load_sent_messages()
        
        # Настраиваем обработчики
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Настройка обработчиков команд и обратных вызовов"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("analyze", self.analyze_command))
        self.app.add_handler(CommandHandler("monitor", self.monitor_command))
        self.app.add_handler(CommandHandler("stop", self.stop_monitor_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
    
    def _load_sent_messages(self):
        """Загружаем ранее отправленные сообщения из файла"""
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
        """Сохраняем отправленные сообщения в файл"""
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
        """Обработка команды /start"""
        chat_id = update.effective_chat.id
        
        # Предотвращение дублирования команды /start
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
        """Получаем текст справки бота"""
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
        """Обработка команды /help"""
        chat_id = update.effective_chat.id
        
        # Предотвращение дублирования команды /help
        if self._is_duplicate_command(chat_id, "help"):
            return
            
        await update.message.reply_text(self._get_help_text(), parse_mode=ParseMode.MARKDOWN)
    
    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /analyze - отображение меню выбора периода"""
        chat_id = update.effective_chat.id
        
        # Предотвращение дублирования команды /analyze
        if self._is_duplicate_command(chat_id, "analyze"):
            return
            
        await self._show_date_selection_menu(chat_id, context)
    
    async def monitor_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /monitor - запуск реального времени мониторинга"""
        chat_id = update.effective_chat.id
        
        # Предотвращение дублирования команды /monitor
        if self._is_duplicate_command(chat_id, "monitor"):
            return
            
        if self.monitoring_active:
            await update.message.reply_text("🔄 Мониторинг уже активен!")
            return
        
        self.monitoring_active = True
        self.monitoring_chat_id = update.effective_chat.id
        
        # Запланировать задачу мониторинга
        context.job_queue.run_repeating(
            self._monitor_callback,
            interval=300,  # 5 minutes
            first=10,      # Start in 10 seconds
            data=update.effective_chat.id,
            name=f"monitor_{update.effective_chat.id}"
        )
        
        # Получаем список каналов для отображения
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
        """Обработка команды /stop - остановка мониторинга"""
        chat_id = update.effective_chat.id
        
        # Предотвращение дублирования команды /stop
        if self._is_duplicate_command(chat_id, "stop"):
            return
        
        if not self.monitoring_active:
            await update.message.reply_text("❌ Мониторинг не активен")
            return
        
        # Удаляем задачу
        current_jobs = context.job_queue.get_jobs_by_name(f"monitor_{chat_id}")
        for job in current_jobs:
            job.schedule_removal()
        
        self.monitoring_active = False
        self.monitoring_chat_id = None
        
        await update.message.reply_text("⏹️ Мониторинг остановлен")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /status"""
        chat_id = update.effective_chat.id
        
        # Предотвращение дублирования команды /status
        if self._is_duplicate_command(chat_id, "status"):
            return
            
        status_text = f"""
📊 **Статус бота**

**Конфигурация:**
• Порог негативности: {Config.NEGATIVE_COMMENT_THRESHOLD * 100}%

**Мониторинг:**
• Статус: {'🔄 Активен' if self.monitoring_active else '⏹️ Неактивен'}
• Отслеживаемых сообщений: {len(self.sent_message_ids)}
        """
        
        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)
    
    def _is_duplicate_callback(self, callback_key: str, timeout: float = 3.0) -> bool:
        """Проверяем, был ли этот обратный вызов выполнен недавно, чтобы предотвратить дублирование"""
        current_time = time.time()
        
        if callback_key in self.recent_callbacks:
            time_diff = current_time - self.recent_callbacks[callback_key]
            if time_diff < timeout:
                logger.info(f"Ignoring duplicate callback '{callback_key}' (sent {time_diff:.1f}s ago)")
                return True
        
        # Обновляем временную метку и очищаем старые записи
        self.recent_callbacks[callback_key] = current_time
        self.recent_callbacks = {
            key: timestamp for key, timestamp in self.recent_callbacks.items()
            if current_time - timestamp < 10.0
        }
        return False

    def _is_duplicate_command(self, chat_id: int, command: str, timeout: float = 2.0) -> bool:
        """Проверяем, была ли эта команда выполнена недавно, чтобы предотвратить дублирование"""
        current_time = time.time()
        command_key = f"{chat_id}_{command}"
        
        if command_key in self.recent_commands:
            time_diff = current_time - self.recent_commands[command_key]
            if time_diff < timeout:
                logger.info(f"Ignoring duplicate command '{command}' from {chat_id} (sent {time_diff:.1f}s ago)")
                return True
        
        # Обновляем временную метку и очищаем старые записи
        self.recent_commands[command_key] = current_time
        self.recent_commands = {
            key: timestamp for key, timestamp in self.recent_commands.items()
            if current_time - timestamp < 10.0
        }
        return False

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий на кнопки"""
        query = update.callback_query
        
        # Отвечаем на обратный вызов немедленно, чтобы избежать таймаута
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Failed to answer callback query (query may be too old): {e}")
        
        # Создаем уникальный ключ обратного вызова
        chat_id = query.message.chat_id
        callback_key = f"{chat_id}_{query.data}"
        
        # Проверяем на дубликат обратного вызова
        if self._is_duplicate_callback(callback_key):
            return
        
        if query.data == "analyze_now":
            # Отображаем меню выбора периода
            await self._show_date_selection_menu(query.message.chat_id, context)
        
        elif query.data == "select_channels":
            # Отображаем меню выбора каналов
            await self._show_channels_selection_menu(query.message.chat_id, context)
        
        elif query.data.startswith("toggle_channel_"):
            # Переключаем выбор канала
            channel = query.data.replace("toggle_channel_", "")
            await self._toggle_channel_selection(channel, query.message.chat_id, context)
        
        elif query.data == "channels_done":
            # Завершаем выбор канала
            await self._finish_channel_selection(query.message.chat_id, context)
        
        elif query.data == "start_monitor":
            if self.monitoring_active:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="🔄 Мониторинг уже активен!"
                )
                return
            
            # Отправляем сообщение о прогрессе
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="🔄 Запускаем мониторинг..."
            )
            
            self.monitoring_active = True
            self.monitoring_chat_id = query.message.chat_id
            
            # Запланировать задачу мониторинга
            context.job_queue.run_repeating(
                self._monitor_callback,
                interval=300,  # 5 minutes
                first=10,      # Start in 10 seconds
                data=query.message.chat_id,
                name=f"monitor_{query.message.chat_id}"
            )
            
            # Получаем список каналов для отображения
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
            # Отправляем справку как новое сообщение
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=self._get_help_text(),
                parse_mode=ParseMode.MARKDOWN
            )
            
        elif query.data == "get_html_report":
            try:
                # Используем сохраненный путь HTML-файла
                if hasattr(self, 'last_html_path') and self.last_html_path:
                    html_path = self.last_html_path
                    
                    # Отправляем HTML-файл только один раз
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
        
        # Обработка быстрого выбора даты
        elif query.data.startswith("analyze_"):
            date_option = query.data.replace("analyze_", "")
            await self._handle_date_selection(query.message.chat_id, context, date_option)
        
        # Обработка взаимодействия с календарем
        elif query.data.startswith("cal_"):
            await self._handle_calendar_callback(query, context)
    
    async def _show_date_selection_menu(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Отображаем меню выбора даты с быстрыми опциями"""
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
        """Обработка выбора даты и запуск анализа"""
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
            # Отображаем календарь для выбора даты
            await self._show_custom_date_selection(chat_id, context)
            return
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Некорректный период. Попробуйте еще раз"
            )
            return
        
        # Запуск анализа с выбранным диапазоном дат
        await self._run_analysis_with_dates(chat_id, context, start_date, end_date, period_name)
    
    async def _show_custom_date_selection(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Отображаем интерфейс выбора даты"""
        # Инициализируем состояние выбора даты для этого пользователя
        if not hasattr(self, 'date_selection_state'):
            self.date_selection_state = {}
        
        self.date_selection_state[chat_id] = {
            'stage': 'start_date',
            'start_date': None,
            'end_date': None,
            'current_month': datetime.now().replace(day=1),
        }
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="📅 **Выберите период**",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Отображаем календарь для выбора даты
        await self._show_calendar(chat_id, context, self.date_selection_state[chat_id]['current_month'])
    
    def _create_calendar_keyboard(self, year: int, month: int) -> InlineKeyboardMarkup:
        """Создаем календарь для выбора даты"""
        import calendar
        
        # Создаем календарь для выбранного месяца
        cal = calendar.monthcalendar(year, month)
        
        month_names = [
            "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
            "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
        ]
        
        keyboard = []
        
        # Заголовок с месяцем/годом и навигацией
        keyboard.append([
            InlineKeyboardButton("◀", callback_data=f"cal_prev_{year}_{month}"),
            InlineKeyboardButton(f"{month_names[month-1]} {year}", callback_data="cal_ignore"),
            InlineKeyboardButton("▶", callback_data=f"cal_next_{year}_{month}")
        ])
        
        days_header = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        keyboard.append([InlineKeyboardButton(day, callback_data="cal_ignore") for day in days_header])
        
        # Дни недели
        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    # Пустая ячейка
                    row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
                else:
                    # Кнопка даты
                    today = datetime.now()
                    button_date = datetime(year, month, day)
                    
                    # Не разрешаем будущие даты
                    if button_date > today:
                        row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
                    else:
                        row.append(InlineKeyboardButton(str(day), callback_data=f"cal_date_{year}_{month}_{day}"))
            keyboard.append(row)
        
        # Кнопка отмены
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cal_cancel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def _show_calendar(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, date: datetime):
        """Отображаем календарь для выбора даты"""
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
        """Обработка нажатий на кнопки календаря"""
        chat_id = query.message.chat_id
        data = query.data
        
        # Инициализируем сессию, если необходимо
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
            # Отмена выбора даты
            del self.date_selection_state[chat_id]
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Выбор периода отменен"
            )
            return
        
        elif data == "cal_ignore":
            # Ничего не делаем для кнопок игнорирования
            return
        
        elif data.startswith("cal_prev_") or data.startswith("cal_next_"):
            # Навигация между месяцами
            parts = data.split("_")
            current_year = int(parts[2])
            current_month = int(parts[3])
            
            if data.startswith("cal_prev_"):
                # Предыдущий месяц
                if current_month == 1:
                    new_month = 12
                    new_year = current_year - 1
                else:
                    new_month = current_month - 1
                    new_year = current_year
            else:
                # Следующий месяц
                if current_month == 12:
                    new_month = 1
                    new_year = current_year + 1
                else:
                    new_month = current_month + 1
                    new_year = current_year
            
            # Обновляем текущий месяц
            state['current_month'] = datetime(new_year, new_month, 1)
            
            # Обновляем календарь
            keyboard = self._create_calendar_keyboard(new_year, new_month)
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=query.message.message_id,
                reply_markup=keyboard
            )
        
        elif data.startswith("cal_date_"):
            # Дата выбрана
            parts = data.split("_")
            selected_year = int(parts[2])
            selected_month = int(parts[3])
            selected_day = int(parts[4])
            
            selected_date = datetime(selected_year, selected_month, selected_day)
            
            if state['stage'] == 'start_date':
                # Начальная дата выбрана, теперь выбираем конечную дату
                state['start_date'] = selected_date
                state['stage'] = 'end_date'
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=query.message.message_id,
                    text=f"Шаг 2: Выберите конечную дату",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Отображаем календарь для выбора конечной даты
                await self._show_calendar(chat_id, context, state['current_month'])
                
            elif state['stage'] == 'end_date':
                # Конечная дата выбрана, валидируем и запускаем анализ
                state['end_date'] = selected_date
                
                start_date = state['start_date']
                end_date = state['end_date']
                
                # Валидируем даты
                if end_date < start_date:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="❌ Конечная дата не может быть раньше начальной",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    await self._show_calendar(chat_id, context, state['current_month'])
                    return
                
                # Очищаем состояние
                del self.date_selection_state[chat_id]
                
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"✅ **Период выбран:**\n\n"
                         f"📅 С: {start_date.strftime('%d.%m.%Y')}\n"
                         f"📅 По: {end_date.strftime('%d.%m.%Y')}\n\n"
                         f"🔄 Запускаем анализ...",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                # Рассчитываем название периода
                days_diff = (end_date - start_date).days + 1
                if days_diff == 1:
                    period_name = f"{start_date.strftime('%d.%m.%Y')}"
                else:
                    period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
                
                # Запускаем анализ
                await self._run_analysis_with_dates(chat_id, context, start_date, end_date, period_name)
    
    async def _run_analysis_with_dates(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE, 
                                     start_date: datetime, end_date: datetime, period_name: str):
        """Запускаем анализ для определенного диапазона дат"""
        
        # Дополнительная защита от дублирования для анализа
        analysis_key = f"analysis_{chat_id}"
        if self._is_duplicate_callback(analysis_key, timeout=30.0):  # 30 секунд для анализа
            logger.info(f"Analysis already running for chat {chat_id}, ignoring duplicate request")
            return
            
        try:
            # Отправляем сообщение о прогрессе
            progress_msg = await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔄 **Анализ за {period_name}...**",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Получаем сообщения за выбранный период из выбранных каналов
            async with TelegramNewsClient() as client:
                await client.connect(self.selected_channels)
                messages_by_channel = await client.get_recent_messages_from_all_channels(
                    limit=Config.MAX_MESSAGES,
                    days_back=(end_date - start_date).days + 1
                )
            
            # Фильтруем сообщения по диапазону дат и объединяем все каналы
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
            
            # Отображаем прогресс по каналам
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
            
            # Анализируем сообщения из всех каналов
            all_messages = self.sentiment_analyzer.analyze_messages_sentiment(all_messages)
            
            # Генерируем многоканальный отчет
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
            
            # Генерируем многоканальный отчет
            report_result = self.report_generator.generate_multichannel_negative_posts_report(all_messages)
            
            # Завершаем анализ
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
            
            # Сохраняем путь HTML-файла и создаем кнопку
            self.last_html_path = report_result.get('html_file', report_result.get('html_path'))
            
            keyboard = [[InlineKeyboardButton("📊 Получить HTML-отчет", callback_data="get_html_report")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Генерируем подробную сводку по каналам
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
            """.format(
                "\n".join(channels_summary),
                os.path.basename(report_result.get('html_file', report_result.get('html_path', 'unknown'))),
            )
            
            # Отправляем подробную сводку с кнопкой HTML
            await context.bot.send_message(
                chat_id=chat_id,
                text=summary_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Отправляем форматированные данные JSON как текстовое сообщение
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
        """Мониторинг"""
        if not self.monitoring_active or not self.monitoring_chat_id:
            return
        
        try:
            logger.info("Running monitoring check...")
            
            # Получаем только последние сообщения из всех каналов (последние 10 минут)
            async with TelegramNewsClient() as client:
                all_messages_by_channel = await client.get_recent_messages_from_all_channels(limit=5, days_back=1)
                
                # Преобразуем сообщения из всех каналов в один список
                messages = []
                for channel, channel_messages in all_messages_by_channel.items():
                    messages.extend(channel_messages)
            
            # Фильтруем сообщения из последних 60 минут, чтобы поймать новые
            now = datetime.now()
            cutoff_time = now - timedelta(minutes=60)
            print(f"Cutoff time: {cutoff_time}")
            
            recent_messages = []
            for msg in messages:
                print(f"Message ID: {msg.get('id', 'Unknown')}")
                msg_date = msg.get('date')
                if hasattr(msg_date, 'replace'):
                    # Удаляем информацию о часовом поясе
                    msg_date = msg_date.replace(tzinfo=None)

                    print(f"Message date: {msg_date}")
                    if msg_date >= cutoff_time:
                        recent_messages.append(msg)
            
            if not recent_messages:
                logger.info("No recent messages found")
                return
            
            # Анализируем последние сообщения
            analyzed_messages = self.sentiment_analyzer.analyze_messages_sentiment(recent_messages)

            # Находим новые негативные сообщения
            new_negative_messages = []
            for msg in analyzed_messages:
                if msg.get('is_negative', False) and msg['id'] not in self.sent_message_ids:
                    new_negative_messages.append(msg)
                    self.sent_message_ids.add(msg['id'])
            
            if new_negative_messages:
                # Сохраняем обновленные отправленные сообщения
                self._save_sent_messages()
                
                # Отправляем уведомления о новых негативных постах
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
        """Отправляем длинное сообщение, разделяя его, если необходимо, чтобы соблюсти лимит в 4096 символов Telegram"""
        MAX_MESSAGE_LENGTH = 4000  # Оставляем небольшой буфер для безопасности
        
        if len(message) <= MAX_MESSAGE_LENGTH:
            # Сообщение помещается в один кусок
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
        else:
            # Нужно разделить сообщение
            chunks = []
            lines = message.split('\n')
            current_chunk = ""
            
            for line in lines:
                # Проверяем, не превышает ли добавление этой строки лимит
                if len(current_chunk) + len(line) + 1 > MAX_MESSAGE_LENGTH:
                    # Сохраняем текущий кусок и начинаем новый
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    # Добавляем строку в текущий кусок
                    if current_chunk:
                        current_chunk += "\n" + line
                    else:
                        current_chunk = line
            
            # Добавляем последний кусок
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # Отправляем все куски
            for i, chunk in enumerate(chunks):
                if i == 0:
                    # Первый кусок - отправляем как есть
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )
                else:
                    # Последующие куски - добавляем индикатор продолжения
                    await self.app.bot.send_message(
                        chat_id=chat_id,
                        text=f"📄 Продолжение...\n\n{chunk}",
                        parse_mode=ParseMode.MARKDOWN,
                        disable_web_page_preview=True
                    )

    async def _send_formatted_json_data(self, chat_id: int, json_path: str):
        """Отправляем форматированные данные JSON как читаемое сообщение Telegram"""
        try:
            # Загружаем данные JSON
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Обрабатываем оба формата данных одноканальных и многоканальных
            if 'channels' in data:  # Multi-channel format
                metadata = data.get('metadata', {})
                channels_data = data.get('channels', {})
                
                # Создаем полное сообщение с всем содержимым
                complete_message = "📊 Данные анализа\n\n"
                complete_message += "Метаданные:\n"
                complete_message += "• Проанализировано постов: {}\n".format(metadata.get('total_messages', 0))
                complete_message += "• Найдено негативных постов: {}\n".format(metadata.get('total_negative', 0))
                
                # Добавляем все посты, сгруппированные по каналам
                total_negative_posts = sum(len(channel_data.get('negative_posts', [])) for channel_data in channels_data.values())
                if total_negative_posts > 0:
                    complete_message += "\n\nТоп негативных постов:\n"
                    
                    for channel, channel_data in channels_data.items():
                        negative_posts = channel_data.get('negative_posts', [])
                        if not negative_posts:
                            continue
                            
                        # Добавляем заголовок канала
                        complete_message += f"\n• **Канал: {channel_data.get('channel_title', channel)}**\n"
                        
                        # Добавляем топ негативных постов из этого канала
                        for post_idx, post in enumerate(negative_posts[:3], 1):  # Show top 3 from each channel
                            # Очищаем и форматируем предварительный просмотр текста
                            text_preview = clean_text_preview(post.get('text', ''), 100)  # Короче для совмещенного сообщения
                            
                            post_id = post.get('id', 'N/A')
                            post_date = post.get('date', 'N/A')
                            negative_score = post.get('negative_score', 0)
                            total_comments = post.get('total_comments', 0)
                            negative_comments = post.get('negative_comments', 0)
                            negative_comment_percentage = post.get('negative_comment_percentage', 0)
                            views = post.get('views', 0)
                            forwards = post.get('forwards', 0)
                            
                            # Создаем Telegram-ссылку - извлекаем имя пользователя канала из заголовка канала или используем generic
                            channel_username = post.get('channel', channel)
                            if channel_username.startswith('@'):
                                channel_username = channel_username[1:]
                            
                            post_link = f"https://t.me/{channel_username}/{post_id}" if channel_username else "#"
                            
                            # Форматируем пост в компактном стиле с Telegram-ссылкой
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
                
                # Отправляем полное сообщение как одно, обрабатывая ограничения по длине
                await self._send_long_message(chat_id, complete_message)
                
                return  # Выходим раньше, так как мы отправили все сообщения
            else:  # Формат одноканальных данных
                metadata = data.get('metadata', {})
                negative_posts = data.get('negative_posts', [])
                
                # Создаем полное сообщение с всем содержимым
                complete_message = "📊 Данные анализа\n\n"
                complete_message += "Метаданные:\n"
                complete_message += "• Проанализировано постов: {}\n".format(metadata.get('total_posts_analyzed', 0))
                complete_message += "• Найдено негативных постов: {}\n".format(metadata.get('negative_posts_found', 0))
                complete_message += "• Канал: {}\n".format(metadata.get('channel_username', 'Неизвестно'))
                
                # Добавляем все посты
                if negative_posts:
                    complete_message += "\n\nТоп негативных постов:\n"
                    
                    for i, post in enumerate(negative_posts[:3], 1):
                        # Очищаем и форматируем предварительный просмотр текста
                        text_preview = clean_text_preview(post.get('text', ''), 100)  # Короче для совмещенного сообщения
                        
                        # Форматируем подробную информацию о посте
                        post_id = post.get('id', 'N/A')
                        post_date = post.get('date', 'N/A')
                        negative_score = post.get('negative_score', 0)
                        total_comments = post.get('total_comments', 0)
                        negative_comments = post.get('negative_comments', 0)
                        negative_comment_percentage = post.get('negative_comment_percentage', 0)
                        views = post.get('views', 0)
                        forwards = post.get('forwards', 0)
                        
                        # Создаем Telegram-ссылку
                        channel_username = metadata.get('channel_username', Config.CHANNEL_USERNAME or '')
                        if channel_username.startswith('@'):
                            channel_username = channel_username[1:]
                        
                        post_link = f"https://t.me/{channel_username}/{post_id}" if channel_username else "#"
                        
                        # Форматируем пост в компактном стиле с Telegram-ссылкой
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
                
                # Отправляем полное сообщение как одно, обрабатывая ограничения по длине
                await self._send_long_message(chat_id, complete_message)
                
                return  # Выходим раньше, так как мы отправили все сообщения
            
        except Exception as e:
            logger.error(f"Error sending formatted JSON: {e}")
            # Отправляем исходный JSON-файл
            with open(json_path, 'rb') as f:
                await self.app.bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=os.path.basename(json_path),
                    caption="📄 Данные анализа (ошибка отображения)"
                )
    
    async def _send_negative_post_alert(self, message: dict):
        """Отправляем уведомление о новом негативном посте"""
        if not self.monitoring_chat_id:
            return
        
        # Форматируем дату
        msg_date = message.get('date')
        if hasattr(msg_date, 'strftime'):
            formatted_date = msg_date.strftime('%Y-%m-%d %H:%M')
        else:
            formatted_date = str(msg_date)
        
        # Получаем информацию о настроении
        sentiment_data = message.get('sentiment', {})
        negative_score = sentiment_data.get('negative', 0)
        
        # Получаем информацию о комментариях
        comments = message.get('comments', [])
        total_comments = len(comments)
        negative_comments = sum(1 for c in comments if c.get('is_negative', False))
        negative_percentage = (negative_comments / total_comments * 100) if total_comments > 0 else 0
        
        # Создаем Telegram-ссылку
        channel_username = Config.CHANNEL_USERNAME.replace('@', '') if Config.CHANNEL_USERNAME.startswith('@') else Config.CHANNEL_USERNAME
        post_link = f"https://t.me/{channel_username}/{message['id']}"
        
        # Очищаем и форматируем предварительный просмотр текста
        text_preview = clean_text_preview(message.get('text', ''), 300)
        
        # Получаем просмотры и перепосты
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
            # Создаем inline-клавиатуру с ссылкой
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
    
    async def _show_channels_selection_menu(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Отображаем меню выбора каналов"""
        available_channels = Config.get_channels_list()
        
        if not available_channels:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Не найдено доступных каналов для выбора."
            )
            return
        
        keyboard = []
        
        # Добавляем переключатели для каждого канала
        for channel in available_channels:
            is_selected = channel in self.selected_channels
            status_icon = "✅" if is_selected else "☐"
            button_text = "{} {}".format(status_icon, channel)
            keyboard.append([InlineKeyboardButton(button_text, callback_data="toggle_channel_{}".format(channel))])
        
        # Добавляем кнопку "Готово"
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
        """Переключаем выбор канала"""
        if channel in self.selected_channels:
            self.selected_channels.remove(channel)
        else:
            self.selected_channels.append(channel)
        
        # Обновляем сообщение с новым выбором
        await self._show_channels_selection_menu(chat_id, context)
    
    async def _finish_channel_selection(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        """Завершаем выбор канала"""
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
        logger.info("Negative posts analysis")
        self.app.run_polling()
