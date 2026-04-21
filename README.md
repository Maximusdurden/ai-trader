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

### How Parameters Are Used

For each active ticker, the bot:

1. **Loads ticker-specific parameters** from `best_parameters` table
2. **Uses parameters to configure technical analysis**:
   - `fast_ema`: Period for fast exponential moving average (default: 12)
   - `slow_ema`: Period for slow exponential moving average (default: 26)
3. **Includes parameters in AI decision context**:
   - Strategy name and configured parameters sent to Gemini
   - Technical indicators calculated using ticker-specific periods
4. **Logs parameters during execution**:
   - Trailing stop percentage logged with each trade

Example parameter structure in database:
```json
{
  "fast_ema": 12,
  "slow_ema": 26,
  "trailing_stop": 2.5,
  "confidence_threshold": 75,
  "allocation_pct": 50
}
```

### Retrieving Parameters

```python
from database import setup_database, get_best_parameters_json

setup_database()
# Get SOL/USD parameters (CRYPTO asset class)
params = get_best_parameters_json("SOL/USD", "CRYPTO")
# Returns: {'ticker': 'SOL/USD', 'strategy_name': '...', 'parameters': '...', 'parameters_dict': {...}}
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

For each active ticker, the bot will:
1. **Load parameters** from database for the ticker
2. **Fetch account data**: Available cash and current positions
3. **Calculate technical indicators**: EMA(fast) and EMA(slow) using ticker-specific periods
4. **Retrieve market data**: 15-minute bars and recent news for the trading pair
5. **Request AI decision**: Send context + parameters to Gemini for buy/sell/hold decision
6. **Execute trades**: Place orders if confidence > 75%
7. **Log results**: Record decision, parameters used, and execution status

Example evaluation cycle for SOL/USD:
```
1. Load parameters: EMA(12,26), Stop=2.5%
2. Calculate EMA_12 and EMA_26 on 15-min bars
3. Determine EMA signal: BULLISH (if EMA_12 > EMA_26) or BEARISH
4. Fetch latest news about SOL/USD
5. Send to Gemini: "EMA_12: 145.2, EMA_12: 142.5, Signal: BULLISH, Recent news: ..."
6. Gemini responds: "BUY with 82% confidence, allocate 50% of cash"
7. Execute 50% cash position, log with parameters used
```

The bot cycles through all active tickers and repeats every 5 minutes.

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