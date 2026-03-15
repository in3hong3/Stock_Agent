"""
베이스 에이전트 클래스
모든 에이전트가 상속받아야 하는 기본 클래스
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseAgent(ABC):
    """모든 에이전트의 베이스 클래스"""
    
    def __init__(self, agent_id: str, name: str, description: str, **kwargs):
        """
        Args:
            agent_id: 에이전트 고유 ID
            name: 에이전트 이름
            description: 에이전트 설명
            **kwargs: 추가 설정
        """
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.config = kwargs
        self.enabled = kwargs.get('enabled', True)
    
    @abstractmethod
    def process(self, query: str, **kwargs) -> Dict[str, Any]:
        """
        에이전트별 처리 로직 (서브클래스에서 구현)
        
        Args:
            query: 사용자 쿼리
            **kwargs: 추가 파라미터
            
        Returns:
            처리 결과 딕셔너리
        """
        raise NotImplementedError("Subclass must implement process() method")
    
    def get_info(self) -> Dict[str, str]:
        """에이전트 정보 반환"""
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled
        }
    
    def is_enabled(self) -> bool:
        """에이전트 활성화 상태 확인"""
        return self.enabled
    
    def enable(self):
        """에이전트 활성화"""
        self.enabled = True
    
    def disable(self):
        """에이전트 비활성화"""
        self.enabled = False
