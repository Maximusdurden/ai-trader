# filename: core/api.py

import os
import re
import time
import logging
import pytz
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, timedelta
from google.cloud import storage

def get_gcp_storage_client():
    """Initializes and returns a GCP Storage client using the local key."""
    # Locates the key in the config folder relative to the project root
    key_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "gcp-key.json")
    if os.path.exists(key_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key_path
        return storage.Client()
    else:
        logger.error(f"GCP Key not found at {key_path}")
        return None

def upload_to_gcs(bucket_name, source_file_path, destination_blob_name):
    """Uploads a file to the specified GCP bucket."""
    client = get_gcp_storage_client()
    if not client:
        return False
    
    try:
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_path)
        return True
    except Exception as e:
        logger.error(f"Failed to upload {source_file_path} to GCS: {e}")
        return False
    
# Alpaca Imports
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetAssetsRequest, 
    GetOptionContractsRequest, 
    TrailingStopOrderRequest, 
    StopLimitOrderRequest, 
    GetOrdersRequest, 
    LimitOrderRequest
)
from alpaca.trading.enums import (
    AssetClass, 
    AssetStatus, 
    ContractType, 
    OrderSide, 
    TimeInForce,
    QueryOrderStatus,
    OrderStatus
)
from alpaca.common.exceptions import APIError as TradingAPIError

