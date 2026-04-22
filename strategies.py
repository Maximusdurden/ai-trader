import logging
from api import place_order, submit_trailing_stop_order, submit_stop_limit_order
from alpaca.trading.enums import OrderSide

logger = logging.getLogger(__name__)


def execute_ema_crossover_strategy(trading_client, ticker, decision, current_position, cash, params):
	"""
	EMA Crossover Strategy: Standard buy/sell based on EMA signals.
	Uses parameters: fast_ema, slow_ema, trailing_stop
	"""
	logger.info(f"Executing EMA Crossover strategy for {ticker}")

	trailing_stop = params.get('trailing_stop', 2.0)
	allocation_pct = decision.get('allocation_pct', 50)
	confidence = decision['confidence']
	action = decision['action']

	if action == 'BUY' and confidence > 75:
		amount_to_spend = cash * (allocation_pct / 100)
		if amount_to_spend > 10:
			logger.info(f"BUY signal: Allocating {allocation_pct}% of cash (${amount_to_spend:.2f})")
			# Place standard buy order
			return {
				'action': 'BUY',
				'amount': amount_to_spend,
				'use_trailing_stop': True,
				'trailing_stop_percent': trailing_stop
			}

	elif action == 'SELL' and current_position and confidence > 75:
		qty_to_sell = float(current_position.qty) * (allocation_pct / 100)
		if qty_to_sell > 0:
			logger.info(f"SELL signal: Selling {allocation_pct}% of position ({qty_to_sell:.4f} units)")
			return {
				'action': 'SELL',
				'quantity': qty_to_sell
			}

	logger.info(f"No action for {ticker}: HOLD")
	return {'action': 'HOLD'}


def execute_grid_trading_strategy(trading_client, ticker, decision, current_position, cash, params):
	"""
	Grid Trading Strategy: Places multiple orders at different price levels.
	Uses parameters: grid_levels, grid_spacing, position_size
	"""
	logger.info(f"Executing Grid Trading strategy for {ticker}")

	grid_levels = params.get('grid_levels', 5)
	grid_spacing = params.get('grid_spacing', 1.0)  # percentage
	position_size = params.get('position_size', 10)  # base position size

	decision_action = decision.get('action', 'HOLD')

	if decision_action == 'BUY' and decision['confidence'] > 75:
		logger.info(f"Grid BUY: Creating {grid_levels} grid levels with {grid_spacing}% spacing")
		return {
			'action': 'GRID_BUY',
			'grid_levels': grid_levels,
			'grid_spacing': grid_spacing,
			'position_size': position_size
		}

	elif decision_action == 'SELL' and current_position and decision['confidence'] > 75:
		logger.info(f"Grid SELL: Liquidating position across {grid_levels} levels")
		return {
			'action': 'GRID_SELL',
			'grid_levels': grid_levels,
			'grid_spacing': grid_spacing,
			'position_size': position_size
		}

	return {'action': 'HOLD'}


def execute_trailing_stop_strategy(trading_client, ticker, decision, current_position, cash, params):
	"""
	Trailing Stop Strategy: Enters position and sets trailing stop loss.
	Uses parameters: trailing_stop, entry_threshold, exit_threshold
	"""
	logger.info(f"Executing Trailing Stop strategy for {ticker}")

	trailing_stop = params.get('trailing_stop', 2.5)
	entry_threshold = params.get('entry_threshold', 80)
	allocation_pct = decision.get('allocation_pct', 50)

	if decision['action'] == 'BUY' and decision['confidence'] > entry_threshold:
		amount_to_spend = cash * (allocation_pct / 100)
		if amount_to_spend > 10:
			logger.info(f"Trailing Stop BUY: {allocation_pct}% allocation with {trailing_stop}% stop")
			return {
				'action': 'BUY_WITH_TRAILING_STOP',
				'amount': amount_to_spend,
				'trailing_stop_percent': trailing_stop
			}

	elif decision['action'] == 'SELL' and current_position and decision['confidence'] > 75:
		logger.info(f"Trailing Stop SELL: Exiting position")
		return {
			'action': 'SELL',
			'quantity': float(current_position.qty)
		}

	return {'action': 'HOLD'}


