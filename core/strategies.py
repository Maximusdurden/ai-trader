import logging
import pandas as pd
import numpy as np
from .api import place_order, OrderSide

logger = logging.getLogger(__name__)


class StrategyExecutor:
	"""
	Base strategy executor that interprets Gemini decisions using
	strategy parameters from best_parameters table.

	Each strategy defines:
	- How to calculate indicators (fast_ema, slow_ema, etc.)
	- How to interpret signals (entry/exit conditions)
	- How to interact with the API (order types, sizing, etc.)
	"""

	def __init__(self, strategy_name, parameters):
		self.strategy_name = strategy_name
		self.parameters = parameters
		self.fast_ema = parameters.get('fast_ema', 12)
		self.slow_ema = parameters.get('slow_ema', 26)
		self.trailing_stop = parameters.get('trailing_stop', 2.0)
		self.trend_ema_period = parameters.get('trend_ema_period', 200)
		self.take_profit_percent = parameters.get('take_profit_percent')
		self.trade_size_percent = parameters.get('trade_size_percent', 0.95)

	def validate_parameters(self):
		"""Validate parameter combinations are valid for this strategy."""
		if self.fast_ema >= self.slow_ema:
			logger.error(f"Invalid EMA periods: fast_ema ({self.fast_ema}) must be < slow_ema ({self.slow_ema})")
			return False
		return True

	def calculate_indicators(self, df):
		"""Calculate technical indicators needed for this strategy."""
		if df is None or df.empty:
			return df

		# Use HLC3 (High+Low+Close)/3 for smoother MA
		df['HLC3'] = (df['high'] + df['low'] + df['close']) / 3

		# Calculate EMAs
		df[f'EMA_{self.fast_ema}'] = df['HLC3'].ewm(span=self.fast_ema, adjust=False).mean()
		df[f'EMA_{self.slow_ema}'] = df['HLC3'].ewm(span=self.slow_ema, adjust=False).mean()

		# Shift previous values for crossover detection
		df['EMA_fast_prev'] = df[f'EMA_{self.fast_ema}'].shift(1)
		df['EMA_slow_prev'] = df[f'EMA_{self.slow_ema}'].shift(1)

		# Trend filter EMA
		df[f'EMA_{self.trend_ema_period}'] = df['HLC3'].ewm(span=self.trend_ema_period, adjust=False).mean()

		return df

	def detect_crossover_signals(self, current_row, prev_row):
		"""Detect bullish and bearish EMA crossovers."""
		if prev_row is None:
			return {'bullish': False, 'bearish': False}

		fast_col = f'EMA_{self.fast_ema}'
		slow_col = f'EMA_{self.slow_ema}'

		# Bullish: fast EMA crosses above slow EMA
		bullish = (
			current_row[fast_col] > current_row[slow_col] and
			prev_row[fast_col] <= prev_row[slow_col]
		)

		# Bearish: fast EMA crosses below slow EMA
		bearish = (
			current_row[fast_col] < current_row[slow_col] and
			prev_row[fast_col] >= prev_row[slow_col]
		)

		return {'bullish': bullish, 'bearish': bearish}

	def generate_execution_plan(self, decision, current_position, cash, indicators=None):
		"""
		Generate API execution plan based on:
		- Gemini decision (action, confidence, allocation, + new execution fields)
		- Strategy parameters (trailing stop, position sizing, etc. — database defaults)
		- Current market state (position, price, indicators)

		Gemini's execution fields override database defaults when not null:
		- order_type: market|limit|trailing_stop|stop_limit (overrides default)
		- trail_percent: trailing stop % (overrides stored trailing_stop)
		- take_profit_percent: take profit level (overrides stored value)
		- limit_price_offset: % offset for limit orders

		Returns dict with execution instructions for apply_execution_plan()
		"""
		action = decision.get('action', 'HOLD')
		confidence = decision.get('confidence', 0)
		allocation_pct = decision.get('allocation_pct', 50)

		# Get execution overrides from Gemini (can be None)
		gemini_order_type = decision.get('order_type')
		gemini_trail_percent = decision.get('trail_percent')
		gemini_take_profit = decision.get('take_profit_percent')
		gemini_limit_offset = decision.get('limit_price_offset')

		# Merge: Gemini overrides DB defaults
		order_type = gemini_order_type or 'market'
		trail_percent = gemini_trail_percent if gemini_trail_percent is not None else self.trailing_stop
		take_profit = gemini_take_profit if gemini_take_profit is not None else self.take_profit_percent

		if action == 'BUY' and confidence > 75:
			# Calculate position size based on strategy parameters
			amount = cash * (allocation_pct / 100)

			return {
				'action': 'BUY',
				'amount': amount,
				'order_type': order_type,
				'trail_percent': trail_percent,
				'take_profit_percent': take_profit,
				'limit_price_offset': gemini_limit_offset,
				'strategy': self.strategy_name,
				'gemini_overrides': {
					'order_type': gemini_order_type,
					'trail_percent': gemini_trail_percent,
					'take_profit_percent': gemini_take_profit
				},
				'parameters_used': {
					'fast_ema': self.fast_ema,
					'slow_ema': self.slow_ema,
					'trailing_stop': trail_percent,
					'allocation': allocation_pct,
					'order_type': order_type
				}
			}

		elif action == 'SELL' and current_position and confidence > 75:
			qty_to_sell = float(current_position.qty) * (allocation_pct / 100)

			return {
				'action': 'SELL',
				'quantity': qty_to_sell,
				'order_type': order_type,
				'strategy': self.strategy_name,
				'gemini_overrides': {
					'order_type': gemini_order_type
				},
				'parameters_used': {
					'allocation': allocation_pct,
					'order_type': order_type
				}
			}

		return {
			'action': 'HOLD',
			'strategy': self.strategy_name,
			'reason': f"Action={action}, Confidence={confidence}% (need >75%)"
		}


