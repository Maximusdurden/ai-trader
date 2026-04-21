import sqlite3
import json
import logging
import os
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# Database configuration
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_NAME = os.path.join(CURRENT_DIR, "ai-trader.db")


def get_db_connection():
	"""Establishes a connection to the SQLite database with timeout and WAL mode."""
	conn = sqlite3.connect(DATABASE_NAME, timeout=30.0)
	try:
		conn.execute('PRAGMA journal_mode=WAL;')
		conn.execute('PRAGMA busy_timeout = 30000;')  # 30 seconds
	except Exception as e:
		logger.error(f"Failed to set PRAGMA: {e}")
	return conn


def setup_database():
	"""Initializes the database and creates all necessary tables."""
	conn = get_db_connection()
	cursor = conn.cursor()

	# 1. Tickers table
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS tickers (
			ticker TEXT PRIMARY KEY,
			active INTEGER NOT NULL,
			insert_date TEXT NOT NULL,
			last_update TEXT NOT NULL
		)
	""")

	# 2. Best Parameters table (for storing optimized strategy parameters)
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS best_parameters (
			ticker TEXT,
			asset_class TEXT,
			is_active INTEGER DEFAULT 1,
			fast_ema INTEGER,
			slow_ema INTEGER,
			trailing_stop REAL,
			strategy_name TEXT,
			parameters TEXT,
			last_updated TEXT,
			PRIMARY KEY (ticker, asset_class)
		)
	""")

	# 3. Trade Log table (for logging AI trading decisions and executions)
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS trade_log (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			ticker TEXT,
			timestamp TEXT,
			decision TEXT,
			confidence REAL,
			allocation_pct REAL,
			reasoning TEXT,
			action_taken TEXT,
			price_at_decision REAL,
			executed_price REAL,
			quantity REAL,
			order_id TEXT
		)
	""")

	# 4. Daily Performance table
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS daily_performance (
			date TEXT PRIMARY KEY,
			ticker TEXT,
			total_pnl REAL,
			trade_count INTEGER,
			total_trades REAL,
			win_rate REAL,
			last_updated TEXT
		)
	""")

	# 5. Account Metrics table (for tracking account state over time)
	cursor.execute("""
		CREATE TABLE IF NOT EXISTS account_metrics (
			timestamp TEXT PRIMARY KEY,
			date TEXT,
			equity REAL,
			cash REAL,
			buying_power REAL,
			total_positions REAL,
			unrealized_pnl REAL
		)
	""")

	# Populate default data
	current_dt = datetime.now().isoformat()
	cursor.execute(
		"INSERT OR IGNORE INTO tickers (ticker, active, insert_date, last_update) VALUES (?, 1, ?, ?)",
		("SOL/USD", current_dt, current_dt)
	)

	conn.commit()
	conn.close()
	logger.info("Database setup complete.")


def get_best_parameters(ticker="SOL/USD", asset_class=None):
	"""
	Retrieves the best parameters for a given ticker from the best_parameters table.
	Only returns parameters where is_active = 1.

	Args:
		ticker: Ticker symbol (e.g., 'SOL/USD')
		asset_class: Optional filter by asset class ('STOCK', 'CRYPTO', etc.)

	Returns:
		Dictionary with parameters, or None if not found.
	"""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		if asset_class:
			query = """
				SELECT ticker, asset_class, is_active, fast_ema, slow_ema, trailing_stop,
						strategy_name, parameters, last_updated
				FROM best_parameters
				WHERE is_active = 1 AND ticker = ? AND asset_class = ?
			"""
			result = cursor.execute(query, (ticker, asset_class)).fetchone()
		else:
			query = """
				SELECT ticker, asset_class, is_active, fast_ema, slow_ema, trailing_stop,
						strategy_name, parameters, last_updated
				FROM best_parameters
				WHERE is_active = 1 AND ticker = ?
			"""
			result = cursor.execute(query, (ticker,)).fetchone()

		if result:
			ticker_val, asset_cls, is_active, fast_ema, slow_ema, trailing_stop, strategy_name, params_json, last_updated = result

			# If parameters column has JSON, parse it; otherwise use individual columns
			if params_json:
				try:
					params = json.loads(params_json)
				except:
					params = {
						"ticker": ticker_val,
						"asset_class": asset_cls,
						"fast_ema": fast_ema,
						"slow_ema": slow_ema,
						"trailing_stop": trailing_stop,
						"strategy_name": strategy_name,
						"is_active": is_active
					}
			else:
				params = {
					"ticker": ticker_val,
					"asset_class": asset_cls,
					"is_active": is_active,
					"fast_ema": fast_ema,
					"slow_ema": slow_ema,
					"trailing_stop": trailing_stop,
					"strategy_name": strategy_name,
					"last_updated": last_updated
				}

			logger.info(f"Loaded parameters for {ticker_val}: {params}")
			return params

		logger.warning(f"No active parameters found for ticker {ticker}")
		return None

	except Exception as e:
		logger.error(f"Error fetching best parameters for {ticker}: {e}")
		return None
	finally:
		conn.close()