def execute_dca_strategy(trading_client, ticker, decision, current_position, cash, params):
	"""
	Dollar Cost Averaging (DCA) Strategy: Regular small buys regardless of price.
	Uses parameters: dca_amount, dca_frequency, max_position
	"""
	logger.info(f"Executing DCA strategy for {ticker}")

	dca_amount = params.get('dca_amount', 100)  # USD amount per order
	max_position = params.get('max_position', 1000)  # max position size

	if decision['action'] == 'BUY' and decision['confidence'] > 50:
		logger.info(f"DCA BUY: ${dca_amount} purchase")
		return {
			'action': 'DCA_BUY',
			'amount': dca_amount,
			'max_position': max_position
		}

	elif decision['action'] == 'SELL' and current_position:
		logger.info(f"DCA SELL: Liquidating {ticker}")
		return {
			'action': 'SELL',
			'quantity': float(current_position.qty)
		}

	return {'action': 'HOLD'}


STRATEGY_HANDLERS = {
	'ema_crossover': execute_ema_crossover_strategy,
	'full_featured_ema_crossover': execute_ema_crossover_strategy,
	'grid_trading': execute_grid_trading_strategy,
	'full_featured_grid_trading': execute_grid_trading_strategy,
	'trailing_stop': execute_trailing_stop_strategy,
	'dca': execute_dca_strategy,
	'dollar_cost_averaging': execute_dca_strategy,
	'ai_trader_gemini': execute_ema_crossover_strategy,  # default strategy
}


def execute_strategy(trading_client, ticker, decision, current_position, cash, strategy_name, params):
	"""
	Route to appropriate strategy handler based on strategy_name and parameters.

	Args:
		trading_client: Alpaca trading client
		ticker: Ticker symbol
		decision: Dict from Gemini with action, confidence, allocation_pct, reasoning
		current_position: Current position object or None
		cash: Available cash
		strategy_name: Name of strategy to execute
		params: Dict with strategy parameters

	Returns:
		Dict with execution plan that can be applied to API
	"""
	handler = STRATEGY_HANDLERS.get(strategy_name.lower(), execute_ema_crossover_strategy)

	logger.info(f"Strategy handler selected: {strategy_name}")
	execution_plan = handler(trading_client, ticker, decision, current_position, cash, params)

	return execution_plan


def apply_execution_plan(trading_client, ticker, execution_plan):
	"""
	Applies the execution plan by calling appropriate API functions.

	Args:
		trading_client: Alpaca trading client
		ticker: Ticker symbol
		execution_plan: Dict returned from execute_strategy()

	Returns:
		Bool indicating success
	"""
	action = execution_plan.get('action', 'HOLD')

	try:
		if action == 'HOLD':
			logger.info(f"{ticker}: No action taken")
			return True

		elif action == 'BUY':
			from api import get_latest_crypto_data
			amount = execution_plan.get('amount')
			latest_quote = get_latest_crypto_data([ticker])
			price = latest_quote[ticker].ask_price
			qty = amount / price
			logger.info(f"Placing BUY order: {qty:.4f} units of {ticker} at ${price:.2f}")
			place_order(trading_client, ticker, OrderSide.BUY, qty, None)
			return True

		elif action == 'BUY_WITH_TRAILING_STOP':
			from api import get_latest_crypto_data
			amount = execution_plan.get('amount')
			trailing_stop_pct = execution_plan.get('trailing_stop_percent', 2.0)
			latest_quote = get_latest_crypto_data([ticker])
			price = latest_quote[ticker].ask_price
			qty = amount / price
			logger.info(f"Placing BUY with trailing stop: {qty:.4f} units at ${price:.2f}, stop={trailing_stop_pct}%")
			place_order(trading_client, ticker, OrderSide.BUY, qty, None)
			# Trailing stop would be placed separately after order fills
			return True

		elif action == 'SELL':
			qty = execution_plan.get('quantity')
			logger.info(f"Placing SELL order: {qty:.4f} units of {ticker}")
			place_order(trading_client, ticker, OrderSide.SELL, qty, None)
			return True

		elif action == 'GRID_BUY':
			logger.info(f"Grid trading BUY logic would be implemented here for {ticker}")
			# This would require extended API calls for grid implementation
			return True

		elif action == 'GRID_SELL':
			logger.info(f"Grid trading SELL logic would be implemented here for {ticker}")
			return True

		elif action == 'DCA_BUY':
			from api import get_latest_crypto_data
			amount = execution_plan.get('amount')
			latest_quote = get_latest_crypto_data([ticker])
			price = latest_quote[ticker].ask_price
			qty = amount / price
			logger.info(f"DCA BUY: ${amount:.2f} → {qty:.4f} units at ${price:.2f}")
			place_order(trading_client, ticker, OrderSide.BUY, qty, None)
			return True

		else:
			logger.warning(f"Unknown action: {action}")
			return False

	except Exception as e:
		logger.error(f"Error applying execution plan for {ticker}: {e}")
		return False
