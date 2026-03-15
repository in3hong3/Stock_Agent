import logging
import json
import datetime
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict
from openai import OpenAI
from config.settings import LLM_MODEL_DEFAULT

logger = logging.getLogger(__name__)

class LoopState(TypedDict):
    query: str
    tickers: List[str]
    conversation_history: Optional[List]
    agents_to_run: List[str]
    
    rag_result: Dict
    quant_result: Dict
    tech_result: Dict
    
    validation_status: str # "PASS" / "REJECT"
    validation_reason: str
    
    final_answer: str
    final_sources: List[Dict]
    followup_questions: List[str]

def build_multi_agent_loop(router_instance):
    """
    LangGraph 기반 순환형 구조. 
    1) 각 에이전트 동시 fetch 
    2) RAG와 Quant의 오차 검토 (check_relevance)
    3) 실패 시 web_search 백업 (fallback)
    4) 종합 및 답변 생성 (synthesize)
    """
    
    def fetch_data_node(state: LoopState):
        logger.info("[LangGraph] Node: fetch_data")
        import concurrent.futures
        
        query = state["query"]
        tickers = state["tickers"]
        agents_to_run = state["agents_to_run"]
        history = state.get("conversation_history")
        
        rag_res, quant_res, tech_res = {}, {}, {}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            if "rag" in agents_to_run:
                futures[executor.submit(router_instance._call_rag, query, history)] = "rag"
            if "quant" in agents_to_run:
                futures[executor.submit(router_instance._call_quant, tickers)] = "quant"
            if "tech" in agents_to_run:
                futures[executor.submit(router_instance._call_tech, query, tickers)] = "tech"
                
            for future in concurrent.futures.as_completed(futures):
                agent_name = futures[future]
                try:
                    if agent_name == "rag":
                        rag_res = future.result()
                    elif agent_name == "quant":
                        quant_res = future.result()
                    elif agent_name == "tech":
                        tech_res = future.result()
                except Exception as e:
                    logger.error(f"[LangGraph] 병렬 에이전트 오류 ({agent_name}): {e}")
                    
        return {"rag_result": rag_res, "quant_result": quant_res, "tech_result": tech_res}

    def check_relevance_node(state: LoopState):
        logger.info("[LangGraph] Node: check_relevance (RAG vs Quant 교차 검증)")
        rag_data = state.get("rag_result", {}).get("data", {})
        rag_answer = rag_data.get("answer", "")
        
        quant_result = state.get("quant_result", {})
        
        # 티커별 현재가 문자열 구성
        price_info = []
        for ticker, data in quant_result.items():
            if data.get("success"):
                price = data.get("stock_data", {}).get("price")
                if price:
                    price_info.append(f"{ticker}: ${price}")
        
        if not rag_answer or not price_info:
            return {"validation_status": "PASS", "validation_reason": "비교 불가"}

        prices_str = ", ".join(price_info)
        
        # LLM에게 RAG 답변의 목표가/현재가와 진짜 현재가의 괴리도를 평가시킴
        prompt = f"""당신은 "팩트체크 시스템"입니다.
아래의 [RAG 응답]에 포함된 주가(특히 과거의 주가나 목표가)와 [실제 파악된 현재가]를 비교하세요.
가격이 20% 이상 차이나거나, RAG 응답의 시점이 너무 구형이라 잘못된 판단을 유도할 수 있다면 REJECT를 반환하세요.
그 외에는 PASS를 반환하세요.

[RAG 응답]
{rag_answer}

[실제 파악된 현재가]
{prices_str}

**JSON 형식으로 응답:**
{{
    "status": "PASS" 혹은 "REJECT",
    "reason": "검증 사유 (1문장)"
}}
"""
        try:
            client = OpenAI()
            response = client.chat.completions.create(
                model=LLM_MODEL_DEFAULT,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            res_json = json.loads(response.choices[0].message.content)
            status = res_json.get("status", "PASS")
            reason = res_json.get("reason", "")
            logger.info(f"[LangGraph] 가격 오차 검증 결과: {status} ({reason})")
            return {"validation_status": status, "validation_reason": reason}
        except Exception as e:
            logger.warning(f"[LangGraph] 검증 실패, PASS로 진행: {e}")
            return {"validation_status": "PASS", "validation_reason": "검증 오류"}

    def web_search_node(state: LoopState):
        logger.info("[LangGraph] Node: web_search_fallback (교차 검증 실패로 최신 뉴스 보완)")
        query = state["query"]
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.news(query + " 주식 현재가 최신 뉴스", region='kr-kr', max_results=3))
                
                new_rag = dict(state.get("rag_result", {}))
                data = dict(new_rag.get("data", {}))
                
                # 기존 답변 경고 문구 추가 + 웹 검색 결과
                warning = f"\n\n🚨 **긴급 알림:** AI가 파악한 유튜버의 목표가/주가가 실제 현재가와 크게 괴리되어 있습니다. ({state['validation_reason']})\n최신 뉴스를 가져왔습니다:\n"
                for res in results:
                    warning += f"- [{res.get('title', '')}] {res.get('body', '')}\n"
                
                data["answer"] = data.get("answer", "") + warning
                new_rag["data"] = data
                return {"rag_result": new_rag}
        except Exception as e:
            logger.error(f"[LangGraph] duckduckgo-search 오류: {e}")
            return {}

    def synthesize_node(state: LoopState):
        logger.info("[LangGraph] Node: format_and_synthesize")
        
        # 내부 구조 분해해서 _synthesize 및 최종 마크다운 조합
        rag_result = state.get("rag_result", {})
        quant_result = state.get("quant_result", {})
        tech_result = state.get("tech_result", {})
        query = state["query"]
        tickers = state["tickers"]

        # RAG 메타
        rag_data = rag_result.get("data", {})
        rag_answer = rag_data.get("answer", "")
        rag_sources = rag_data.get("sources", [])
        
        # Quant 섹션 구성
        quant_section_parts = []
        for ticker, data in quant_result.items():
            if data.get("success"):
                sd = data["stock_data"]
                quant_section_parts.append(
                    f"**{sd.get('company_name', ticker)} ({ticker})**\n"
                    f"- 현재가: **${sd.get('price', 'N/A')}** | P/E: {sd.get('pe_ratio', 'N/A')}\n\n"
                    f"{data.get('analysis', '')}"
                )
            else:
                quant_section_parts.append(f"⚠️ {ticker} 데이터 수집 실패: {data.get('error')}")

        # Tech 섹션 구성
        tech_section_parts = []
        for ticker, data in tech_result.items():
            if data.get("success"):
                ind = data["indicators"]
                tech_section_parts.append(
                    f"**{ticker}** ({ind.get('date')})\n"
                    f"- 추세: **{ind.get('trend')}** | 편차: RSI {ind.get('rsi')}\n\n"
                    f"{data.get('analysis', '')}"
                )

        # _synthesize 호출
        synthesis = router_instance._synthesize(query, rag_result, quant_result, tech_result)

        answer_sections = []
        if quant_section_parts:
            answer_sections.append("## 📊 [밸류에이션 분석관] 기본 지표 & 현재가\n\n" + "\n\n".join(quant_section_parts))
        if tech_section_parts:
            answer_sections.append("## 📈 [기술분석관] 차트 분석\n\n" + "\n\n".join(tech_section_parts))
        if rag_answer:
            answer_sections.append("## 🎥 [영상분석관] 정보\n\n" + rag_answer)
        if synthesis:
            answer_sections.append("## 🧠 [시니어 애널리스트] 종합 판단\n\n" + synthesis)

        final_answer = "\n\n---\n".join(answer_sections)

        return {
            "final_answer": final_answer,
            "final_sources": rag_sources,
            "followup_questions": rag_data.get("followup_questions", [])
        }

    # Graph 빌드
    workflow = StateGraph(LoopState)
    workflow.add_node("fetch_data", fetch_data_node)
    workflow.add_node("check_relevance", check_relevance_node)
    workflow.add_node("web_search", web_search_node)
    workflow.add_node("synthesize", synthesize_node)
    
    workflow.add_edge(START, "fetch_data")
    workflow.add_edge("fetch_data", "check_relevance")
    
    def relevance_decider(state: LoopState) -> str:
        if state.get("validation_status") == "REJECT":
            return "web_search"
        return "synthesize"
        
    workflow.add_conditional_edges("check_relevance", relevance_decider)
    workflow.add_edge("web_search", "synthesize")
    workflow.add_edge("synthesize", END)
    
    return workflow.compile()
