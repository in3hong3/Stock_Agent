from main import SheetLogger
import os
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

def summarize_results():
    credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_url = os.getenv("SPREADSHEET_URL")
    
    if not credentials_json or not sheet_url:
        print("Error: Environment variables missing.")
        return

    logger = SheetLogger(credentials_json, sheet_url)
    print("=== Collection Summary ===\n")

    # 1. Youtube_Log
    try:
        ws_log = logger.get_worksheet("Youtube_Log")
        data_log = ws_log.get_all_values()
        print(f"[Youtube_Log] Total Rows: {len(data_log)-1 if data_log else 0}")
        if len(data_log) > 1:
            print(f"  Last entry: {data_log[-1][2]} ({data_log[-1][5]})")
    except Exception as e:
        print(f"Error reading Youtube_Log: {e}")

    # 2. Stock_Mentions
    try:
        ws_mentions = logger.get_worksheet("Stock_Mentions")
        data_mentions = ws_mentions.get_all_values()
        print(f"\n[Stock_Mentions] Total Rows: {len(data_mentions)-1 if data_mentions else 0}")
        
        # Analyze missing mapping
        missing_counts = {}
        valid_counts = 0
        for row in data_mentions[1:]:
            if len(row) < 5: continue
            ticker = row[4]
            stock_name = row[3]
            
            # Simple validation logic
            is_valid = False
            if ticker.endswith('.KS') or ticker.endswith('-USD') or ticker.startswith('^'):
                is_valid = True
            elif ticker.isalpha() and ticker.isupper() and len(ticker) <= 5:
                is_valid = True
            
            if is_valid:
                valid_counts += 1
            else:
                key = f"{stock_name} -> {ticker}"
                missing_counts[key] = missing_counts.get(key, 0) + 1
                
        print(f"  Valid Tickers: {valid_counts}")
        print(f"  Potentially Missing/Invalid: {sum(missing_counts.values())}")
        if missing_counts:
            print("  Top Missing Mappings:")
            for k, v in sorted(missing_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                print(f"    - {k}: {v} times")
            
    except Exception as e:
        print(f"Error reading Stock_Mentions: {e}")

    # 3. Stock_Prices
    try:
        ws_prices = logger.get_worksheet("Stock_Prices")
        data_prices = ws_prices.get_all_values()
        print(f"\n[Stock_Prices] Total Rows: {len(data_prices)-1 if data_prices else 0}")
        if len(data_prices) > 1:
            print(f"  Last entry: {data_prices[-1][0]} - {data_prices[-1][2]} ({data_prices[-1][3]})")
    except Exception as e:
        print(f"Error reading Stock_Prices: {e}")

if __name__ == "__main__":
    summarize_results()
