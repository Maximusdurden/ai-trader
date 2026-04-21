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
from alpaca.trading.enums import OrderSide, TimeInForce

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
TICKER = "SOL/USD"
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

def run_bot():
    trading_client = get_trading_client(paper_trading=True)
    
    for _ in range(1):
        try:
            logger.info(f"--- Starting evaluation cycle for {TICKER} ---")
            
            # 1. Account Info
            cash = get_available_cash(trading_client)
            logger.info(f"Available cash: ${cash:.2f}")
            
            # 2. Current Position & PNL
            current_position = None
            try:
                current_position = trading_client.get_open_position(TICKER)
                pnl = float(current_position.unrealized_pl)
                pnl_pct = float(current_position.unrealized_plpc) * 100
                pos_status = f"Position: {current_position.qty} units, PNL: ${pnl:.2f} ({pnl_pct:.2f}%)"
            except:
                pos_status = "No open position."
            
            logger.info(pos_status)

            # 3. Market Data & Technicals
            # Use 1 minute bars for 5 min frequency? Or 1 hour?
            # Let's use 15Min for a bit more context
            bars = get_historical_bars([TICKER], "15Min", days_ago=1)
            tech_context = ""
            if TICKER in bars and not bars[TICKER].empty:
                tech_context = get_technicals(bars[TICKER])
            
            # 4. News
            news = get_latest_news([TICKER], limit=3)
            news_context = "\n".join([f"- {n.created_at}: {n.headline} ({n.summary[:100]}...)" for n in news])
            
            # 5. Compile Full Context
            full_context = f"""
            TICKER: {TICKER}
            CURRENT STATUS: {pos_status}
            CASH AVAILABLE: ${cash:.2f}
            
            TECHNICAL ANALYSIS:
            {tech_context}
            
            RECENT NEWS:
            {news_context}
            """
            
            # 6. Ask Gemini
            decision = evaluate_asset(TICKER, full_context)
            logger.info(f"Gemini Decision: {decision['action']} (Confidence: {decision['confidence']}%)")
            logger.info(f"Reasoning: {decision['reasoning']}")
            
            # 7. Execute Decision
            if decision['action'] == 'BUY' and decision['confidence'] > 75:
                # Basic buying logic
                amount_to_spend = cash * (decision['allocation_pct'] / 100)
                if amount_to_spend > 10:
                    latest_quote = get_latest_crypto_data([TICKER])
                    price = latest_quote[TICKER].ask_price
                    qty = amount_to_spend / price
                    logger.info(f"EXECUTING BUY: {qty:.4f} units at ~${price}")
                    try:
                        place_order(trading_client, TICKER, OrderSide.BUY, qty, None, time_in_force=TimeInForce.GTC)
                    except Exception as e:
                        logger.error(f"Buy Order Failed: {e}")
            
            elif decision['action'] == 'SELL' and current_position and decision['confidence'] > 75:
                # Basic selling logic
                qty_to_sell = float(current_position.qty) * (decision['allocation_pct'] / 100)
                if qty_to_sell > 0:
                    logger.info(f"EXECUTING SELL: {qty_to_sell:.4f} units")
                    try:
                        place_order(trading_client, TICKER, OrderSide.SELL, qty_to_sell, None, time_in_force=TimeInForce.GTC)
                    except Exception as e:
                        logger.error(f"Sell Order Failed: {e}")
            
            else:
                logger.info("Decision: HOLD / No action taken.")

            logger.info(f"Cycle complete. Sleeping for {POLL_INTERVAL} seconds.")
            time.sleep(POLL_INTERVAL)
            
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_bot()
