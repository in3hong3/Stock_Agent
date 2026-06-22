import os
import time
import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from googleapiclient.discovery import build
import yt_dlp
from openai import OpenAI
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import yfinance as yf
from youtube_transcript_api import YouTubeTranscriptApi
import json

# 환경 변수 로드
load_dotenv()

# 상수 정의
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
TARGET_CHANNEL_ID_LIST = os.getenv("TARGET_CHANNEL_ID_LIST", "").split(",")
SPREADSHEET_URL = os.getenv("SPREADSHEET_URL")

class CNNScraper:
    """CNN Fear & Greed Index를 수집하는 클래스"""
    
    @staticmethod
    def get_fear_and_greed_index():
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        # CNN dataviz API는 봇 차단(HTTP 418)이 있어 브라우저 수준 헤더가 모두 필요하다.
        # (UA·Referer만으로는 418 — Accept/Accept-Language/Origin까지 있어야 200)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Origin": "https://edition.cnn.com",
            "Referer": "https://edition.cnn.com/markets/fear-and-greed",
        }
        
        print("Processing [Fear & Greed Index]...")
        
        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    fg_data = data.get('fear_and_greed', {})
                    score = fg_data.get('score')
                    rating = fg_data.get('rating')
                    
                    if score is not None:
                        return int(score), rating
                
                print(f"  Attempt {attempt + 1} failed. Status Code: {response.status_code}")
                if attempt < 2:
                    time.sleep(2)
                    
            except Exception as e:
                print(f"  Attempt {attempt + 1} error: {e}")
                if attempt < 2:
                    time.sleep(2)
        
        return -1, "Error"


class MarketDataCollector:
    """yfinance를 사용한 시장 지표 수집"""
    
    TICKERS = {
        'kospi': '^KS11',
        'nasdaq': '^IXIC',
        'sp500': '^GSPC',
        'krw_usd': 'KRW=X',
        'samsung': '005930.KS',
        'tesla': 'TSLA',
        'nvidia': 'NVDA',
        'bitcoin': 'BTC-USD'
    }
    
    @staticmethod
    def get_latest_prices():
        """모든 티커의 최신 종가 수집"""
        print("Collecting market data...")
        results = {}
        
        for name, ticker in MarketDataCollector.TICKERS.items():
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period='5d')  # 최근 5일 데이터 (주말 대비)
                
                if not hist.empty:
                    latest_close = hist['Close'].iloc[-1]
                    results[name] = round(latest_close, 2)
                    print(f"  {name}: {results[name]}")
                else:
                    results[name] = 'N/A'
                    print(f"  {name}: No data available")
                    
            except Exception as e:
                print(f"  Error fetching {name} ({ticker}): {e}")
                results[name] = 'N/A'
        
        return results

