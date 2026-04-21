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
- **main.py**: Main bot loop that polls every 5 minutes, gathers data, and executes trades

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

- **Trading Pair**: SOL/USD (Solana)
- **Poll Interval**: 5 minutes
- **Technical Data**: 15-minute bars with SMA(5) and SMA(10)
- **Confidence Threshold**: 75% for order execution
- **Order Type**: Good-Till-Canceled (GTC) for crypto

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