class EMAcrossoverExecutor(StrategyExecutor):
	"""
	EMA Crossover Strategy Executor
	Based on full_featured_ema_crossover from dexter-trader

	Key Logic:
	1. Calculate fast EMA and slow EMA
	2. Detect crossovers (bullish when fast > slow, bearish when fast < slow)
	3. Use trend filter for additional confirmation
	4. Apply trailing stop loss on positions
	5. Execute with Gemini-assisted decision-making
	"""

	def __init__(self, parameters):
		super().__init__('ema_crossover', parameters)
		logger.info(f"EMA Crossover Executor: fast={self.fast_ema}, slow={self.slow_ema}, trail_stop={self.trailing_stop}%")


class GridTradingExecutor(StrategyExecutor):
	"""
	Grid Trading Strategy Executor
	Based on full_featured_grid_trading from dexter-trader

	Key Parameters:
	- grid_levels: Number of grid lines above/below center
	- grid_spacing: Spacing between levels (percentage)
	- atr_multiplier: ATR multiple for grid width

	Places multiple orders at different price levels for scaling in/out.
	"""

	def __init__(self, parameters):
		super().__init__('grid_trading', parameters)
		self.grid_levels = parameters.get('grid_levels', 5)
		self.grid_spacing = parameters.get('grid_spacing', 1.0)
		self.atr_multiplier = parameters.get('atr_multiplier', 1.5)
		logger.info(f"Grid Trading Executor: levels={self.grid_levels}, spacing={self.grid_spacing}%")

	def generate_execution_plan(self, decision, current_position, cash, indicators=None):
		"""Grid trading places multiple orders at grid levels."""
		action = decision.get('action', 'HOLD')
		confidence = decision.get('confidence', 0)

		if action == 'BUY' and confidence > 75:
			return {
				'action': 'GRID_BUY',
				'grid_levels': self.grid_levels,
				'grid_spacing': self.grid_spacing,
				'available_cash': cash,
				'strategy': self.strategy_name,
				'parameters_used': {
					'grid_levels': self.grid_levels,
					'grid_spacing': self.grid_spacing,
					'atr_multiplier': self.atr_multiplier
				}
			}

		elif action == 'SELL' and current_position and confidence > 75:
			return {
				'action': 'GRID_SELL',
				'grid_levels': self.grid_levels,
				'position_quantity': float(current_position.qty),
				'strategy': self.strategy_name
			}

		return {'action': 'HOLD', 'strategy': self.strategy_name}


STRATEGY_EXECUTORS = {
	'ema_crossover': EMAcrossoverExecutor,
	'full_featured_ema_crossover': EMAcrossoverExecutor,
	'ai_trader_gemini': EMAcrossoverExecutor,
	'grid_trading': GridTradingExecutor,
	'full_featured_grid_trading': GridTradingExecutor,
}


