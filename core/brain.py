import os
import json
import time
import logging
import google.generativeai as genai
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Configure Gemini API
api_key = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash')

def evaluate_asset(ticker, context, strategy_name="ema_crossover", strategy_params=None):
    """
    Uses Gemini to evaluate an asset based on comprehensive context.
    Returns a dictionary with action, confidence, execution details, and reasoning.

    New execution fields (can override database defaults):
    - order_type: "market", "limit", "trailing_stop", or "stop_limit"
    - trail_percent: override for trailing stop percentage
    - take_profit_percent: override for take profit level
    - limit_price_offset: percentage offset for limit orders
    """
    if strategy_params is None:
        strategy_params = {}

    prompt = f"""
You are an expert crypto trader. Analyze the following context and decide whether to BUY, SELL, or HOLD.

CURRENT STRATEGY: {strategy_name}
STRATEGY PARAMETERS: {strategy_params}

CONTEXT:
{context}

INSTRUCTIONS:
1. Look for trends in Technical Analysis. Consider if the strategy parameters (EMA periods, trailing stop, etc.) align with current conditions.
2. Consider News sentiment and its potential impact on price.
3. Evaluate current PNL - if in profit, consider if it's time to take some or all gains. If in loss, decide if we should cut losses or hold.
4. Sizing: allocation_pct should be based on your confidence and the remaining cash.
5. EXECUTION STRATEGY: You can override the default strategy parameters:
   - If market is trending strongly, suggest a tighter trailing_stop (e.g., 1.5% instead of default 2.5%)
   - If market is choppy, suggest order_type="limit" to avoid slippage
   - If volatility is high, suggest order_type="trailing_stop" to protect gains
6. OPTIONAL FIELDS: If you want to stick with defaults, return null for optional fields (order_type, trail_percent, take_profit_percent, limit_price_offset).

Respond ONLY in JSON format with the following keys:
- "action": "BUY", "SELL", or "HOLD"
- "confidence": (0-100)
- "allocation_pct": (0-100)
- "order_type": "market" | "limit" | "trailing_stop" | "stop_limit" (or null to use default)
- "trail_percent": float (e.g. 1.8) or null to use default from strategy
- "take_profit_percent": float (e.g. 3.5) or null to use default
- "limit_price_offset": float (% above/below market) or null
- "reasoning": "A brief but thorough explanation of your decision"

Ensure the JSON is valid.
    """

    try:
        response = _generate_content_with_retry(prompt, max_retries=3)
        text = response.text
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()

        result = json.loads(text)
        # Ensure all new fields exist (even if null)
        result.setdefault('order_type', None)
        result.setdefault('trail_percent', None)
        result.setdefault('take_profit_percent', None)
        result.setdefault('limit_price_offset', None)
        return result

    except Exception as e:
        logger.error(f'Error evaluating {ticker}: {e}')
        return {
            'action': 'HOLD',
            'confidence': 0,
            'allocation_pct': 0,
            'order_type': None,
            'trail_percent': None,
            'take_profit_percent': None,
            'limit_price_offset': None,
            'reasoning': f'Error: {e}'
        }


def _generate_content_with_retry(prompt, max_retries=3, initial_delay=5):
    """Wraps Gemini API call with exponential backoff retry logic for 429 errors."""
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            return model.generate_content(prompt)
        except Exception as e:
            error_str = str(e)

            # Check if it's a rate limit error (429)
            if '429' in error_str or 'Resource exhausted' in error_str:
                if attempt < max_retries - 1:
                    logger.warning(f"Rate limited (429). Retry {attempt + 1}/{max_retries} in {delay}s...")
                    time.sleep(delay)
                    delay *= 3  # Exponential backoff: 5s, 15s, 30s
                else:
                    logger.error(f"Max retries ({max_retries}) exceeded for rate limit. Giving up.")
                    raise
            else:
                # Non-rate-limit error, fail immediately
                raise

if __name__ == '__main__':
    # Test evaluation
    test_data = 'TICKER: SOL/USD, Price: 100, SMA_5: 98, SMA_10: 95, News: SOL hits new high'
    print(evaluate_asset('SOL/USD', test_data))