from alpaca.data.historical import (
    StockHistoricalDataClient, 
    CryptoHistoricalDataClient, 
    OptionHistoricalDataClient,
    NewsClient
)
from alpaca.data.requests import (
    StockBarsRequest, 
    StockLatestQuoteRequest,
    StockLatestTradeRequest, 
    CryptoBarsRequest, 
    CryptoLatestQuoteRequest,
    OptionChainRequest,
    OptionLatestQuoteRequest,
    NewsRequest
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# Load environment variables
load_dotenv()
API_KEY = os.getenv("ALPACA_PAPER_KEY")
API_SECRET = os.getenv("ALPACA_PAPER_SECRET")

# Set up logging
logger = logging.getLogger(__name__)

# Re-export Alpaca enums for use in other modules
__all__ = [
	'OrderSide',
	'TimeInForce',
	'OrderStatus',
	'AssetClass',
	'QueryOrderStatus',
	'TradingAPIError',
	'get_trading_client',
	'get_market_data_client',
	'get_crypto_data_client',
	'get_latest_crypto_data',
	'get_historical_bars',
	'place_order',
	'get_available_cash',
	'get_latest_news',
	'submit_trailing_stop_order',
	'submit_stop_limit_order',
]

# --- CLIENT INITIALIZATION ---

def get_trading_client(paper_trading=True):
    """Initializes and returns an authenticated Alpaca TradingClient."""
    if not API_KEY or not API_SECRET:
        raise ValueError("Alpaca API keys are not set in the .env file.")
    return TradingClient(api_key=API_KEY, secret_key=API_SECRET, paper=paper_trading)

def get_market_data_client():
    if not API_KEY or not API_SECRET:
        raise ValueError("Alpaca API keys are not set in the .env file.")
    return StockHistoricalDataClient(api_key=API_KEY, secret_key=API_SECRET)

def get_crypto_data_client():
    if not API_KEY or not API_SECRET:
        raise ValueError("Alpaca API keys are not set in the .env file.")
    return CryptoHistoricalDataClient(api_key=API_KEY, secret_key=API_SECRET)

def get_option_data_client():
    if not API_KEY or not API_SECRET:
        raise ValueError("Alpaca API keys are not set in the .env file.")
    return OptionHistoricalDataClient(api_key=API_KEY, secret_key=API_SECRET)

def get_news_client():
    if not API_KEY or not API_SECRET:
        raise ValueError('Alpaca API keys are not set in the .env file.')
    return NewsClient(api_key=API_KEY, secret_key=API_SECRET)

def get_latest_news(tickers, limit=5):
    """Fetches recent news for given tickers."""
    client = get_news_client()
    if isinstance(tickers, list): tickers = ','.join(tickers)
    request_params = NewsRequest(symbols=tickers, limit=limit)
    news = client.get_news(request_params)
    return news.data['news']

# --- ACCOUNT & ASSET INFO ---

def get_account_info(paper_trading=True):
    client = get_trading_client(paper_trading)
    return client.get_account()

def get_available_cash(trading_client):
    account = trading_client.get_account()
    # Use non_marginable_buying_power for the most accurate 'spendable' cash
    return float(account.non_marginable_buying_power)

import requests

def fetch_account_metrics(api_key, secret_key, is_paper=True):
    """Fetches real-time account metrics from Alpaca's /v2/account endpoint."""
    base_url = "https://paper-api.alpaca.markets" if is_paper else "https://api.alpaca.markets"
    endpoint = f"{base_url}/v2/account"
    
    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key
    }
    
    response = requests.get(endpoint, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        
        # Helper to safely convert Alpaca's string numbers to floats/ints
        def get_flt(key): return float(data.get(key, 0) or 0)
        def get_int(key): return int(data.get(key, 0) or 0)

        # Map and return the clean metrics
        return {
            "equity": get_flt("equity"),
            "cash": get_flt("cash"),
            "cash_withdrawable": get_flt("cash_withdrawable"),
            "regt_buying_power": get_flt("regt_buying_power"),
            "daytrading_buying_power": get_flt("daytrading_buying_power"),
            "effective_buying_power": get_flt("buying_power"),
            "non_marginable_buying_power": get_flt("non_marginable_buying_power"),
            "initial_margin": get_flt("initial_margin"),
            "maintenance_margin": get_flt("maintenance_margin"),
            "long_market_value": get_flt("long_market_value"),
            "short_market_value": get_flt("short_market_value"),
            "accrued_fees": get_flt("accrued_fees"),
            "pending_transfer_in": get_flt("pending_transfer_in"),
            "pending_transfer_out": get_flt("pending_transfer_out"),
            "daytrade_count": get_int("daytrade_count")
        }
    else:
        print(f"âŒ Error fetching account data: {response.status_code} - {response.text}")
        return None

def get_total_unrealized_pnl():
    try:
        trading_client = get_trading_client()
        positions = trading_client.get_all_positions()
        total_unrealized_pnl = 0.0
        for position in positions:
            try:
                total_unrealized_pnl += float(position.unrealized_intraday_pl)
            except (ValueError, TypeError):
                pass
        return total_unrealized_pnl
    except Exception as e:
        logger.error(f"Error fetching total unrealized P/L: {e}")
        return 0.0

def get_tradable_assets(asset_class=None):
    trading_client = get_trading_client()
    request_params = GetAssetsRequest(
        asset_class=AssetClass.US_EQUITY if asset_class == 'us_equity' else None,
        status=AssetStatus.ACTIVE
    )
    assets = trading_client.get_all_assets(request_params)
    return [asset for asset in assets if asset.tradable]

# --- MARKET DATA WRAPPERS ---

def get_latest_market_data(tickers):
    data_client = get_market_data_client()
    request_params = StockLatestQuoteRequest(symbol_or_symbols=tickers)
    return data_client.get_stock_latest_quote(request_params)

def get_latest_crypto_data(tickers):
    data_client = get_crypto_data_client()
    request_params = CryptoLatestQuoteRequest(symbol_or_symbols=tickers)
    return data_client.get_crypto_latest_quote(request_params)

def get_latest_option_data(symbols):
    data_client = get_option_data_client()
    request_params = OptionLatestQuoteRequest(symbol_or_symbols=symbols)
    return data_client.get_option_latest_quote(request_params)

def get_historical_bars(tickers, timeframe, days_ago=40, limit=None):
    """Fetches historical bar data for a list of tickers."""
    end_date = datetime.now(pytz.utc)
    start_date = end_date - timedelta(days=days_ago)

    if isinstance(timeframe, str):
        unit_map = {
            "min": TimeFrameUnit.Minute, "hour": TimeFrameUnit.Hour,
            "day": TimeFrameUnit.Day, "week": TimeFrameUnit.Week, "month": TimeFrameUnit.Month
        }
        match = re.match(r"(\d+)([a-zA-Z]+)", timeframe, re.I)
        if match:
            amount = int(match.group(1))
            unit = match.group(2).lower()
        else:
            amount = 1
            unit = timeframe.lower()

        if unit not in unit_map:
            raise ValueError(f"Invalid timeframe unit: {unit}")
        timeframe_obj = TimeFrame(amount, unit_map[unit])
    else:
        timeframe_obj = timeframe
    
    first_ticker = tickers[0]
    if '/' in first_ticker or ('_' in first_ticker and first_ticker.endswith('USD')):
        data_client = get_crypto_data_client()
        clean_tickers = [t.replace('_', '/') for t in tickers]
        request_params = CryptoBarsRequest(symbol_or_symbols=clean_tickers, timeframe=timeframe_obj, start=start_date, end=end_date, limit=limit)
        return data_client.get_crypto_bars(request_params).df
    else:
        data_client = get_market_data_client()
        request_params = StockBarsRequest(symbol_or_symbols=tickers, timeframe=timeframe_obj, start=start_date, end=end_date, limit=limit, feed=DataFeed.IEX)
        return data_client.get_stock_bars(request_params).df

def get_option_chain_snapshot(underlying_symbol: str, expiration_date_gte=None, expiration_date_lte=None, strike_price_gte=None, strike_price_lte=None, contract_type=None):
    option_data_client = get_option_data_client()
    request = OptionChainRequest(
        underlying_symbol=underlying_symbol,
        expiration_date_gte=expiration_date_gte,
        expiration_date_lte=expiration_date_lte,
        strike_price_gte=strike_price_gte,
        strike_price_lte=strike_price_lte,
        type=contract_type
    )
    return option_data_client.get_option_chain(request)

# --- ADVANCED HELPERS ---

def format_occ_symbol(raw_symbol):
    """Removes spaces from Option symbols."""
    return raw_symbol.replace(" ", "")

def sync_position_state(trading_client, ticker):
    """Safely gets the current position quantity."""
    api_ticker_clean = ticker.upper().replace("/", "")
    try:
        position = trading_client.get_open_position(api_ticker_clean)
        return float(position.qty)
    except TradingAPIError as e:
        if e.status_code == 404:
            return 0.0
        else:
            logger.error(f"API error during position sync for {ticker}: {e}")
            return 0.0
def get_available_inventory(trading_client, ticker):
    """
    Safely gets the current position quantity MINUS any quantity 
    currently locked up in open SELL orders.
    """
    api_ticker_clean = ticker.upper().replace("/", "")
    
    # 1. Get total owned quantity
    try:
        position = trading_client.get_open_position(api_ticker_clean)
        total_qty = float(position.qty)
    except TradingAPIError as e:
        if getattr(e, 'status_code', None) == 404:
            return 0.0
        else:
            logger.error(f"API error during position sync for {ticker}: {e}")
            return 0.0
    except Exception as e:
        logger.error(f"Error fetching position for {ticker}: {e}")
        return 0.0

    # 2. Subtract quantity locked in open SELL orders
    locked_qty = 0.0
    try:
        req = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            symbols=[api_ticker_clean]
        )
        open_orders = trading_client.get_orders(filter=req)
        for order in open_orders:
            if order.side == OrderSide.SELL:
                locked_qty += float(order.qty)
    except Exception as e:
        logger.error(f"Error fetching open orders for {ticker} inventory check: {e}")
    
    # 3. Return true available inventory
    available_qty = total_qty - locked_qty
    return max(0.0, available_qty)

