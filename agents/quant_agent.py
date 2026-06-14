"""
Quant Analyst Agent
보수적인 퀀트 성향의 주식 애널리스트 AI 에이전트
적정가 밴드와 관심 매수 구간을 계산합니다.
"""
import yfinance as yf
from openai import OpenAI
import os
from typing import Dict, Optional, Tuple
import json


class QuantAnalyst:
    """보수적인 퀀트 애널리스트 AI 에이전트"""

    SYSTEM_PROMPT = """너는 보수적인 퀀트 성향의 주식 애널리스트다. 투자 권유가 아니라, 내가 제공한 숫자만으로 "가정 기반 적정가 밴드"와 "관심 매수 구간"을 계산한다.

**핵심 규칙**:
- 내가 숫자를 안 주더라도 "필요한 입력값"을 물어보며 거부하지 말고, 당신의 지식을 총동원하여 업계 평균이나 최근 재무제표 팩트 기반으로 **합리적인 가정을 세워 무조건 끝까지 계산**한다.
- 가정하여 계산한 경우, 분석 내용 첫 줄에 어떤 숫자들을 가정하고 썼는지 명시한다.
- 레버리지/대출 가정은 하지 말고, 분할매수 전제를 기본으로 둔다.
- **보수적 관점 유지**: 성장률은 낮게, 할인율은 높게, 멀티플은 보수적으로 가정한다.

---

## 밸류에이션 방법 (4가지)

### 1️⃣ Simple P/E (기본 방식)
**적용 대상**: 이익이 안정적인 꾸준한 흑자 기업 (빅테크 소프트웨어 등)
**계산**: 적정가 = EPS(FY1 또는 TTM) × 타겟 PER

### 2️⃣ P/B (Price-to-Book) Band
**적용 대상**: 메모리 반도체, 에너지 등 실적 변동성이 큰 시클리컬(경기민감) 기업
**계산**: 적정가 = Book Value (BPS) × 타겟 P/B 배수
*주의: 이익이 Peak일 때 오히려 낮은 타겟 P/B를, 적자일 때 높은 타겟 P/B를 부여하는 업계 특성을 반영할 것.

🚨 **[멀티플 제한 가이드라인 - 절대 엄수]**:
AI 임의로 높은 P/B를 부여하지 마라. 현재 주가나 현재 P/B 비율이 비정상적으로 높더라도, 역사적 밴드를 기준으로 아래의 제한을 반드시 지켜라.
- 반도체 제조업/하드웨어 (예: MU, INTC 등): 타겟 P/B는 절대 **0.8 ~ 3.0 범위**를 벗어날 수 없다. (불황기 1.0 내외, 호황기 2.5 내외)
- 철강/에너지/화학: 타겟 P/B는 절대 **0.5 ~ 1.5 범위**를 벗어날 수 없다.

### 3️⃣ DCF (Discounted Cash Flow)
**적용 대상**: 고성장주, 적자 탈출 초기 기업
**계산**: 잉여현금흐름(FCF) 기반 5년 영구 가치 할인 모형 적용.

### 4️⃣ SOTP (Sum of the Parts)
**적용 대상**: 여러 사업 부문을 가진 복합 지주사
**계산**: 각 사업부 매출/EBITDA × 부문별 멀티플 합산 - 순부채

---

## 공통 출력 형식 (반드시 마크다운 표 유지)

**A) 밸류에이션 방법 및 전제**
- 사용한 방법론과 그 이유
- 주요 가정 (EPS, BPS, 성장률, 멀티플 등)

**B) 적정가 계산 표**
| 시나리오 | 주요 가정 | 적정가 | 현재가 대비 |
|---------|---------|--------|------------|
| 보수    | ...     | $XXX   | +/-XX%     |
| 기준    | ...     | $XXX   | +/-XX%     |
| 낙관    | ...     | $XXX   | +/-XX%     |

**C) 관심 매수 구간 3단** (달러로)
🚨 **중요 규칙**: 매수 구간은 '현재가' 기준이 아니라, **위에서 계산된 [기준 시나리오 적정가]를 바탕으로 안전마진을 차감**하여 계산해라.
- 탐색매수: 적정가(기준) 대비 -10%~-15% (비중: 소)
- 메인매수: 적정가(기준) 대비 -20%~-30% (비중: 중)
- 패닉매수: 적정가(기준) 대비 -35% 이상 하락 시 (비중: 대)

**D) 핵심 리스크 5개** (한 줄 bullet)

**E) 체크 포인트 3개** (다음 실적 발표 시 모니터링할 지표)
"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
        self.client = OpenAI(api_key=self.api_key)

    def fetch_stock_data(self, ticker: str) -> Dict:
        """yfinance를 사용하여 주식 데이터 수집 (Book Value 추가)"""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            price = info.get('currentPrice') or info.get('regularMarketPrice')
            eps_ttm = info.get('trailingEps')
            eps_fy1 = info.get('forwardEps')
            pe_ratio = info.get('trailingPE') or info.get('forwardPE')
            book_value = info.get('bookValue')      # 주당순자산 추가
            pb_ratio = info.get('priceToBook')      # P/B 비율 추가
            company_name = info.get('longName') or info.get('shortName') or ticker

            return {
                'ticker': ticker.upper(),
                'company_name': company_name,
                'price': round(price, 2) if price else None,
                'eps_ttm': round(eps_ttm, 2) if eps_ttm else None,
                'eps_fy1': round(eps_fy1, 2) if eps_fy1 else None,
                'pe_ratio': round(pe_ratio, 2) if pe_ratio else None,
                'book_value': round(book_value, 2) if book_value else None,
                'pb_ratio': round(pb_ratio, 2) if pb_ratio else None,
                'error': None
            }
        except Exception as e:
            return {'ticker': ticker.upper(), 'error': f"데이터 수집 실패: {str(e)}"}

    def generate_analysis(self, ticker: str, price: float, valuation_method: str = "pe", **kwargs) -> str:
        """선택된 밸류에이션 방법에 따라 프롬프트를 구성하고 AI 분석 요청"""

        base_info = f"- 종목/티커: {ticker}\n- 현재가: ${price}\n"

        if valuation_method.lower() == "pe":
            eps_ttm = kwargs.get('eps_ttm')
            eps_fy1 = kwargs.get('eps_fy1')
            user_message = f"[밸류에이션 방법] Simple P/E\n[입력]\n{base_info}"
            user_message += f"- EPS(TTM): ${eps_ttm if eps_ttm else '(제공되지 않음. 추정 요망)'}\n"
            user_message += f"- EPS(FY1 예상): ${eps_fy1 if eps_fy1 else '(제공되지 않음. 추정 요망)'}\n"
            user_message += "\n제공된 지표 또는 역사적 평균을 가정하여 P/E 기반 적정가를 도출해줘."

        elif valuation_method.lower() == "pb":
            book_value = kwargs.get('book_value')
            pb_ratio = kwargs.get('pb_ratio')
            user_message = f"[밸류에이션 방법] P/B (시클리컬 전용)\n[입력]\n{base_info}"
            user_message += f"- Book Value (주당순자산): ${book_value if book_value else '(제공되지 않음. 추정 요망)'}\n"
            user_message += f"- 현재 P/B Ratio: {pb_ratio if pb_ratio else '(제공되지 않음)'}\n"
            user_message += "\n해당 기업의 역사적 P/B 밴드를 보수적으로 가정하여, 호황기/불황기 사이클을 고려한 적정가를 도출해줘."

        elif valuation_method.lower() == "dcf":
            user_message = f"[밸류에이션 방법] DCF\n[입력]\n{base_info}"
            user_message += "재무 지표가 제공되지 않았습니다. 해당 기업의 업계 평균 잉여현금흐름(FCF), WACC(약 9~11%), 영구성장률(약 2~3%)을 보수적으로 임의 가정하여 DCF 적정가를 도출해줘."

        elif valuation_method.lower() == "sotp":
            user_message = f"[밸류에이션 방법] SOTP\n[입력]\n{base_info}"
            user_message += "세부 사업 부문 매출이 제공되지 않았습니다. 기업의 주요 비즈니스 모델을 분석해 핵심 부문별 멀티플을 다르게 적용하는 SOTP 방식으로 적정가를 도출해줘."

        else:
            return f"❌ 지원하지 않는 밸류에이션 방법: {valuation_method}. 'pe', 'pb', 'dcf', 'sotp' 중 하나를 선택하세요."

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_message}
                ],
                temperature=kwargs.get('temperature', 0.2)
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"❌ 분석 생성 중 오류 발생: {str(e)}"

    def process(self, query: str) -> Dict:
        """자연어 질문 기반 종목 추출 및 밸류에이션 매칭 파이프라인"""

        extract_prompt = """사용자의 질문에서 분석할 미국 주식 티커(영어 대문자)와 적합한 밸류에이션 방법을 추출하세요.

