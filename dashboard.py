"""Real-time trading dashboard for day traders."""

import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from core.database import (
	get_db_connection,
	get_tickers_from_best_parameters,
	get_best_parameters_json
)
from core.api import get_trading_client, get_available_cash, get_latest_crypto_data

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_account_metrics():
	"""Fetch current account metrics from Alpaca."""
	try:
		client = get_trading_client(paper_trading=True)
		account = client.get_account()
		return {
			'equity': float(account.equity),
			'cash': float(account.cash),
			'buying_power': float(account.buying_power),
			'portfolio_value': float(account.portfolio_value),
			'daily_pl': float(account.unrealized_pl) if hasattr(account, 'unrealized_pl') else 0,
			'daily_pl_pct': (float(account.unrealized_pl) / float(account.portfolio_value) * 100) if hasattr(account, 'unrealized_pl') and float(account.portfolio_value) > 0 else 0,
			'trading_halted': account.trading_halted
		}
	except Exception as e:
		logger.error(f"Error fetching account metrics: {e}")
		return {}


def get_positions():
	"""Fetch current open positions."""
	try:
		client = get_trading_client(paper_trading=True)
		positions = client.get_all_positions()

		position_list = []
		for pos in positions:
			try:
				current_price = float(pos.current_price) if pos.current_price else 0
				qty = float(pos.qty)
				market_value = float(pos.market_value) if pos.market_value else 0
				unrealized_pl = float(pos.unrealized_pl) if pos.unrealized_pl else 0
				unrealized_plpc = float(pos.unrealized_plpc) if pos.unrealized_plpc else 0

				position_list.append({
					'symbol': pos.symbol,
					'qty': qty,
					'entry_price': float(pos.avg_fill_price) if pos.avg_fill_price else 0,
					'current_price': current_price,
					'market_value': market_value,
					'unrealized_pl': unrealized_pl,
					'unrealized_pl_pct': unrealized_plpc * 100,
					'side': 'LONG' if qty > 0 else 'SHORT'
				})
			except Exception as e:
				logger.error(f"Error processing position {pos.symbol}: {e}")
				continue

		return position_list
	except Exception as e:
		logger.error(f"Error fetching positions: {e}")
		return []


def get_today_trades():
	"""Fetch trades from today's trade log."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		today = datetime.now().strftime('%Y-%m-%d')
		query = """
			SELECT ticker, timestamp, action, confidence, allocation_pct, reasoning,
					trigger_type, ema_signal, execution_status, executed_price, quantity
			FROM trade_log
			WHERE DATE(timestamp) = ? AND action IN ('BUY', 'SELL')
			ORDER BY timestamp DESC
			LIMIT 20
		"""
		rows = cursor.execute(query, (today,)).fetchall()

		trades = []
		for row in rows:
			trades.append({
				'ticker': row[0],
				'timestamp': row[1],
				'action': row[2],
				'confidence': row[3],
				'allocation_pct': row[4],
				'reasoning': row[5][:100] + '...' if len(row[5] or '') > 100 else row[5],
				'trigger_type': row[6],
				'ema_signal': row[7],
				'execution_status': row[8],
				'executed_price': row[9],
				'quantity': row[10]
			})

		return trades
	except Exception as e:
		logger.error(f"Error fetching today's trades: {e}")
		return []
	finally:
		conn.close()


def get_daily_stats():
	"""Calculate daily trading statistics."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		today = datetime.now().strftime('%Y-%m-%d')

		# Total trades
		cursor.execute(
			"SELECT COUNT(*) FROM trade_log WHERE DATE(timestamp) = ? AND action IN ('BUY', 'SELL')",
			(today,)
		)
		total_trades = cursor.fetchone()[0]

		# Win count (executed sell with profit)
		cursor.execute("""
			SELECT COUNT(*) FROM trade_log
			WHERE DATE(timestamp) = ? AND action = 'SELL' AND executed_price > 0
		""", (today,))
		executed_sells = cursor.fetchone()[0]

		# Average confidence
		cursor.execute(
			"SELECT AVG(confidence) FROM trade_log WHERE DATE(timestamp) = ? AND confidence > 0",
			(today,)
		)
		avg_confidence = cursor.fetchone()[0] or 0

		return {
			'total_trades': total_trades,
			'executed_sells': executed_sells,
			'avg_confidence': round(avg_confidence, 1),
			'win_rate': (executed_sells / total_trades * 100) if total_trades > 0 else 0
		}
	except Exception as e:
		logger.error(f"Error calculating daily stats: {e}")
		return {'total_trades': 0, 'executed_sells': 0, 'avg_confidence': 0, 'win_rate': 0}
	finally:
		conn.close()


