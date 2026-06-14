"""
Agentic RAG Router
사용자 질문의 의도를 분석하여 최적의 에이전트로 라우팅하는 오케스트레이터.

라우팅 전략:
  A (RAG_ONLY)   : 유튜버 인사이트, 매매 관점, 영상 기반 시황 분석
  B (QUANT_ONLY) : 현재가, 재무 지표, 적정가 계산 등 실시간 수치
  C (BOTH)       : 유튜버 시각 + 실시간 데이터를 함께 요구하는 복합 질문
"""
import json
import logging
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from openai import OpenAI
from agents.rag_agent import RAGAgent
from agents.quant_agent import QuantAnalyst
from config.settings import LLM_MODEL_DEFAULT, AGENT_REGISTRY

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 1. 라우터 전용 시스템 프롬프트
# ──────────────────────────────────────────────
ROUTER_SYSTEM_PROMPT = """당신은 "Stock Agent" 멀티-에이전트 시스템의 **지능형 트래픽 컨트롤러(라우터)**입니다.
당신의 유일한 임무는 사용자의 질문을 분석하여, 아래 4가지 경로 중 하나를 선택하는 것입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[경로 A] RAG_ONLY  → ChromaDB 유튜브 영상 검색
  적합한 질문:
  - 유튜버의 의견, 전망, 매매 전략이 궁금한 경우
  - "유튜버가 뭐라고 했어?", "OOO 종목 어떻게 봐?", "시장 분위기 어때?" 류
  - 투자 철학, 거시 경제 관점, 섹터 트렌드 질문

[경로 B] QUANT_ONLY  → yfinance 기본 실시간 데이터
  적합한 질문:
  - 지금 당장의 주가, 시총, PER, EPS, 배당률 등 가치평가 및 기본적 수치 질문
  - "현재가 얼마야?", "PER 몇이야?", "적정가 계산해줘" 류

[경로 C] TECH_ONLY → yfinance 기술적 지표 및 차트 분석
  적합한 질문:
  - 캔들차트, 이동평균선(MA), RSI, MACD, 볼린저 밴드 등 차트 지표 질문
  - 단기적인 매수/매도 타이밍, 지지선/저항선, 추세, "지금 차트 어때?" 류
  - "엔비디아 차트 분석해줘", "RSI 얼마야?", "과매도 구간이야?" 류

[경로 D] BOTH  → RAG(유튜버) + QUANT(기본적) + TECH(기술적) 모두 종합
  적합한 질문:
  - 종합적인 투자 판단이 필요한 경우
  - "현재 주가랑 유튜버 목표가, 그리고 차트 상황까지 싹 다 비교해줘", "지금 사도 될까?" 류

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[🚨 핵심 규칙 - 할루시네이션 방지]
1. "현재가", "지금 가격" 등의 키워드가 있으면 과거 수치인 RAG_ONLY를 피하고 QUANT_ONLY, TECH_ONLY 또는 BOTH를 선택하세요.
2. "차트", "RSI", "이평선", "타점" 등의 단어가 나오면 반드시 TECH_ONLY 또는 BOTH를 선택하세요.
3. 종목 티커(NVDA, AAPL 등)나 한글 종목명이 포함되면 해당 티커를 추출하세요.
4. 질문이 모호하면 경로 A(RAG)를 기본으로 선택하세요.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

반드시 아래 JSON 형식만 반환하세요. 다른 텍스트는 절대 포함하지 마세요:
{
  "route": "RAG_ONLY" | "QUANT_ONLY" | "TECH_ONLY" | "BOTH",
  "tickers": ["NVDA", "AAPL"],
  "reasoning": "라우팅 이유 (한 문장)"
}"""


