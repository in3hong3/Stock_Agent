from main import SheetLogger
import os
from dotenv import load_dotenv
import re

load_dotenv()

def is_valid_ticker(ticker):
    # KR
    if re.match(r'^\d{6}\.KS$', ticker):
        return True
    # US / ETF / Index (simple check)
    if re.match(r'^[A-Z]{1,5}$', ticker) or ticker.startswith('^'):
        return True
    # Crypto
    if re.match(r'^[A-Z]+-USD$', ticker):
        return True
    return False

def check_missing():
    credentials_json = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
    sheet_url = os.getenv("SPREADSHEET_URL")
    if not credentials_json or not sheet_url:
        print("Error: Missing environment variables.")
        return

    logger = SheetLogger(credentials_json, sheet_url)
    print("Reading Stock_Mentions...")
    try:
        worksheet = logger.get_worksheet("Stock_Mentions")
        data = worksheet.get_all_values()
        
        if not data:
            print("No data found.")
            return

        header = data[0]
        # Assuming header: ["영상제목", "채널명", "업로드일자", "종목명", "티커", "시장", "영상링크"]
        # Indcies: 종목명(3), 티커(4)
        
        missing_map = {}
        
        print(f"Total rows: {len(data)-1}")
        
        for i, row in enumerate(data[1:], start=2):
            if len(row) < 5:
                continue
                
            stock_name = row[3]
            ticker = row[4]
            market = row[5] if len(row) > 5 else ""
            
            # Logic to find "missing" tickers
            # 1. Ticker is same as Stock Name but not uppercase (US)
            # 2. Korean name in Ticker column?
            # 3. Known failure patterns from logs
            
            # Simple check: if valid ticker format, assume good. If not, flag it.
            if not is_valid_ticker(ticker):
                key = f"{stock_name} ({market})"
                if key not in missing_map:
                    missing_map[key] = []
                missing_map[key].append(ticker)

        print("\n=== Potentially Missing/Invalid Tickers ===")
        for key, tickers in missing_map.items():
            print(f"Stock: {key} -> Current Ticker Value: {tickers[0]}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_missing()