def fetch_data_with_retries(api_ticker, timeframe, days_ago, retries=3, delay=5):
    """Fetches historical bars with built-in retry logic."""
    for attempt in range(retries):
        try:
            data = get_historical_bars([api_ticker], timeframe=timeframe, days_ago=days_ago)
            if 'symbol' in data.index.names:
                data = data.droplevel('symbol')
            return data
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1}/{retries} failed to fetch data for {api_ticker}: {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    logger.error(f"All {retries} attempts to fetch data for {api_ticker} failed.")
    return pd.DataFrame()

def wait_for_order_fill(trading_client, order_id, timeout_seconds=180):
    """Waits for an order to be filled."""
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        try:
            order = trading_client.get_order_by_id(order_id)
            if order.status == OrderStatus.FILLED:
                logger.info(f"Order {order_id} confirmed as FILLED.")
                return order
            if order.status == OrderStatus.PARTIALLY_FILLED:
                 logger.warning(f"Order {order_id} is PARTIALLY_FILLED. Proceeding.")
                 return order
            elif order.status in [OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED]:
                logger.error(f"Order {order_id} will not be filled. Status: {order.status}")
                return None
            time.sleep(5)
        except Exception as e:
            logger.error(f"Temporary error checking status for order {order_id}: {e}")
            time.sleep(5) 
    
    logger.warning(f"Timeout reached waiting for order {order_id}. Attempting cancel.")
    try:
        order = trading_client.get_order_by_id(order_id)
        if order.status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED]:
            return order
        trading_client.cancel_order_by_id(order_id)
        return None
    except Exception as e:
         logger.error(f"Error during timeout/cancel logic for {order_id}: {e}")
         return None

