import time
import logging
import json
import os
from dotenv import load_dotenv
from datetime import datetime

from core.api import get_trading_client, get_available_cash, get_historical_bars
from core.brain import evaluate_asset
from core.database import (
	setup_database,
	get_tickers_from_best_parameters,
	get_best_parameters_json,
	log_trade_decision
)
from core.strategies import get_strategy_executor, apply_execution_plan
from core.ticker_state import TickerState
from core.stream_manager import TriggerEngine, start_streams

# Setup logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Get API keys
ALPACA_KEY = os.getenv('ALPACA_PAPER_KEY')
ALPACA_SECRET = os.getenv('ALPACA_PAPER_SECRET')


def decision_callback(ticker, state, trigger_type):
	"""
	Called when a trigger fires. Makes Gemini decision and executes.
	This is the core decision loop, now event-driven instead of polling.
	"""
	logger.info(f"\n{'='*60}")
	logger.info(f"DECISION TRIGGER: {ticker} - {trigger_type.upper()}")
	logger.info(f"{'='*60}")

	try:
		# 1. Get trading client for order placement
		trading_client = get_trading_client(paper_trading=True)

		# 2. Load parameters
		params = get_best_parameters_json(ticker, state.params.get('asset_class', 'CRYPTO'))
		if not params:
			logger.error(f"No parameters found for {ticker}")
			return

		strategy_name = params.get('strategy_name', 'ema_crossover')
		strategy_params = params.get('parameters_dict', {})

		# 3. Build context from ticker state
		full_context = state.build_context()
		logger.info(f"Context built:\n{full_context}")

		# 4. Call Gemini with strategy-aware prompt
		logger.info("Calling Gemini for decision...")
		decision = evaluate_asset(ticker, full_context, strategy_name, strategy_params)
		logger.info(f"Gemini Decision: {decision['action']} (Confidence: {decision['confidence']}%)")
		logger.info(f"  Order Type: {decision.get('order_type', 'market')}")
		logger.info(f"  Override Trail: {decision.get('trail_percent')}%")
		logger.info(f"Reasoning: {decision['reasoning']}")

		# 5. Prepare audit log data
		audit_data = {
			'ticker': ticker,
			'action': decision.get('action'),
			'confidence': decision.get('confidence'),
			'allocation_pct': decision.get('allocation_pct'),
			'reasoning': decision.get('reasoning'),
			'trigger_type': trigger_type,
			'gemini_response_json': json.dumps(decision),
			'ema_fast': state.ema_fast,
			'ema_slow': state.ema_slow,
			'ema_signal': state.ema_signal,
			'position_qty_before': state.position_qty,
			'position_pnl_pct_before': state.unrealized_pnl_pct,
			'strategy_name': strategy_name,
			'strategy_params_json': json.dumps(strategy_params),
			'gemini_overrides_json': json.dumps({
				'order_type': decision.get('order_type'),
				'trail_percent': decision.get('trail_percent'),
				'take_profit_percent': decision.get('take_profit_percent')
			}),
		}

		# 6. Generate execution plan (merge DB defaults with Gemini overrides)
		executor = get_strategy_executor(strategy_name, {
			'fast_ema': state.fast_ema_period,
			'slow_ema': state.slow_ema_period,
			'trailing_stop': strategy_params.get('trailing_stop', 2.0),
			'trend_ema_period': 200
		})

		execution_plan = executor.generate_execution_plan(
			decision,
			state.position_qty > 0,  # Pass position object or bool for simplicity
			state.cash,
			{
				'ema_fast': state.ema_fast,
				'ema_slow': state.ema_slow,
				'ema_signal': state.ema_signal,
				'price': state.last_known_price
			}
		)
		logger.info(f"Execution plan: {execution_plan}")

		# 7. Apply execution plan (make actual API calls)
		try:
			success = apply_execution_plan(trading_client, ticker, execution_plan)
			audit_data['execution_status'] = 'success' if success else 'error'
			audit_data['execution_error'] = None if success else 'Unknown error'
			logger.info(f"Execution {'succeeded' if success else 'failed'}")
		except Exception as e:
			audit_data['execution_status'] = 'error'
			audit_data['execution_error'] = str(e)
			logger.error(f"Execution failed: {e}")

		# 8. Log decision to database
		log_trade_decision(audit_data)

	except Exception as e:
		logger.error(f"Error in decision callback: {e}", exc_info=True)
		# Still log the error for audit
		try:
			audit_data = {
				'ticker': ticker,
				'trigger_type': trigger_type,
				'action': 'ERROR',
				'confidence': 0,
				'execution_status': 'error',
				'execution_error': str(e),
			}
			log_trade_decision(audit_data)
		except:
			pass


def run_bot():
	"""
	Hybrid event-driven bot using WebSocket streams instead of polling loop.
	"""
	setup_database()
	logger.info("Database initialized")

	# Load all active tickers
	tickers = get_tickers_from_best_parameters()
	if not tickers:
		logger.error("No active tickers found in best_parameters. Exiting.")
		return

	logger.info(f"Loaded {len(tickers)} active tickers: {tickers}")

	# Initialize TickerState for each ticker
	ticker_states = {}
	for ticker in tickers:
		# Determine asset class based on ticker format
		asset_class = 'CRYPTO' if '/' in ticker else 'STOCK'
		params = get_best_parameters_json(ticker, asset_class)
		if params:
			ticker_states[ticker] = TickerState(ticker, params.get('parameters_dict', params))
		else:
			logger.warning(f"No parameters found for {ticker}, skipping")

	if not ticker_states:
		logger.error("No tickers with valid parameters. Exiting.")
		return

	# Seed initial bars (one-time REST call to warm up EMAs)
	logger.info("Seeding initial bar data...")
	for ticker in ticker_states:
		try:
			bars_df = get_historical_bars([ticker], "15Min", days_ago=2)
			if ticker in bars_df.index.get_level_values(0):
				for bar in bars_df.loc[ticker].itertuples():
					ticker_states[ticker].update_bar(bar)
			logger.info(f"[{ticker}] Seeded with historical bars")
		except Exception as e:
			logger.error(f"Failed to seed {ticker}: {e}")

	# Seed initial cash (refreshed periodically, not per-decision)
	try:
		trading_client = get_trading_client(paper_trading=True)
		cash = get_available_cash(trading_client)
		for state in ticker_states.values():
			state.cash = cash
		logger.info(f"Initial cash: ${cash:.2f}")
	except Exception as e:
		logger.error(f"Failed to get initial cash: {e}")

	# Create trigger engine
	trigger_engine = TriggerEngine(ticker_states, decision_callback)
	logger.info("Trigger engine created")

	# Start WebSocket streams
	logger.info("Starting WebSocket streams...")
	streams = start_streams(ticker_states, trigger_engine, ALPACA_KEY, ALPACA_SECRET, paper=True)

	# Keep-alive loop: refresh cash every 5 minutes
	logger.info("Streams started. Bot is live. Press Ctrl+C to stop.")
	try:
		while True:
			time.sleep(300)  # 5 minutes
			try:
				cash = get_available_cash(trading_client)
				for state in ticker_states.values():
					state.cash = cash
				logger.info(f"Cash refreshed: ${cash:.2f}")
			except Exception as e:
				logger.warning(f"Failed to refresh cash: {e}")
	except KeyboardInterrupt:
		logger.info("Shutting down...")


if __name__ == "__main__":
	run_bot()