def get_active_tickers():
	"""Get all active tickers with current status."""
	try:
		tickers = get_tickers_from_best_parameters()
		ticker_status = []

		# Get latest prices
		if tickers:
			try:
				# Separate crypto and stock tickers for appropriate API calls
				crypto_tickers = [t for t in tickers if '/' in t]
				stock_tickers = [t for t in tickers if '/' not in t]
				quotes = {}

				if crypto_tickers:
					crypto_quotes = get_latest_crypto_data(crypto_tickers)
					quotes.update(crypto_quotes)

				# Stock tickers would need a different API - for now just return 0 price
				for stock in stock_tickers:
					quotes[stock] = None

				for ticker in tickers:
					quote = quotes.get(ticker)
					price = 0
					if quote and hasattr(quote, 'ask_price'):
						price = float(quote.ask_price)

					# Get strategy directly from database
					conn = get_db_connection()
					cursor = conn.cursor()
					result = cursor.execute(
						"SELECT strategy_name FROM best_parameters WHERE ticker = ? AND is_active = 1",
						(ticker,)
					).fetchone()
					conn.close()

					strategy = result[0] if result else 'unknown'

					ticker_status.append({
						'ticker': ticker,
						'price': price,
						'strategy': strategy,
						'status': 'active'
					})
			except Exception as e:
				logger.error(f"Error fetching quotes: {e}")
				for ticker in tickers:
					conn = get_db_connection()
					cursor = conn.cursor()
					result = cursor.execute(
						"SELECT strategy_name FROM best_parameters WHERE ticker = ? AND is_active = 1",
						(ticker,)
					).fetchone()
					conn.close()
					strategy = result[0] if result else 'unknown'

					ticker_status.append({
						'ticker': ticker,
						'price': 0,
						'strategy': strategy,
						'status': 'error'
					})

		return ticker_status
	except Exception as e:
		logger.error(f"Error getting active tickers: {e}")
		return []


def get_recent_news():
	"""Get recent market news that triggered decisions."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		query = """
			SELECT DISTINCT ticker, timestamp, trigger_type, reasoning
			FROM trade_log
			WHERE trigger_type = 'breaking_news' AND reasoning IS NOT NULL
			ORDER BY timestamp DESC
			LIMIT 10
		"""
		rows = cursor.execute(query).fetchall()

		news = []
		for row in rows:
			news.append({
				'ticker': row[0],
				'timestamp': row[1],
				'trigger_type': row[2],
				'reason': row[3][:150] + '...' if len(row[3] or '') > 150 else row[3]
			})

		return news
	except Exception as e:
		logger.error(f"Error fetching recent news: {e}")
		return []
	finally:
		conn.close()


def get_all_traded_tickers():
	"""Get all tickers that have been traded with statistics."""
	conn = get_db_connection()
	cursor = conn.cursor()

	try:
		query = """
			SELECT DISTINCT ticker FROM trade_log WHERE action IN ('BUY', 'SELL')
			ORDER BY ticker ASC
		"""
		rows = cursor.execute(query).fetchall()
		tickers = [row[0] for row in rows]

		ticker_stats = []
		for ticker in tickers:
			# Get stats for this ticker
			stats_query = """
				SELECT
					COUNT(*) as total_trades,
					SUM(CASE WHEN action = 'BUY' THEN 1 ELSE 0 END) as buy_count,
					SUM(CASE WHEN action = 'SELL' THEN 1 ELSE 0 END) as sell_count,
					AVG(confidence) as avg_confidence
				FROM trade_log
				WHERE ticker = ? AND action IN ('BUY', 'SELL')
			"""
			stats = cursor.execute(stats_query, (ticker,)).fetchone()

			ticker_stats.append({
				'ticker': ticker,
				'total_trades': stats[0] or 0,
				'buy_count': stats[1] or 0,
				'sell_count': stats[2] or 0,
				'avg_confidence': round(stats[3] or 0, 1)
			})

		return ticker_stats
	except Exception as e:
		logger.error(f"Error fetching traded tickers: {e}")
		return []
	finally:
		conn.close()


@app.route('/')
def dashboard():
	"""Serve dashboard HTML."""
	return render_template('dashboard.html')


@app.route('/api/metrics')
def api_metrics():
	"""API endpoint for account metrics."""
	return jsonify(get_account_metrics())


@app.route('/api/positions')
def api_positions():
	"""API endpoint for current positions."""
	return jsonify(get_positions())


@app.route('/api/trades')
def api_trades():
	"""API endpoint for today's trades."""
	return jsonify(get_today_trades())


@app.route('/api/stats')
def api_stats():
	"""API endpoint for daily statistics."""
	return jsonify(get_daily_stats())


@app.route('/api/tickers')
def api_tickers():
	"""API endpoint for active tickers."""
	return jsonify(get_active_tickers())


@app.route('/api/news')
def api_news():
	"""API endpoint for recent news."""
	return jsonify(get_recent_news())


@app.route('/api/traded-tickers')
def api_traded_tickers():
	"""API endpoint for all tickers that have been traded."""
	return jsonify(get_all_traded_tickers())


@app.route('/api/dashboard')
def api_dashboard():
	"""Combined endpoint for all dashboard data."""
	return jsonify({
		'metrics': get_account_metrics(),
		'positions': get_positions(),
		'trades': get_today_trades(),
		'stats': get_daily_stats(),
		'active_tickers': get_active_tickers(),
		'traded_tickers': get_all_traded_tickers(),
		'recent_news': get_recent_news(),
		'timestamp': datetime.now().isoformat()
	})


if __name__ == '__main__':
	logger.info("Starting Trading Dashboard on http://localhost:5000")
	app.run(debug=True, host='0.0.0.0', port=5000)
