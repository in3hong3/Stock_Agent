"""
종목 추출 모듈
영상 요약에서 AI를 사용하여 언급된 종목 정보를 추출합니다.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv
import json
import re

load_dotenv()


class StockExtractor:
    """영상 요약에서 종목 정보를 추출하는 클래스"""
    
    # 주요 종목 티커 매핑 (한글 → 티커)
    TICKER_MAP = {
        # 주요 지수 및 ETF
        "S&P 500": "^GSPC",
        "S&P500": "^GSPC",
        "SP500": "^GSPC",
        "나스닥": "^IXIC",
        "나스닥종합": "^IXIC",
        "다우": "^DJI",
        "다우존스": "^DJI",
        "다우 존스": "^DJI",
        "다우존스 산업평균지수": "^DJI",
        "러셀": "^RUT",
        "러셀2000": "^RUT",
        "반도체지수": "^SOX",
        "필라델피아반도체": "^SOX",
        "VIX": "^VIX",
        "공포탐욕지수": "^VIX",
        "QQQ": "QQQ",
        "SPY": "SPY",
        "SOXL": "SOXL",
        "TQQQ": "TQQQ",
        "금": "GLD",
        "은": "SLV",
        "금 ETF": "GLD",
        "은 ETF": "SLV",
        "방산주": "ITA", # iShares U.S. Aerospace & Defense ETF (대표 ETF)
        
        # 한국 주식
        "삼성전자": "005930.KS",
        "삼성": "005930.KS", # 약어 추가
        "삼전": "005930.KS",
        "Samsung Electronics": "005930.KS",
        "SK하이닉스": "000660.KS",
        "하이닉스": "000660.KS",
        "SK 하이닉스": "000660.KS",
        "SK Hynix": "000660.KS",
        "현대차": "005380.KS",
        "기아": "000270.KS",
        "POSCO홀딩스": "005490.KS",
        "포스코홀딩스": "005490.KS",
        "LG에너지솔루션": "373220.KS",
        "엔솔": "373220.KS",
        "삼성바이오로직스": "207940.KS",
        "카카오": "035720.KS",
        "네이버": "035420.KS",
        "NAVER": "035420.KS",
        "셀트리온": "068270.KS",
        "현대모비스": "012330.KS",
        "LG화학": "051910.KS",
        "삼성SDI": "006400.KS",
        "KB금융": "105560.KS",
        "신한지주": "055550.KS",
        
        # 미국 주식
        "애플": "AAPL",
        "Apple": "AAPL",
        "마이크로소프트": "MSFT",
        "Microsoft": "MSFT",
        "마소": "MSFT",
        "엔비디아": "NVDA",
        "NVIDIA": "NVDA",
        "테슬라": "TSLA",
        "Tesla": "TSLA",
        "아마존": "AMZN",
        "Amazon": "AMZN",
        "구글": "GOOGL",
        "Google": "GOOGL",
        "알파벳": "GOOGL",
        "메타": "META",
        "페이스북": "META",
        "넷플릭스": "NFLX",
        "AMD": "AMD",
        "인텔": "INTC",
        "퀄컴": "QCOM",
        "마이크론": "MU",
        "Micron": "MU",
        "팔란티어": "PLTR",
        "팔란테르": "PLTR",
        "스노우플레이크": "SNOW",
        "코인베이스": "COIN",
        "로블록스": "RBLOX",
        "아이온큐": "IONQ",
        "아온큐": "IONQ", # 오타 대응
        "아Q": "IONQ",
        "아이런": "IONQ", # 오타 대응
        "아이랜": "IONQ", # 오타 대응
        "아이렌": "IONQ", # 오타 대응
        "아이언": "IONQ", # 오타 대응
        "로켓랩": "RKLB",
        "로켓 랩": "RKLB",
        "Rocket Lab": "RKLB",
        "오픈도어": "OPEN",
        "유니티": "U",
        "TSMC": "TSM",
        "슈퍼마이크로": "SMCI",
        "슈마컴": "SMCI",
        "브로드컴": "AVGO",
        "일라이릴리": "LLY",
        "노보노디스크": "NVO",
        "오라클": "ORCL",
        "어도비": "ADBE",
        "세일즈포스": "CRM",
        "IBM": "IBM",
        "SAP": "SAP",
        "서비스나우": "NOW",
        "우버": "UBER",
        "에어비앤비": "ABNB",
        "보잉": "BA",
        "록히드마틴": "LMT",
        "RTX": "RTX",
        "제이피모건": "JPM",
        "JP모건": "JPM",
        "모건스탠리": "MS",
        "모건 스탠리": "MS",
        "골드만삭스": "GS",
        "뱅크오브아메리카": "BAC",
        "Bank of America": "BAC",
        "씨티그룹": "C",
        "비자": "V",
        "Visa": "V",
        "마스터카드": "MA",
        "Mastercard": "MA",
        "월마트": "WMT",
        "코스트코": "COST",
        "유나이티드헬스": "UNH",
        "유나이티드 헬스 그룹": "UNH",
        "존슨앤존슨": "JNJ",
        "화이자": "PFE",
        "모더나": "MRNA",
        "샌디스크": "WDC", # 웨스턴디지털로 매핑 (샌디스크 인수됨)
        "웨스턴디지털": "WDC",
        "엑슨모빌": "XOM",
        "엑스모빌": "XOM",
        "스카이워드": "SWKS", # 스카이웍스 솔루션즈 추정 (Skyworks)
        "스카이웍스": "SWKS",
        
        # 암호화폐
        "비트코인": "BTC-USD",
        "이더리움": "ETH-USD",
        "리플": "XRP-USD",
        "솔라나": "SOL-USD",
        "도지코인": "DOGE-USD",
    }
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        self.client = OpenAI(api_key=api_key)
    
    def extract_stocks_from_transcript(self, transcript, video_title=""):
        """
        원본 자막에서 언급된 종목 추출 (AI 요약 없이 직접 추출)
        Args:
            transcript: 원본 자막 텍스트
            video_title: 영상 제목 (추가 컨텍스트)
        Returns:
            list: 종목 정보 딕셔너리 리스트
                  [{'종목명': '삼성전자', 'ticker': '005930.KS', 'market': 'KR'}, ...]
        """
        if not transcript or transcript.strip() in ['자막 없음', '요약 실패', '자막 없음 (자동 자막 미지원)']:
            return []
        
        # 1단계: 정규식으로 먼저 시도 (무료)
        regex_stocks = self.extract_stocks_regex(transcript)
        
        # 2단계: 정규식으로 찾은 게 있으면 바로 반환 (비용 절감)
        if len(regex_stocks) >= 3:  # 3개 이상 찾으면 충분
            return regex_stocks
        
        # 3단계: 못 찾았거나 적게 찾으면 AI 사용 (자막 앞부분만)
        truncated_transcript = transcript[:5000]  # 비용 절감을 위해 5,000자만
        
        prompt = f"""다음은 주식/투자 관련 YouTube 영상의 자막입니다. 