# ──────────────────────────────────────────────
# 2. 종합(Synthesize) 및 페르소나 주입 프롬프트
# ──────────────────────────────────────────────
SYNTHESIZER_SYSTEM_PROMPT = """당신은 리스크 관리를 생명으로 아는 "깐깐한 시니어 투자 분석가"입니다.
당신의 임무는 실시간 수치(기본/기술적 분석)와 유튜버의 인사이트를 융합하여 사용자에게 '뼈 때리는' 조언을 건네는 것입니다.

[나의 페르소나 및 행동 강령]
1. **단호함**: 불확실한 호재에 들떠있는 사용자에게는 냉정한 지표(PER 과열, RSI 과매도 등)를 들이밀며 제동을 거세요.
2. **팩트 우선**: 유튜버가 긍정적으로 말했더라도, 실시간 수치나 차트 지표가 나쁘면 "유튜버는 이렇게 보지만, 현재 수치는 위험 신호를 보내고 있다"고 경고하세요.
3. **리스크 강조**: 모든 답변의 마지막에는 반드시 발생 가능한 리스크 2가지를 언급하며 "추격 매수는 독약"이라는 점을 상기시키세요.
4. **구체성**: "좋아 보인다"는 말 대신 "언제 녹화된 영상에서 어느 수치를 근거로 이렇게 말했다"고 출처를 명확히 하세요.

[입력 소스]
- 📊 실시간 기본 지표 (yfinance) : 현재 가격, EPS, PER 등
- 📈 실시간 기술적 지표 (yfinance) : RSI, MACD, 이동평균선, 볼린저 밴드 등
- 🎥 유튜버 인사이트 (RAG DB)     : 최근 영상 기반 시각과 매매 관점

[응답 가이드]
- 유튜버의 의견이 현재 시황과 어긋난다면 가감 없이 지적하세요.
- 차트(기술적 지표)와 펀더멘탈(기본 지표)을 종합하여 단기/장기 뷰를 나눠 설명해도 좋습니다.
- 말투는 정중하지만 매우 단호하고 분석적이어야 합니다.
- 투자 권유가 아닌 분석 결과임을 명시하고, 최종 판단은 본인의 책임임을 강조하세요."""