class YouTubeManager:
    """유튜브 영상 정보 수집 및 자막 추출"""
    
    def __init__(self, api_key):
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def get_recent_videos(self, channel_id, hours=24):
        """최근 N시간 이내 영상 조회 (기존 호환성 유지)"""
        now = datetime.datetime.now(datetime.timezone.utc)
        start_time = (now - datetime.timedelta(hours=hours)).isoformat()
        return self.get_videos_in_range(channel_id, start_time, None, max_results=5)
    
    def get_videos_in_range(self, channel_id, start_date, end_date=None, max_results=50):
        """
        특정 기간의 영상 조회 (페이지네이션 지원)
        Args:
            channel_id: 채널 ID
            start_date: 시작일 (ISO format 또는 "YYYY-MM-DD")
            end_date: 종료일 (None이면 현재)
            max_results: 최대 결과 수 (기본 50)
        Returns:
            list: 영상 정보 리스트
        """
        # 날짜 형식 변환
        if isinstance(start_date, str) and 'T' not in start_date:
            start_date = f"{start_date}T00:00:00Z"
        if end_date and isinstance(end_date, str) and 'T' not in end_date:
            end_date = f"{end_date}T23:59:59Z"
        
        print(f"Fetching videos for channel {channel_id} from {start_date}...")
        
        all_videos = []
        next_page_token = None
        
        try:
            while True:
                request_params = {
                    "part": "snippet",
                    "channelId": channel_id,
                    "order": "date",
                    "type": "video",
                    "publishedAfter": start_date,
                    "maxResults": min(50, max_results - len(all_videos))  # API 최대 50
                }
                
                if end_date:
                    request_params["publishedBefore"] = end_date
                
                if next_page_token:
                    request_params["pageToken"] = next_page_token
                
                request = self.youtube.search().list(**request_params)
                response = request.execute()
                
                for item in response.get("items", []):
                    all_videos.append({
                        "video_id": item["id"]["videoId"],
                        "title": item["snippet"]["title"],
                        "channel_title": item["snippet"]["channelTitle"],
                        "publish_time": item["snippet"]["publishedAt"],
                        "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}"
                    })
                
                # 페이지네이션 처리
                next_page_token = response.get("nextPageToken")
                
                # 종료 조건: 다음 페이지 없음 또는 최대 결과 수 도달
                if not next_page_token or len(all_videos) >= max_results:
                    break
            
            print(f"  Found {len(all_videos)} videos")
            return all_videos
            
        except Exception as e:
            print(f"  Error fetching videos: {e}")
            return all_videos  # 부분 결과라도 반환

    def get_transcript(self, video_id):
        """
        자막 추출 (텍스트 + 타임스탬프)
        Returns:
            tuple: (full_text, timestamps_json) 또는 (None, None)
        """
        print(f"    Searching for transcript for {video_id}...")
        
        # 1. 시도: youtube-transcript-api (가장 빠름 + 타임스탬프 포함)
        try:
            # 환경에 따라 static method가 없을 수 있으므로 유연하게 대처
            if hasattr(YouTubeTranscriptApi, 'get_transcript'):
                transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            else:
                # 인스턴스 방식 시도 (일부 버전/환경 대비)
                api = YouTubeTranscriptApi()
                transcript_list = api.list(video_id).find_transcript(['ko', 'en']).fetch()
            
            # 텍스트 추출 고도화: 중합된 구조(events/segs) 대응
            processed_fragments = []
            for item in transcript_list:
                # 1. 일반적인 구조 (dict.get 또는 getattr)
                def get_val(obj, key):
                    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
                
                text = get_val(item, 'text')
                start = get_val(item, 'start') or get_val(item, 'tStartMs') or 0
                if isinstance(start, (int, float)) and start > 1000: # ms 단위인 경우 sec로 변환
                    start = start / 1000.0
                
                duration = get_val(item, 'duration') or get_val(item, 'dDurationMs') or 0
                if isinstance(duration, (int, float)) and duration > 1000:
                    duration = duration / 1000.0

                # 2. 중첩 구조 (segs 안의 utf8) 처리
                segs = get_val(item, 'segs')
                if segs and isinstance(segs, list):
                    nested_texts = [s.get('utf8', '') if isinstance(s, dict) else getattr(s, 'utf8', '') for s in segs]
                    text = "".join(nested_texts)
                elif not text: # 직접적인 text 필드가 없는 경우 utf8 확인
                    text = get_val(item, 'utf8') or ""
                
                if text.strip():
                    processed_fragments.append({
                        'text': text.strip(),
                        'start': start,
                        'duration': duration
                    })
            
            if not processed_fragments:
                # 만약 전체가 하나의 큰 JSON 덩어리로 들어왔을 경우 (희귀 케이스) 대비
                if isinstance(transcript_list, dict) and 'events' in transcript_list:
                    for event in transcript_list['events']:
                        if 'segs' in event:
                            text = "".join([s.get('utf8', '') for s in event['segs'] if 'utf8' in s])
                            if text.strip():
                                start = event.get('tStartMs', 0) / 1000.0
                                processed_fragments.append({'text': text.strip(), 'start': start, 'duration': 0})

            if processed_fragments:
                full_text = " ".join([f['text'] for f in processed_fragments])
                print(f"    [youtube-transcript-api] Success! ({len(full_text)} chars)")
                return full_text, json.dumps(processed_fragments, ensure_ascii=False)
            
        except Exception as e:
            print(f"    [youtube-transcript-api] Failed: {type(e).__name__} - {str(e)[:100]}")

        # 2. 시도: yt-dlp (유튜브 차단 시 대비) - 타임스탬프 없이 텍스트만
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        # 쿠키 파일 확인
        cookie_file = "cookies.txt"
        cookie_path = os.path.join(os.getcwd(), cookie_file)
        
        ydl_opts = {
            'skip_download': True,
            'writeautomaticsub': True,
            'writesubtitles': True,
            'subtitleslangs': ['ko', 'en'],
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Referer': 'https://www.google.com/',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
            }
        }
        
        if os.path.exists(cookie_path):
            print(f"    [yt-dlp] Using cookies from {cookie_file}")
            ydl_opts['cookiefile'] = cookie_path
        
        try:
            print(f"    [yt-dlp] Attempting fallback extraction...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                subtitles = info.get('subtitles', {})
                auto_captions = info.get('automatic_captions', {})
                
                # 수동 자막 우선
                for lang in ['ko', 'en']:
                    if lang in subtitles:
                        text = self._download_and_parse_subs(subtitles[lang][0]['url'])
                        if text:
                            print(f"    [yt-dlp] Success using manual subtitles ({lang})")
                            return text, "[]"
                
                # 자동 자막 차선
                for lang in ['ko', 'en']:
                    if lang in auto_captions:
                        text = self._download_and_parse_subs(auto_captions[lang][0]['url'])
                        if text:
                            print(f"    [yt-dlp] Success using automatic captions ({lang})")
                            return text, "[]"
                
                # 3. 시도: 영상 설명(Description)을 대체 데이터로 사용 (자막 차단 시 대비)
                print(f"    [yt-dlp] Captions not available. Using description as fallback.")
                description = info.get('description', '')
                if description:
                    return f"[영상 설명으로 대체]\n{description}", "[]"
                    
                print(f"    [yt-dlp] No suitable subtitles or description found.")
                return None, None

        except Exception as e:
            print(f"    [yt-dlp Error] {type(e).__name__}: {str(e)[:100]}")
            return None, None

    def _download_and_parse_subs(self, url):
        try:
            response = requests.get(url, timeout=20)
            if response.status_code == 200:
                return self._parse_vtt(response.text)
            return None
        except Exception as e:
            print(f"    [Sub Download Error] {e}")
            return None

    def _parse_vtt(self, vtt_content):
        lines = vtt_content.splitlines()
        text_lines = []
        for line in lines:
            if '-->' in line: continue
            if line.strip() == '': continue
            if line.strip().isdigit(): continue
            if line.startswith('WEBVTT'): continue
            clean_line = BeautifulSoup(line, "html.parser").get_text()
            if clean_line not in text_lines:
                text_lines.append(clean_line)
        return " ".join(text_lines)

# AISummarizer 클래스 제거 (더 이상 데이터 수집 시 요약하지 않음)
# 챗봇이 on-demand로 원본 자막을 분석합니다.

class AISummarizer:
    """OpenAI API를 이용한 요약 (DEPRECATED - 사용하지 않음)"""
    
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)

    def summarize(self, text):
        if not text:
            return "자막 없음"
        
        try:
            # 최대 40,000자 처리 (더 긴 영상 대응)
            truncated_text = text[:40000]
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": """너는 전문 금융 애널리스트이자 리서치 작가야. 
주어진 유튜브 영상 자막을 **전문 분석 보고서 수준**으로 작성해야 해.