영상에서 언급된 **모든 기업, 종목, ETF, 암호화폐, 지수**를 빠짐없이 추출해주세요.

영상 제목: {video_title}
 
영상 자막 (앞부분):
{truncated_transcript}

**추출 규칙:**
1. 투자 대상이 될 수 있는 모든 고유명사 추출 (기업명, 티커, 코인명, ETF 등)
2. "매수", "매도", "전망", "분석", "실적", "상승", "하락" 등과 함께 언급된 기업은 반드시 포함
3. 단순히 비유로 사용된 경우가 아니라면 스쳐가듯 언급된 종목도 포함
4. 한글 종목명과 영문 종목명 모두 추출
5. 각 종목에 대해 다음 정보를 JSON 배열로 반환:
   - stock_name: 종목명 (가능한 정확한 공식 명칭 사용, 예: "삼전"->"삼성전자")
   - market: 시장 구분 ("KR"=한국, "US"=미국, "CRYPTO"=암호화폐, "INDEX"=지수/ETF)

**출력 형식 (JSON만 반환):**
[
  {{"stock_name": "삼성전자", "market": "KR"}},
  {{"stock_name": "NVIDIA", "market": "US"}},
  {{"stock_name": "비트코인", "market": "CRYPTO"}},
  {{"stock_name": "나스닥", "market": "INDEX"}}
]

