import logging
import threading
import time
from alpaca.data.live import CryptoDataStream, NewsDataStream
from alpaca.trading.stream import TradingStream

logger = logging.getLogger(__name__)


class TriggerEngine:
	"""
	Evaluates ticker state and fires decision triggers.
	Decides when to call Gemini based on events.
	"""

	def __init__(self, ticker_states, decision_callback):
		"""
		Args:
			ticker_states: dict {ticker: TickerState}
			decision_callback: function(ticker, state, trigger_type) to call when triggering
		"""
		self.ticker_states = ticker_states
		self.decision_callback = decision_callback

	def on_bar(self, bar):
		"""Called when a new bar arrives from CryptoDataStream."""
		ticker = bar.symbol
		if ticker not in self.ticker_states:
			return

		state = self.ticker_states[ticker]
		state.update_bar(bar)

		# Check if we can trigger (respects decision_interval cooldown)
		if not state.can_trigger_decision():
			return

		# Check 1: EMA crossover
		crossover = state.detect_ema_crossover()
		if crossover:
			logger.info(f"[{ticker}] EMA crossover detected: {crossover.upper()}")
			state.record_trigger()
			self.decision_callback(ticker, state, trigger_type='ema_crossover')
			return

		# Check 2: PnL threshold
		if state.check_pnl_threshold():
			logger.info(f"[{ticker}] PnL threshold triggered: {state.unrealized_pnl_pct:.2f}%")
			state.record_trigger()
			self.decision_callback(ticker, state, trigger_type='pnl_threshold')
			return

	def on_news(self, news):
		"""Called when news arrives from NewsDataStream. Always triggers."""
		ticker = news.symbols[0] if news.symbols else None
		if not ticker:
			return

		# Convert ticker format if needed (news uses base symbol, not /USD)
		if ticker not in self.ticker_states:
			ticker_full = ticker + '/USD'
			if ticker_full in self.ticker_states:
				ticker = ticker_full

		if ticker not in self.ticker_states:
			return

		state = self.ticker_states[ticker]
		state.update_news(news)

		# News always triggers (urgent)
		logger.info(f"[{ticker}] Breaking news: {news.headline[:50]}...")
		state.record_trigger()
		self.decision_callback(ticker, state, trigger_type='breaking_news')

	def on_fill(self, fill_event):
		"""Called when order fill arrives from TradingStream."""
		ticker = fill_event.symbol
		if ticker not in self.ticker_states:
			return

		state = self.ticker_states[ticker]
		state.update_position(fill_event)
		logger.info(f"[{ticker}] Order filled: {fill_event.side.upper()} {fill_event.qty} @ ${fill_event.price}")


def start_streams(ticker_states, trigger_engine, api_key, api_secret, paper=True):
	"""
	Starts three WebSocket streams in separate daemon threads.

	Args:
		ticker_states: dict {ticker: TickerState}
		trigger_engine: TriggerEngine instance
		api_key: Alpaca API key
		api_secret: Alpaca API secret
		paper: True for paper trading, False for live
	"""

	# Prepare ticker lists
	crypto_tickers = list(ticker_states.keys())
	news_symbols = [t.replace('/USD', '') for t in crypto_tickers]  # news uses base symbol

	# Stream 1: Crypto bars
	def run_crypto_stream():
		try:
			logger.info(f"Starting CryptoDataStream for {len(crypto_tickers)} tickers")
			crypto_stream = CryptoDataStream(api_key, api_secret)
			crypto_stream.subscribe_bars(trigger_engine.on_bar, *crypto_tickers)
			crypto_stream.run()
		except Exception as e:
			logger.error(f"CryptoDataStream error: {e}", exc_info=True)

	# Stream 2: News
	def run_news_stream():
		try:
			logger.info(f"Starting NewsDataStream for {len(news_symbols)} symbols")
			news_stream = NewsDataStream(api_key, api_secret)
			news_stream.subscribe_news(trigger_engine.on_news, *news_symbols)
			news_stream.run()
		except Exception as e:
			logger.error(f"NewsDataStream error: {e}", exc_info=True)

	# Stream 3: Trade updates
	def run_trading_stream():
		try:
			logger.info("Starting TradingStream for fill/position updates")
			trade_stream = TradingStream(api_key, api_secret, paper=paper)
			trade_stream.subscribe_trade_updates(trigger_engine.on_fill)
			trade_stream.run()
		except Exception as e:
			logger.error(f"TradingStream error: {e}", exc_info=True)

	# Start all streams in daemon threads
	threads = [
		threading.Thread(target=run_crypto_stream, name='CryptoStream', daemon=True),
		threading.Thread(target=run_news_stream, name='NewsStream', daemon=True),
		threading.Thread(target=run_trading_stream, name='TradingStream', daemon=True),
	]

	for t in threads:
		t.start()
		time.sleep(0.5)  # Slight delay to avoid connection race conditions

	logger.info("All WebSocket streams started")

	return threads
