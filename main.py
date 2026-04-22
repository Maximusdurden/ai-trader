import time
import logging
import pandas as pd
from core.api import (
    get_trading_client,
    get_latest_crypto_data,
    get_historical_bars,
    place_order,
    get_available_cash,
    get_latest_news,
    OrderSide,
    TimeInForce
)
from core.brain import evaluate_asset
from core.database import setup_database, get_tickers_from_best_parameters, get_best_parameters_json
from core.strategies import get_strategy_executor, apply_execution_plan

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
POLL_INTERVAL = 300 # 5 minutes

def get_technicals(df, fast_period=5, slow_period=10):
    """Calculate technical indicators based on EMA periods.

    Args:
        df: DataFrame with OHLCV data
        fast_period: Fast EMA period (default 5)
        slow_period: Slow EMA period (default 10)
    """
    if df is None or df.empty:
        return ""

    # Calculate Exponential Moving Averages
    df['EMA_fast'] = df['close'].ewm(span=fast_period, adjust=False).mean()
    df['EMA_slow'] = df['close'].ewm(span=slow_period, adjust=False).mean()

    latest = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else latest

    price_change = ((latest['close'] - prev['close']) / prev['close'] * 100) if prev['close'] != 0 else 0
    ema_signal = "BULLISH" if latest['EMA_fast'] > latest['EMA_slow'] else "BEARISH"

    tech_str = f"""
    Latest Price: {latest['close']:.2f}
    EMA({fast_period}): {latest['EMA_fast']:.2f}
    EMA({slow_period}): {latest['EMA_slow']:.2f}
    EMA Signal: {ema_signal}
    Price Change (1 period): {price_change:.2f}%
    """
    return tech_str

def evaluate_ticker(trading_client, ticker):
    """Evaluates a single ticker and executes trades if conditions are met."""
    try:
        logger.info(f"--- Evaluating {ticker} ---")

        # 0. Load Ticker Parameters
        params = get_best_parameters_json(ticker, "CRYPTO")
        if not params:
            logger.warning(f"No parameters found for {ticker}. Using defaults.")
            fast_ema = 12
            slow_ema = 26
            trailing_stop = 2.0
            strategy_name = "default"
        else:
            params_dict = params.get('parameters_dict', {})
            fast_ema = params_dict.get('fast_ema', 12)
            slow_ema = params_dict.get('slow_ema', 26)
            trailing_stop = params_dict.get('trailing_stop', 2.0)
            strategy_name = params.get('strategy_name', 'ai_trader_gemini')
            logger.info(f"Loaded parameters for {ticker}: EMA({fast_ema},{slow_ema}), Stop={trailing_stop}%")

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

        # 3. Market Data & Technicals (using ticker-specific parameters)
        bars = get_historical_bars([ticker], "15Min", days_ago=1)
        tech_context = ""
        indicators = {}
        if ticker in bars and not bars[ticker].empty:
            df = bars[ticker]
            tech_context = get_technicals(df, fast_period=fast_ema, slow_period=slow_ema)

            # Extract indicator values for executor
            latest = df.iloc[-1]
            ema_fast = latest['EMA_fast']
            ema_slow = latest['EMA_slow']
            ema_signal = "BULLISH" if ema_fast > ema_slow else "BEARISH"
            price_change = ((latest['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100) if len(df) > 1 else 0

            indicators = {
                'ema_fast': ema_fast,
                'ema_slow': ema_slow,
                'ema_signal': ema_signal,
                'price_change_pct': price_change
            }

        # 4. News
        news = get_latest_news([ticker], limit=3)
        news_context = "\n".join([f"- {n.created_at}: {n.headline} ({n.summary[:100]}...)" for n in news])

        # 5. Compile Full Context (including strategy parameters)
        full_context = f"""
        TICKER: {ticker}
        STRATEGY: {strategy_name}
        STRATEGY PARAMETERS:
        - EMA Fast Period: {fast_ema}
        - EMA Slow Period: {slow_ema}
        - Trailing Stop: {trailing_stop}%

        CURRENT STATUS: {pos_status}
        CASH AVAILABLE: ${cash:.2f}

        TECHNICAL ANALYSIS:
        {tech_context}

        RECENT NEWS:
        {news_context}
        """

        # 6. Ask Gemini (with expanded schema for free-style execution)
        decision = evaluate_asset(ticker, full_context, strategy_name, {
            'fast_ema': fast_ema,
            'slow_ema': slow_ema,
            'trailing_stop': trailing_stop,
            'strategy_type': 'long_only'
        })
        logger.info(f"Gemini Decision: {decision['action']} (Confidence: {decision['confidence']}%)")
        logger.info(f"  Order Type: {decision.get('order_type', 'default (market)')}")
        logger.info(f"  Override Trail: {decision.get('trail_percent')}%")
        logger.info(f"Reasoning: {decision['reasoning']}")

        # 7. Get strategy executor and generate execution plan (merges DB defaults + Gemini overrides)
        executor = get_strategy_executor(strategy_name, {
            'fast_ema': fast_ema,
            'slow_ema': slow_ema,
            'trailing_stop': trailing_stop,
            'trend_ema_period': 200
        })

        execution_plan = executor.generate_execution_plan(decision, current_position, cash, indicators)
        logger.info(f"Execution plan: {execution_plan}")

        # 8. Apply Execution Plan (interact with API based on strategy)
        apply_execution_plan(trading_client, ticker, execution_plan)

    except Exception as e:
        logger.error(f"Error evaluating {ticker}: {e}")


def run_bot():
    """Main bot loop that evaluates all active tickers from best_parameters."""
    setup_database()
    trading_client = get_trading_client(paper_trading=True)

    while True:
        try:
            # Get all tickers with active parameters (source of truth is best_parameters.is_active = 1)
            active_tickers = get_tickers_from_best_parameters()

            if not active_tickers:
                logger.warning("No tickers with active parameters found in best_parameters table. Sleeping...")
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
