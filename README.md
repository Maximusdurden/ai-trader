# AI Trader

An AI-powered cryptocurrency trading bot that uses Google's Gemini API to make intelligent buy/sell decisions based on technical analysis, market news, and account metrics.

## Features

- **AI-Driven Decisions**: Leverages Google Gemini 2.0 Flash to analyze market data and make trading decisions
- **Technical Analysis**: Calculates Simple Moving Averages (SMA) on 15-minute bar data
- **News Sentiment**: Incorporates recent news headlines to inform trading decisions
- **Risk Management**: Monitors account PNL and position sizing before executing orders
- **Paper Trading**: Safely test strategies using Alpaca's paper trading account
- **Crypto Trading**: Trades cryptocurrency pairs (e.g., SOL/USD) on Alpaca

## Architecture

```
main.py
├── api.py (Alpaca trading + data client)
├── brain.py (Gemini AI decision engine)
└── 5-minute polling loop with order execution
```

### Key Components

- **api.py**: Alpaca API wrapper providing access to account info, market data, and order management
- **brain.py**: Gemini-based decision engine that analyzes context and returns JSON decisions
- **database.py**: SQLite database manager for storing parameters, trades, and performance metrics
- **main.py**: Main bot loop that polls every 5 minutes, gathers data, and executes trades

## Database

The bot uses SQLite (`ai-trader.db`) to persist data with the following tables:

- **best_parameters**: Stores optimized strategy parameters for active tickers (active=1 required)
- **trade_log**: Records all AI decisions, confidence levels, and executed trades
- **daily_performance**: Aggregates daily PnL and trade statistics
- **account_metrics**: Tracks historical equity, cash, and buying power snapshots
- **tickers**: Tracks which tickers are active and available for trading

### Loading SOL/USD Parameters

The bot loads best parameters for SOL/USD from the `best_parameters` table. Parameters are only loaded for active tickers (where `active = 1` in the tickers table).

```python
from database import setup_database, get_best_parameters

setup_database()  # Initialize database
params = get_best_parameters("SOL/USD")  # Load SOL/USD parameters
```

## Setup

### Requirements

- Python 3.8+
- Alpaca API account (paper or live)
- Google Gemini API key

### Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Create a `.env` file in the project root with your API keys:

```
ALPACA_PAPER_KEY=your_alpaca_key
ALPACA_PAPER_SECRET=your_alpaca_secret
GEMINI_API_KEY=your_gemini_key
```

## Usage

Run the bot:

```bash
python main.py
```

The bot will:
1. Check available cash and current positions
2. Fetch 15-minute bar data and calculate technical indicators
3. Retrieve recent news for the trading pair
4. Ask Gemini for a buy/sell/hold decision
5. Execute orders if confidence > 75%
6. Sleep for 5 minutes and repeat

## Current Configuration

- **Trading Pairs**: All active tickers from database (SOL/USD by default)
- **Active Ticker Requirement**: `active = 1` in tickers table
- **Poll Interval**: 5 minutes (evaluates all active tickers per cycle)
- **Technical Data**: 15-minute bars with SMA(5) and SMA(10)
- **Confidence Threshold**: 75% for order execution
- **Order Type**: Good-Till-Canceled (GTC) for crypto

## Managing Tickers

The bot evaluates all active tickers from the database. To add or remove tickers:

```python
from database import setup_database, get_active_tickers

# View all active tickers
active = get_active_tickers()  # Returns list of ticker symbols

# To add a ticker to database
conn = get_db_connection()
conn.execute("INSERT OR IGNORE INTO tickers (ticker, active, insert_date, last_update) VALUES (?, 1, ?, ?)", 
             ("BTC/USD", datetime.now().isoformat(), datetime.now().isoformat()))
conn.commit()
conn.close()

# To deactivate a ticker
conn = get_db_connection()
conn.execute("UPDATE tickers SET active = 0 WHERE ticker = ?", ("BTC/USD",))
conn.commit()
conn.close()
```

## Testing

Run tests:

```bash
python main_test.py
```

Test connection:

```bash
python test_connection.py
```

Inspect market data:

```bash
python inspect_news.py
```