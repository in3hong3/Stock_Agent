import os
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

print(f"Credentials file: {GOOGLE_SHEETS_CREDENTIALS_JSON}")
print(f"Sheet URL: {SPREADSHEET_URL}")
print(f"File exists: {os.path.exists(GOOGLE_SHEETS_CREDENTIALS_JSON)}")

try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS_JSON, scope)
    client = gspread.authorize(creds)
    
    print("\n✅ Authentication successful!")
    
    doc = client.open_by_url(SPREADSHEET_URL)
    worksheet = doc.get_worksheet(0)
    
    print(f"✅ Sheet opened: {doc.title}")
    print(f"✅ Worksheet: {worksheet.title}")
    
    # 현재 데이터 확인
    all_data = worksheet.get_all_values()
    print(f"\n📊 Total rows in sheet: {len(all_data)}")
    
    if all_data:
        print("\n첫 5줄:")
        for i, row in enumerate(all_data[:5]):
            print(f"  Row {i+1}: {row}")
    else:
        print("⚠️ Sheet is empty!")
        
except Exception as e:
    print(f"\n❌ Error: {e}")