# 📋 출력 구조 (필수 섹션)

## 1. Executive Summary (핵심 요약)
- 1단락 (3-5문장): 영상의 핵심을 한눈에
- 주요 주장 3가지
- 최종 결론/메시지

## 2. Context & Background (배경)
- 영상이 다루는 시간적 배경 (날짜, 이벤트)
- 현재 시장 상황/문제 설정
- 필요한 사전 지식

## 3. Main Arguments & Analysis (주요 주장 및 분석)
**영상에서 언급된 모든 주요 주장을 섹션으로 분리**
각 주장마다:
- 분석가가 주장하는 내용
- 그 근거 (제시된 데이터/자료)
- 인과관계 설명 (왜 그런가?)
- 암시하는 의미

## 4. Data & Evidence (데이터 및 근거)
**영상에서 제시된 모든 구체적 수치/사례를 표로 정리**
- 수출 증가율, P/E 비율, 주가, 환율 등
- 출처 명시
- 수치가 의미하는 바

## 5. Comparisons & Perspectives (비교 분석)
**영상에서 비교/대조한 항목들**
- 기업 간 비교 (삼성 vs SK하이닉스 등)
- 시간 경과에 따른 변화
- 지역/시장 간 차이

## 6. Expert Views & External References (전문가 의견)
**영상에서 인용/언급한 외부 의견**
- 모건스탠리, Ray Dalio 등 전문가
- 각 의견의 핵심
- 어떤 맥락에서 인용했는지