def get_strategy_executor(strategy_name, parameters):
	"""
	Factory function to get the appropriate strategy executor
	based on strategy_name and loaded parameters.
	"""
	executor_class = STRATEGY_EXECUTORS.get(
		strategy_name.lower(),
		EMAcrossoverExecutor  # Default to EMA Crossover
	)

	executor = executor_class(parameters)

	if not executor.validate_parameters():
		logger.error(f"Invalid parameters for {strategy_name}. Using defaults.")
		# Fall back to defaults if validation fails
		return EMAcrossoverExecutor(parameters)

	return executor


def apply_execution_plan(trading_client, ticker, execution_plan):
	"""
	Execute the plan by calling appropriate api.py functions.
	Routes to different API calls based on order_type:
	- market: place_order() without limit
	- trailing_stop: submit_trailing_stop_order()
	- stop_limit: submit_stop_limit_order()
	- limit: place_order() with limit price
	"""
	action = execution_plan.get('action', 'HOLD')
	order_type = execution_plan.get('order_type', 'market')

	try:
		if action == 'HOLD':
			logger.info(f"{ticker}: {execution_plan.get('reason', 'No action')}")
			return True

		elif action == 'BUY':
			from api import get_latest_crypto_data
			amount = execution_plan.get('amount')
			trail_percent = execution_plan.get('trail_percent')
			limit_offset = execution_plan.get('limit_price_offset')

			latest_quote = get_latest_crypto_data([ticker])
			price = latest_quote[ticker].ask_price
			qty = amount / price

			logger.info(f"BUY {ticker}: {qty:.4f} units @ ${price:.2f}")
			logger.info(f"  Strategy: {execution_plan.get('strategy')}")
			logger.info(f"  Order Type: {order_type}")
			logger.info(f"  Trailing Stop: {trail_percent}%")
			logger.info(f"  Gemini Overrides: {execution_plan.get('gemini_overrides')}")
			logger.info(f"  Parameters: {execution_plan.get('parameters_used')}")

			# Route to appropriate API call based on order type
			if order_type == 'trailing_stop':
				from api import submit_trailing_stop_order
				submit_trailing_stop_order(trading_client, ticker, qty, OrderSide.BUY, trail_percent / 100)
			elif order_type == 'limit':
				limit_price = price * (1 + (limit_offset or 0) / 100) if limit_offset else price
				place_order(trading_client, ticker, OrderSide.BUY, qty, limit_price)
			elif order_type == 'stop_limit':
				stop_price = price * (1 - (trail_percent or 2.0) / 100)
				limit_price = stop_price * 0.99
				from api import submit_stop_limit_order
				submit_stop_limit_order(trading_client, ticker, qty, OrderSide.BUY, stop_price, limit_price)
			else:
				# Default: market order
				place_order(trading_client, ticker, OrderSide.BUY, qty, None)

			return True

		elif action == 'SELL':
			from api import get_latest_crypto_data
			qty = execution_plan.get('quantity')

			latest_quote = get_latest_crypto_data([ticker])
			price = latest_quote[ticker].bid_price

			logger.info(f"SELL {ticker}: {qty:.4f} units @ ${price:.2f}")
			logger.info(f"  Strategy: {execution_plan.get('strategy')}")
			logger.info(f"  Order Type: {order_type}")
			logger.info(f"  Gemini Overrides: {execution_plan.get('gemini_overrides')}")
			logger.info(f"  Parameters: {execution_plan.get('parameters_used')}")

			# Route to appropriate API call
			if order_type == 'limit':
				limit_offset = execution_plan.get('limit_price_offset')
				limit_price = price * (1 - (limit_offset or 0) / 100) if limit_offset else price
				place_order(trading_client, ticker, OrderSide.SELL, qty, limit_price)
			else:
				# Default: market order
				place_order(trading_client, ticker, OrderSide.SELL, qty, None)

			return True

		elif action in ['GRID_BUY', 'GRID_SELL']:
			# Grid trading would place multiple orders
			logger.info(f"Grid Trading ({action}) for {ticker} - implementation placeholder")
			logger.info(f"  Levels: {execution_plan.get('grid_levels')}")
			logger.info(f"  Spacing: {execution_plan.get('grid_spacing')}%")
			return True

		else:
			logger.warning(f"Unknown action: {action}")
			return False

	except Exception as e:
		logger.error(f"Error applying execution plan for {ticker}: {e}")
		return False