def get_latest_price(ticker, side: OrderSide = None, stock_tickers_list=None):
    """
    Smartly fetches the latest price based on asset type.
    If side is None, it attempts to fetch the LAST TRADE PRICE (Stable).
    """
    api_ticker_clean = ticker.upper().replace("/", "")
    is_crypto = '/' in ticker
    has_digits = any(c.isdigit() for c in api_ticker_clean)
    is_option = has_digits and not is_crypto
    
    data_object = None
    try:
        if is_crypto:
            data = get_latest_crypto_data([ticker])
            data_object = data.get(ticker)
        elif is_option:
            data = get_latest_option_data([api_ticker_clean])
            data_object = data.get(api_ticker_clean)
        else:
            # --- STOCK LOGIC ---
            if side is None:
                # NEW: Fetch explicit LAST TRADE for stocks to get a real 'price'
                data_client = get_market_data_client()
                req = StockLatestTradeRequest(symbol_or_symbols=[api_ticker_clean])
                data = data_client.get_stock_latest_trade(req)
                data_object = data.get(api_ticker_clean)
            else:
                # Existing behavior: Fetch Quote for Bid/Ask
                data = get_latest_market_data([api_ticker_clean])
                data_object = data.get(api_ticker_clean)
            
    except Exception as e:
        logger.error(f"Failed to fetch market data for {ticker}: {e}")
        return None

    if not data_object: return None
    
    # 1. Requesting Last Trade Price (Stable)
    if side is None:
        return getattr(data_object, 'price', None) or getattr(data_object, 'close', None)

    # 2. Requesting Executable Price (Bid/Ask)
    if is_option:
        return getattr(data_object, 'ask_price', None) if side == OrderSide.BUY else getattr(data_object, 'bid_price', None)
    else:
        if side == OrderSide.BUY:
            return getattr(data_object, 'ask_price', None)
        else:
            return getattr(data_object, 'bid_price', None)

# --- ORDER PLACEMENT WRAPPERS ---

def place_order(trading_client, symbol, side, qty, price_limit, client_order_id=None, time_in_force=None):
    
    # 1. Determine TIF (Priority: Explicit Argument > Symbol Logic)
    if time_in_force:
        tif = time_in_force
    elif '/' in symbol:
        tif = TimeInForce.GTC
    else:
        # Default stocks to DAY if not specified
        tif = TimeInForce.DAY
        
    # 2. Format inputs
    if '/' in symbol:
        rounded_limit_price = price_limit 
        qty_str = f"{qty:.8f}" 
    else:
        rounded_limit_price = round(price_limit, 2)
        qty_str = str(qty)

    order_request = LimitOrderRequest(
        symbol=symbol, qty=qty_str, side=side,
        time_in_force=tif, limit_price=rounded_limit_price,
        client_order_id=client_order_id
    )
    logger.info(f"Submitting {side.name} limit order for {symbol}. Qty: {qty_str}, Limit Price: {rounded_limit_price:.4f}, TIF: {tif.value}")
    return trading_client.submit_order(order_request)

def place_option_order(trading_client, symbol, qty, limit_price, client_order_id=None):
    compact_symbol = format_occ_symbol(symbol)
    order_request = LimitOrderRequest(
        symbol=compact_symbol,
        qty=str(qty),
        side=OrderSide.BUY,
        time_in_force=TimeInForce.DAY,
        limit_price=round(limit_price, 2),
        client_order_id=client_order_id 
    )
    logger.info(f"Submitting BUY limit order for option {compact_symbol}. Qty: {qty}, Limit Price: {limit_price:.2f}, ClientOrderID: {client_order_id}")
    return trading_client.submit_order(order_request)

def submit_trailing_stop_order(trading_client, symbol: str, qty: float, side: OrderSide, trail_percent: float, client_order_id=None):
    order_request = TrailingStopOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        trail_percent=trail_percent,
        client_order_id=client_order_id
    )
    return trading_client.submit_order(order_data=order_request)

def submit_stop_limit_order(trading_client, symbol: str, qty: float, side: OrderSide, stop_price: float, limit_price: float, client_order_id=None):
    order_request = StopLimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        time_in_force=TimeInForce.GTC,
        stop_price=stop_price,
        limit_price=limit_price,
        client_order_id=client_order_id
    )
    return trading_client.submit_order(order_data=order_request)

def cancel_single_order(trading_client, order_id: str):
    try:
        trading_client.cancel_order_by_id(order_id)
    except Exception as e:
        logger.error(f"Failed to cancel order {order_id}: {e}")

def cancel_all_open_orders(trading_client):
    return trading_client.cancel_orders()

def check_active_trailing_stop(trading_client, symbol: str) -> bool:
    try:
        clean_symbol = symbol.replace('/', '')
        req = GetOrdersRequest(status='open', symbols=[clean_symbol])
        open_orders = trading_client.get_orders(filter=req)
        for order in open_orders:
            if order.side == OrderSide.SELL and any(x in order.type for x in ['stop', 'trailing_stop', 'stop_limit']):
                return True
        return False
    except Exception as e:
        logger.error(f"Error checking active trailing stop for {symbol}: {e}")
        return False

