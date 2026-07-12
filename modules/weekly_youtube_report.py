"""
주간 유튜버 리포트 (Weekly YouTube Report)

한 주(월~일) 동안 RAG에 쌓인 유튜버 영상들을 종합해 "이번 주 유튜버판 흐름"을
한 편으로 정리한다. 매주 일요일 저녁(KST)에 1회 발행하는 게 기본 운영.

구성 5섹션 중 4개는 LLM 없이 메타데이터 집계로 만든다:
  ① 이번 주 언급 TOP 종목 + 매수/주의 분포        (집계)
  ② 지난주 대비 변화 — 언급 급증 · 톤 반전          (집계)
  ③ 이번 주 공통 테마 / 시황 내러티브               (LLM 1회)
  ④ 소수의견 · 특이 콜                              (③과 같은 호출)
  ⑤ 내 보유종목 관련 코멘트                          (UI에서 videos 필터, 집계)

LLM은 ③④ 내러티브 한 번만 사용 (우리 아카이브 요약이라 웹검색 불필요 → OpenAI 직접).
키가 없거나 실패하면 집계 기반 템플릿으로 폴백 → 키 없이도 리포트는 나온다.

저장: data/weekly_reports/YYYY-Www.json (ISO 주차별 보관 — 시장 전체라 전 사용자 공용).
"""
import os
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

from modules.daily_paper import now_kst

_NS = "stock-summaries"
_EXCLUDE = {"MARKET", "UNKNOWN", ""}

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPORT_DIR = os.path.join(_BASE_DIR, "data", "weekly_reports")


