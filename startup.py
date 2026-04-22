#!/usr/bin/env python3
"""
AI Trader Bootstrap - Start all services (bot + dashboard)

Usage:
    python startup.py              # Start all services
    python startup.py --bot-only   # Start only the trading bot
    python startup.py --dashboard-only  # Start only the dashboard
"""

import subprocess
import sys
import time
import logging
import signal
import os
from datetime import datetime

# Setup logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - [%(levelname)s] - %(message)s'
)
logger = logging.getLogger(__name__)

# Process references
processes = {}


def start_bot():
	"""Start the trading bot (main_hybrid.py)."""
	logger.info("🤖 Starting AI Trading Bot (main_hybrid.py)...")
	try:
		process = subprocess.Popen(
			[sys.executable, 'main_hybrid.py'],
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1
		)
		processes['bot'] = process
		logger.info("✅ Trading Bot started (PID: %d)" % process.pid)
		return process
	except Exception as e:
		logger.error(f"❌ Failed to start bot: {e}")
		return None


def start_dashboard():
	"""Start the web dashboard (dashboard.py)."""
	logger.info("📊 Starting Dashboard (dashboard.py)...")
	try:
		process = subprocess.Popen(
			[sys.executable, 'dashboard.py'],
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			text=True,
			bufsize=1
		)
		processes['dashboard'] = process
		logger.info("✅ Dashboard started (PID: %d)" % process.pid)
		logger.info("   🌐 Open http://localhost:5000 in your browser")
		return process
	except Exception as e:
		logger.error(f"❌ Failed to start dashboard: {e}")
		return None


def handle_shutdown(signum, frame):
	"""Handle graceful shutdown on Ctrl+C."""
	logger.info("\n⚠️  Shutting down services...")
	for service_name, process in processes.items():
		if process and process.poll() is None:
			logger.info(f"   Stopping {service_name}...")
			try:
				process.terminate()
				process.wait(timeout=5)
				logger.info(f"   ✅ {service_name} stopped")
			except subprocess.TimeoutExpired:
				logger.warning(f"   ⚠️  Force killing {service_name}")
				process.kill()
			except Exception as e:
				logger.error(f"   ❌ Error stopping {service_name}: {e}")
	logger.info("✅ All services stopped. Goodbye!")
	sys.exit(0)


def monitor_processes():
	"""Monitor running processes and log their output."""
	import select

	while True:
		# Check if any process has died
		for service_name, process in list(processes.items()):
			if process and process.poll() is not None:
				logger.error(f"⚠️  {service_name} has exited (return code: {process.returncode})")

		# Small sleep to prevent busy waiting
		time.sleep(1)


def run_all():
	"""Start all services."""
	logger.info("=" * 60)
	logger.info("🚀 AI TRADER BOOTSTRAP")
	logger.info("=" * 60)
	logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
	logger.info("")

	# Start services
	bot_process = start_bot()
	time.sleep(2)  # Give bot time to initialize

	dashboard_process = start_dashboard()
	time.sleep(2)  # Give dashboard time to start

	if not bot_process and not dashboard_process:
		logger.error("❌ Failed to start any services!")
		sys.exit(1)

	logger.info("")
	logger.info("=" * 60)
	logger.info("✅ ALL SERVICES RUNNING")
	logger.info("=" * 60)
	logger.info("")
	logger.info("📌 Services:")
	if bot_process:
		logger.info("   🤖 Trading Bot (main_hybrid.py)")
	if dashboard_process:
		logger.info("   📊 Dashboard (http://localhost:5000)")
	logger.info("")
	logger.info("Press Ctrl+C to stop all services")
	logger.info("")

	# Set up signal handler for graceful shutdown
	signal.signal(signal.SIGINT, handle_shutdown)

	# Keep the main process alive and monitor child processes
	try:
		while True:
			time.sleep(1)
			# Check if any critical process died unexpectedly
			for service_name, process in list(processes.items()):
				if process and process.poll() is not None:
					logger.error(f"❌ {service_name} has crashed!")
					logger.info("Run startup.py again to restart services")
					sys.exit(1)
	except KeyboardInterrupt:
		handle_shutdown(None, None)


def run_bot_only():
	"""Start only the trading bot."""
	logger.info("🤖 Starting Trading Bot Only...")
	bot_process = start_bot()
	if not bot_process:
		logger.error("Failed to start bot")
		sys.exit(1)

	signal.signal(signal.SIGINT, handle_shutdown)
	logger.info("Press Ctrl+C to stop")

	try:
		while True:
			time.sleep(1)
			if bot_process.poll() is not None:
				logger.error("Bot process has exited")
				sys.exit(1)
	except KeyboardInterrupt:
		handle_shutdown(None, None)


def run_dashboard_only():
	"""Start only the dashboard."""
	logger.info("📊 Starting Dashboard Only...")
	logger.info("   🌐 Open http://localhost:5000 in your browser")
	dashboard_process = start_dashboard()
	if not dashboard_process:
		logger.error("Failed to start dashboard")
		sys.exit(1)

	signal.signal(signal.SIGINT, handle_shutdown)
	logger.info("Press Ctrl+C to stop")

	try:
		while True:
			time.sleep(1)
			if dashboard_process.poll() is not None:
				logger.error("Dashboard process has exited")
				sys.exit(1)
	except KeyboardInterrupt:
		handle_shutdown(None, None)


if __name__ == '__main__':
	# Check for command line arguments
	if len(sys.argv) > 1:
		arg = sys.argv[1].lower()
		if arg == '--bot-only':
			run_bot_only()
		elif arg == '--dashboard-only':
			run_dashboard_only()
		elif arg in ['--help', '-h']:
			print(__doc__)
			sys.exit(0)
		else:
			print(f"Unknown argument: {arg}")
			print(__doc__)
			sys.exit(1)
	else:
		# Default: run all services
		run_all()
