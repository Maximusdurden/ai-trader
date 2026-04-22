#!/usr/bin/env python3
"""
Setup multiple tickers with different strategies and parameters.
Run once to populate initial trading tickers.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.database import setup_database, save_best_parameters

def setup_tickers():
	"""Add multiple tickers with various strategies."""
	setup_database()

	# Define tickers with their parameters
	tickers = [
		{
			"ticker": "SOL/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 12,
				"slow_ema": 26,
				"trailing_stop": 2.0,
				"decision_interval": 300,
				"pnl_trigger_pct": 3.0
			}
		},
		{
			"ticker": "BTC/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 12,
				"slow_ema": 26,
				"trailing_stop": 1.5,
				"decision_interval": 600,
				"pnl_trigger_pct": 2.5
			}
		},
		{
			"ticker": "ETH/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 10,
				"slow_ema": 20,
				"trailing_stop": 2.5,
				"decision_interval": 300,
				"pnl_trigger_pct": 3.5
			}
		},
		{
			"ticker": "DOGE/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 5,
				"slow_ema": 15,
				"trailing_stop": 3.0,
				"decision_interval": 300,
				"pnl_trigger_pct": 4.0
			}
		},
		{
			"ticker": "XRP/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 12,
				"slow_ema": 26,
				"trailing_stop": 2.0,
				"decision_interval": 300,
				"pnl_trigger_pct": 3.0
			}
		},
		{
			"ticker": "ADA/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 12,
				"slow_ema": 26,
				"trailing_stop": 2.5,
				"decision_interval": 300,
				"pnl_trigger_pct": 3.5
			}
		},
		{
			"ticker": "AVAX/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 10,
				"slow_ema": 20,
				"trailing_stop": 2.0,
				"decision_interval": 300,
				"pnl_trigger_pct": 3.0
			}
		},
		{
			"ticker": "LINK/USD",
			"strategy": "ema_crossover",
			"params": {
				"fast_ema": 12,
				"slow_ema": 26,
				"trailing_stop": 2.5,
				"decision_interval": 300,
				"pnl_trigger_pct": 3.5
			}
		},
	]

	print("=" * 60)
	print("[*] ADDING TICKERS TO DATABASE")
	print("=" * 60 + "\n")

	for ticker_config in tickers:
		ticker = ticker_config["ticker"]
		strategy = ticker_config["strategy"]
		params = ticker_config["params"]

		save_best_parameters(
			ticker=ticker,
			parameters=params,
			asset_class="CRYPTO",
			strategy_name=strategy,
			is_active=1
		)

		print("[OK] {}".format(ticker))
		print("   Strategy: {}".format(strategy))
		print("   EMA: {}/{}".format(params['fast_ema'], params['slow_ema']))
		print("   Stop: {}% | Trigger: {}%\n".format(params['trailing_stop'], params['pnl_trigger_pct']))

	print("=" * 60)
	print("[OK] ADDED {} TICKERS".format(len(tickers)))
	print("=" * 60)
	print("\n[*] Ready to trade! Run: python startup.py\n")

if __name__ == "__main__":
	setup_tickers()
