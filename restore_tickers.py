#!/usr/bin/env python3
"""Restore your original tickers to the database."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.database import setup_database, save_best_parameters
import json

def restore_tickers():
	"""Restore your original trading tickers."""
	setup_database()

	tickers = [
		("AMD", "opening_range_breakout", {"trailing_stop_percent": 0.05, "orb_period_minutes": 30, "take_profit_percent": 0.05, "intraday_timeframe": "1Hour", "lookback_days": 5}),
		("BTC/USD", "full_featured_ema_crossover", {"fast_ema": 19, "slow_ema": 27, "trailing_stop_percent": 0.04, "intraday_timeframe": "1Hour", "lookback_days": 9}),
		("ETH/USD", "full_featured_ema_crossover", {"fast_ema": 18, "slow_ema": 22, "trailing_stop_percent": 0.04, "intraday_timeframe": "1Hour", "lookback_days": 9}),
		("GOOG", "solana_strategy", {"fast_ema": 9, "slow_ema": 21, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("META", "solana_strategy", {"fast_ema": 15, "slow_ema": 21, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("MSFT", "solana_strategy", {"fast_ema": 9, "slow_ema": 21, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("MU", "solana_strategy", {"fast_ema": 15, "slow_ema": 33, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("NVDA", "solana_strategy", {"fast_ema": 9, "slow_ema": 33, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("QQQ", "solana_strategy", {"fast_ema": 15, "slow_ema": 33, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("RUN", "solana_strategy", {"fast_ema": 9, "slow_ema": 21, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("SOL/USD", "full_featured_ema_crossover", {"fast_ema": 19, "slow_ema": 33, "trailing_stop_percent": 0.04, "intraday_timeframe": "1Hour", "lookback_days": 9}),
		("SPY", "solana_strategy", {"fast_ema": 15, "slow_ema": 33, "trailing_stop_percent": 0.03, "adx_threshold": 25, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("TSLA", "solana_strategy", {"fast_ema": 9, "slow_ema": 33, "trailing_stop_percent": 0.03, "adx_threshold": 30, "intraday_timeframe": "1Hour", "lookback_days": 45}),
		("XRP/USD", "solana_strategy", {"fast_ema": 9, "slow_ema": 33, "trailing_stop_percent": 0.03, "adx_threshold": 20, "intraday_timeframe": "1Hour", "lookback_days": 9}),
	]

	print("=" * 60)
	print("[*] RESTORING YOUR ORIGINAL TICKERS")
	print("=" * 60 + "\n")

	for ticker, strategy, params in tickers:
		save_best_parameters(
			ticker=ticker,
			parameters=params,
			asset_class="STOCK" if not "/" in ticker else "CRYPTO",
			strategy_name=strategy,
			is_active=1
		)
		print(f"[OK] {ticker:10} | {strategy:30} | EMA: {params.get('fast_ema', 'N/A')}/{params.get('slow_ema', 'N/A')}")

	print("\n" + "=" * 60)
	print(f"[OK] RESTORED {len(tickers)} TICKERS")
	print("=" * 60)
	print("\n[*] Run: python startup.py\n")

if __name__ == "__main__":
	restore_tickers()
