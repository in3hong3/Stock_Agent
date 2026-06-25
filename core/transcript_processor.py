"""
유튜브 스크립트 전처리 모듈
LLM을 사용하여 원본 자막을 구조화된 JSON으로 변환
"""
import os
import json
import re
import uuid
from openai import OpenAI
from dotenv import load_dotenv
from typing import Dict, List, Optional

load_dotenv()


from config.settings import TYPO_CORRECTIONS, LLM_MODEL_DEFAULT, TRANSCRIPT_MODEL

class TranscriptProcessor:
    """
    LLM 기반 스크립트 전처리 엔진
    - 원본 자막 → 구조화된 JSON 변환
    - 종목별 분석 추출
    - 오타 보정
    """
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        self.client = OpenAI(api_key=api_key)
        self.TYPO_CORRECTIONS = TYPO_CORRECTIONS
    
    def _build_raw_chunks(self, transcript_list: List[Dict], chunk_seconds: float = 60.0) -> Dict:
        """
        youtube-transcript-api 결과물을 시간 단위(60초)로 뿐어 Raw Chunk dict 생성
        Returns: {uuid: {'text': str, 'start_time': float, 'end_time': float}}
        """
        if not transcript_list:
            return {}
        raw_chunks = {}
        current_text = ""
        start_time = transcript_list[0].get('start', 0.0)
        for item in transcript_list:
            item_start = item.get('start', 0.0)
            item_text = item.get('text', '').strip()
            if not item_text:
                continue
            current_text += item_text + " "
            if item_start - start_time >= chunk_seconds:
                chunk_id = str(uuid.uuid4())
                raw_chunks[chunk_id] = {"text": current_text.strip(), "start_time": start_time, "end_time": item_start}
                current_text = ""
                start_time = item_start
        if current_text.strip():
            last = transcript_list[-1]
            chunk_id = str(uuid.uuid4())
            raw_chunks[chunk_id] = {"text": current_text.strip(), "start_time": start_time, "end_time": last.get('start', start_time) + last.get('duration', 0.0)}
        print(f"  [Time-aware Chunking] {len(raw_chunks)} raw chunks ({chunk_seconds}s)")
        return raw_chunks

    def process(
        self,
        transcript: str,
        video_title: str = "",
        video_url: str = "",
        transcript_list: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        스크립트를 구조화된 JSON으로 변환
        transcript_list 제공 시 60초 raw_chunks 생성 및 결과에 포함
        """
        if not transcript or transcript.strip() in ['자막 없음', '자막 없음 (자동 자막 미지원)']:
            return {'stocks': [], 'market_context': '', 'summary': '자막 없음', 'raw_transcript': transcript, 'raw_chunks': {}}
        raw_chunks = self._build_raw_chunks(transcript_list) if transcript_list else {}
        corrected_transcript = self._correct_typos(transcript)
        try:
            structured_data = self._extract_structured_data(
                corrected_transcript, video_title, raw_chunk_ids=list(raw_chunks.keys())
            )
            structured_data['raw_transcript'] = transcript[:5000]
            structured_data['raw_chunks'] = raw_chunks
            return structured_data
        except Exception as e:
            print(f"  Error processing transcript: {e}")
            return {'stocks': [], 'market_context': '', 'summary': f'전처리 실패: {str(e)}', 'raw_transcript': transcript[:5000], 'raw_chunks': raw_chunks}
    
    def _correct_typos(self, text: str) -> str:
        """
        오타 보정 (문맥 기반)
        """
        corrected = text
        for typo, correction in self.TYPO_CORRECTIONS.items():
            # 대소문자 구분 없이 교체
            corrected = re.sub(
                re.escape(typo),
                correction,
                corrected,
                flags=re.IGNORECASE
            )
        return corrected
    
    def _extract_structured_data(
        self, transcript: str, video_title: str, raw_chunk_ids: Optional[List[str]] = None
    ) -> Dict:
        """
        LLM으로 구조화 및 세부 세그멘테이션(Semantic Segmentation) 수행.
        각 종목별 요약과 해당 주제의 원문(raw_text)을 추출합니다.
        """
        # 비용 절감을 위해 앞부분만 처리 (중요 정보는 보통 앞에 있음)
        truncated = transcript[:15000]
        
        # [Feature 4] 영상 길이에 따른 동적 처리
        length_instruction = ""
        if len(transcript) < 5000:
            length_instruction = "\n[특수 지시]: 이 영상은 길이가 짧습니다. 억지로 여러 개의 종목으로 나누지 마시고, 문맥(Context)이 끊기지 않도록 가급적 핵심 종목 1~2개나 전체 요약본으로 추출하되, 'raw_text'에는 대본 전체 내용을 통째로 포함시켜 다중 에이전트가 분석할 수 있는 전체 컨텍스트를 제공하세요.\n"
        
        prompt = f"""[Role Definition]
당신은 금융 데이터 전처리 AI이자 전문 주식 애널리스트입니다.
제공된 유튜브 대본을 분석하여 종목별로 '의미 단위 분리(Semantic Segmentation)'를 수행하고 구조화된 정보를 추출하세요.

영상 제목: {video_title}

대본:
{truncated}

---

[보고사항 및 요구사항]{length_instruction}
1. **종목별 분리**: 영상에서 다루는 모든 종목을 파악하고, 각 종목에 대해 이야기하는 '원문 대본(raw_text)'을 최대한 보존하여 분리하세요.
2. **문맥 주입(Contextual Injection)**: 각 종목의 요약과 원문 앞에 [영상 제목][종목명] 정보를 주입하여 정보의 주어를 명확히 하세요.
3. **요약(Summary)**: 검색(Vector Search)에 최적화된 핵심 키워드 중심의 요약을 작성하세요. 목표가, 실적 등 수치를 반드시 포함하세요.
4. **구조화 정보**: 투자 의견(sentiment), 핵심 논지(core_thesis), 주요지표(key_metrics), 리스크 요인을 추출하세요.
5. **연관 관계(Graph)**: 영상에서 이 종목과 함께 언급된 외부 종목/회사(경쟁사, 부품 공급사, 수혜주 등)를 파악하세요.

**출력 형식 (JSON만 반환):**
{{
  "stocks": [
    {{
      "ticker": "티커 (예: NVDA)",
      "name": "종목명",
      "sentiment": "매수/중립/주의",
      "summary": "[영상: {video_title}] [종목: 종목명] 검색용 핵심 요약 텍스트",
      "raw_text": "[영상: {video_title}] [종목: 종목명] 해당 종목을 다루는 실제 대본 원문 전체",
      "core_thesis": ["핵심 논거 1", "핵심 논거 2"],
      "key_metrics": {{
        "target_price": "$900",
        "entry_zone": ["$750", "$800"]
      }},
      "risk_factors": ["리스크 1"],
      "relationships": [
        {{"related_company": "SK하이닉스", "relation_type": "HBM 핵심 공급사 (협력/수혜)", "details": "엔비디아 AI 가속기에 필수적인 HBM 메모리 독점 공급"}}
      ]
    }}
  ]
}}

**주의사항:**
- ⚠️ 이 대본은 음성인식(STT) 결과라 오타·오인식이 매우 많다. 문맥으로 올바른 용어·회사명·미국 티커·숫자로 반드시 교정한 뒤 추출하라.
  예) 밀년→million, 은닝→어닝(실적), 이별선→이동평균선, 정별되→정배열, 계수해서→계속해서,
      서클→Circle(CRCL), 아Q·아이옹크→IonQ(IONQ), 오클러→Oklo(OKLO), 레드켓→Red Cat(RCAT), 템퍼스→Tempus AI(TEM).
