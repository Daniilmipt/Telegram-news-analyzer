import re
import logging
from typing import List, Dict, Tuple
from textblob import TextBlob
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
from config import Config
from logging_config import setup_logger

# Configure logging with file output
logger = setup_logger(__name__)

class SentimentAnalyzer:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.sentiment_pipeline = None
        self.initialize_models()
    
    def initialize_models(self):
        """Initialize sentiment analysis models"""
        try:
            # Использование многоязычной модели настроений для лучших результатов
            model_name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
            
            # Принудительно используем slow tokenizer для избежания ошибок конвертации
            tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=False)
            model = AutoModelForSequenceClassification.from_pretrained(model_name)
            
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=model,
                tokenizer=tokenizer,
                device=0 if self.device == "cuda" else -1,
                return_all_scores=True
            )
            logger.info(f"Initialized sentiment model on {self.device}")
        except Exception as e:
            logger.warning(f"Failed to load transformer model: {e}")
            logger.info("Falling back to TextBlob for sentiment analysis")
            self.sentiment_pipeline = None
    
    def clean_text(self, text: str) -> str:
        """Очистка текста для анализа"""
        if not text:
            return ""
        
        # Удаление URL, упоминаний, хештегов
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        text = re.sub(r'@\w+', '', text)
        text = re.sub(r'#\w+', '', text)
        
        # Удаление лишних пробелов
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def analyze_sentiment_transformer(self, text: str) -> Dict[str, float]:
        """Анализ настроений с использованием трансформер модели"""
        try:
            results = self.sentiment_pipeline(text)[0]

            # Преобразование в стандартизованный формат
            sentiment_scores = {'positive': 0.0, 'negative': 0.0, 'neutral': 0.0}
            
            for result in results:
                label = result['label'].lower()
                score = result['score']
                
                if 'positive' in label or label == 'pos':
                    sentiment_scores['positive'] = score
                elif 'negative' in label or label == 'neg':
                    sentiment_scores['negative'] = score
                else:
                    sentiment_scores['neutral'] = score
            
            return sentiment_scores
            
        except Exception as e:
            logger.error(f"Ошибка в анализе настроений трансформером: {e}")
            return self.analyze_sentiment_textblob(text)
    
    def analyze_sentiment_textblob(self, text: str) -> Dict[str, float]:
        """Резервный анализ настроений с использованием TextBlob"""
        try:
            blob = TextBlob(text)
            polarity = blob.sentiment.polarity
            
            # Преобразование полярности в оценки позитивного/негативного/нейтрального
            if polarity > Config.SENTIMENT_THRESHOLD:
                return {'positive': abs(polarity), 'negative': 0.0, 'neutral': 1 - abs(polarity)}
            elif polarity < -Config.SENTIMENT_THRESHOLD:
                return {'positive': 0.0, 'negative': abs(polarity), 'neutral': 1 - abs(polarity)}
            else:
                return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
                
        except Exception as e:
            logger.error(f"Error in TextBlob sentiment analysis: {e}")
            return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
    
    def analyze_sentiment(self, text: str) -> Dict[str, float]:
        """Основная функция анализа настроений"""
        cleaned_text = self.clean_text(text)

        if not cleaned_text:
            return {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
        
        if self.sentiment_pipeline:
            return self.analyze_sentiment_transformer(cleaned_text)
        else:
            return self.analyze_sentiment_textblob(cleaned_text)
    
    def get_dominant_sentiment(self, sentiment_scores: Dict[str, float]) -> str:
        """Получение доминирующего настроения из оценок"""
        return max(sentiment_scores.items(), key=lambda x: x[1])[0]
    
    def is_negative(self, sentiment_scores: Dict[str, float]) -> bool:
        """Проверка, является ли настроение преимущественно негативным"""
        return sentiment_scores['negative'] > max(sentiment_scores['positive'], sentiment_scores['neutral'])
    
    def determine_post_sentiment_from_comments(self, comments: List[Dict]) -> Tuple[Dict[str, float], str, bool]:
        """
        Определение настроения поста на основе анализа комментариев.
        Если более NEGATIVE_COMMENT_THRESHOLD% комментариев негативные, пост считается негативным.
        
        Returns:
            Tuple[sentiment_scores, dominant_sentiment, is_negative]
        """
        if not comments:
            # Если комментариев нет, возвращаем нейтральное настроение
            neutral_sentiment = {'positive': 0.0, 'negative': 0.0, 'neutral': 1.0}
            return neutral_sentiment, 'neutral', False
        
        # Анализируем настроения всех комментариев
        comment_sentiments = []
        negative_count = 0
        total_comments = len(comments)
        
        # Собираем данные о настроениях комментариев
        positive_scores = []
        negative_scores = []
        neutral_scores = []
        
        for comment in comments:
            comment_sentiment = self.analyze_sentiment(comment['text'])
            comment_sentiments.append(comment_sentiment)
            
            # Подсчитываем негативные комментарии
            if self.is_negative(comment_sentiment):
                negative_count += 1
            
            # Собираем оценки для усреднения
            positive_scores.append(comment_sentiment['positive'])
            negative_scores.append(comment_sentiment['negative'])
            neutral_scores.append(comment_sentiment['neutral'])
        
        # Вычисляем процент негативных комментариев
        negative_percentage = negative_count / total_comments
        
        # Определяем общее настроение поста на основе комментариев
        if negative_percentage >= Config.NEGATIVE_COMMENT_THRESHOLD:
            # Если много негативных комментариев, пост считается негативным
            # Усиливаем негативную оценку пропорционально проценту негативных комментариев
            post_sentiment = {
                'positive': sum(positive_scores) / total_comments * (1 - negative_percentage),
                'negative': sum(negative_scores) / total_comments + negative_percentage * 0.5,
                'neutral': sum(neutral_scores) / total_comments * (1 - negative_percentage * 0.5)
            }
            
            # Нормализуем оценки, чтобы сумма была 1.0
            total_score = sum(post_sentiment.values())
            if total_score > 0:
                post_sentiment = {k: v / total_score for k, v in post_sentiment.items()}
            
            dominant_sentiment = 'negative'
            is_negative = True
        else:
            # Иначе используем усредненные оценки комментариев
            post_sentiment = {
                'positive': sum(positive_scores) / total_comments,
                'negative': sum(negative_scores) / total_comments,
                'neutral': sum(neutral_scores) / total_comments
            }
            
            dominant_sentiment = self.get_dominant_sentiment(post_sentiment)
            is_negative = self.is_negative(post_sentiment)
        
        logger.debug(f"Comments: {total_comments}, negative: {negative_count} ({negative_percentage:.1%}), "
                    f"post sentiment: {dominant_sentiment}")
        
        return post_sentiment, dominant_sentiment, is_negative
    
    def analyze_messages_sentiment(self, messages: List[Dict]) -> List[Dict]:
        """
        Анализ настроений для всех сообщений и их комментариев.
        Настроение поста определяется на основе анализа комментариев.
        """
        analyzed_messages = []
        
        for message in messages:
            # Сначала анализируем комментарии
            analyzed_comments = []
            for comment in message.get('comments', []):
                comment_sentiment = self.analyze_sentiment(comment['text'])
                analyzed_comment = {
                    **comment,
                    'sentiment': comment_sentiment,
                    'dominant_sentiment': self.get_dominant_sentiment(comment_sentiment),
                    'is_negative': self.is_negative(comment_sentiment)
                }
                analyzed_comments.append(analyzed_comment)
            
            # Определяем настроение поста на основе комментариев
            post_sentiment, dominant_sentiment, is_negative = self.determine_post_sentiment_from_comments(
                message.get('comments', [])
            )
            
            analyzed_message = {
                **message,
                'sentiment': post_sentiment,
                'dominant_sentiment': dominant_sentiment,
                'is_negative': is_negative,
                'comments': analyzed_comments,
                # Сохраняем информацию о том, как было определено настроение
                'sentiment_source': 'comments' if analyzed_comments else 'neutral_default'
            }
            
            analyzed_messages.append(analyzed_message)
            
            # Логирование прогресса
            if len(analyzed_messages) % 10 == 0:
                logger.info(f"Analyzed sentiment for {len(analyzed_messages)} messages")
        
        logger.info(f"Completed sentiment analysis for {len(analyzed_messages)} messages")
        return analyzed_messages 