# ──────────────────────────────────────────────
# 주(week) 경계 — 항상 KST 기준 (서버 UTC 함정 회피)
# ──────────────────────────────────────────────
def week_bounds(ref: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """ref가 속한 주의 월요일 00:00 ~ 다음 월요일 00:00 (KST). ref 기본=지금."""
    ref = ref or now_kst()
    monday = (ref - timedelta(days=ref.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return monday, monday + timedelta(days=7)


def week_key(ref: Optional[datetime] = None) -> str:
    """ISO 주차 키 (예: 2026-W28). 파일명·조회 키로 사용."""
    ref = ref or now_kst()
    y, w, _ = ref.isocalendar()
    return f"{y}-W{w:02d}"


def _parse_date(s) -> Optional[datetime]:
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(s)[:10], fmt)
        except (ValueError, TypeError):
            continue
    return None


# ──────────────────────────────────────────────
# 1. 주간 영상 수집 (Pinecone summary 네임스페이스 전체 스캔 → 해당 주만 보관)
#    주 1회 off-peak cron에서만 도므로 전체 스캔 허용. 메모리는 '그 주'만 들고 있음.
# ──────────────────────────────────────────────
def collect_week_rows(start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """
    [start, end) 기간에 업로드된 영상의 (영상, 종목) 단위 행 수집.
    한 영상이 여러 종목을 다루면 종목마다 1행 (각자 sentiment). (링크,종목) 중복 제거.
    """
    from utils.pinecone_store import PineconeStore
    ps = PineconeStore()

    start_d, end_d = start.date(), end.date()
    rows: List[Dict[str, Any]] = []
    seen = set()  # (링크, 종목)

    for page in ps.index.list(namespace=_NS):
        if hasattr(page, "vectors"):
            ids = [it.id for it in page.vectors]
        elif isinstance(page, (list, tuple)):
            ids = list(page)
        else:
            ids = []
        if not ids:
            continue
        res = ps.index.fetch(ids=ids, namespace=_NS)
        vecs = res.get("vectors", {}) if isinstance(res, dict) else getattr(res, "vectors", {})
        for v in (vecs.values() if hasattr(vecs, "values") else vecs):
            m = (v.get("metadata", {}) if isinstance(v, dict) else getattr(v, "metadata", {})) or {}
            d = _parse_date(m.get("업로드일자", ""))
            if d is None or not (start_d <= d.date() < end_d):
                continue
            ticker = str(m.get("ticker", "")).strip()
            link = str(m.get("영상링크", "")) or str(m.get("영상제목", ""))
            key = (link, ticker)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "link": link,
                "title": str(m.get("영상제목", "")),
                "channel": str(m.get("채널명", "")),
                "date": d.strftime("%Y-%m-%d"),
                "ticker": ticker,
                "name": str(m.get("stock_name", "")) or ticker,
                "sentiment": str(m.get("sentiment", "중립")),
                "text": str(m.get("text", ""))[:600],
            })
    return rows


# ──────────────────────────────────────────────
# 2. 집계 (LLM 없음)
# ──────────────────────────────────────────────
def _score(buy: int, caution: int, total: int) -> int:
    if not total:
        return 0
    return round((buy - caution) / total * 100)


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """언급 TOP · 종목별 센티먼트 분포. 시장(MARKET)/미상 제외."""
    stock_rows = [r for r in rows if r["ticker"] not in _EXCLUDE]

    per_ticker: Dict[str, Counter] = defaultdict(Counter)
    names: Dict[str, str] = {}
    for r in stock_rows:
        per_ticker[r["ticker"]][r["sentiment"]] += 1
        if r["name"] and r["ticker"] not in names:
            names[r["ticker"]] = r["name"]

    top = []
    for tk, sc in per_ticker.items():
        buy, neutral, caution = sc.get("매수", 0), sc.get("중립", 0), sc.get("주의", 0)
        total = buy + neutral + caution
        top.append({
            "ticker": tk, "name": names.get(tk, tk),
            "buy": buy, "neutral": neutral, "caution": caution,
            "total": total, "score": _score(buy, caution, total),
        })
    top.sort(key=lambda x: (x["total"], x["score"]), reverse=True)

    videos = {r["link"]: r for r in rows}  # 영상 단위 유니크
    channels = {r["channel"] for r in rows if r["channel"]}
    return {
        "top_mentions": top,
        "video_count": len(videos),
        "channel_count": len(channels),
        "stock_count": len(per_ticker),
    }


def diff_vs_prior(this_rows, prior_rows) -> Dict[str, List[Dict]]:
    """지난주 대비: 언급 급증 + 톤 반전 (LLM 없음)."""
    def counts(rows):
        c = Counter(r["ticker"] for r in rows if r["ticker"] not in _EXCLUDE)
        net = defaultdict(lambda: [0, 0])  # ticker -> [buy, caution]
        for r in rows:
            if r["ticker"] in _EXCLUDE:
                continue
            if r["sentiment"] == "매수":
                net[r["ticker"]][0] += 1
            elif r["sentiment"] == "주의":
                net[r["ticker"]][1] += 1
        return c, net

    this_c, this_net = counts(this_rows)
    prior_c, prior_net = counts(prior_rows)

    surges = []
    for tk, cnt in this_c.items():
        prev = prior_c.get(tk, 0)
        # 이번 주 3회+ 이고, 지난주 대비 2배+ (또는 지난주 0이었던 신규 급부상)
        if cnt >= 3 and (prev == 0 or cnt >= 2 * prev):
            surges.append({"ticker": tk, "this_week": cnt, "prior": prev})
    surges.sort(key=lambda x: x["this_week"], reverse=True)

    def tone(buy, caution):
        if buy - caution >= 1:
            return "매수우위"
        if caution - buy >= 1:
            return "주의우위"
        return "중립"

    flips = []
    for tk in this_c:
        if this_c[tk] < 2 or prior_c.get(tk, 0) < 2:
            continue  # 양쪽 표본 최소 2
        pb, pc = prior_net[tk]
        tb, tc = this_net[tk]
        p_tone, t_tone = tone(pb, pc), tone(tb, tc)
        if p_tone != t_tone and "중립" not in (p_tone, t_tone):
            flips.append({"ticker": tk, "prior": p_tone, "now": t_tone,
                          "this_week": this_c[tk]})
    flips.sort(key=lambda x: x["this_week"], reverse=True)
    return {"surges": surges[:8], "tone_flips": flips[:8]}


# ──────────────────────────────────────────────
# 3. 내러티브 (LLM 1회 — 없거나 실패 시 집계 템플릿 폴백)
# ──────────────────────────────────────────────
_SYSTEM = (
    "너는 주식 유튜브 아카이브를 종합하는 애널리스트야. 여러 유튜버가 이번 주 한 말을 "
    "묶어 '이번 주 유튜버판의 흐름'을 정리한다. 원칙: "
    "(1) 여러 채널이 공통으로 짚은 테마를 먼저. "
    "(2) 숫자·종목명을 근거로 인용하되 과장 금지. "
    "(3) 남들과 반대로 말한 소수의견·특이 콜을 따로 부각(역발상 힌트). "
    "(4) 유튜버 의견은 참고일 뿐 보장이 아님을 톤에 반영, 단정 대신 균형. "
    "(5) 이모지 남용 금지, 신문 종합기사체."
)


def _videos_block(rows: List[Dict], max_videos: int = 40) -> str:
    """LLM 입력용 — 영상 단위로 묶어 제목/채널/다룬 종목/요약."""
    by_video: Dict[str, Dict] = {}
    for r in rows:
        v = by_video.setdefault(r["link"], {
            "title": r["title"], "channel": r["channel"], "date": r["date"],
            "tickers": [], "text": r["text"],
        })
        if r["ticker"] not in _EXCLUDE and r["ticker"] not in v["tickers"]:
            v["tickers"].append(r["ticker"])
    lines = []
    for i, v in enumerate(list(by_video.values())[:max_videos]):
        tks = ", ".join(v["tickers"]) or "-"
        lines.append(
            f"[{i+1}] {v['title']}\n  채널: {v['channel']} | {v['date']} | 종목: {tks}\n  요약: {v['text']}"
        )
    return "\n\n".join(lines)


def compose_narrative(rows: List[Dict], agg: Dict, diff: Dict,
                      model: str = "gpt-4o-mini") -> Tuple[str, str]:
    """(narrative_markdown, engine). LLM 실패 시 집계 기반 폴백."""
    top = agg["top_mentions"][:10]
    top_text = "\n".join(
        f"- {t['name']}({t['ticker']}): 언급 {t['total']}회 "
        f"(매수 {t['buy']}·중립 {t['neutral']}·주의 {t['caution']}, 점수 {t['score']:+d})"
        for t in top
    ) or "(집계된 종목 없음)"
    surge_text = ", ".join(
        f"{s['ticker']}({s['prior']}→{s['this_week']}회)" for s in diff["surges"]
    ) or "없음"
    flip_text = ", ".join(
        f"{f['ticker']}({f['prior']}→{f['now']})" for f in diff["tone_flips"]
    ) or "없음"

    try:
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY 없음")
        from openai import OpenAI

        prompt = f"""이번 주({rows and rows[0]['date']} 전후) 유튜버 영상 종합이야.

[이번 주 언급 TOP 종목 — 이미 집계됨]
{top_text}

[지난주 대비 변화 — 이미 집계됨]
- 언급 급증: {surge_text}
- 톤 반전: {flip_text}

[이번 주 영상 요약들]
{_videos_block(rows)}

위를 근거로 아래 두 섹션만 마크다운으로 써줘 (집계 표는 다시 쓰지 말 것):

## 🌊 이번 주 흐름
여러 채널이 공통으로 짚은 테마·시황 내러티브 4~6문장. 어떤 종목·섹터에 관심이 쏠렸고
분위기가 매수 쪽인지 경계 쪽인지, 근거가 된 종목명을 인용하며.

## 🔍 소수의견 · 특이 콜
남들과 반대로 말했거나 혼자만 강하게 주장한 콜 2~4개를 bullet로. 누가(채널) 무엇을
왜 그렇게 봤는지 직접 인용 위주. 없으면 '뚜렷한 소수의견 없음'."""

        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": prompt}],
            temperature=0.4,
        )
        return resp.choices[0].message.content, f"openai:{model}"
    except Exception as e:
        print(f"주간 리포트 내러티브 LLM 폴백: {e}")
        parts = ["## 🌊 이번 주 흐름",
                 f"이번 주 유튜버들이 가장 많이 다룬 종목은 " +
                 (", ".join(f"{t['name']}({t['total']}회)" for t in top[:5]) or "집계 없음") +
                 " 순입니다. (LLM 종합 미사용 — 집계 요약)"]
        if diff["surges"]:
            parts.append("\n**언급 급증:** " + surge_text)
        if diff["tone_flips"]:
            parts.append("\n**톤 반전:** " + flip_text)
        return "\n".join(parts), "fallback"