# --- NEW: ROBUST ORDER HISTORY FETCHING ---

def fetch_orders_in_window(ticker, start_dt, end_dt):
    """
    Fetches ALL orders (Filled, Canceled, New) for a ticker in a specific time window.
    Handles naive datetimes by localizing to US/Eastern before converting to UTC.
    """
    try:
        trading_client = get_trading_client()
        
        # 1. Localize Start Time (If naive, assume ET)
        if start_dt.tzinfo is None:
            start_dt = pytz.timezone('US/Eastern').localize(start_dt)
        start_utc = start_dt.astimezone(pytz.utc)

        # 2. Localize End Time (If naive, assume ET)
        if end_dt.tzinfo is None:
            end_dt = pytz.timezone('US/Eastern').localize(end_dt)
        end_utc = end_dt.astimezone(pytz.utc)
        
        # FIX: Do NOT strip the slash for Crypto pairs. Pass ticker as-is (e.g., 'BTC/USD')
        # Alpaca's Order API expects 'BTC/USD' for crypto queries.
        req = GetOrdersRequest(
            status=QueryOrderStatus.ALL, 
            symbols=[ticker], 
            after=start_utc,
            until=end_utc,
            limit=500
        )
        orders = trading_client.get_orders(filter=req)
        
        parsed_orders = []
        for o in orders:
            timestamp = o.filled_at if o.filled_at else o.created_at
            if not timestamp: continue
            
            # Determine Price
            price = float(o.filled_avg_price) if o.filled_avg_price else (float(o.limit_price) if o.limit_price else 0.0)
            
            parsed_orders.append({
                'id': str(o.id),
                'time': timestamp,
                'side': o.side,
                'status': o.status,
                'price': price,
                'qty': float(o.qty) if o.qty else 0.0
            })
            
        return parsed_orders
    except Exception as e:
        logger.error(f"Error fetching order history for {ticker}: {e}")
        return []

def fetch_daily_executions(date_str):
    """
    Fetches ALL filled orders (Buys AND Sells) for a specific date.
    Returns: [{'symbol': 'SOL/USD', 'side': 'buy', 'qty': 10, 'price': 85.50, 'time': datetime}]
    """
    try:
        trading_client = get_trading_client()
        target_dt = datetime.strptime(date_str, "%Y-%m-%d")
        
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=500,
            after=target_dt
        )
        
        orders = trading_client.get_orders(filter=req)
        
        executions = []
        for o in orders:
            if o.status != OrderStatus.FILLED: continue
            
            # UTC to ET Check
            if o.filled_at.astimezone(pytz.timezone('US/Eastern')).strftime("%Y-%m-%d") != date_str: continue
                
            qty = float(o.filled_qty)
            if o.asset_class == AssetClass.US_EQUITY and qty.is_integer(): 
                qty = int(qty)
            
            executions.append({
                'symbol': o.symbol,
                'side': o.side,      
                'qty': qty,
                'price': float(o.filled_avg_price) if o.filled_avg_price else 0.0,
                'time': o.filled_at
            })
            
        return executions
        
    except Exception as e:
        logger.error(f"Error fetching executions: {e}")
        return []

def fetch_todays_filled_buys(date_str):
    """
    Fetches all BUY orders filled on the given date.
    Returns a list of dicts: [{'symbol': 'NVDA', 'qty': 10, 'time': datetime}]
    """
    try:
        trading_client = get_trading_client()
        target_dt = datetime.strptime(date_str, "%Y-%m-%d")
        
        req = GetOrdersRequest(
            status=QueryOrderStatus.CLOSED,
            limit=50,
            after=target_dt
        )
        
        orders = trading_client.get_orders(filter=req)
        
        todays_buys = []
        for o in orders:
            if o.side != OrderSide.BUY: continue
            if o.status != OrderStatus.FILLED: continue
            
            # Check date match (UTC to local date string match)
            if o.filled_at.strftime("%Y-%m-%d") != date_str: continue
                
            qty = float(o.filled_qty)
            if qty.is_integer(): qty = int(qty)
            
            todays_buys.append({
                'symbol': o.symbol,
                'qty': qty,
                'time': o.filled_at
            })
            
        return todays_buys
        
    except Exception as e:
        logger.error(f"Error fetching buys: {e}")
        return []

if __name__ == "__main__":
    pass




