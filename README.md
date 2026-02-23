## Telegram News Analyzer

🤖 **Intelligent bot for analyzing negative posts in Telegram channels**

### 📋 Description

Telegram News Analyzer is a powerful tool for monitoring and analyzing sentiment in Telegram channels. The bot uses modern machine learning technologies to detect negative posts based on the analysis of user comments.

### ✨ Key Features

- 🔍 **Sentiment analysis** — automatic detection of negative posts using AI  
- 📊 **Multi-channel monitoring** — simultaneous analysis of multiple channels  
- 📅 **Flexible time ranges** — analysis for today, yesterday, last week, last month, or a custom period  
- 🎯 **Configurable thresholds** — ability to adjust the sensitivity of the analysis  

### 🛠 Technologies

- **Python 3.8+** — main programming language  
- **Telethon** — interaction with the Telegram API  
- **Transformers** — machine learning models for sentiment analysis  
- **PyTorch** — deep learning framework  
- **spaCy & NLTK** — natural language processing  
- **pandas & scikit-learn** — data analysis  
- **python-telegram-bot** — Telegram bot framework  

### 🚀 Installation and Setup

#### 1. Clone the repository

```bash
git clone https://github.com/your-username/Telegram-news-analyzer.git
cd Telegram-news-analyzer
```

#### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows
```

#### 3. Install dependencies

```bash
pip install -r requirements.txt
```

#### 4. Configure environment

Copy the `env_template` file to `.env` and fill in the required parameters:

```bash
cp env_template .env
```

Edit the `.env` file:

```env
# Telegram API Configuration
TELEGRAM_API_ID=your_api_id_here
TELEGRAM_API_HASH=your_api_hash_here
TELEGRAM_PHONE=+1234567890

# Telegram Bot Token
BOT_TOKEN=your_bot_token_here

# Channels to analyze
CHANNELS_LIST=@yourchannel,@anotherchannel,@thirdchannel

# Analysis settings
NEGATIVE_COMMENT_THRESHOLD=0.3
OUTPUT_DIR=output
MAX_MESSAGES=200
```

#### 5. Obtain API keys

##### Telegram API
1. Go to [my.telegram.org](https://my.telegram.org/auth)  
2. Log in to your account  
3. Create a new application  
4. Copy the `API ID` and `API Hash`  

##### Telegram Bot Token
1. Find [@BotFather](https://t.me/BotFather) in Telegram  
2. Send the `/newbot` command  
3. Follow the instructions to create a bot  
4. Copy the generated token  

### 🎯 Usage

#### Run the bot

```bash
python main.py
```

#### Bot commands

- `/start` — start and main menu  
- `/help` — usage help  
- `/analyze` — start post analysis  

#### Interface options

1. **📊 Analyze** — select a period and start analysis  
2. **📋 Select channels** — configure the list of channels to monitor  
3. **ℹ️ Help** — detailed information about the features  

#### Analysis modes

- 📅 **Today** — analyze posts for the current day  
- 📆 **Yesterday** — analyze posts for the previous day  
- 📊 **Last 7 days** — weekly analysis  
- 📈 **Last 30 days** — monthly analysis  
- 🔧 **Custom period** — arbitrary time range  

### 📊 Report Formats

#### HTML report
- Interactive web page with detailed statistics  
- Data visualizations and charts  
- Convenient navigation through results  

#### JSON data
- Structured data for further processing  
- Complete information about posts and comments  
- Metrics and statistics  

### ⚙️ Parameters Configuration

#### Negativity threshold (`NEGATIVE_COMMENT_THRESHOLD`)
- **0.3** (30%) — moderate sensitivity  
- **0.5** (50%) — high sensitivity  
- **0.2** (20%) — very high sensitivity  

#### Maximum number of messages (`MAX_MESSAGES`)
- Recommended: **100–500** messages  
- For large channels: **1000+** messages  

### 📁 Project Structure

```text
Telegram-news-analyzer/
├── main.py                 # Entry point
├── telegram_bot.py         # Telegram bot logic
├── telegram_client.py      # Client for working with Telegram API
├── sentiment_analyzer.py   # Sentiment analysis
├── report_generator.py     # Report generation
├── config.py               # Configuration
├── logging_config.py       # Logging configuration
├── requirements.txt        # Dependencies
├── env_template            # Configuration template
└── output/                 # Reports folder
```

### 🔧 Development

#### Adding new channels

Edit the `CHANNELS_LIST` variable in the `.env` file:

```env
CHANNELS_LIST=@channel1,@channel2,@channel3
```

#### Configuring the analysis model

You can change the machine learning model in `sentiment_analyzer.py`:

```python
model_name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
```

#### Customizing reports

Edit `report_generator.py` to change the format and style of the reports.

### 🐛 Troubleshooting

#### Common issues

1. **Telegram authorization error**  
   - Check that `API_ID` and `API_HASH` are correct  
   - Make sure the phone number is in international format  

2. **The bot does not respond**  
   - Check that `BOT_TOKEN` is correct  
   - Make sure the bot is running and not blocked  

3. **Sentiment analysis errors**  
   - Check your internet connection  
   - Make sure all dependencies are installed  

#### Logs

Logs are saved to `logs/news_analyzer.log` for debugging.

### 🤝 Contributing

We welcome contributions to the project! Please:

1. Fork the repository  
2. Create a branch for your feature  
3. Make your changes  
4. Open a Pull Request  

### 📞 Support

If you have any questions or issues:

- Open an [Issue](https://github.com/your-username/Telegram-news-analyzer/issues)  

**Created with ❤️ for analyzing Telegram content**

