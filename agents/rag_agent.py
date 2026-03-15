"""
RAG 챗봇 에이전트
YouTube 영상 자막 기반 주식 정보 검색 에이전트
"""
from typing import Dict, Any, List, Optional
from agents.base_agent import BaseAgent
from core.rag_engine import RAGEngine


class RAGAgent(BaseAgent):
    """RAG 챗봇 에이전트"""
    
    def __init__(self, agent_id: str, name: str, description: str, **kwargs):
        """
        Args:
            agent_id: 에이전트 고유 ID
            name: 에이전트 이름
            description: 에이전트 설명
            **kwargs: 추가 설정 (channel_id 등)
        """
        super().__init__(agent_id, name, description, **kwargs)
        
        # RAG 엔진 초기화 (지연 초기화)
        self._rag_engine = None
        self.channel_id = kwargs.get('channel_id')
    
    @property
    def rag_engine(self):
        """RAG 엔진 지연 초기화"""
        if self._rag_engine is None:
            self._rag_engine = RAGEngine()
        return self._rag_engine
    
    def process(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        RAG 검색 및 답변 생성
        
        Args:
            query: 사용자 질문
            **kwargs: 추가 파라미터 (top_k, temperature, agent_filter, conversation_history 등)
            
        Returns:
            dict: {'answer': 답변, 'sources': 참고 소스 리스트, 'followup_questions': 후속 질문 리스트}
        """
        top_k = kwargs.get('top_k', 8)
        temperature = kwargs.get('temperature', 0.3)
        agent_filter = kwargs.get('agent_filter', None)  # 선택된 에이전트 ID 리스트
        conversation_history = kwargs.get('conversation_history', None)  # 대화 히스토리
        
        # RAG 엔진 호출
        result = self.rag_engine.chat(
            query=query,
            top_k=top_k,
            temperature=temperature,
            agent_filter=agent_filter,
            conversation_history=conversation_history
        )
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """에이전트 통계 정보 반환"""
        return {
            **self.get_info(),
            "channel_id": self.channel_id,
            "type": "rag_chatbot"
        }
