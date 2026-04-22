#!/usr/bin/env python3
"""
Quick setup script to add a ticker to the database.
Run this once to configure which tickers the bot should trade.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.database import setup_database, save_best_parameters

def setup_default_ticker():
	"""Add SOL/USD as the default trading ticker."""
	setup_database()

	params = {
		"fast_ema": 12,
		"slow_ema": 26,
		"trailing_stop": 2.0,
		"decision_interval": 300,    # 5 minutes between decisions
		"pnl_trigger_pct": 3.0       # Trigger on ±3% PnL move
	}

	save_best_parameters(
		ticker="SOL/USD",
		parameters=params,
		asset_class="CRYPTO",
		strategy_name="ema_crossover",
		is_active=1
	)

	print("[OK] Added SOL/USD to trading parameters")
	print(f"   Strategy: ema_crossover")
	print(f"   EMA: fast=12, slow=26")
	print(f"   Trailing stop: 2.0%")
	print(f"   Decision interval: 5 minutes")
	print("\n[*] Now run: python startup.py")

if __name__ == "__main__":
	setup_default_ticker()
