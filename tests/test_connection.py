import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.api import get_account_info, get_trading_client
from core.brain import evaluate_asset
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_connection():
	"""Test Alpaca and Gemini API connections."""
	print("\n" + "="*60)
	print("[*] AI TRADER CONNECTION TEST")
	print("="*60 + "\n")

	# Test Alpaca connection
	try:
		logger.info("[1/3] Testing Alpaca connection...")
		client = get_trading_client(paper_trading=True)
		account = client.get_account()
		print(f"[OK] Connected to Alpaca!")
		print(f"   Account ID: {account.id}")
		print(f"   Status: {account.status}")
		print(f"   Equity: ${float(account.equity):.2f}")
		print(f"   Cash: ${float(account.cash):.2f}")
		print(f"   Buying Power: ${float(account.buying_power):.2f}\n")
	except Exception as e:
		print(f"[ERR] Alpaca connection failed: {e}\n")
		return False

	# Test Gemini connection
	try:
		logger.info("[2/3] Testing Gemini API...")
		decision = evaluate_asset(
			"SOL/USD",
			"Test context: Current price $100, EMA signal BULLISH",
			"ema_crossover",
			{"fast_ema": 12, "slow_ema": 26}
		)
		print(f"[OK] Gemini API responsive!")
		print(f"   Action: {decision.get('action')}")
		print(f"   Confidence: {decision.get('confidence')}%")
		print(f"   Reasoning: {decision.get('reasoning')[:60]}...\n")
	except Exception as e:
		print(f"[ERR] Gemini API failed: {e}\n")
		return False

	print("="*60)
	print("[OK] ALL CONNECTIONS OK - Ready to run startup.py!")
	print("="*60 + "\n")
	return True

if __name__ == "__main__":
	success = test_connection()
	sys.exit(0 if success else 1)
