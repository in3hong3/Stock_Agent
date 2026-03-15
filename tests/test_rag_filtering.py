"""
RAG 에이전트 필터링 테스트
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.rag_agent import RAGAgent
from config.settings import AGENT_REGISTRY

def test_rag_agent_filtering():
    print("=== RAG 에이전트 필터링 테스트 ===\n")
    
    # 올랜도킴 에이전트 생성
    orlando_info = AGENT_REGISTRY['orlando_kim']
    agent = RAGAgent(
        agent_id=orlando_info['id'],
        name=orlando_info['name'],
        description=orlando_info['description'],
        channel_id=orlando_info.get('channel_id')
    )
    
    print(f"에이전트: {agent.name}")
    print(f"ID: {agent.agent_id}")
    print(f"채널 ID: {agent.channel_id}\n")
    
    # 테스트 1: agent_filter 없이
    print("[테스트 1] agent_filter 없이 검색")
    print("-" * 50)
    result1 = agent.process("구글의 전망", top_k=3, agent_filter=None)
    print(f"답변 길이: {len(result1['answer'])} 자")
    print(f"소스 개수: {len(result1['sources'])}개")
    if result1['sources']:
        print("첫 번째 소스:", result1['sources'][0].get('영상제목', 'N/A')[:50])
    print()
    
    # 테스트 2: agent_filter 사용
    print("[테스트 2] agent_filter=['orlando_kim'] 사용")
    print("-" * 50)
    result2 = agent.process("구글의 전망", top_k=3, agent_filter=['orlando_kim'])
    print(f"답변 길이: {len(result2['answer'])} 자")
    print(f"소스 개수: {len(result2['sources'])}개")
    if result2['sources']:
        print("첫 번째 소스:", result2['sources'][0].get('영상제목', 'N/A')[:50])
    else:
        print("⚠️ 소스가 없습니다!")
        print(f"답변: {result2['answer'][:200]}...")


if __name__ == "__main__":
    test_rag_agent_filtering()