# ──────────────────────────────────────────────
# 3. 라우터 클래스
# ──────────────────────────────────────────────
class AgenticRouter:
    """
    사용자 질문을 의도에 따라 적절한 에이전트로 라우팅하는 오케스트레이터.
    """

    def __init__(self):
        self.client = OpenAI()

        # RAGAgent 초기화 (설정에서 첫 번째 rag 타입 에이전트 사용)
        rag_config = next(
            (v for v in AGENT_REGISTRY.values() if v.get("type") == "rag"),
            {"id": "rag_default", "name": "RAG 에이전트", "description": "유튜브 영상 검색"}
        )
        self.rag_agent = RAGAgent(
            agent_id=rag_config.get("id", "rag_default"),
            name=rag_config.get("name", "RAG 에이전트"),
            description=rag_config.get("description", "유튜브 영상 검색"),
            channel_id=rag_config.get("channel_id")
        )

        # QuantAnalyst 초기화
        self.quant_agent = QuantAnalyst()

        # TechnicalAgent 초기화
        from agents.technical_agent import TechnicalAgent
        self.tech_agent = TechnicalAgent()

        logger.info("AgenticRouter 초기화 완료")

    # ──────────────────────────────────────────
    # 3-1. 의도 분류(라우팅) 결정
    # ──────────────────────────────────────────
    def _classify_intent(self, query: str) -> Dict[str, Any]:
        """
        LLM을 사용해 사용자 질문의 라우팅 경로를 결정합니다.

        Returns:
            {"route": str, "tickers": list, "reasoning": str}
        """
        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": query}
                ],
                temperature=0.0,  # 라우팅은 결정론적으로
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content.strip()
            result = json.loads(raw)
            logger.info(f"[Router] 라우팅 결정: {result}")
            return result
        except Exception as e:
            logger.warning(f"[Router] 의도 분류 실패, RAG_ONLY 기본값 사용: {e}")
            return {"route": "RAG_ONLY", "tickers": [], "reasoning": "분류 실패, 기본 경로 사용"}

    # ──────────────────────────────────────────
    # 3-2. 각 에이전트 호출
    # ──────────────────────────────────────────
    def _call_rag(self, query: str, conversation_history: Optional[List] = None) -> Dict:
        """RAGAgent를 호출하고 결과를 반환합니다."""
        try:
            result = self.rag_agent.process(
                query=query,
                conversation_history=conversation_history
            )
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"[Router] RAG 에이전트 호출 실패: {e}")
            return {"success": False, "error": str(e)}

    def _call_quant(self, tickers: List[str]) -> Dict:
        """
        QuantAnalyst를 호출하고 결과를 반환합니다.
        여러 종목이면 모두 조회합니다.
        """
        results = {}
        for ticker in tickers:
            try:
                stock_data = self.quant_agent.fetch_stock_data(ticker=ticker)
                results[ticker] = {
                    "success": True,
                    "stock_data": stock_data,
                }
            except Exception as e:
                logger.error(f"[Router] Quant 에이전트 호출 실패 ({ticker}): {e}")
                results[ticker] = {"success": False, "error": str(e)}
        return results

    def _call_tech(self, query: str, tickers: List[str]) -> Dict:
        """
        TechnicalAgent를 호출하고 결과를 반환합니다.
        여러 종목이면 모두 조회합니다.
        """
        results = {}
        for ticker in tickers:
            try:
                response = self.tech_agent.process(query=query, ticker=ticker)
                if response.get("indicators") and "error" not in response["indicators"]:
                    results[ticker] = {
                        "success": True,
                        "indicators": response["indicators"],
                        "analysis": response["analysis"]
                    }
                else: 
                    error_msg = response.get("indicators", {}).get("error", "알 수 없는 오류 발생") if isinstance(response.get("indicators"), dict) else response.get("analysis")
                    results[ticker] = {"success": False, "error": error_msg}
            except Exception as e:
                logger.error(f"[Router] Tech 에이전트 호출 실패 ({ticker}): {e}")
                results[ticker] = {"success": False, "error": str(e)}
        return results

    # ──────────────────────────────────────────
    # 3-3. BOTH 경로: 결과 종합
    # ──────────────────────────────────────────
    def _synthesize(
        self,
        query: str,
        rag_result: Dict,
        quant_result: Dict,
        tech_result: Dict
    ) -> str:
        """
        RAG, Quant, Tech 에이전트의 결과를 종합하여 최종 답변을 생성합니다.
        """
        # RAG 결과 요약
        rag_answer = rag_result.get("data", {}).get("answer", "유튜버 인사이트를 가져올 수 없습니다.")
        rag_sources = rag_result.get("data", {}).get("sources", [])
        source_summary = "\n".join(
            [f"- {s.get('title','?')} ({s.get('upload_date','?')})" for s in rag_sources[:3]]
        ) if rag_sources else "참고 영상 없음"

        # Quant 결과 요약
        quant_summary_parts = []
        for ticker, data in quant_result.items():
            if data.get("success"):
                sd = data.get("stock_data", {})
                quant_summary_parts.append(
                    f"[{ticker}] 현재가: ${sd.get('price','N/A')} | "
                    f"EPS(TTM): {sd.get('eps_ttm','N/A')} | PER: {sd.get('pe_ratio','N/A')}"
                )
            else:
                quant_summary_parts.append(f"[{ticker}] 기본 데이터 수집 실패: {data.get('error')}")
        quant_summary = "\n".join(quant_summary_parts) if quant_summary_parts else "실시간 데이터 없음"

        # Tech 결과 요약
        tech_summary_parts = []
        for ticker, data in tech_result.items():
            if data.get("success"):
                ind = data.get("indicators", {})
                tech_summary_parts.append(
                    f"[{ticker}] 📈 차트 지표 요약\n"
                    f"- 이동평균선: MA20(${ind.get('ma20')}), MA50(${ind.get('ma50')}), MA200(${ind.get('ma200', 'N/A')}) -> 추세: {ind.get('trend')}\n"
                    f"- RSI: {ind.get('rsi')} ({ind.get('rsi_signal')})\n"
                    f"- MACD: {ind.get('macd')} (시그널: {ind.get('macd_signal')}, 추세: {ind.get('macd_trend')})\n"
                    f"- 볼린저 밴드: 현재 위치 {ind.get('bb_position')}%\n"
                    f"- AI 분석 요약:\n{data.get('analysis')}"
                )
            else:
                tech_summary_parts.append(f"[{ticker}] 기술적 데이터 수집 실패: {data.get('error')}")
        tech_summary = "\n\n".join(tech_summary_parts) if tech_summary_parts else "실시간 기술적 데이터 없음"

        synthesis_prompt = f"""사용자 질문: {query}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 [실시간 기본 분석 현황 (yfinance)]
{quant_summary}

📈 [실시간 기술적 분석 현황 (yfinance)]
{tech_summary}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎥 [유튜버 인사이트 (RAG 검색 결과)]
{rag_answer}

참고 영상:
{source_summary}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

위 세 가지 소스를 종합하여 사용자의 질문에 최종 답변을 작성해 주세요."""

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL_DEFAULT,
                messages=[
                    {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": synthesis_prompt}
                ],
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"[Router] 종합 생성 실패: {e}")
            return f"⚠️ 종합 답변 생성 실패: {e}\n\n**유튜버 인사이트:**\n{rag_answer}\n\n**실시간 데이터:**\n{quant_summary}\n\n**기술적 분석:**\n{tech_summary}"

    # ──────────────────────────────────────────
    # 3-4. 메인 진입점
    # ──────────────────────────────────────────
    def route(
        self,
        query: str,
        conversation_history: Optional[List] = None,
        force_agents: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        사용자 질문을 받아 라우팅 후 최종 답변을 반환하는 메인 함수.

        Args:
            query: 사용자 질문
            conversation_history: 이전 대화 히스토리

        Returns:
            {
                "answer": str,          # 최종 답변
                "route": str,           # 사용된 경로 (RAG_ONLY / QUANT_ONLY / BOTH)
                "tickers": list,        # 감지된 티커
                "sources": list,        # RAG 참고 소스
                "reasoning": str,       # 라우팅 이유
                "quant_data": dict,     # 실시간 퀀트 데이터 (있는 경우)
                "followup_questions": list
            }
        """
        logger.info(f"[Router] 질문 수신: {query}")

        # 1단계: 의도 및 티커 추출
        intent = self._classify_intent(query)
        route = intent.get("route", "RAG_ONLY")
        tickers = intent.get("tickers", [])
        reasoning = intent.get("reasoning", "")
        
        # UI에서 강제 선택한 에이전트가 있다면 라우트 오버라이드
        if force_agents:
            if set(force_agents) == {"rag"}:
                route = "RAG_ONLY"
                reasoning = "사용자 지정 (유튜버 인사이트 단일)"
            elif set(force_agents) == {"quant"}:
                route = "QUANT_ONLY"
                reasoning = "사용자 지정 (밸류에이션 단일)"
            elif set(force_agents) == {"tech"}:
                route = "TECH_ONLY"
                reasoning = "사용자 지정 (차트 기술분석 단일)"
            else:
                route = "BOTH"  # 2개 이상의 조합은 종합 분석
                reasoning = f"사용자 지정 (다중 경로: {', '.join(force_agents)})"

        result_base = {
            "route": route,
            "tickers": tickers,
            "reasoning": reasoning,
            "sources": [],
            "quant_data": {},
            "tech_data": {},
            "followup_questions": []
        }

        # 2단계: 라우팅 실행
        # ── A: RAG만 ──────────────────────────
        if route == "RAG_ONLY":
            rag_result = self._call_rag(query, conversation_history)
            if rag_result["success"]:
                data = rag_result["data"]
                return {
                    **result_base,
                    "answer": data.get("answer", "답변을 생성하지 못했습니다."),
                    "sources": data.get("sources", []),
                    "followup_questions": data.get("followup_questions", [])
                }
            else:
                return {**result_base, "answer": f"⚠️ RAG 검색 오류: {rag_result['error']}"}

        # ── B: Quant만 ────────────────────────
        elif route == "QUANT_ONLY":
            if not tickers:
                # 티커 추출 실패 시 RAG로 폴백
                logger.warning("[Router] QUANT_ONLY인데 티커 없음, RAG로 폴백")
                rag_result = self._call_rag(query, conversation_history)
                data = rag_result.get("data", {})
                return {
                    **result_base,
                    "route": "RAG_ONLY (폴백)",
                    "answer": data.get("answer", "티커를 인식하지 못했습니다. 종목명이나 티커를 명시해 주세요."),
                    "sources": data.get("sources", []),
                }

            quant_result = self._call_quant(tickers)
            # Quant 결과를 마크다운으로 정리
            answer_parts = []
            for ticker, data in quant_result.items():
                if data.get("success"):
                    sd = data["stock_data"]
                    answer_parts.append(
                        f"## 📊 {sd.get('company_name', ticker)} ({ticker}) 실시간 데이터\n"
                        f"- 현재가: **${sd.get('price', 'N/A')}**\n"
                        f"- EPS (TTM): {sd.get('eps_ttm', 'N/A')}\n"
                        f"- EPS (Forward): {sd.get('eps_fy1', 'N/A')}\n"
                        f"- P/E Ratio: {sd.get('pe_ratio', 'N/A')}\n\n"
                        f"---\n{data.get('analysis', '')}"
                    )
                else:
                    answer_parts.append(f"⚠️ **{ticker}** 데이터 수집 실패: {data.get('error')}")

            return {
                **result_base,
                "answer": "\n\n".join(answer_parts),
                "quant_data": quant_result
            }

        # ── C: TECH만 ────────────────────────
        elif route == "TECH_ONLY":
            if not tickers:
                logger.warning("[Router] TECH_ONLY인데 티커 없음, RAG로 폴백")
                rag_result = self._call_rag(query, conversation_history)
                data = rag_result.get("data", {})
                return {
                    **result_base,
                    "route": "RAG_ONLY (폴백)",
                    "answer": data.get("answer", "티커를 인식하지 못했습니다. 종목명이나 티커 (예: TSLA) 를 명시해 주세요."),
                    "sources": data.get("sources", []),
                }

            tech_result = self._call_tech(query, tickers)
            answer_parts = []
            for ticker, data in tech_result.items():
                if data.get("success"):
                    ind = data["indicators"]
                    analysis = data["analysis"]
                    answer_parts.append(
                        f"## 📈 {ticker} 기술적 분석 및 차트 현황 ({ind.get('date')})\n\n"
                        f"{analysis}\n\n"
                        f"---\n"
                        f"**주요 지표 요약:**\n"
                        f"- 🎯 **현재가:** ${ind.get('current_price')} (1일 변동: {ind.get('price_change_1d')}%, 5일: {ind.get('price_change_5d', 'N/A')}%)\n"
                        f"- 📊 **추세 (이동평균선):** {ind.get('trend')} (MA20: ${ind.get('ma20')}, MA50: ${ind.get('ma50')})\n"
                        f"- 🎛️ **RSI (14일):** {ind.get('rsi')} ➜ **{ind.get('rsi_signal')}**\n"
                        f"- 📉 **MACD:** {ind.get('macd')} ➜ **{ind.get('macd_trend')} 추세**\n"
                        f"- 🎚️ **볼린저 밴드 위치:** {ind.get('bb_position')}% (0%=하단, 100%=상단)\n"
                    )
                else:
                    answer_parts.append(f"⚠️ **{ticker}** 기술적 분석 실패: {data.get('error')}")

            return {
                **result_base,
                "answer": "\n\n".join(answer_parts),
                "tech_data": tech_result
            }

        # ── D: 세 에이전트 (또는 다중 선택) 동시 호출 ──────────
        elif route == "BOTH":
            from agents.agent_loop import build_multi_agent_loop
            
            # workflow 컴파일 및 로드 (싱글톤 패턴 응용)
            if not hasattr(self, 'loop_graph'):
                self.loop_graph = build_multi_agent_loop(self)
                
            agents_to_run = force_agents if force_agents else ["rag", "quant", "tech"]
            
            initial_state = {
                "query": query,
                "tickers": tickers if tickers else [],
                "conversation_history": conversation_history,
                "agents_to_run": agents_to_run
            }
            
            logger.info("[Router] LangGraph Multi-Agent Loop 시작")
            final_state = self.loop_graph.invoke(initial_state)
            
            return {
                **result_base,
                "answer": final_state.get("final_answer", "답변 생성 실패"),
                "sources": final_state.get("final_sources", []),
                "quant_data": final_state.get("quant_result", {}),
                "tech_data": final_state.get("tech_result", {}),
                "followup_questions": final_state.get("followup_questions", [])
            }

        # ── 예외 ──────────────────────────────
        else:
            logger.error(f"[Router] 알 수 없는 경로: {route}")
            rag_result = self._call_rag(query, conversation_history)
            data = rag_result.get("data", {})
            return {**result_base, "answer": data.get("answer", "처리 중 오류 발생")}


# ──────────────────────────────────────────────
# 4. 간편 헬퍼 함수 (app.py에서 바로 사용 가능)
# ──────────────────────────────────────────────
def get_router() -> AgenticRouter:
    """Streamlit 세션별 라우터 인스턴스 반환 (세션 간 상태 오염 방지)"""
    try:
        import streamlit as st
        if "agentic_router" not in st.session_state:
            st.session_state.agentic_router = AgenticRouter()
        return st.session_state.agentic_router
    except Exception:
        # Streamlit 컨텍스트 밖(단독 실행 등)에서는 새 인스턴스 반환
        return AgenticRouter()


def ask(
    query: str,
    conversation_history: Optional[List] = None
) -> Dict[str, Any]:
    """
    app.py에서 단일 함수 호출로 라우팅부터 답변까지 처리하는 헬퍼.

    Usage:
        from agents.router import ask
        result = ask("엔비디아 현재가랑 유튜버 전망 비교해줘")
        print(result["answer"])
        print(result["route"])  # "BOTH"
    """
    router = get_router()
    return router.route(query, conversation_history)


# ──────────────────────────────────────────────
# 5. 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    test_queries = [
        ("A: RAG만",    "올랜도킴이 엔비디아에 대해 어떻게 전망했어?"),
        ("B: Quant만",  "NVDA 지금 PER 얼마야? 적정가 계산해줘"),
        ("C: Tech만",   "엔비디아 차트 지표 좀 분석해줘. RSI는 얼마야?"),
        ("D: 모두",     "삼성전자 현재 주가랑 차트 추세, 그리고 유튜버들이 어떻게 보는지 비교해줘"),
    ]

    router = AgenticRouter()

    for label, q in test_queries:
        print(f"\n{'='*60}")
        print(f"[{label}] 질문: {q}")
        print('='*60)
        result = router.route(q)
        print(f"▶ 라우팅 경로 : {result['route']}")
        print(f"▶ 감지 티커   : {result['tickers']}")
        print(f"▶ 라우팅 이유 : {result['reasoning']}")
        print(f"▶ 답변 (앞200자):\n{result['answer'][:200]}...")
