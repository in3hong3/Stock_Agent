"""
Google Sheets 데이터 로더 모듈
Youtube_Log 및 Market_Log 워크시트에서 데이터를 읽어옵니다.
"""
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()


class SheetDataLoader:
    """Google Sheets에서 데이터를 읽어오는 클래스"""
    
    def __init__(self, credentials_json=None, sheet_url=None):
        self.scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # 환경 변수에서 가져오기
        self.credentials_json = credentials_json or os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
        self.sheet_url = sheet_url or os.getenv("SPREADSHEET_URL")
        
        if not self.credentials_json or not self.sheet_url:
            raise ValueError("Google Sheets credentials and URL must be provided")
        
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(
            self.credentials_json, self.scope
        )
        self.client = gspread.authorize(self.creds)
        self.doc = None
    
    def open_sheet(self):
        """스프레드시트 열기"""
        if not self.doc:
            self.doc = self.client.open_by_url(self.sheet_url)
        return self.doc
    
    def get_worksheet(self, worksheet_name):
        """워크시트 이름으로 가져오기"""
        doc = self.open_sheet()
        try:
            worksheet = doc.worksheet(worksheet_name)
            return worksheet
        except gspread.exceptions.WorksheetNotFound:
            print(f"Warning: Worksheet '{worksheet_name}' not found.")
            return None
    
    def load_youtube_data(self):
        """Youtube_Log 워크시트의 모든 데이터를 DataFrame으로 로드"""
        worksheet = self.get_worksheet("Youtube_Log")
        if not worksheet:
            return pd.DataFrame()
        
        data = worksheet.get_all_values()
        if not data:
            return pd.DataFrame()
        
        # 첫 행을 헤더로 사용
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # 날짜 컬럼 파싱
        if '수집일시' in df.columns:
            df['수집일시'] = pd.to_datetime(df['수집일시'], errors='coerce')
        if '업로드일자' in df.columns:
            df['업로드일자'] = pd.to_datetime(df['업로드일자'], errors='coerce')
        
        return df
    
    def load_market_data(self):
        """Market_Log 워크시트의 모든 데이터를 DataFrame으로 로드"""
        worksheet = self.get_worksheet("Market_Log")
        if not worksheet:
            return pd.DataFrame()
        
        data = worksheet.get_all_values()
        if not data:
            return pd.DataFrame()
        
        # 첫 행을 헤더로 사용
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # 날짜 컬럼 파싱
        if '수집일시' in df.columns:
            df['수집일시'] = pd.to_datetime(df['수집일시'], errors='coerce')
        
        # 숫자 컬럼 변환
        numeric_columns = ['CNN지수', '코스피', '나스닥', '원달러환율', '삼성전자', '테슬라', '엔비디아', '비트코인']
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def get_latest_fear_greed_index(self):
        """
        최신 CNN Fear & Greed Index 값을 반환
        Returns:
            tuple: (지수 값, 상태 문자열) 예: (25, "Extreme Fear")
        """
        df = self.load_market_data()
        if df.empty:
            return None, None
        
        # 가장 최근 데이터 가져오기
        df_sorted = df.sort_values('수집일시', ascending=False)
        latest = df_sorted.iloc[0]
        
        index_value = latest.get('CNN지수')
        status = latest.get('CNN상태')
        
        return index_value, status
    
    def get_latest_entries(self, days=30):
        """
        최근 N일간의 YouTube 데이터만 필터링
        Args:
            days: 최근 며칠 데이터를 가져올지 (기본 30일)
        Returns:
            DataFrame: 필터링된 데이터
        """
        df = self.load_youtube_data()
        if df.empty:
            return df
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        if '수집일시' in df.columns:
            df_filtered = df[df['수집일시'] >= cutoff_date]
            return df_filtered
        
        return df


if __name__ == "__main__":
    # 테스트 코드
    loader = SheetDataLoader()
    
    print("=== YouTube Data ===")
    yt_data = loader.load_youtube_data()
    print(f"Total rows: {len(yt_data)}")
    if not yt_data.empty:
        print(yt_data.head())
    
    print("\n=== Market Data ===")
    market_data = loader.load_market_data()
    print(f"Total rows: {len(market_data)}")
    if not market_data.empty:
        print(market_data.head())
    
    print("\n=== Latest Fear & Greed Index ===")
    index, status = loader.get_latest_fear_greed_index()
    print(f"Index: {index}, Status: {status}")
