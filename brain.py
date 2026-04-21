import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini API
api_key = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.0-flash')

def evaluate_asset(ticker, context):
    """
    Uses Gemini to evaluate an asset based on comprehensive context.
    Returns a dictionary with action, confidence, and reasoning.
    """
    prompt = f"""
    You are an expert crypto trader. Analyze the following context and decide whether to BUY, SELL, or HOLD.
    
    CONTEXT:
    {context}
    
    INSTRUCTIONS:
    1. Look for trends in Technical Analysis.
    2. Consider News sentiment and its potential impact on price.
    3. Evaluate current PNL - if in profit, consider if it's time to take some or all gains. If in loss, decide if we should cut losses or hold.
    4. Sizing: allocation_pct should be based on your confidence and the remaining cash.
    
    Respond ONLY in JSON format with the following keys:
    - "action": "BUY", "SELL", or "HOLD"
    - "confidence": (0-100)
    - "allocation_pct": (0-100, what percentage of available cash to use for BUY, or percentage of current position to sell for SELL)
    - "reasoning": "A brief but thorough explanation of your decision"
    
    Ensure the JSON is valid.
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()
        
        return json.loads(text)
    except Exception as e:
        print(f'Error evaluating {ticker}: {e}')
        return {'action': 'HOLD', 'confidence': 0, 'allocation_pct': 0, 'reasoning': f'Error: {e}'}

if __name__ == '__main__':
    # Test evaluation
    test_data = 'TICKER: SOL/USD, Price: 100, SMA_5: 98, SMA_10: 95, News: SOL hits new high'
    print(evaluate_asset('SOL/USD', test_data))
