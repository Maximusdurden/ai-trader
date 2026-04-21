from api import get_news_client
from alpaca.data.requests import NewsRequest

client = get_news_client()
request_params = NewsRequest(symbols="SOL/USD", limit=2)
news_res = client.get_news(request_params)
print(f"Data keys: {news_res.data.keys()}")
# In some versions of alpaca-py, NewsSet is just a wrapper around a list of news items in .news or similar.
# But here .data is a dict.
for k, v in news_res.data.items():
    print(f"Key: {k}, Value type: {type(v)}")
    if isinstance(v, list) and len(v) > 0:
        print(f"First item in list: {v[0]}")
        print(f"Attributes of first item: {dir(v[0])}")
