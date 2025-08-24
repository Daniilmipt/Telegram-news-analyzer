import json
import os
import re
from typing import List, Dict
from datetime import datetime
from config import Config
from logging_config import setup_logger

logger = setup_logger(__name__)

def clean_text_preview(text: str, max_length: int = 200) -> str:
    """Очищаем и форматируем текст, удаляя переносы строк и нормализуя пробелы"""
    if not text:
        return ""
    
    clean_text = text.replace('\n', ' ').replace('\r', ' ').strip()
    clean_text = re.sub(r'\s+', ' ', clean_text)
    return clean_text[:max_length] + '...' if len(clean_text) > max_length else clean_text


class ReportGenerator:
    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or Config.OUTPUT_DIR
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_multichannel_negative_posts_report(self, messages: List[Dict], max_posts: int = 100, output_dir: str = None) -> Dict:
        """
        Генерация отчета для негативных постов, сгруппированных по каналам.
        
        Args:
            messages: Список аназированных сообщений с данными о настроении (включая информацию о канале)
            max_posts: Максимальное количество постов на канал
            output_dir: Пользовательская директория вывода (опционально)
            
        Returns:
            Словарь с путями к сгенерированным файлам и статистикой по каналам
        """
        logger.info(f"Generating report for negative posts, grouped by channels. Maximum number of posts per channel: {max_posts}")
        
        channels_data = {}
        total_messages = 0
        total_negative = 0
        
        for msg in messages:
            channel = msg.get('channel', '@unknown')
            
            if channel not in channels_data:
                channels_data[channel] = {
                    'channel_title': msg.get('channel_title', channel),
                    'messages': [],
                    'negative_posts': []
                }
            
            channels_data[channel]['messages'].append(msg)
            total_messages += 1
            
            if msg.get('is_negative', False):
                total_negative += 1
                
                # Форматируем сообщение для отчета
                comments = msg.get('comments', [])
                total_comments = len(comments)
                negative_comments = sum(1 for c in comments if c.get('is_negative', False))
                negative_comment_percentage = (negative_comments / total_comments * 100) if total_comments > 0 else 0
                
                post_date = msg.get('date')
                if hasattr(post_date, 'strftime'):
                    formatted_date = post_date.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    formatted_date = str(post_date)
                
                post_data = {
                    'id': msg.get('id'),
                    'date': formatted_date,
                    'text': msg.get('text', ''),
                    'negative_score': round(msg.get('sentiment', {}).get('negative', 0), 4),
                    'total_comments': total_comments,
                    'negative_comments': negative_comments,
                    'negative_comment_percentage': round(negative_comment_percentage, 2),
                    'views': msg.get('views', 0),
                    'forwards': msg.get('forwards', 0),
                    'replies': msg.get('replies', 0),
                    'channel': channel,
                    'channel_title': msg.get('channel_title', channel)
                }
                
                channels_data[channel]['negative_posts'].append(post_data)
        
        # Сортируем негативные посты по оценке в каждом канале и ограничиваем количество
        for channel_info in channels_data.values():
            channel_info['negative_posts'].sort(key=lambda x: x['negative_score'], reverse=True)
            channel_info['negative_posts'] = channel_info['negative_posts'][:max_posts]
        
        if output_dir is None:
            report_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join(self.output_dir, f"multichannel_negative_posts_{report_timestamp}")
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Генерируем JSON отчет с многоканальной структурой
        json_data = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_channels': len(channels_data),
                'total_messages': total_messages,
                'total_negative': total_negative,
                'negative_percentage': round((total_negative / total_messages * 100) if total_messages > 0 else 0, 1)
            },
            'channels': {}
        }
        
        # Добавляем данные канала в JSON
        for channel, channel_info in channels_data.items():
            negative_count = len(channel_info['negative_posts'])
            total_count = len(channel_info['messages'])
            json_data['channels'][channel] = {
                'channel_title': channel_info['channel_title'],
                'total_messages': total_count,
                'negative_posts_count': negative_count,
                'negative_percentage': round((negative_count / total_count * 100) if total_count > 0 else 0, 1),
                'negative_posts': channel_info['negative_posts']
            }
        
        json_path = os.path.join(output_dir, "multichannel_negative_posts.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        # Генерируем HTML отчет
        html_path = os.path.join(output_dir, "multichannel_negative_posts.html")
        html_content = self._create_multichannel_html_report(channels_data, total_messages, total_negative)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        result = {
            'output_dir': output_dir,
            'html_path': html_path,
            'posts_count': total_negative
        }
        
        # Добавляем данные канала в результат и исправляем имена ключей для совместимости
        result.update({
            'channels_data': channels_data,
            'total_messages': total_messages,
            'total_negative': total_negative,
            'html_file': result.get('html_path'),
        })
        
        return result
        
    def _create_html_report(self, negative_posts: List[Dict]) -> str:
        """Создаем простой HTML шаблон для отчета о негативных постах"""
        
        # Получаем имя канала из конфига для генерации ссылки
        channel_username = Config.CHANNEL_USERNAME.replace('@', '') if Config.CHANNEL_USERNAME.startswith('@') else Config.CHANNEL_USERNAME
        
        html = f"""<!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Топ {len(negative_posts)} негативных постов</title>
            <style>
        body {{ 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background-color: #f8f9fa; 
            line-height: 1.6;
        }}
        .container {{ 
            max-width: 1200px; 
            margin: 0 auto; 
            background-color: white; 
            padding: 20px; 
            border-radius: 8px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }}
        h1 {{ 
            color: #dc3545; 
            text-align: center; 
            margin-bottom: 30px; 
            border-bottom: 3px solid #dc3545;
            padding-bottom: 10px;
        }}
        .stats {{ 
            background-color: #f8f9fa; 
            padding: 15px; 
            border-radius: 5px; 
            margin-bottom: 20px; 
            text-align: center;
        }}
        .post {{ 
            border: 1px solid #dee2e6; 
            border-radius: 8px; 
            margin-bottom: 20px; 
            padding: 20px; 
            background-color: #fff;
        }}
        .post-header {{ 
            display: flex; 
            justify-content: space-between; 
            align-items: center; 
            margin-bottom: 15px; 
            padding-bottom: 10px;
            border-bottom: 1px solid #e9ecef;
        }}
        .post-id {{ 
            font-weight: bold; 
            color: #007bff; 
            font-size: 1.1em;
        }}
        .post-link {{ 
            background-color: #007bff; 
            color: white; 
            padding: 8px 15px; 
            text-decoration: none; 
            border-radius: 5px; 
            font-size: 0.9em;
        }}
        .post-link:hover {{ 
            background-color: #0056b3; 
            text-decoration: none;
            color: white;
        }}
        .post-content {{ 
            margin: 15px 0; 
            padding: 15px; 
            background-color: #f8f9fa; 
            border-left: 4px solid #dc3545; 
            border-radius: 0 5px 5px 0;
        }}
        .post-metrics {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); 
            gap: 15px; 
            margin-top: 15px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 5px;
        }}
        .metric {{ 
            text-align: center; 
            padding: 10px;
            background-color: white;
            border-radius: 5px;
        }}
        .metric-value {{ 
            font-size: 1.4em; 
            font-weight: bold; 
            color: #dc3545; 
        }}
        .metric-label {{ 
            color: #6c757d; 
            font-size: 0.9em; 
            margin-top: 5px;
        }}
        .timestamp {{ 
            text-align: center; 
            color: #6c757d; 
            margin-top: 30px; 
            padding-top: 20px;
            border-top: 1px solid #e9ecef;
        }}
            </style>
        </head>
        <body>
            <div class="container">
        <h1>🔥 Топ {len(negative_posts)} негативных постов</h1>
        
        <div class="stats">
            <h3>📊 Статистика отчета</h3>
            <p>Всего негативных постов найдено: <strong>{len(negative_posts)}</strong></p>
            <p>Отчет создан: <strong>{datetime.now().strftime('%Y-%m-%d в %H:%M:%S')}</strong></p>
        </div>
"""
        
        if not negative_posts:
            html += """
        <div style="text-align: center; color: #6c757d; padding: 40px;">
            <h3>🎉 Отличные новости!</h3>
            <p>Негативных постов не найдено. Все посты имеют нейтральное или позитивное настроение.</p>
        </div>
            """
        else:
            for i, post in enumerate(negative_posts, 1):
                # Format date
                formatted_date = post['date']
                
                # Generate Telegram link
                post_link = f"https://t.me/{channel_username}/{post['id']}"
                
                # Clean and truncate long text
                text_preview = clean_text_preview(post['text'], 500)
                
                html += f"""
        <div class="post">
            <div class="post-header">
                <div class="post-id">#{i} | Post ID: {post['id']} | 📅 {formatted_date}</div>
                <a href="{post_link}" target="_blank" class="post-link">🔗 Открыть в Telegram</a>
            </div>
            
            <div class="post-content">
                <p>{text_preview}</p>
            </div>
            
            <div class="post-metrics">
                <div class="metric">
                    <div class="metric-value">{post['negative_score']:.3f}</div>
                    <div class="metric-label">Негативная оценка</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{post['total_comments']}</div>
                    <div class="metric-label">Всего комментариев</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{post['negative_comments']}</div>
                    <div class="metric-label">Негативных комментариев</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{post['negative_comment_percentage']:.1f}%</div>
                    <div class="metric-label">% негативных комментариев</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{post['views']}</div>
                    <div class="metric-label">👀 Просмотры</div>
                </div>
                <div class="metric">
                    <div class="metric-value">{post['forwards']}</div>
                    <div class="metric-label">↗️ Пересылки</div>
                </div>
            </div>
        </div>
                """
        
        html += f"""
                <div class="timestamp">
            Отчет создан системой анализа настроений Telegram новостей<br>
            {datetime.now().strftime('%Y-%m-%d в %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _create_multichannel_html_report(self, channels_data: Dict, total_messages: int, total_negative: int) -> str:
        """Создаем HTML шаблон для отчета о негативных постах, сгруппированных по каналам, соответствующий стилю Telegram"""
        
        negative_percentage = round((total_negative / total_messages * 100) if total_messages > 0 else 0, 1)
        
        html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📊 Данные анализа</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            margin: 0; 
            padding: 20px; 
            background-color: #1c1c1e;
            color: #ffffff;
            line-height: 1.4;
        }}
        .container {{ 
            max-width: 800px; 
            margin: 0 auto; 
            background-color: #2c2c2e;
            border-radius: 12px; 
            overflow: hidden;
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
        }}
        .header {{ 
            background-color: #0a84ff;
            color: white; 
            padding: 20px; 
            text-align: center;
        }}
        .header h1 {{ 
            margin: 0; 
            font-size: 1.5em; 
            font-weight: 600;
        }}
        .metadata {{ 
            padding: 20px;
            background-color: #3a3a3c;
            border-bottom: 1px solid #48484a;
        }}
        .metadata h2 {{
            margin: 0 0 15px 0;
            font-size: 1.2em;
            font-weight: 600;
        }}
        .metadata-item {{
            margin: 8px 0;
            font-size: 0.95em;
            display: flex;
            align-items: center;
        }}
        .metadata-item::before {{
            content: "•";
            color: #0a84ff;
            margin-right: 8px;
            font-weight: bold;
        }}
        .channel-section {{
            border-bottom: 1px solid #48484a;
        }}
        .channel-header {{
            background-color: #3a3a3c;
            padding: 15px 20px;
            font-weight: 600;
            font-size: 1.1em;
            border-bottom: 1px solid #48484a;
        }}
        .channel-title {{
            color: #0a84ff;
        }}
        .posts-header {{
            background-color: #2c2c2e;
            padding: 15px 20px;
            font-weight: 600;
            color: #ffffff;
            border-bottom: 1px solid #48484a;
        }}
        .post {{
            padding: 20px;
            border-bottom: 1px solid #48484a;
            background-color: #2c2c2e;
        }}
        .post:last-child {{
            border-bottom: none;
        }}
        .post-header {{
            margin-bottom: 12px;
        }}
        .post-id {{
            font-weight: 600;
            font-size: 1.1em;
            color: #ffffff;
            margin-bottom: 8px;
        }}
        .post-date {{
            color: #98989a;
            font-size: 0.9em;
            margin-bottom: 8px;
        }}
        .post-metrics {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin: 12px 0;
            font-size: 0.9em;
        }}
        .metric {{
            color: #98989a;
        }}
        .metric.score {{
            color: #ff453a;
            font-weight: 600;
        }}
        .post-content {{
            background-color: #3a3a3c;
            padding: 15px;
            border-radius: 8px;
            margin: 12px 0;
            border-left: 3px solid #0a84ff;
        }}
        .post-link {{
            display: inline-block;
            background-color: #0a84ff;
            color: white;
            padding: 8px 16px;
            text-decoration: none;
            border-radius: 8px;
            font-size: 0.9em;
            margin-top: 12px;
            transition: background-color 0.2s;
        }}
        .post-link:hover {{
            background-color: #0056b3;
            color: white;
            text-decoration: none;
        }}
        .timestamp {{
            text-align: center;
            padding: 20px;
            color: #98989a;
            font-size: 0.85em;
            background-color: #1c1c1e;
        }}
        .no-posts {{
            padding: 40px 20px;
            text-align: center;
            color: #98989a;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Данные анализа</h1>
        </div>
        
        <div class="metadata">
            <h2>Метаданные:</h2>
            <div class="metadata-item">Проанализировано постов: {total_messages}</div>
            <div class="metadata-item">Найдено негативных постов: {total_negative}</div>
        </div>
"""
        
        if not channels_data or total_negative == 0:
            html += """
        <div class="no-posts">
            <h3>🎉 Отличные новости!</h3>
            <p>Негативных постов не найдено. Все посты имеют нейтральное или позитивное настроение.</p>
        </div>
            """
        else:
            # Группируем по каналам
            for channel, channel_info in channels_data.items():
                if not channel_info['negative_posts']:
                    continue
                    
                channel_title = channel_info.get('channel_title', channel)
                
                html += f"""
        <div class="channel-section">
            <div class="channel-header">
                <span class="channel-title">Канал: {channel_title}</span>
            </div>
            <div class="posts-header">
                Топ негативных постов:
            </div>
"""
                
                # Добавляем посты для этого канала
                for i, post in enumerate(channel_info['negative_posts'], 1):
                    # Форматируем дату
                    formatted_date = post['date']
                    
                    # Generate Telegram link
                    channel_username = channel.replace('@', '') if channel.startswith('@') else channel
                    post_link = f"https://t.me/{channel_username}/{post['id']}"
                    
                    # Очищаем и обрезаем длинный текст для предварительного просмотра
                    text_preview = clean_text_preview(post['text'], 200)
                    
                    # Рассчитываем процент отображения
                    comment_percentage = f"{post['negative_comment_percentage']:.1f}%" if post['total_comments'] > 0 else "0.0%"
                    
                    html += f"""
            <div class="post">
                <div class="post-header">
                    <div class="post-id">{i}. Пост ID {post['id']}</div>
                    <div class="post-date">🗓 {formatted_date}</div>
                    <div class="post-metrics">
                        <span class="metric score">📊 Оценка: {post['negative_score']:.3f}</span>
                        <span class="metric">💬 Комментарии: {post['negative_comments']}/{post['total_comments']} ({comment_percentage} нег.)</span>
                        <span class="metric">👀 Просмотры: {post['views']} | ↗️ Перепосты: {post['forwards']}</span>
                    </div>
                </div>
                <div class="post-content">
                    📄 {text_preview}
                </div>
                <a href="{post_link}" target="_blank" class="post-link">🔗 Открыть в Telegram</a>
            </div>
"""
                
                html += """
        </div>
"""
        
        html += f"""
        <div class="timestamp">
            Отчет создан системой анализа настроений Telegram новостей<br>
            {datetime.now().strftime('%Y-%m-%d в %H:%M:%S')}
        </div>
    </div>
</body>
</html>
        """
        
        return html 