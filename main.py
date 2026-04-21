import time
import logging
import pandas as pd
from api import (
    get_trading_client,
    get_latest_crypto_data,
    get_historical_bars,
    place_order,
    get_available_cash,
    get_latest_news
)
from brain import evaluate_asset
from database import setup_database, get_active_tickers
from alpaca.trading.enums import OrderSide, TimeInForce

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
POLL_INTERVAL = 300 # 5 minutes

def get_technicals(df):
    """Simple technical analysis."""
    if df is None or df.empty:
        return ""
    
    # Simple Moving Averages
    df['SMA_5'] = df['close'].rolling(window=5).mean()
    df['SMA_10'] = df['close'].rolling(window=10).mean()
    
    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest
    
    tech_str = f"""
    Latest Price: {latest['close']:.2f}
    SMA_5: {latest['SMA_5']:.2f}
    SMA_10: {latest['SMA_10']:.2f}
    Price Change (1 period): {((latest['close'] - prev['close']) / prev['close'] * 100):.2f}%
    """
    return tech_str

def evaluate_ticker(trading_client, ticker):
    """Evaluates a single ticker and executes trades if conditions are met."""
    try:
        logger.info(f"--- Evaluating {ticker} ---")

        # 1. Account Info
        cash = get_available_cash(trading_client)
        logger.info(f"Available cash: ${cash:.2f}")

        # 2. Current Position & PNL
        current_position = None
        try:
            current_position = trading_client.get_open_position(ticker)
            pnl = float(current_position.unrealized_pl)
            pnl_pct = float(current_position.unrealized_plpc) * 100
            pos_status = f"Position: {current_position.qty} units, PNL: ${pnl:.2f} ({pnl_pct:.2f}%)"
        except:
            pos_status = "No open position."

        logger.info(pos_status)

        # 3. Market Data & Technicals
        bars = get_historical_bars([ticker], "15Min", days_ago=1)
        tech_context = ""
        if ticker in bars and not bars[ticker].empty:
            tech_context = get_technicals(bars[ticker])

        # 4. News
        news = get_latest_news([ticker], limit=3)
        news_context = "\n".join([f"- {n.created_at}: {n.headline} ({n.summary[:100]}...)" for n in news])

        # 5. Compile Full Context
        full_context = f"""
        TICKER: {ticker}
        CURRENT STATUS: {pos_status}
        CASH AVAILABLE: ${cash:.2f}

        TECHNICAL ANALYSIS:
        {tech_context}

        RECENT NEWS:
        {news_context}
        """

        # 6. Ask Gemini
        decision = evaluate_asset(ticker, full_context)
        logger.info(f"Gemini Decision: {decision['action']} (Confidence: {decision['confidence']}%)")
        logger.info(f"Reasoning: {decision['reasoning']}")

        # 7. Execute Decision
        if decision['action'] == 'BUY' and decision['confidence'] > 75:
            amount_to_spend = cash * (decision['allocation_pct'] / 100)
            if amount_to_spend > 10:
                latest_quote = get_latest_crypto_data([ticker])
                price = latest_quote[ticker].ask_price
                qty = amount_to_spend / price
                logger.info(f"EXECUTING BUY: {qty:.4f} units of {ticker} at ~${price}")
                try:
                    place_order(trading_client, ticker, OrderSide.BUY, qty, None, time_in_force=TimeInForce.GTC)
                except Exception as e:
                    logger.error(f"Buy Order Failed: {e}")

        elif decision['action'] == 'SELL' and current_position and decision['confidence'] > 75:
            qty_to_sell = float(current_position.qty) * (decision['allocation_pct'] / 100)
            if qty_to_sell > 0:
                logger.info(f"EXECUTING SELL: {qty_to_sell:.4f} units of {ticker}")
                try:
                    place_order(trading_client, ticker, OrderSide.SELL, qty_to_sell, None, time_in_force=TimeInForce.GTC)
                except Exception as e:
                    logger.error(f"Sell Order Failed: {e}")
        else:
            logger.info(f"Decision: HOLD / No action taken for {ticker}.")

    except Exception as e:
        logger.error(f"Error evaluating {ticker}: {e}")


def run_bot():
    """Main bot loop that evaluates all active tickers."""
    setup_database()
    trading_client = get_trading_client(paper_trading=True)

    while True:
        try:
            # Get all active tickers
            active_tickers = get_active_tickers()

            if not active_tickers:
                logger.warning("No active tickers found. Sleeping...")
                time.sleep(POLL_INTERVAL)
                continue

            logger.info(f"Starting evaluation cycle for {len(active_tickers)} tickers")

            # Evaluate each active ticker
            for ticker in active_tickers:
                evaluate_ticker(trading_client, ticker)

            logger.info(f"Cycle complete. Sleeping for {POLL_INTERVAL} seconds.")
            time.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)


if __name__ == "__main__":
    run_bot()