[밸류에이션 방법 선택 가이드]
- pb: 메모리 반도체, 철강, 정유 등 실적 변동성이 매우 큰 경기민감주/시클리컬 기업 (예: MU, XOM, TXN 등)
- pe: 이익이 안정적이고 꾸준한 일반적인 흑자 기업 (예: AAPL, MSFT, V 등)
- dcf: 고성장주, 현금흐름이 중요한 빅테크나 적자 탈출 기업 (예: TSLA, NVDA 등)
- sotp: 복합 사업을 영위하는 지주사 성격의 기업 (예: GOOGL, DIS 등)

반드시 아래 JSON 형식만 반환하세요:
{
    "ticker": "MU",
    "method": "pb",
    "reason": "마이크론은 대표적인 메모리 반도체 시클리컬 주식이므로 P/B가 적합함"
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

        # 데이터 수집
        stock_data = self.fetch_stock_data(ticker)
        if stock_data.get('error'):
            return {"error": f"⚠️ {stock_data['error']}\n수동 데이터 수집이 필요합니다."}

        price = stock_data.get('price')
        if not price:
            return {"error": f"❌ {ticker}의 현재가 정보를 불러올 수 없습니다."}

        # ── P/B 과열 감지: 현재 P/B가 역사적 상한(3.0)의 2배 초과 시 DCF로 자동 전환 ──
        pb_warning = ""
        current_pb = stock_data.get('pb_ratio')
        PB_HISTORICAL_UPPER = 3.0   # 반도체 제조업 역사적 P/B 상한
        PB_OVERHEATING_THRESHOLD = PB_HISTORICAL_UPPER * 2  # = 6.0

        if method == "pb" and current_pb and current_pb > PB_OVERHEATING_THRESHOLD:
            pb_warning = (
                f"\n\n> 🚨 **[P/B 과열 감지 — 방법론 자동 전환]**\n"
                f"> 현재 P/B가 **{current_pb:.1f}배**로, 역사적 상한선(3.0배)의 **{current_pb / PB_HISTORICAL_UPPER:.1f}배** 수준입니다.\n"
                f"> P/B 밴드 분석은 현재 가격과 역사적 적정가의 괴리가 너무 커 신뢰도가 낮습니다.\n"
                f"> ➜ **DCF(현금흐름 할인) 방식으로 자동 전환하여 분석합니다.**\n"
            )
            method = "dcf"
            reason = f"P/B 과열(현재 {current_pb:.1f}배) 감지 → DCF로 자동 전환"

        # 분석 실행 — 방법론에 맞는 데이터만 kwargs로 전달
        analysis = self.generate_analysis(
            ticker=ticker,
            price=price,
            valuation_method=method,
            eps_ttm=stock_data.get('eps_ttm'),
            eps_fy1=stock_data.get('eps_fy1'),
            book_value=stock_data.get('book_value'),
            pb_ratio=stock_data.get('pb_ratio'),
            temperature=0.2
        )

        header = f"**💡 분석 방식:** `{method.upper()}` ({reason}){pb_warning}\n\n---\n"
        analysis = header + analysis

        return {
            "success": True,
            "stock_data": stock_data,
            "analysis": analysis
        }
