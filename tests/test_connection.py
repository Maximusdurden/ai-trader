from api import get_account_info
try:
    account = get_account_info()
    print(f"Connected! Account ID: {account.id}")
    print(f"Status: {account.status}")
    print(f"Cash: ${account.cash}")
except Exception as e:
    print(f"Connection failed: {e}")