# ──────────────────────────────────────────────
# 4. 발행 · 저장 · 조회
# ──────────────────────────────────────────────
def _report_path(key: str) -> str:
    return os.path.join(_REPORT_DIR, f"{key}.json")


def publish_weekly_report(ref: Optional[datetime] = None,
                          model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """ref가 속한 주의 리포트 발행 후 저장·반환. ref 기본=지금."""
    ref = ref or now_kst()
    start, end = week_bounds(ref)
    prior_start = start - timedelta(days=7)

    rows = collect_week_rows(start, end)
    prior_rows = collect_week_rows(prior_start, start)

    agg = aggregate(rows)
    diff = diff_vs_prior(rows, prior_rows)
    narrative, engine = compose_narrative(rows, agg, diff, model=model)

    # UI 보유종목 오버레이용 — 영상 단위 컴팩트 목록
    by_video: Dict[str, Dict] = {}
    for r in rows:
        v = by_video.setdefault(r["link"], {
            "title": r["title"], "channel": r["channel"], "date": r["date"],
            "link": r["link"], "tickers": [], "sentiments": {},
        })
        if r["ticker"] not in _EXCLUDE:
            if r["ticker"] not in v["tickers"]:
                v["tickers"].append(r["ticker"])
            v["sentiments"][r["ticker"]] = r["sentiment"]

    report = {
        "week_key": week_key(ref),
        "period": {"start": start.strftime("%Y-%m-%d"),
                   "end": (end - timedelta(days=1)).strftime("%Y-%m-%d")},
        "published_at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "video_count": agg["video_count"],
        "channel_count": agg["channel_count"],
        "stock_count": agg["stock_count"],
        "top_mentions": agg["top_mentions"],
        "surges": diff["surges"],
        "tone_flips": diff["tone_flips"],
        "narrative": narrative,
        "videos": list(by_video.values()),
        "engine": engine,
    }
    _save_report(report)
    return report


def _save_report(report: Dict[str, Any]):
    os.makedirs(_REPORT_DIR, exist_ok=True)
    with open(_report_path(report["week_key"]), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


def get_report(key: Optional[str] = None) -> Dict[str, Any]:
    """주차 키의 리포트 로드. key 기본=이번 주. 없으면 {}."""
    key = key or week_key()
    try:
        with open(_report_path(key), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def list_reports() -> List[str]:
    """보관된 주차 키 목록 (최신순)."""
    if not os.path.isdir(_REPORT_DIR):
        return []
    keys = [f[:-5] for f in os.listdir(_REPORT_DIR) if f.endswith(".json")]
    return sorted(keys, reverse=True)
