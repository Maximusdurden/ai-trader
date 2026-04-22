#!/usr/bin/env python3
"""Remove unwanted tickers from database."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.database import get_db_connection

def cleanup_tickers():
	"""Remove unwanted crypto tickers."""
	conn = get_db_connection()
	cursor = conn.cursor()

	# Tickers to remove
	tickers_to_remove = ['ADA/USD', 'AVAX/USD', 'DOGE/USD', 'LINK/USD']

	print("=" * 60)
	print("[*] REMOVING UNWANTED TICKERS")
	print("=" * 60 + "\n")

	for ticker in tickers_to_remove:
		cursor.execute("DELETE FROM best_parameters WHERE ticker = ?", (ticker,))
		print(f"[OK] Removed {ticker}")

	conn.commit()
	conn.close()

	print("\n" + "=" * 60)
	print(f"[OK] REMOVED {len(tickers_to_remove)} TICKERS")
	print("=" * 60 + "\n")

if __name__ == "__main__":
	cleanup_tickers()
