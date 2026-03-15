
import yfinance as yf

tickers = ['MU', 'MSFT', 'NVDA', 'SMCI', 'AVGO']
print("=== Current Stock Prices ===")
for t in tickers:
    try:
        ticker = yf.Ticker(t)
        price = ticker.history(period='1d')['Close'].iloc[-1]
        print(f"{t}: ${price:.2f}")
    except Exception as e:
        print(f"{t}: Error - {e}")
