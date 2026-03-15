# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()
import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDS_FILE = os.getenv('GOOGLE_SHEETS_CREDENTIALS_JSON')
SPREADSHEET_URL = os.getenv('SPREADSHEET_URL')

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
client = gspread.authorize(creds)

sheet = client.open_by_url(SPREADSHEET_URL)
ws = sheet.worksheet('Youtube_Log')
rows = ws.get_all_values()

from collections import Counter
dates = Counter(r[0] for r in rows[1:] if r and len(r) > 0)
print("=== Google Sheets Youtube_Log - all dates ===")
for d, cnt in sorted(dates.items(), reverse=True)[:15]:
    print(f"  {d}: {cnt} videos")

print("\n=== 2026-02-25 ~ 2026-02-27 videos ===")
for r in rows[1:]:
    if r and r[0] in ('2026-02-25', '2026-02-26', '2026-02-27'):
        url = r[4] if len(r) > 4 else '?'
        title = r[2] if len(r) > 2 else '?'
        has_transcript = len(r[3]) > 10 if len(r) > 3 else False
        print(f"  date={r[0]}, title={title[:40]}, transcript={'O' if has_transcript else 'X'}, url={url[:60]}")

# ChromaDB 확인
from utils.vector_store import VectorStore
vs = VectorStore()
print("\n=== ChromaDB youtube_summaries 최근 날짜 ===")
res = vs.collection.get(include=['metadatas'])
date_counts = Counter(m.get('업로드일자','?') for m in res['metadatas'])
for d, cnt in sorted(date_counts.items(), reverse=True)[:8]:
    print(f"  {d}: {cnt} chunks")