종목이 없으면 빈 배열 [] 반환.
"""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "너는 주식 종목 추출 전문가야. JSON 형식으로만 답변해."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # JSON 파싱
            # 코드 블록 제거
            result_text = re.sub(r'```json\s*|\s*```', '', result_text)
            
            stocks_data = json.loads(result_text)
            
            # 티커 변환
            processed_stocks = []
            for stock in stocks_data:
                stock_name = stock.get('stock_name', '')
                market = stock.get('market', 'US')
                
                ticker = self.normalize_ticker(stock_name, market)
                
                if ticker:
                    processed_stocks.append({
                        '종목명': stock_name,
                        'ticker': ticker,
                        'market': market
                    })
            
            return processed_stocks
            
        except Exception as e:
            print(f"  Error extracting stocks: {e}")
            return []
    
    def extract_stocks_regex(self, text):
        """
        정규식 패턴 매칭으로 종목 추출 (AI 없이 무료)
        Args:
            text: 자막 또는 요약 텍스트
        Returns:
            list: 종목 정보 딕셔너리 리스트
        """
        found_stocks = []
        seen_tickers = set()
        
        # TICKER_MAP에서 종목명 찾기
        for stock_name, ticker in self.TICKER_MAP.items():
            if stock_name in text:
                # 중복 방지
                if ticker in seen_tickers:
                    continue
                
                # 시장 구분 추정
                market = self._guess_market(ticker)
                
                found_stocks.append({
                    '종목명': stock_name,
                    'ticker': ticker,
                    'market': market
                })
                seen_tickers.add(ticker)
        
        return found_stocks
    
    def _guess_market(self, ticker):
        """
        티커로부터 시장 구분 추정
        Args:
            ticker: 티커 심볼
        Returns:
            str: 시장 구분 (KR/US/CRYPTO/INDEX)
        """
        if ticker.endswith('.KS') or ticker.endswith('.KQ'):
            return 'KR'
        elif ticker.endswith('-USD'):
            return 'CRYPTO'
        elif ticker.startswith('^'):
            return 'INDEX'
        else:
            return 'US'
    
    def extract_stocks_from_summary(self, summary, video_title=""):
        """
        영상 요약에서 언급된 종목 추출 (기존 메서드, 하위 호환성 유지)
        Args:
            summary: 영상 AI 요약 텍스트
            video_title: 영상 제목 (추가 컨텍스트)
        Returns:
            list: 종목 정보 딕셔너리 리스트
        """
        # 내부적으로 extract_stocks_from_transcript 호출
        return self.extract_stocks_from_transcript(summary, video_title)
    
    def normalize_ticker(self, stock_name, market):
        """
        종목명을 티커 심볼로 변환
        Args:
            stock_name: 종목명
            market: 시장 구분 (KR/US/CRYPTO/INDEX)
        Returns:
            str: 티커 심볼 (예: "005930.KS", "AAPL", "BTC-USD", "^GSPC")
        """
        # 공백 제거 및 대문자 변환
        stock_name_clean = stock_name.strip()
        
        # 매핑 테이블에서 찾기 (정확한 이름)
        if stock_name_clean in self.TICKER_MAP:
            return self.TICKER_MAP[stock_name_clean]
            
        # 매핑 테이블에서 찾기 (대문자로 변환하여 검색)
        if stock_name_clean.upper() in self.TICKER_MAP:
            return self.TICKER_MAP[stock_name_clean.upper()]
        
        # 이미 티커 형식인 경우 처리
        
        # 1. 지수 (INDEX)
        if market == "INDEX" or stock_name_clean.startswith("^"):
            if stock_name_clean.startswith("^"):
                return stock_name_clean
            # 주요 지수 티커 패턴
            if stock_name_clean in ["SPX", "NDX", "DJX"]:
                index_map = {"SPX": "^GSPC", "NDX": "^IXIC", "DJX": "^DJI"}
                return index_map.get(stock_name_clean)
        
        # 2. 미국 주식 (US)
        if market == "US":
            # 영문 대문자만 있는 경우 (예: NVDA, AAPL)
            if re.match(r'^[A-Z]{1,5}$', stock_name_clean.upper()):
                return stock_name_clean.upper()
        
        # 3. 한국 주식 (KR)
        elif market == "KR":
            # 6자리 숫자인 경우 (예: 005930)
            if re.match(r'^\d{6}$', stock_name_clean):
                return f"{stock_name_clean}.KS"
        
        # 4. 암호화폐 (CRYPTO)
        elif market == "CRYPTO":
            # 암호화폐 티커 (예: BTC, ETH)
            clean_ticker = stock_name_clean.upper()
            if re.match(r'^[A-Z]{2,10}$', clean_ticker):
                return f"{clean_ticker}-USD"
        
        # 변환 실패 시 원본 반환 (나중에 수동 매핑 필요)
        print(f"  Warning: Could not normalize ticker for '{stock_name}' ({market})")
        return stock_name


if __name__ == "__main__":
    # 테스트 코드
    extractor = StockExtractor()
    
    test_summary = """
    ## Executive Summary
    삼성전자와 SK하이닉스의 실적 전망을 분석했습니다. 
    엔비디아의 GPU 수요 증가로 인해 HBM 시장이 성장하고 있습니다.
    비트코인은 최근 급등세를 보이고 있으며, 테슬라의 전기차 판매도 증가했습니다.
    다우 존스와 나스닥은 사상 최고치를 경신 중입니다.
    """
    
    stocks = extractor.extract_stocks_from_summary(test_summary, "반도체 시장 전망")
    
    print("=== 추출된 종목 ===")
    for stock in stocks:
        print(f"종목명: {stock['종목명']}, 티커: {stock['ticker']}, 시장: {stock['market']}")