## 7. Key Insights & Implications (핵심 통찰)
**영상이 암시하는 더 깊은 의미**
- "왜 이것이 중요한가?"
- 장기적 영향
- 투자 의사결정에 미치는 영향

## 8. Investment Strategy & Recommendations (투자 전략)
**영상에서 제시한 구체적 권고사항**
- 시점별 전략 (현재/추가 하락 시/장기)
- 피해야 할 것
- 관찰해야 할 지표

## 9. Risks & Uncertainties (리스크 및 불확실성)
**영상에서 인정하거나 남겨진 질문**
- 분석의 한계
- 미확인된 가정
- 앞으로 지켜봐야 할 변수

## 10. Conclusion (결론)
- 영상의 최종 메시지
- 주요 내용 2-3줄 요약

---

# 📐 작성 규칙

## 길이
- **최소 2,000자 이상** (영상 내용이 풍부하면 제한 없음)
- 각 섹션당 최소 200자
- 주요 주장마다 충분한 설명

## 표 & 시각화
- **최소 2개 이상의 마크다운 표**
- 영상의 모든 수치/비교는 표로 정리
- 표 형식: `| 항목 | 값 | 설명 |`

## 마크다운 형식
- `## ` : 주요 섹션
- `### ` : 소제목
- `**볼드**` : 중요 개념
- `> 인용` : 직접 인용
- `- 리스트` : 열거

## 문체
- 객관적/중립적 톤
- "분석가는 주장한다", "데이터에 따르면" 같은 명확한 주어
- 단순 요약이 아닌 **분석** (왜? 어떻게? 의미는?)

---

