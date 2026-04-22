import logging
import pandas as pd
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)


class TickerState:
	"""
	Maintains live in-memory state for a single ticker.
	Updated by WebSocket events (bars, news, fills).
	"""

	def __init__(self, ticker, params):
		self.ticker = ticker
		self.params = params

		# Strategy parameters
		self.fast_ema_period = params.get('fast_ema', 12)
		self.slow_ema_period = params.get('slow_ema', 26)
		self.decision_interval = params.get('decision_interval', 300)  # seconds
		self.pnl_trigger_pct = params.get('pnl_trigger_pct', 3.0)

		# Rolling bar buffer (max 250 bars for EMA(200) warmup)
		self.rolling_bars = deque(maxlen=250)
		self.latest_bar = None

		# EMA state
		self.ema_fast = None
		self.ema_slow = None
		self.ema_fast_prev = None
		self.ema_slow_prev = None
		self.ema_signal = None  # 'BULLISH' or 'BEARISH'

		# Position state
		self.position_qty = 0.0
		self.entry_price = 0.0
		self.unrealized_pnl = 0.0
		self.unrealized_pnl_pct = 0.0
		self.last_known_price = 0.0
		self.pnl_at_last_trigger = 0.0  # PnL when we last triggered

		# News
		self.recent_news = []  # list of dicts: {timestamp, headline, summary}

		# Rate limiting
		self.last_decision_at = None  # datetime of last Gemini call
		self.last_pnl_trigger_pct = 0.0  # avoid re-triggering on same PnL level

		# Account
		self.cash = 0.0

		logger.info(f"[{ticker}] TickerState initialized: EMA({self.fast_ema_period},{self.slow_ema_period}), interval={self.decision_interval}s, pnl_trigger={self.pnl_trigger_pct}%")

	def update_bar(self, bar):
		"""Update with a new 15-min bar. Recalculate EMAs."""
		self.latest_bar = bar
		self.rolling_bars.append(bar)
		self.last_known_price = bar.close

		# Recalculate EMAs on HLC3
		if len(self.rolling_bars) >= self.slow_ema_period:
			df = pd.DataFrame([{
				'high': b.high,
				'low': b.low,
				'close': b.close
			} for b in self.rolling_bars])

			df['HLC3'] = (df['high'] + df['low'] + df['close']) / 3
			df[f'EMA_{self.fast_ema_period}'] = df['HLC3'].ewm(span=self.fast_ema_period, adjust=False).mean()
			df[f'EMA_{self.slow_ema_period}'] = df['HLC3'].ewm(span=self.slow_ema_period, adjust=False).mean()

			# Save prev values before updating current
			if self.ema_fast is not None:
				self.ema_fast_prev = self.ema_fast
				self.ema_slow_prev = self.ema_slow

			self.ema_fast = df.iloc[-1][f'EMA_{self.fast_ema_period}']
			self.ema_slow = df.iloc[-1][f'EMA_{self.slow_ema_period}']
			self.ema_signal = "BULLISH" if self.ema_fast > self.ema_slow else "BEARISH"

	def update_position(self, fill_event):
		"""Update with trade fill event from TradingStream."""
		self.position_qty = float(fill_event.qty) if fill_event.side == 'buy' else -float(fill_event.qty)
		self.entry_price = float(fill_event.price)
		self._update_pnl()
		logger.info(f"[{self.ticker}] Position updated: qty={self.position_qty}, entry=${self.entry_price:.2f}")

	def update_news(self, news_item):
		"""Add a news item. Keep most recent 5."""
		self.recent_news.insert(0, {
			'timestamp': news_item.created_at,
			'headline': news_item.headline,
			'summary': news_item.summary[:100] if news_item.summary else ''
		})
		self.recent_news = self.recent_news[:5]

	def _update_pnl(self):
		"""Recalculate unrealized PnL based on current price and position."""
		if self.position_qty != 0 and self.last_known_price > 0:
			if self.position_qty > 0:
				pnl = (self.last_known_price - self.entry_price) * self.position_qty
			else:
				pnl = (self.entry_price - self.last_known_price) * abs(self.position_qty)

			self.unrealized_pnl = pnl
			self.unrealized_pnl_pct = (pnl / (self.entry_price * abs(self.position_qty))) * 100 if self.entry_price > 0 else 0
		else:
			self.unrealized_pnl = 0.0
			self.unrealized_pnl_pct = 0.0

	def can_trigger_decision(self):
		"""Check if enough time has passed since last decision (respects cooldown)."""
		if self.last_decision_at is None:
			return True

		elapsed = (datetime.now() - self.last_decision_at).total_seconds()
		return elapsed >= self.decision_interval

	def detect_ema_crossover(self):
		"""Check if EMA crossover just happened (bull or bear)."""
		if (self.ema_fast is None or self.ema_slow is None or
		    self.ema_fast_prev is None or self.ema_slow_prev is None):
			return None

		# Bullish: fast crosses above slow
		if self.ema_fast > self.ema_slow and self.ema_fast_prev <= self.ema_slow_prev:
			return 'bullish'

		# Bearish: fast crosses below slow
		if self.ema_fast < self.ema_slow and self.ema_fast_prev >= self.ema_slow_prev:
			return 'bearish'

		return None

	def check_pnl_threshold(self):
		"""Check if unrealized PnL moved more than pnl_trigger_pct since last trigger."""
		if self.position_qty == 0:
			return False

		pnl_change = abs(self.unrealized_pnl_pct - self.last_pnl_trigger_pct)
		return pnl_change >= self.pnl_trigger_pct

	def record_trigger(self):
		"""Record when a trigger was evaluated (for rate limiting)."""
		self.last_decision_at = datetime.now()
		self.last_pnl_trigger_pct = self.unrealized_pnl_pct

	def build_context(self):
		"""Compile context string for Gemini (same format as current main.py)."""
		position_status = (
			f"Position: {self.position_qty} units, PNL: ${self.unrealized_pnl:.2f} ({self.unrealized_pnl_pct:.2f}%)"
			if self.position_qty != 0
			else "No open position."
		)

		tech_str = f"""
	Latest Price: {self.last_known_price:.2f}
	EMA({self.fast_ema_period}): {self.ema_fast:.2f if self.ema_fast else 'N/A'}
	EMA({self.slow_ema_period}): {self.ema_slow:.2f if self.ema_slow else 'N/A'}
	EMA Signal: {self.ema_signal if self.ema_signal else 'N/A'}
		"""

		news_str = "\n".join([
			f"- {n['timestamp']}: {n['headline']} ({n['summary']}...)"
			for n in self.recent_news[:3]
		]) if self.recent_news else "No recent news."

		context = f"""
	TICKER: {self.ticker}
	STRATEGY: {self.params.get('strategy_name', 'unknown')}
	STRATEGY PARAMETERS:
	- EMA Fast Period: {self.fast_ema_period}
	- EMA Slow Period: {self.slow_ema_period}
	- Trailing Stop: {self.params.get('trailing_stop', 2.0)}%

	CURRENT STATUS: {position_status}
	CASH AVAILABLE: ${self.cash:.2f}

	TECHNICAL ANALYSIS:
	{tech_str}

	RECENT NEWS:
	{news_str}
		"""

		return context
