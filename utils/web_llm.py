"""
웹 검색 가능 LLM 추상화 레이어
신문 1면, 보유종목 평가 등 "검색해서 쓰는" 작업을 공급자에 상관없이 호출한다.

우선순위 (SEARCH_LLM_PROVIDER 환경변수로 강제 가능: perplexity | gemini | claude | none):
  1. Perplexity — PERPLEXITY_API_KEY (sonar 모델, 검색 내장)
  2. Gemini     — GEMINI_API_KEY     (구글 검색 그라운딩, 무료 티어 제공)
  3. Claude     — ANTHROPIC_API_KEY  (웹 검색 도구, $10/1k 검색)
"""
import os

_PROVIDERS = ("perplexity", "gemini", "claude")
_KEY_ENV = {
    "perplexity": "PERPLEXITY_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


def get_search_provider() -> str:
    """사용 가능한 검색 LLM 공급자 반환. 없으면 None."""
    explicit = os.getenv("SEARCH_LLM_PROVIDER", "").strip().lower()
    if explicit == "none":
        return None
    if explicit in _PROVIDERS:
        return explicit
    for p in _PROVIDERS:
        if os.getenv(_KEY_ENV[p]):
            return p
    return None


def search_generate(system: str, prompt: str,
                    max_tokens: int = 8000, max_searches: int = 12) -> str:
    """
    웹 검색을 활용해 텍스트 생성. 공급자 자동 선택.
    Raises: RuntimeError (사용 가능한 키 없음)
    """
    provider = get_search_provider()
    if provider == "perplexity":
        return _perplexity_generate(system, prompt, max_tokens)
    if provider == "gemini":
        return _gemini_generate(system, prompt, max_tokens)
    if provider == "claude":
        return _claude_generate(system, prompt, max_tokens, max_searches)
    raise RuntimeError("검색 LLM 키가 없습니다. .env에 PERPLEXITY_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY 중 하나를 설정하세요.")


# ──────────────────────────────────────────────
# Perplexity (sonar — 검색 내장, OpenAI 호환 API)
# ──────────────────────────────────────────────
def _perplexity_generate(system: str, prompt: str, max_tokens: int) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=os.getenv("PERPLEXITY_API_KEY"),
        base_url="https://api.perplexity.ai",
    )
    response = client.chat.completions.create(
        model=os.getenv("PERPLEXITY_MODEL", "sonar-pro"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=0.4,
    )
    text = response.choices[0].message.content or "응답을 생성하지 못했습니다."

    # 출처 인용 추가 (Perplexity는 citations 필드로 검색 출처를 반환)
    citations = getattr(response, "citations", None)
    if citations:
        sources = "\n".join(f"{i}. {url}" for i, url in enumerate(citations[:10], 1))
        text += f"\n\n---\n**📎 검색 출처**\n{sources}"
    return text


# ──────────────────────────────────────────────
# Gemini (구글 검색 그라운딩)
# ──────────────────────────────────────────────
def _gemini_generate(system: str, prompt: str, max_tokens: int) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=os.getenv("GEMINI_SEARCH_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(google_search=types.GoogleSearch())],
            max_output_tokens=max_tokens,
            temperature=0.4,
        ),
    )
    return response.text or "응답을 생성하지 못했습니다."


# ──────────────────────────────────────────────
# Claude (웹 검색 도구)
# ──────────────────────────────────────────────
def _claude_generate(system: str, prompt: str, max_tokens: int, max_searches: int) -> str:
    import anthropic

    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_searches}]

    # 서버측 검색 루프가 pause_turn으로 끊기면 이어서 재요청
    for _ in range(5):
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system,
            messages=messages,
            tools=tools,
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": response.content},
        ]

    return "".join(b.text for b in response.content if b.type == "text")