- 회사를 정확히 식별하고 'ticker'에는 실제 미국 상장 티커를 넣어라. 비상장(예: SpaceX)이면 ticker는 빈 값으로.
  확신이 없으면 name 옆에 (추정)으로 표시하라. 같은 회사를 STT 오타 때문에 두 종목으로 중복 생성하지 마라.
- "무식하게" 자르지 말고, 주제가 바뀌는 지점을 정확히 파악하여 raw_text를 구성하세요.
- 숫자가 언급되면 하나도 빠짐없이 summary와 key_metrics에 반영하세요. (단 STT로 깨진 숫자·연도는 문맥으로 보정)
- JSON 형식만 반환하고 다른 설명은 하지 마세요.
"""


        response = self.client.chat.completions.create(
            model=TRANSCRIPT_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": """너는 월가 출신 투자 애널리스트야. 
유튜브 영상을 분석하여 투자 보고서를 작성해.
모든 구체적 숫자(가격, 비율, 성장률)를 반드시 추출하고,
투자자가 실전에서 사용할 수 있는 전략과 리스크를 명시해.
항상 유효한 JSON만 반환해."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2,  # 더 정확한 추출을 위해 낮춤
            response_format={"type": "json_object"}  # JSON 모드 강제
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # JSON 파싱
        try:
            data = json.loads(result_text)
            
            # 티커 정규화
            for stock in data.get('stocks', []):
                stock['ticker'] = self._normalize_ticker(stock.get('ticker', ''), stock.get('name', ''))
            
            return data
        except json.JSONDecodeError as e:
            print(f"  JSON parsing error: {e}")
            print(f"  Raw response: {result_text[:200]}")
            raise
    
    def _normalize_ticker(self, ticker: str, name: str) -> str:
        """
        티커 정규화 (대문자 변환, 형식 통일)
        """
        if not ticker:
            # 티커가 없으면 이름으로 추정
            ticker = name
        
        ticker = ticker.strip().upper()
        
        # 한국 주식 (6자리 숫자)
        if re.match(r'^\d{6}$', ticker):
            return f"{ticker}.KS"
        
        # 미국 주식 (1-5자 영문)
        if re.match(r'^[A-Z]{1,5}$', ticker):
            return ticker
        
        # 암호화폐
        if re.match(r'^[A-Z]{2,10}$', ticker) and any(crypto in name.lower() for crypto in ['비트코인', 'bitcoin', '이더리움', 'ethereum']):
            return f"{ticker}-USD"
        
        # 지수
        if ticker.startswith('^'):
            return ticker
        
        return ticker


if __name__ == "__main__":
    # 테스트
    processor = TranscriptProcessor()
    
    test_transcript = """
    안녕하세요 여러분. 오늘은 아이온큐에 대해 얘기해보겠습니다.
    아이온큐는 최근 실적 발표에서 매출이 전년 대비 120% 성장했다고 밝혔습니다.
    EPS는 예상치 0.18을 크게 상회하는 2.8을 기록했고요.
    가이던스도 상향 조정했습니다. 양자컴퓨팅 시장에서 선두를 달리고 있죠.
    
    반면 테슬라는 최근 판매량 감소로 주가가 하락했습니다.
    경쟁이 심화되면서 마진도 압박받고 있어요.
    
    전반적으로 나스닥은 사상 최고치를 경신 중이고, AI 관련주들이 강세입니다.
    """
    
    result = processor.process(test_transcript, "IonQ 실적 분석")
    
    print("=== 처리 결과 ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