def log_trade(ticker, timestamp, decision, confidence, allocation_pct, reasoning,
			  action_taken=None, price_at_decision=None, executed_price=None,
			  quantity=None, order_id=None):
	"""Logs a trading decision and execution to the trade_log table."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		cursor.execute("""
			INSERT INTO trade_log (
				ticker, timestamp, decision, confidence, allocation_pct, reasoning,
				action_taken, price_at_decision, executed_price, quantity, order_id
			) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		""", (
			ticker, timestamp, decision, confidence, allocation_pct, reasoning,
			action_taken, price_at_decision, executed_price, quantity, order_id
		))
		conn.commit()
		logger.info(f"Trade logged for {ticker}: {decision} at {timestamp}")
		return cursor.lastrowid

	except Exception as e:
		logger.error(f"Failed to log trade: {e}")
		return None
	finally:
		conn.close()


def log_daily_performance(date, ticker, total_pnl, trade_count=0, total_trades=0, win_rate=0):
	"""Logs or updates the daily performance metrics."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		cursor.execute("""
			INSERT INTO daily_performance (date, ticker, total_pnl, trade_count, total_trades, win_rate, last_updated)
			VALUES (?, ?, ?, ?, ?, ?, ?)
			ON CONFLICT(date) DO UPDATE SET
				total_pnl = excluded.total_pnl,
				trade_count = excluded.trade_count,
				total_trades = excluded.total_trades,
				win_rate = excluded.win_rate,
				last_updated = excluded.last_updated
		""", (
			date, ticker, total_pnl, trade_count, total_trades, win_rate, datetime.now().isoformat()
		))
		conn.commit()
		logger.info(f"Daily performance logged for {date}: PnL={total_pnl}, Trades={trade_count}")

	except Exception as e:
		logger.error(f"Failed to log daily performance: {e}")
	finally:
		conn.close()


def save_account_metrics(equity, cash, buying_power, total_positions, unrealized_pnl):
	"""Saves current account metrics with a timestamp."""
	eastern = pytz.timezone('America/New_York')
	timestamp = datetime.now(eastern).isoformat()
	date = datetime.now(eastern).strftime('%Y-%m-%d')

	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		cursor.execute("""
			INSERT INTO account_metrics (timestamp, date, equity, cash, buying_power, total_positions, unrealized_pnl)
			VALUES (?, ?, ?, ?, ?, ?, ?)
		""", (
			timestamp, date, equity, cash, buying_power, total_positions, unrealized_pnl
		))
		conn.commit()
		logger.info(f"Account metrics saved: Equity=${equity:.2f}, Cash=${cash:.2f}")

	except Exception as e:
		logger.error(f"Failed to save account metrics: {e}")
	finally:
		conn.close()


def get_today_trades(ticker="SOL/USD"):
	"""Retrieves all trades logged for today for a specific ticker."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		today = datetime.now().strftime('%Y-%m-%d')
		query = """
			SELECT id, timestamp, decision, confidence, allocation_pct, reasoning,
					action_taken, executed_price, quantity
			FROM trade_log
			WHERE ticker = ? AND date(timestamp) = ?
			ORDER BY timestamp DESC
		"""
		rows = cursor.execute(query, (ticker, today)).fetchall()

		trades = []
		for row in rows:
			trades.append({
				'id': row[0],
				'timestamp': row[1],
				'decision': row[2],
				'confidence': row[3],
				'allocation_pct': row[4],
				'reasoning': row[5],
				'action_taken': row[6],
				'executed_price': row[7],
				'quantity': row[8]
			})

		return trades

	except Exception as e:
		logger.error(f"Error retrieving today's trades: {e}")
		return []
	finally:
		conn.close()


def get_best_parameters_json(ticker, asset_class):
	"""
	Retrieves best parameters as raw JSON string (unparsed).

	Args:
		ticker: Ticker symbol (e.g., 'SOL/USD')
		asset_class: Asset class (e.g., 'STOCK', 'CRYPTO')

	Returns:
		Tuple of (ticker, strategy_name, parameters_json) or None if not found.
	"""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		query = """
			SELECT ticker, strategy_name, parameters
			FROM best_parameters
			WHERE asset_class = ? AND is_active = 1 AND ticker = ?
		"""
		result = cursor.execute(query, (asset_class, ticker)).fetchone()

		if result:
			ticker_val, strategy_name, params_json = result
			logger.info(f"Retrieved JSON parameters for {ticker_val} ({asset_class})")
			return {
				'ticker': ticker_val,
				'strategy_name': strategy_name,
				'parameters': params_json,
				'parameters_dict': json.loads(params_json) if params_json else {}
			}

		logger.warning(f"No parameters found for {ticker} ({asset_class})")
		return None

	except Exception as e:
		logger.error(f"Error fetching parameters JSON: {e}")
		return None
	finally:
		conn.close()


def save_best_parameters(ticker, parameters, asset_class='crypto', strategy_name='ai_trader_gemini', is_active=1):
	"""
	Saves or updates the best parameters for a ticker.

	Args:
		ticker: Ticker symbol
		parameters: Dict of parameters or JSON string
		asset_class: Asset class (e.g., 'STOCK', 'CRYPTO')
		strategy_name: Strategy name
		is_active: Whether parameters are active (1) or inactive (0)
	"""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		if isinstance(parameters, dict):
			params_json = json.dumps(parameters)
		else:
			params_json = parameters

		cursor.execute("""
			INSERT INTO best_parameters (ticker, asset_class, strategy_name, parameters, is_active, last_updated)
			VALUES (?, ?, ?, ?, ?, ?)
			ON CONFLICT(ticker, asset_class) DO UPDATE SET
				strategy_name = excluded.strategy_name,
				parameters = excluded.parameters,
				is_active = excluded.is_active,
				last_updated = excluded.last_updated
		""", (
			ticker, asset_class, strategy_name, params_json, is_active, datetime.now().isoformat()
		))
		conn.commit()
		logger.info(f"Saved best parameters for {ticker} ({asset_class}): is_active={is_active}")

	except Exception as e:
		logger.error(f"Failed to save best parameters: {e}")
	finally:
		conn.close()


if __name__ == "__main__":
	setup_database()
	params = get_best_parameters("SOL/USD")
	print(f"SOL/USD Parameters: {params}")
