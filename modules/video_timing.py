"""
유튜버 타이밍 알림
RAG에 쌓인 영상에서 "지금 알아야 할" 시점 기반 매매 권고/경고를 추출한다.

3가지 카테고리:
1. 🚨 즉시 경고 — 최근 1-2일 영상에서 "오늘/내일/이번 주" 류 단기 권고
2. ⏰ 시점 도래 — 과거 영상에서 'X월에', '반년 후' 등 언급한 시점이 지금 도래
3. 📅 이벤트 임박 — 실적/FOMC 등 임박한 이벤트 관련 권고

저장: data/video_alerts.json (공용 — 모든 사용자에게 시장 알림은 동일)
"""
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any

from openai import OpenAI

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERTS_FILE = os.path.join(_BASE_DIR, "data", "video_alerts.json")


def get_recent_videos(days: int = 90, max_videos: int = 60) -> List[Dict]:
    """최근 N일 영상 메타+요약 텍스트 가져오기 (Pinecone)"""
    from utils.pinecone_store import PineconeStore
    from config.settings import PINECONE_NAMESPACE_SUMMARY

    store = PineconeStore()
    cutoff = (datetime.now().date() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 일반 시황 쿼리로 광범위하게 가져온 뒤 클라이언트에서 날짜 필터
    res = store.index.query(
        vector=store.get_embedding("시황 종목 매수 매도 전망 주의 조심 기회"),
        top_k=300,
        namespace=PINECONE_NAMESPACE_SUMMARY,
        include_metadata=True,
    )

    videos = []
    seen_titles = set()
    for m in res.get("matches", []):
        meta = m.get("metadata", {})
        upload = str(meta.get("업로드일자", ""))[:10]
        if not upload or upload < cutoff:
            continue
        title = meta.get("영상제목", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        videos.append({
            "title": title,
            "channel": meta.get("채널명", ""),
            "date": upload,
            "ticker": meta.get("ticker", ""),
            "text": str(meta.get("text", ""))[:400],
            "link": meta.get("영상링크", ""),
        })

    videos.sort(key=lambda v: v["date"], reverse=True)
    return videos[:max_videos]


def extract_timing_alerts(videos: List[Dict], holdings: List[Dict] = None,
                          model: str = "gpt-4o-mini") -> List[Dict]:
    """LLM으로 시점 알림 추출"""
    if not videos:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    weekday = ["월", "화", "수", "목", "금", "토", "일"][datetime.now().weekday()]

    holdings_text = ""
    tickers_for_events = []
    if holdings:
        tickers = [h.get("ticker", "") for h in holdings if h.get("ticker")]
        tickers_for_events = tickers
        if tickers:
            holdings_text = f"내 보유 종목: {', '.join(tickers)}\n"

    # 진짜 캘린더의 다가오는 이벤트 (실적/FOMC/CPI 등) — LLM이 이걸 사실 기준으로 사용
    upcoming_events_text = "\n[향후 21일 실제 일정 — '이벤트 임박' 알림은 이 안에 있는 것만 쓸 것]\n"
    try:
        from modules.event_calendar import get_all_events, get_upcoming_events
        all_events = get_all_events(tickers_for_events)
        upcoming = get_upcoming_events(all_events, days=21)
        if upcoming:
            upcoming_events_text += "\n".join(
                f"- {e['date'].strftime('%Y-%m-%d')} (D-{e['d_day']}) {e['title']}"
                for e in upcoming[:15]
            )
        else:
            upcoming_events_text += "(향후 21일 내 예정된 주요 일정 없음 — 이벤트 임박 알림 만들지 말 것)"
    except Exception as e:
        print(f"이벤트 목록 조회 실패: {e}")
        upcoming_events_text = ""

    videos_text = "\n\n".join(
        f"[{i+1}] {v['title']}\n  채널: {v['channel']} | 업로드: {v['date']} | 종목: {v.get('ticker','-')}\n  요약: {v['text']}"
        for i, v in enumerate(videos)
    )

    system_prompt = (
        "너는 주식 유튜브 영상 분석가야. 보유자에게 '지금 알아야 할' 정보만 골라낸다. "
        "유튜버 의견은 참고용일 뿐 보장이 아니다. 직접적 인용 위주로 추출하고 과장하지 마라."
    )

    user_prompt = f"""오늘 날짜: {today} ({weekday}요일)
{holdings_text}{upcoming_events_text}

아래는 최근 90일간 유튜버 영상이야 (최신순):

{videos_text}

위 영상들에서 **오늘({today}) 이후 활성인 시점 알림**만 골라줘:

1. 🚨 **즉시 경고** — 최근 1~3일 이내 영상에서 "오늘/내일/이번 주 장 시작 전" 류 단기 권고·경고
   (영상이 4일 이상 묵었으면 그때의 "오늘/내일"은 이미 지난 날 — 알림으로 만들지 마라)
2. ⏰ **시점 도래** — 과거 영상에서 'X월에', '여름에', '반년 후', '하반기' 등 언급한 시점이
   **오늘({today})~앞으로 2주 안에** 도래하는 것 (가장 적극적으로 찾을 카테고리)
3. 📅 **이벤트 임박** — 위 "실제 일정" 목록에 있는 이벤트에 대한 영상 속 권고만
   (영상에서 "CPI 임박" 같은 말이 나와도 위 일정에 없거나 이미 지난 거면 만들지 마라)

순수 JSON으로만 반환:
{{
  "alerts": [
    {{
      "level": "🚨 긴급" | "⚠️ 주의" | "💡 기회",
      "category": "즉시" | "시점도래" | "이벤트",
      "title": "한 줄 요약 (60자 이내)",
      "message": "유튜버 핵심 발언 직접 인용 (120자 이내)",
      "ticker": "NVDA",
      "theme": "AI 반도체",
      "source_video": "영상 제목",
      "source_date": "YYYY-MM-DD",
      "expires": "YYYY-MM-DD",
      "video_link": "영상 URL"
    }}
  ]
}}

만료일 기준 (관대하게):
- 즉시 경고: 영상일 + 5일
- 시점 도래: 언급한 시점일 + 14일 (시점 모호하면 오늘 + 14일)
- 이벤트 임박: 이벤트일 + 3일

기타 규칙:
- 내 보유 종목 직접 관련을 우선 (있을 시 상단)
- 시장 전반 경고/기회도 포함 (조정 임박, 변동성 확대, 매수 기회 등)
- 모호한 의견("그냥 좋다", "전망 밝다")은 제외 — 시점·행동 명확한 것만
- 같은 종목·같은 주장 중복 금지
- ticker/theme/video_link 없으면 null
- ❗ **시점 검증 필수**: 영상 발언이 "이번 주", "내일" 같이 영상 시점 기준이면
  영상일이 오늘({today})로부터 며칠 전인지 계산해서 그 시점이 지났는지 확인하라.
  이미 지난 일에 대한 권고는 절대 알림으로 만들지 마라.
- ❗ **이벤트 검증 필수**: CPI/FOMC/실적은 위의 '실제 일정' 목록과 대조해 검증.
  목록에 없으면(=다음 일정이 없거나 21일 밖) 이벤트 임박 알림 만들지 마라.
- 최대 10개. 정말 활성인 게 없으면 alerts:[]
"""

    client = OpenAI()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        result = json.loads(response.choices[0].message.content)
        alerts = result.get("alerts", [])

        # video_link 매핑 (LLM이 누락하면 영상 제목으로 검색해서 보강)
        title_to_link = {v["title"]: v["link"] for v in videos}
        for a in alerts:
            if not a.get("video_link") and a.get("source_video"):
                a["video_link"] = title_to_link.get(a["source_video"], "")

        return alerts
    except Exception as e:
        print(f"알림 추출 실패: {e}")
        return []


def save_alerts(alerts: List[Dict]):
    os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
    with open(ALERTS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(timespec="minutes"),
            "alerts": alerts,
        }, f, ensure_ascii=False, indent=2)


def load_alerts() -> Dict:
    if not os.path.exists(ALERTS_FILE):
        return {"alerts": [], "generated_at": None}
    try:
        with open(ALERTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"alerts": [], "generated_at": None}


def get_active_alerts() -> List[Dict]:
    """오늘 시점 기준 만료되지 않은 알림만"""
    today = datetime.now().strftime("%Y-%m-%d")
    data = load_alerts()
    return [a for a in data.get("alerts", []) if a.get("expires", "9999-99-99") >= today]


def refresh_alerts(holdings: List[Dict] = None, days: int = 90) -> Dict:
    """RAG에서 영상 가져와 알림 강제 갱신"""
    videos = get_recent_videos(days=days)
    alerts = extract_timing_alerts(videos, holdings)
    save_alerts(alerts)
    return {"video_count": len(videos), "alert_count": len(alerts)}


def needs_refresh(stale_hours: int = 12) -> bool:
    """알림이 stale_hours 이상 묵었으면 True"""
    data = load_alerts()
    gen_at = data.get("generated_at")
    if not gen_at:
        return True
    try:
        last = datetime.fromisoformat(gen_at)
        return (datetime.now() - last).total_seconds() > stale_hours * 3600
    except (ValueError, TypeError):
        return True