# ✅ 필수 체크리스트
- [ ] 영상의 모든 주요 주장 포함
- [ ] 제시된 수치/데이터 모두 포함
- [ ] 인과관계 명확히 설명
- [ ] 마크다운 표 최소 2개
- [ ] 2,000자 이상
- [ ] 영상 내용만 사용 (추측 금지)
- [ ] 계층 구조 (##, ###)

한국어로 작성하되, 전문 리서치 보고서 퀄리티를 유지해줘."""},
                    {"role": "user", "content": f"다음 유튜브 영상 자막을 전문 분석 보고서로 작성해줘:\n\n{truncated_text}"}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"  Error summarizing: {e}")
            return "요약 실패"

class SheetLogger:
    """구글 시트 저장 관리 (다중 워크시트 지원)"""
    
    def __init__(self, credentials_json, sheet_url):
        self.scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        
        # JSON 유효성 검사 추가
        try:
            with open(credentials_json, 'r') as f:
                content = f.read().strip()
                if not content:
                    raise ValueError(f"Credentials file '{credentials_json}' is empty.")
                json.loads(content) # JSON 형식이 맞는지 확인
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
            print(f"Critical Error: Invalid Google Credentials JSON: {e}")
            raise

        self.creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_json, self.scope)
        self.client = gspread.authorize(self.creds)
        self.sheet_url = sheet_url
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
            print(f"  Warning: Worksheet '{worksheet_name}' not found. Creating it...")
            worksheet = doc.add_worksheet(title=worksheet_name, rows=1000, cols=20)
            return worksheet

    def set_all_rows_height(self, worksheet, height=25):
        """특정 워크시트의 모든 행 높이를 설정"""
        try:
            body = {
                "requests": [
                    {
                        "updateDimensionProperties": {
                            "range": {
                                "sheetId": worksheet.id,
                                "dimension": "ROWS",
                                "startIndex": 0,
                            },
                            "properties": {
                                "pixelSize": height
                            },
                            "fields": "pixelSize"
                        }
                    }
                ]
            }
            self.doc.batch_update(body)
            print(f"  Rows height set to {height} for {worksheet.title}.")
        except Exception as e:
            print(f"  Error setting row height: {e}")

    def log_youtube_data(self, data_rows):
        """
        Youtube_Log 워크시트에 데이터 저장 (요청 사항: 업로드일자, 채널명, 영상제목, 전체자막, 영상링크, 수집일시)
        Args:
            data_rows: [업로드일자, 채널명, 영상제목, 전체자막, 영상링크, 수집일시]
        """
        print("Accessing Youtube_Log worksheet...")
        try:
            worksheet = self.get_worksheet("Youtube_Log")
            
            existing_data = worksheet.get_all_values()
            if not existing_data:
                header = ["업로드일자", "채널명", "영상제목", "전체자막", "영상링크", "수집일시"]
                worksheet.append_row(header)
                existing_urls = set()
            else:
                # 영상링크 기반 중복 체크 (index 4)
                # '자막 없음'이거나 JSON 형식으로 잘못 저장된 경우 다시 수집할 수 있도록 필터링
                existing_urls = {
                    row[4] for row in existing_data 
                    if len(row) > 4 and row[4] and 
                    "자막 없음" not in row[3] and 
                    not row[3].strip().startswith("{")
                }

            new_rows_count = 0
            rows_to_add = []
            
            for row in data_rows:
                url = row[4]  # 영상링크
                if url in existing_urls:
                    print(f"  Skipping duplicate URL: {url}")
                    continue
                
                rows_to_add.append(row)
                existing_urls.add(url)
            
            if rows_to_add:
                chunk_size = 20
                for i in range(0, len(rows_to_add), chunk_size):
                    chunk = rows_to_add[i:i+chunk_size]
                    worksheet.append_rows(chunk)
                    new_rows_count += len(chunk)
                    print(f"  Added {len(chunk)} rows to Youtube_Log... waiting 2s")
                    time.sleep(2)
                
                self.set_all_rows_height(worksheet, 25)
                
                # 내림차순 정렬 (업로드일자 기준: Column A)
                try:
                    print("  Sorting Youtube_Log by Date descending...")
                    worksheet.sort((1, 'des'))
                except Exception as sort_e:
                    print(f"  Warning: Could not sort Youtube_Log: {sort_e}")
                
            print(f"Done. Added {new_rows_count} new rows to Youtube_Log.")
            
        except Exception as e:
            print(f"  Error accessing/writing to Youtube_Log: {e}")

    def log_market_data(self, data_row):
        """Market_Log 워크시트에 데이터 저장 (날짜 중복 방지)"""
        print("Accessing Market_Log worksheet...")
        try:
            worksheet = self.get_worksheet("Market_Log")
            
            existing_data = worksheet.get_all_values()
            today_date = datetime.datetime.now().strftime("%Y-%m-%d")
            
            if not existing_data:
                header = ["수집일시", "CNN지수", "CNN상태", "코스피", "나스닥", "S&P500", "원달러환율", "삼성전자", "테슬라", "엔비디아", "비트코인"]
                worksheet.append_row(header)
                existing_dates = set()
            else:
                existing_dates = {row[0].split()[0] for row in existing_data if len(row) > 0 and row[0]}

            if today_date in existing_dates:
                print(f"  Market data for {today_date} already exists. Skipping.")
            else:
                worksheet.append_row(data_row)
                self.set_all_rows_height(worksheet, 25)
                print(f"Done. Added market data for {today_date}.")
            
        except Exception as e:
            print(f"  Error accessing/writing to Market_Log: {e}")
    
    def log_stock_mentions(self, data_rows):
        """
        Stock_Mentions 워크시트에 종목 언급 데이터 저장
        Args:
            data_rows: [영상제목, 채널명, 업로드일자, 종목명, 티커, 시장, 영상링크]
        """
        print("Accessing Stock_Mentions worksheet...")
        try:
            worksheet = self.get_worksheet("Stock_Mentions")
            
            existing_data = worksheet.get_all_values()
            if not existing_data:
                header = ["영상제목", "채널명", "업로드일자", "종목명", "티커", "시장", "영상링크"]
                worksheet.append_row(header)
                existing_keys = set()
            else:
                # 중복 방지: (영상링크, 티커) 조합
                existing_keys = {(row[6], row[4]) for row in existing_data if len(row) > 6}
            
            new_rows_count = 0
            rows_to_add = []
            
            for row in data_rows:
                key = (row[6], row[4])  # (영상링크, 티커)
                if key in existing_keys:
                    continue
                
                rows_to_add.append(row)
                existing_keys.add(key)
            
            if rows_to_add:
                chunk_size = 20
                for i in range(0, len(rows_to_add), chunk_size):
                    chunk = rows_to_add[i:i+chunk_size]
                    worksheet.append_rows(chunk)
                    new_rows_count += len(chunk)
                    print(f"  Added {len(chunk)} rows to Stock_Mentions... waiting 2s")
                    time.sleep(2)
                
                self.set_all_rows_height(worksheet, 25)
                
                # 내림차순 정렬 (업로드일자 기준: Column C)
                try:
                    print("  Sorting Stock_Mentions by Date descending...")
                    worksheet.sort((3, 'des'))
                except Exception as sort_e:
                    print(f"  Warning: Could not sort Stock_Mentions: {sort_e}")
            
            print(f"Done. Added {new_rows_count} new stock mentions.")
            
        except Exception as e:
            print(f"  Error accessing/writing to Stock_Mentions: {e}")
    
    def log_stock_prices(self, data_rows):
        """
        Stock_Prices 워크시트에 주가 데이터 저장
        Args:
            data_rows: [날짜, 티커, 종목명, 종가, 전일대비, 등락률(%), 거래량]
        """
        print("Accessing Stock_Prices worksheet...")
        try:
            worksheet = self.get_worksheet("Stock_Prices")
            
            existing_data = worksheet.get_all_values()
            if not existing_data:
                header = ["날짜", "티커", "종목명", "종가", "전일대비", "등락률(%)", "거래량"]
                worksheet.append_row(header)
                existing_keys = set()
            else:
                # 중복 방지: (날짜, 티커) 조합
                existing_keys = {(row[0], row[1]) for row in existing_data if len(row) > 1}
            
            new_rows_count = 0
            rows_to_add = []
            
            for row in data_rows:
                key = (row[0], row[1])  # (날짜, 티커)
                if key in existing_keys:
                    continue
                
                rows_to_add.append(row)
                existing_keys.add(key)
            
            if rows_to_add:
                chunk_size = 20
                for i in range(0, len(rows_to_add), chunk_size):
                    chunk = rows_to_add[i:i+chunk_size]
                    worksheet.append_rows(chunk)
                    new_rows_count += len(chunk)
                    print(f"  Added {len(chunk)} rows to Stock_Prices... waiting 2s")
                    time.sleep(2)
                
                self.set_all_rows_height(worksheet, 25)
                
                # 내림차순 정렬 (날짜 기준: Column A)
                try:
                    print("  Sorting Stock_Prices by Date descending...")
                    worksheet.sort((1, 'des'))
                except Exception as sort_e:
                    print(f"  Warning: Could not sort Stock_Prices: {sort_e}")
            
            print(f"Done. Added {new_rows_count} new price records.")
            
        except Exception as e:
            print(f"  Error accessing/writing to Stock_Prices: {e}")

def update_youtube_log():
    """유튜브 영상 수집 및 Youtube_Log 업데이트 (DataPipeline 사용)"""
    print("\n=== Updating Youtube_Log ===")
    
    from core.services.data_pipeline import DataPipeline
    
    try:
        pipeline = DataPipeline()
    except ValueError as e:
        print(f"Error: {e}")
        return

    clean_channel_list = [cid.strip() for cid in TARGET_CHANNEL_ID_LIST if cid.strip() and not cid.strip().startswith("Other")]
    if not clean_channel_list:
        print("No valid target channels found in .env")
        return
        
    # 최근 1~2일 데이터 가져오기 (시간 기반에서 날짜 기반으로 통일)
    start_date_str = (datetime.date.today() - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    end_date_str = (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    
    for channel_id in clean_channel_list:
        print(f"\nProcessing channel: {channel_id}")
        
        def status_cb(msg):
            print(f"  [Status] {msg}")
            
        def progress_cb(ratio, msg):
            pass # 터미널에서는 생략
            
        result = pipeline.run_youtube_pipeline(
            channel_id=channel_id,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
            progress_callback=progress_cb,
            status_callback=status_cb
        )
        
        print("\nSummary:")
        print(f"  - Total Videos: {result.get('total_videos', 0)}")
        print(f"  - Successfully Processed: {result.get('success_count', 0)}")
        print(f"  - Failed: {result.get('fail_count', 0)}")
        print(f"  - Skipped (Duplicate): {result.get('skip_count', 0)}")
        print(f"  - Stocks Extracted: {result.get('extracted_stocks_count', 0)}")


def update_market_log():
    """시장 지표 수집 및 Market_Log 업데이트"""
    print("\n=== Updating Market_Log ===")
    
    # CNN 지수 수집
    cnn = CNNScraper()
    fear_index, fear_status = cnn.get_fear_and_greed_index()
    if fear_index != -1:
        print(f"Market Sentiment: {fear_index} ({fear_status})")
    else:
        print(f"Market Sentiment: Load Failed ({fear_status})")
    
    # 시장 데이터 수집
    market_data = MarketDataCollector.get_latest_prices()
    
    # 데이터 준비: [수집일시, CNN지수, CNN상태, 코스피, 나스닥, 원달러환율, 삼성전자, 테슬라, 엔비디아, 비트코인]
    collect_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        collect_time,
        fear_index,
        fear_status,
        market_data.get('kospi', 'N/A'),
        market_data.get('nasdaq', 'N/A'),
        market_data.get('sp500', 'N/A'),
        market_data.get('krw_usd', 'N/A'),
        market_data.get('samsung', 'N/A'),
        market_data.get('tesla', 'N/A'),
        market_data.get('nvidia', 'N/A'),
        market_data.get('bitcoin', 'N/A')
    ]
    
    # 구글 시트 저장
    if not GOOGLE_SHEETS_CREDENTIALS_JSON or not os.path.exists(GOOGLE_SHEETS_CREDENTIALS_JSON):
        print("Error: Google Sheets credentials file not found.")
        print(f"  [Would Save] {row}")
    else:
        logger = SheetLogger(GOOGLE_SHEETS_CREDENTIALS_JSON, SPREADSHEET_URL)
        logger.log_market_data(row)

def main():
    print("=== Stock Insight Automation Started ===")
    
    # 1. 유튜브 로그 업데이트
    update_youtube_log()
    
    # 2. 시장 로그 업데이트
    update_market_log()
    
    print("\n=== All Tasks Completed ===")

if __name__ == "__main__":
    main()
