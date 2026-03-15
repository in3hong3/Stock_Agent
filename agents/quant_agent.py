"""
Quant Analyst Agent
보수적인 퀀트 성향의 주식 애널리스트 AI 에이전트
적정가 밴드와 관심 매수 구간을 계산합니다.
"""
import yfinance as yf
from openai import OpenAI
import os
from typing import Dict, Optional, Tuple


class QuantAnalyst:
    """보수적인 퀀트 애널리스트 AI 에이전트"""
    
    SYSTEM_PROMPT = """너는 보수적인 퀀트 성향의 주식 애널리스트다. 투자 권유가 아니라, 내가 제공한 숫자만으로 "가정 기반 적정가 밴드"와 "관심 매수 구간"을 계산한다.

**핵심 규칙**:
- 내가 숫자를 안 주더라도(예: FCF나 발행 주식 수, WACC 등) "필요한 입력값"을 물어보며 거부하지 말고, 당신의 지식을 총동원하여 업계 평균이나 최근 재무제표 팩트 기반으로 **합리적인 가정을 세워 무조건 끝까지 계산**한다.
- 가정하여 계산한 경우, 분석 내용 첫 줄에 어떤 숫자들을 가정하고 썼는지 명시한다.
- 결과는 간결하게, 계산 근거가 보이게 쓴다.
- 레버리지/대출 가정은 하지 말고, 분할매수 전제를 기본으로 둔다.
- **보수적 관점 유지**: 성장률은 낮게, 할인율은 높게, 멀티플은 보수적으로 가정한다.

---

## 밸류에이션 방법 (3가지)

### 1️⃣ Simple P/E (기본 방식)
**적용 대상**: 이익이 안정적인 성숙기 기업

**계산 방식**:
1) EPS는 (EPS_FY1이 있으면 FY1, 없으면 EPS_TTM)로 사용한다.
2) 적정가 시나리오 3개를 계산한다.
   - 보수 PER = 제공된 값
   - 기준 PER = 제공된 값
   - 낙관 PER = 제공된 값
   적정가 = EPS × PER
3) 추가로 "테마 평균 PER" 값이 주어지면, 테마 평균 PER로도 적정가 1개를 추가 계산한다.

---

### 2️⃣ DCF (Discounted Cash Flow)
**적용 대상**: 성장주, 적자 기업 (미래 현금흐름이 중요한 경우)

**필요 입력값**:
- 현재 FCF (Free Cash Flow) 또는 Revenue
- 성장률 (Year 1-5, %)
- Terminal Growth Rate (영구 성장률, %)
- WACC (할인율, %)
- 발행 주식 수

**계산 방식**:
1) **Year 1-5 FCF 예측**: 
   FCF_Year_N = FCF_Year_0 × (1 + Growth_Rate)^N
2) **Terminal Value (TV)**:
   TV = FCF_Year_5 × (1 + Terminal_Growth) / (WACC - Terminal_Growth)
3) **현재 가치 (PV) 계산**:
   PV = Σ(FCF_Year_N / (1 + WACC)^N) + TV / (1 + WACC)^5
4) **주당 가치**:
   Fair Value = PV / Shares Outstanding

**보수적 시나리오 3개**:
- 보수: 낮은 성장률, 높은 WACC
- 기준: 제공된 값 그대로
- 낙관: 높은 성장률, 낮은 WACC

---

### 3️⃣ SOTP (Sum of the Parts)
**적용 대상**: 여러 사업 부문을 가진 복합 기업 (빅테크, 지주사)

**필요 입력값**:
- 각 사업 부문별:
  - 부문명
  - Revenue 또는 EBITDA
  - 적용 Multiple (P/S 또는 EV/EBITDA)
- Net Debt (순부채)
- 발행 주식 수

**계산 방식**:
1) **각 부문 가치**:
   Segment_Value = Revenue × P/S Multiple (또는 EBITDA × EV/EBITDA)
2) **Enterprise Value (EV)**:
   EV = Σ(Segment_Value)
3) **Equity Value**:
   Equity Value = EV - Net Debt
4) **주당 가치**:
   Fair Value = Equity Value / Shares Outstanding

**보수적 시나리오 3개**:
- 보수: 각 부문에 낮은 멀티플 적용
- 기준: 제공된 멀티플 그대로
- 낙관: 각 부문에 높은 멀티플 적용

---

## 공통 출력 형식 (반드시 지켜라)

**A) 밸류에이션 방법 및 전제** (2~3문장)
- 어떤 방법을 사용했는지
- 주요 가정 (성장률, 할인율, 멀티플 등)

**B) 적정가 계산 표**
| 시나리오 | 주요 가정 | 적정가 | 현재가 대비 |
|---------|---------|--------|------------|
| 보수    | ...     | $XXX   | +/-XX%     |
| 기준    | ...     | $XXX   | +/-XX%     |
| 낙관    | ...     | $XXX   | +/-XX%     |

**C) 관심 매수 구간 3단** (달러로)
- 탐색매수: 현재가 대비 -5%~-10% (비중: 소)
- 메인매수: 현재가 대비 -15%~-25% (비중: 중)
- 패닉매수: 현재가 대비 -30%~-45% (비중: 대)
※ 적정가(보수/기준)와 너무 동떨어지면 이유를 말하고 구간을 조정해라.

**D) 핵심 리스크 5개** (한 줄 bullet)

**E) 체크 포인트 3개** (다음 실적에서 뭘 보면 되는지)

반드시 마크다운 표 형식을 사용하고, 각 섹션을 명확히 구분하여 출력하라."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: OpenAI API 키 (None이면 환경변수에서 가져옴)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        
        self.client = OpenAI(api_key=self.api_key)
    
    def fetch_stock_data(self, ticker: str) -> Dict:
        """
        yfinance를 사용하여 주식 데이터 수집
        
        Args:
            ticker: 주식 티커 (예: TSLA, AAPL)
        
        Returns:
            dict: {
                'ticker': str,
                'price': float,
                'eps_ttm': float,
                'eps_fy1': float,
                'pe_ratio': float,
                'company_name': str,
                'error': str (오류 발생 시)
            }
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # 현재가
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            
            # EPS (TTM)
            eps_ttm = info.get('trailingEps')
            
            # EPS (Forward/FY1)
            eps_fy1 = info.get('forwardEps')
            
            # P/E Ratio
            pe_ratio = info.get('trailingPE') or info.get('forwardPE')
            
            # 회사명
            company_name = info.get('longName') or info.get('shortName') or ticker
            
            return {
                'ticker': ticker.upper(),
                'company_name': company_name,
                'price': round(price, 2) if price else None,
                'eps_ttm': round(eps_ttm, 2) if eps_ttm else None,
                'eps_fy1': round(eps_fy1, 2) if eps_fy1 else None,
                'pe_ratio': round(pe_ratio, 2) if pe_ratio else None,
                'error': None
            }
        
        except Exception as e:
            return {
                'ticker': ticker.upper(),
                'error': f"데이터 수집 실패: {str(e)}"
            }
    
    def generate_analysis(
        self,
        ticker: str,
        price: float,
        valuation_method: str = "pe",  # "pe", "dcf", "sotp"
        # P/E 파라미터
        eps_ttm: Optional[float] = None,
        eps_fy1: Optional[float] = None,
        theme: Optional[str] = None,
        theme_pe: Optional[float] = None,
        pe_low: float = 15,
        pe_base: float = 20,
        pe_high: float = 25,
        # DCF 파라미터
        fcf_current: Optional[float] = None,
        growth_rate: Optional[float] = None,  # %
        terminal_growth: Optional[float] = None,  # %
        wacc: Optional[float] = None,  # %
        shares_outstanding: Optional[float] = None,  # millions
        # SOTP 파라미터
        segments: Optional[list] = None,  # [{"name": str, "revenue": float, "multiple": float}, ...]
        net_debt: Optional[float] = None,
        temperature: float = 0.3
    ) -> str:
        """
        퀀트 애널리스트 분석 생성
        
        Args:
            ticker: 종목 티커
            price: 현재가 (달러)
            valuation_method: 밸류에이션 방법 ("pe", "dcf", "sotp")
            
            # P/E 방식
            eps_ttm: EPS (TTM)
            eps_fy1: EPS (FY1 예상)
            theme: 테마/비교군
            theme_pe: 테마 평균 PER
            pe_low: 보수 PER (기본값: 15)
            pe_base: 기준 PER (기본값: 20)
            pe_high: 낙관 PER (기본값: 25)
            
            # DCF 방식
            fcf_current: 현재 FCF (Free Cash Flow, 백만 달러)
            growth_rate: 성장률 Year 1-5 (%)
            terminal_growth: 영구 성장률 (%)
            wacc: 할인율 (%)
            shares_outstanding: 발행 주식 수 (백만 주)
            
            # SOTP 방식
            segments: 사업 부문 리스트 [{"name": str, "revenue": float, "multiple": float}, ...]
            net_debt: 순부채 (백만 달러)
            
            temperature: AI 창의성 (기본값: 0.3, 보수적)
        
        Returns:
            str: 분석 결과 (마크다운 형식)
        """
        # 밸류에이션 방법별 입력 데이터 구성
        if valuation_method.lower() == "pe":
            user_message = f"""[밸류에이션 방법]
Simple P/E (주가수익비율)

[입력]
- 종목/티커: {ticker}
- 현재가: ${price}
- EPS(TTM): {f'${eps_ttm}' if eps_ttm else '(제공되지 않음)'}
- EPS(FY1 예상): {f'${eps_fy1}' if eps_fy1 else '(제공되지 않음)'}
- 테마/비교군: {theme if theme else '(제공되지 않음)'}
- 테마 평균 PER: {f'{theme_pe}배' if theme_pe else '(제공되지 않음)'}

[PER 시나리오]
- 보수 PER: {pe_low}배
- 기준 PER: {pe_base}배
- 낙관 PER: {pe_high}배

위 정보를 바탕으로 적정가 밴드와 관심 매수 구간을 계산해줘."""

        elif valuation_method.lower() == "dcf":
            user_message = f"""[밸류에이션 방법]
DCF (Discounted Cash Flow)

[입력]
- 종목/티커: {ticker}
- 현재가: ${price}
- 현재 FCF: ${fcf_current}M {' (제공되지 않음)' if fcf_current is None else ''}
- 성장률 (Year 1-5): {growth_rate}% {' (제공되지 않음)' if growth_rate is None else ''}
- Terminal Growth Rate: {terminal_growth}% {' (제공되지 않음)' if terminal_growth is None else ''}
- WACC (할인율): {wacc}% {' (제공되지 않음)' if wacc is None else ''}
- 발행 주식 수: {shares_outstanding}M {' (제공되지 않음)' if shares_outstanding is None else ''}

[보수적 시나리오 가이드]
- 보수: 성장률 -{growth_rate * 0.2 if growth_rate else 5}%, WACC +1%
- 기준: 제공된 값 그대로
- 낙관: 성장률 +{growth_rate * 0.2 if growth_rate else 5}%, WACC -1%

*주의: FCF나 주식수 등 누락된 값이 있더라도 사용자에게 물어보지 마세요. 당신이 가진 기업의 최근 재무 데이터를 바탕으로 합리적인 근사치를 가정하여 무조건 적정가 밴드를 도출하세요.*

위 정보를 바탕으로 DCF 모델로 적정가 밴드와 관심 매수 구간을 계산해줘."""

        elif valuation_method.lower() == "sotp":
            segments_str = ""
            if segments:
                for i, seg in enumerate(segments):
                    segments_str += f"\n  {i+1}. {seg.get('name', 'N/A')}: Revenue ${seg.get('revenue', 0)}M × {seg.get('multiple', 0)}배"
            else:
                segments_str = "\n  (제공되지 않음)"
            
            user_message = f"""[밸류에이션 방법]
SOTP (Sum of the Parts)

[입력]
- 종목/티커: {ticker}
- 현재가: ${price}
- 사업 부문:{segments_str}
- Net Debt (순부채): ${net_debt}M {' (제공되지 않음)' if net_debt is None else ''}
- 발행 주식 수: {shares_outstanding}M {' (제공되지 않음)' if shares_outstanding is None else ''}

[보수적 시나리오 가이드]
- 보수: 각 부문 멀티플 -20%
- 기준: 제공된 멀티플 그대로
- 낙관: 각 부문 멀티플 +20%

위 정보를 바탕으로 SOTP 모델로 적정가 밴드와 관심 매수 구간을 계산해줘."""

        else:
            return f"❌ 지원하지 않는 밸류에이션 방법: {valuation_method}. 'pe', 'dcf', 'sotp' 중 하나를 선택하세요."
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=temperature
            )
            
            return response.choices[0].message.content
        
        except Exception as e:
            return f"❌ 분석 생성 중 오류 발생: {str(e)}"
    
    def analyze_stock(
        self,
        ticker: str,
        manual_price: Optional[float] = None,
        manual_eps_ttm: Optional[float] = None,
        manual_eps_fy1: Optional[float] = None,
        theme: Optional[str] = None,
        theme_pe: Optional[float] = None,
        pe_low: float = 15,
        pe_base: float = 20,
        pe_high: float = 25
    ) -> Tuple[Dict, str]:
        """
        주식 분석 전체 프로세스 (데이터 수집 + 분석 생성)
        
        Args:
            ticker: 주식 티커
            manual_price: 수동 입력 현재가 (None이면 자동 수집)
            manual_eps_ttm: 수동 입력 EPS(TTM)
            manual_eps_fy1: 수동 입력 EPS(FY1)
            theme: 테마/비교군
            theme_pe: 테마 평균 PER
            pe_low: 보수 PER
            pe_base: 기준 PER
            pe_high: 낙관 PER
        
        Returns:
            tuple: (stock_data dict, analysis str)
        """
        # 1. 데이터 수집 (수동 입력이 없는 경우)
        if manual_price is None:
            stock_data = self.fetch_stock_data(ticker)
            
            if stock_data.get('error'):
                return stock_data, f"⚠️ {stock_data['error']}\n\n수동으로 데이터를 입력해주세요."
            
            # 수동 입력값으로 덮어쓰기
            price = manual_price or stock_data.get('price')
            eps_ttm = manual_eps_ttm or stock_data.get('eps_ttm')
            eps_fy1 = manual_eps_fy1 or stock_data.get('eps_fy1')
        else:
            # 모두 수동 입력
            stock_data = {
                'ticker': ticker.upper(),
                'company_name': ticker.upper(),
                'price': manual_price,
                'eps_ttm': manual_eps_ttm,
                'eps_fy1': manual_eps_fy1,
                'error': None
            }
            price = manual_price
            eps_ttm = manual_eps_ttm
            eps_fy1 = manual_eps_fy1
        
        # 2. 필수 데이터 검증
        if price is None:
            return stock_data, "❌ 현재가 정보가 필요합니다. 수동으로 입력해주세요."
        
        if eps_ttm is None and eps_fy1 is None:
            return stock_data, "❌ EPS(TTM) 또는 EPS(FY1) 정보가 필요합니다. 수동으로 입력해주세요."
        
        # 3. 분석 생성
        analysis = self.generate_analysis(
            ticker=ticker,
            price=price,
            eps_ttm=eps_ttm,
            eps_fy1=eps_fy1,
            theme=theme,
            theme_pe=theme_pe,
            pe_low=pe_low,
            pe_base=pe_base,
            pe_high=pe_high
        )
        
        return stock_data, analysis

    def process(self, query: str, **kwargs) -> Dict:
        """
        자연어 질문을 받아 알아서 종목을 추출하고 알맞은 밸류에이션 방법을 선택하여 분석합니다.
        
        Args:
            query: 사용자 질문 (예: "엔비디아 적정가 얼마야?", "테슬라 DCF 밸류에이션 해줘")
        
        Returns:
            dict: {'analysis': 분석 리포트, 'stock_data': 데이터}
        """
        import json
        
        # 1. 쿼리에서 티커 및 의도 추출
        extract_prompt = """사용자의 질문에서 분석할 미국 주식 티커(영어 대문자)와 적합한 밸류에이션 방법을 추출하세요.

[밸류에이션 방법 선택 가이드]
- pe: 이익이 안정적이고 꾸준한 흑자 기업 (예: 애플, 마이크로소프트, 은행주 등). 가장 널리 쓰임.
- dcf: 고성장주, 잉여현금흐름이 중요하거나 이제 막 흑자 전환한 기업, 미래 가치가 중요한 기업 (예: 테슬라, 엔비디아 등)
- sotp: 복합 기업, 사업부가 다양하게 쪼개진 지주사 성격 기업 (예: 알파벳, 디즈니 등)

반드시 아래 JSON 형식만 반환하세요:
{
    "ticker": "TSLA",
    "method": "dcf",
    "reason": "해당 방법을 선택한 짧은 이유"
}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": extract_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.0
            )
            raw = response.choices[0].message.content.strip()
            
            # 마크다운 백틱 제거
            if raw.startswith("```json"):
                raw = raw[7:-3].strip()
            elif raw.startswith("```"):
                raw = raw[3:-3].strip()
                
            parsed = json.loads(raw)
            ticker = parsed.get("ticker")
            method = parsed.get("method", "pe")
            reason = parsed.get("reason", "")
            
            if not ticker:
                return {"error": "질문에서 분석할 종목(티커)을 찾을 수 없습니다."}
                
        except Exception as e:
            return {"error": f"의도 추출 실패: {str(e)}"}

        # 2. 데이터 수집
        stock_data = self.fetch_stock_data(ticker)
        if stock_data.get('error'):
             return {"error": f"⚠️ {stock_data['error']}\n수동 데이터 수집이 필요합니다."}
             
        # 3. 분석 방법별 맞춤 파라미터 세팅
        price = stock_data.get('price')
        if not price:
            return {"error": f"❌ {ticker}의 현재가 정보를 불러올 수 없습니다."}

        # 기본 분석 호출 (동적으로 방식 결정 지원하도록 generate_analysis 개편 필요 없이 있는 거 사용)
        # SOTP나 DCF에 필요한 파라미터가 비어있으면 AI 시스템 프롬프트가 (제공 안됨) 처리 후 알아서 유추하게끔 처리
        analysis = self.generate_analysis(
            ticker=ticker,
            price=price,
            valuation_method=method,
            eps_ttm=stock_data.get('eps_ttm'),
            eps_fy1=stock_data.get('eps_fy1'),
            pe_low=15, pe_base=20, pe_high=25,
            # DCF용 기본 파라미터 (정보 부족 시 GPT가 평균 가정값 사용)
            growth_rate=20.0,
            terminal_growth=3.0,
            wacc=10.0,
            temperature=0.3
        )

        header = f"**💡 분석 방식:** `{method.upper()}` ({reason})\n\n---\n"
        analysis = header + analysis

        return {
            "success": True,
            "stock_data": stock_data,
            "analysis": analysis
        }
