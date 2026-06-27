"""
데일리 신문 (Daily Paper)
구글 뉴스 RSS + SEC EDGAR 공시 + 매크로 지표를 취합해 신문 형태의 일일 브리핑을 만든다.
모두 무료 소스 (API 키 불필요).
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

import requests

_UA = {"User-Agent": "StockAgent/1.0 (personal research; contact: user@example.com)"}

# 서버 시간대(UTC)와 무관하게 항상 한국시간(KST) 기준으로 "오늘"을 판단한다.
# (KST는 DST 없음 → 고정 UTC+9. tzdata 의존 없이 어디서나 동작)
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """한국시간 기준 현재 시각 (서버가 UTC여도 KST 날짜로 일치시키기 위함)."""
    return datetime.now(KST)


# ──────────────────────────────────────────────
# 1. 구글 뉴스 RSS (무료, 키 불필요)
# ──────────────────────────────────────────────
def fetch_google_news(query: str, max_items: int = 6, lang: str = "ko") -> List[Dict[str, str]]:
    """
    구글 뉴스 RSS 검색.
    lang="ko" → 한국어 기사, "en" → 영어 기사
    """
    if lang == "ko":
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    else:
        url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"

    try:
        r = requests.get(url, headers=_UA, timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "#")
            pub = item.findtext("pubDate", "")
            source = item.find("source")
            source_name = source.text if source is not None else ""
            # pubDate 포맷: Tue, 10 Jun 2026 05:00:00 GMT
            try:
                pub_fmt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").strftime("%m/%d %H:%M")
            except ValueError:
                pub_fmt = pub[:16]
            items.append({"title": title, "link": link, "published": pub_fmt, "publisher": source_name})
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"구글 뉴스 실패 ({query}): {e}")
        return []


def fetch_holdings_news(holdings: List[Dict], per_ticker: int = 4) -> Dict[str, List[Dict]]:
    """보유 종목별 뉴스: 핵심 키워드 조합으로 검색 (실적/계약/인수 등 트리거 위주)"""
    result = {}
    for h in holdings:
        ticker = h["ticker"]
        name = h.get("name", ticker)
        # 영어 기사: 티커 + 트리거 키워드 우선, 부족하면 일반 검색
        news = fetch_google_news(f"{ticker} stock", per_ticker, lang="en")
        # 한국어 기사도 1-2건 보충 (국내 시각)
        news_ko = fetch_google_news(name if not name.isascii() else ticker, 2, lang="ko")
        result[ticker] = news + news_ko
    return result


# ──────────────────────────────────────────────
# 2. SEC EDGAR 공시 (무료 공식 API, 키 불필요)
# ──────────────────────────────────────────────
_cik_cache: Dict[str, str] = {}


def _load_cik_map() -> Dict[str, str]:
    """티커 → CIK 매핑 (SEC 공식 파일)"""
    global _cik_cache
    if _cik_cache:
        return _cik_cache
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers=_UA, timeout=15)
        r.raise_for_status()
        data = r.json()
        _cik_cache = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in data.values()}
    except Exception as e:
        print(f"CIK 매핑 로드 실패: {e}")
    return _cik_cache


# 주목할 공시 유형
IMPORTANT_FORMS = {
    "8-K": "⚡ 주요 이벤트 (8-K)",
    "10-Q": "📊 분기보고서 (10-Q)",
    "10-K": "📚 연간보고서 (10-K)",
    "4": "👤 내부자 거래 (Form 4)",
    "SC 13D": "🐋 5%+ 지분 공시 (13D)",
    "SC 13G": "🐋 5%+ 지분 공시 (13G)",
}


def get_sec_filings(tickers: List[str], max_per_ticker: int = 3, days: int = 14) -> List[Dict[str, Any]]:
    """
    보유 종목들의 최근 N일 내 주요 SEC 공시.
    Returns: [{ticker, form, label, date, link}] 최신순
    """
    cik_map = _load_cik_map()
    filings = []
    cutoff = datetime.now().strftime("%Y-%m-%d")

    for ticker in tickers:
        cik = cik_map.get(ticker.upper())
        if not cik:
            continue
        try:
            r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=_UA, timeout=15)
            r.raise_for_status()
            recent = r.json().get("filings", {}).get("recent", {})
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            docs = recent.get("primaryDocument", [])

            count = 0
            for form, fdate, acc, doc in zip(forms, dates, accessions, docs):
                if form not in IMPORTANT_FORMS:
                    continue
                # 최근 days일 이내만
                try:
                    age = (datetime.now() - datetime.strptime(fdate, "%Y-%m-%d")).days
                except ValueError:
                    continue
                if age > days:
                    break  # 최신순 정렬이므로 중단
                acc_clean = acc.replace("-", "")
                link = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{doc}"
                filings.append({
                    "ticker": ticker,
                    "form": form,
                    "label": IMPORTANT_FORMS[form],
                    "date": fdate,
                    "link": link,
                })
                count += 1
                if count >= max_per_ticker:
                    break
        except Exception as e:
            print(f"EDGAR 조회 실패 ({ticker}): {e}")

    return sorted(filings, key=lambda x: x["date"], reverse=True)


# ──────────────────────────────────────────────
# 3. 당일 신문 저장소 (토큰 절약: 본 헤드라인 기억, 새 정보만 증보)
# ──────────────────────────────────────────────
import os
import json

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAPER_FILE = os.path.join(_BASE_DIR, "data", "daily_paper.json")

_EDITOR_SYSTEM = (
    "너는 30년 경력의 경제신문 편집장이야. 문체 원칙: "
    "(1) 신문 기사체 — 간결하고 품격 있게, 감탄사·이모지 남용 금지. "
    "(2) 숫자 우선 — 주어진 지표·등락률을 근거로 인용. "
    "(3) 사실과 해석 구분 — 헤드라인만으로 추정할 땐 '~로 보인다', '~가능성' 표현 사용. "
    "(4) 독자는 이 종목들의 실제 보유자 — 모든 기사 끝에 보유자 관점의 시사점 한 줄. "
    "(5) 같은 내용 반복 금지, 광고성·홍보성 헤드라인은 무시."
)


def _load_paper_store() -> Dict[str, Any]:
    try:
        with open(PAPER_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_paper_store(store: Dict[str, Any]):
    os.makedirs(os.path.dirname(PAPER_FILE), exist_ok=True)
    with open(PAPER_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def _build_source_text(macro, holdings_news, filings, only_titles: set = None) -> str:
    """LLM 입력용 소스 텍스트. only_titles가 주어지면 해당 제목만 포함 (증보판용)."""
    macro_text = "\n".join(
        f"- {m['name']}: {m['value_str']} ({m['change_pct']:+.2f}%)"
        for m in macro if m.get("change_pct") is not None
    )
    news_text = ""
    for ticker, news in holdings_news.items():
        lines = [
            f"  - {n['title']}" for n in news[:5]
            if only_titles is None or n["title"] in only_titles
        ]
        if lines:
            news_text += f"\n[{ticker}]\n" + "\n".join(lines)
    filings_text = "\n".join(
        f"- {f['date']} {f['ticker']}: {f['label']}"
        for f in filings[:10]
        if only_titles is None or f"{f['ticker']}|{f['date']}|{f['form']}" in only_titles
    ) or "없음"

    return f"""[매크로 지표]
{macro_text}

[보유 종목 뉴스 헤드라인]
{news_text if news_text else '신규 없음'}

[SEC 공시]
{filings_text}"""


_FRONT_FORMAT = """## 오늘의 헤드라인
(가장 중요한 이슈 1개 — 신문 헤드라인처럼 굵고 짧게)

(해설 기사 4-5문장: 무슨 일인지 → 왜 중요한지 → 숫자 근거 → 보유 포트폴리오 영향)

## 주요 기사
**1. (제목)** — 3문장: 내용 요약 + 배경/맥락 + 보유자 시사점
**2. (제목)** — 3문장: 동일 구조
**3. (제목)** — 3문장: 동일 구조

(SEC 공시 중 주목할 게 있으면 주요 기사에 자연스럽게 녹여서 다뤄)

## 편집장의 한마디
(매크로+뉴스 종합 — 오늘 보유자가 가져야 할 관점 2-3문장, 단정 대신 균형)"""


def _collect_keys(holdings_news: Dict, filings: List[Dict]) -> set:
    keys = set()
    for news in holdings_news.values():
        for n in news[:5]:
            keys.add(n["title"])
    for f in filings[:10]:
        keys.add(f"{f['ticker']}|{f['date']}|{f['form']}")
    return keys


# ──────────────────────────────────────────────
# 3-1. 웹 검색 기반 1면 편집 (Gemini 무료 / Claude — utils.web_llm이 자동 선택)
# ──────────────────────────────────────────────
def compose_front_page_search(
    holdings: List[Dict],
    macro: List[Dict],
    previous_front: str = None,
    max_searches: int = 12,
) -> str:
    """
    웹 검색 LLM으로 보유 종목 + 시장 이슈를 직접 검색해 1면 작성.
    헤드라인이 아닌 기사 본문 기반이며 출처 인용이 포함된다.
    previous_front가 있으면 새 소식만 검색해 개정판을 쓴다 (비용 절약).
    """
    from utils.web_llm import search_generate

    # 보유 종목별 실시간 그라운드 트루스 (현재가/평단/수익률).
    # LLM이 검색한 옛 뉴스에 옛 가격이 적혀 있어도 이 값을 우선하게 강제.
    def _h_line(h):
        cur = float(h.get("current_price") or 0)
        avg = float(h.get("avg_price") or 0)
        if cur > 0 and avg > 0:
            pnl = (cur / avg - 1) * 100
            return f"- {h['name']} ({h['ticker']}): 현재가 {cur:,.2f} · 평단 {avg:,.2f} · 수익률 {pnl:+.1f}%"
        if cur > 0:
            return f"- {h['name']} ({h['ticker']}): 현재가 {cur:,.2f}"
        return f"- {h['name']} ({h['ticker']}): 가격 데이터 없음"

    # CSV에 저장된 현재가가 오래/잘못된 값(예: $600)일 수 있어, 발행 직전 실시간 시세로 갱신.
    # (신문·카톡 브리핑이 이 블록을 그라운드 트루스로 쓰므로 여기서 바로잡으면 둘 다 정상화)
    import yfinance as yf
    for _h in holdings:
        try:
            _last = yf.Ticker(_h["ticker"]).fast_info.get("lastPrice")
            if _last and float(_last) > 0:
                _h["current_price"] = float(_last)
        except Exception:
            pass

    holdings_block = "\n".join(_h_line(h) for h in holdings) or "(보유 종목 없음)"
    macro_text = "\n".join(
        f"- {m['name']}: {m['value_str']} ({m['change_pct']:+.2f}%)"
        for m in macro if m.get("change_pct") is not None
    )

    if previous_front:
        task = f"""아래는 오늘 이미 발행한 신문 1면이야:

{previous_front}

─────────────────
발행 이후 새로 나온 소식이 있는지 보유 종목과 시장 전반을 검색해서 확인해.
- 의미 있는 새 소식이 없으면: 기존 1면을 그대로 유지하되 맨 위에 "(증보 검토: 신규 이슈 없음)" 한 줄만 추가
- 새 소식이 있으면: 반영해서 개정판 작성 (유효한 기존 기사는 유지/압축)"""
    else:
        task = """보유 종목 각각의 최신 뉴스와 미국 시장 전반의 주요 이슈를 검색해서 신문 1면을 작성해."""

    prompt = f"""오늘 날짜: {now_kst().strftime('%Y년 %m월 %d일')}

[내 보유 종목 — yfinance 실시간 그라운드 트루스]
{holdings_block}

[현재 매크로 지표 (yfinance 실시간)]
{macro_text}

{task}

형식:

{_FRONT_FORMAT}

추가 규칙:
- 검색으로 확인한 사실에는 근거가 된 매체명을 본문에 자연스럽게 표기 (예: "로이터에 따르면 ...")
- 검색 결과가 서로 충돌하면 더 최신/신뢰도 높은 쪽을 따르고 그 사실을 언급
- 모든 종목을 다룰 필요는 없고, 오늘 실제로 움직임이 있는 종목 위주로

**가격 인용 규칙 (가장 중요)**:
- 종목의 현재 주가/시가/종가를 언급할 때는 **반드시 위 [내 보유 종목] 블록의 '현재가'를 사용**.
- 검색한 뉴스 기사에 다른 가격(예: 며칠/몇 주 전 가격, 분할 전 가격)이 나오더라도 그 가격을 본문에 적지 말 것. 사용자가 보는 진짜 현재가는 위 yfinance 값이다.
- 목표가/저항선/지지선 같은 애널리스트 수치는 인용해도 좋지만, "현재 주가 X달러" 식으로 단언할 땐 무조건 위 그라운드 트루스를 사용.
- 평단/수익률(있는 경우)도 위 값을 그대로 활용해 "보유자 관점"의 코멘트를 달 것."""

    return search_generate(
        system=_EDITOR_SYSTEM,
        prompt=prompt,
        max_tokens=8000,
        max_searches=max_searches,
    )


def publish_daily_paper(
    macro: List[Dict],
    holdings_news: Dict[str, List[Dict]],
    filings: List[Dict],
    model: str = "gpt-4o",
    holdings: List[Dict] = None,
) -> Dict[str, Any]:
    """
    당일 신문 발행/증보.
    - ANTHROPIC_API_KEY가 설정되어 있으면 Claude 웹 검색 엔진 사용 (본문 기반 + 인용)
    - 없으면 기존 OpenAI 방식 (RSS 헤드라인 기반)
    - 오늘 첫 발행: 전체 소스로 1면 생성
    - 재발행 + 새 소식 없음: LLM 호출 없이 기존 신문 반환 (토큰 0)
    - 재발행 + 새 소식 있음: 신규 항목만으로 개정판 생성

    Returns: {front, time, status: "new"|"unchanged"|"updated", new_count, engine}
    """
    # ── 웹 검색 LLM 경로 (Gemini 무료 / Claude) ──
    from utils.web_llm import get_search_provider
    provider = get_search_provider()
    if provider:
        today = now_kst().strftime("%Y-%m-%d")
        now_hm = now_kst().strftime("%H:%M")
        store = _load_paper_store()
        previous = store.get("front") if store.get("date") == today else None

        front = compose_front_page_search(
            holdings or [{"ticker": t, "name": t} for t in holdings_news.keys()],
            macro,
            previous_front=previous,
        )
        _save_paper_store({
            "date": today, "front": front, "time": now_hm,
            "seen_keys": store.get("seen_keys", []) if previous else [],
            "engine": provider,
        })
        return {
            "front": front, "time": now_hm,
            "status": "updated" if previous else "new",
            "new_count": 0, "engine": f"{provider}-websearch",
        }

    # ── 기존 OpenAI 경로 (RSS 헤드라인 기반) ──
    from openai import OpenAI

    today = now_kst().strftime("%Y-%m-%d")
    now_hm = now_kst().strftime("%H:%M")
    store = _load_paper_store()
    current_keys = _collect_keys(holdings_news, filings)

    # ── 케이스 1: 오늘 이미 발행됨 ──
    if store.get("date") == today and store.get("front"):
        seen = set(store.get("seen_keys", []))
        new_keys = current_keys - seen

        if not new_keys:
            return {"front": store["front"], "time": store["time"],
                    "status": "unchanged", "new_count": 0}

        # 증보판: 기존 신문 + 새 항목만 전달 (전체 재전송 안 함 → 토큰 절약)
        new_source = _build_source_text(macro, holdings_news, filings, only_titles=new_keys)
        client = OpenAI()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _EDITOR_SYSTEM},
                {"role": "user", "content": f"""아래는 오늘 이미 발행한 신문 1면이야:

{store['front']}

─────────────────
이후 새로 들어온 소식 (이것만 신규):

{new_source}

새 소식을 반영해 1면을 개정해줘. 규칙:
- 기존 기사 중 여전히 유효한 것은 유지 (다시 쓰지 말고 그대로 또는 압축)
- 새 소식이 더 중요하면 헤드라인 교체, 아니면 주요 기사에 추가
- 형식은 동일하게:

{_FRONT_FORMAT}"""},
            ],
            temperature=0.4,
        )
        front = response.choices[0].message.content
        store.update({
            "front": front, "time": now_hm,
            "seen_keys": list(seen | new_keys),
        })
        _save_paper_store(store)
        return {"front": front, "time": now_hm, "status": "updated", "new_count": len(new_keys)}

    # ── 케이스 2: 오늘 첫 발행 ──
    source = _build_source_text(macro, holdings_news, filings)
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _EDITOR_SYSTEM},
            {"role": "user", "content": f"""오늘 날짜: {now_kst().strftime('%Y년 %m월 %d일')}

{source}

위 데이터로 신문 1면을 작성해줘. 형식:

{_FRONT_FORMAT}"""},
        ],
        temperature=0.4,
    )
    front = response.choices[0].message.content
    _save_paper_store({
        "date": today, "front": front, "time": now_hm,
        "seen_keys": list(current_keys),
    })
    return {"front": front, "time": now_hm, "status": "new", "new_count": len(current_keys)}


def get_saved_paper() -> Dict[str, Any]:
    """오늘 발행된 신문이 있으면 반환 (앱 재시작 후에도 유지)"""
    store = _load_paper_store()
    if store.get("date") == now_kst().strftime("%Y-%m-%d") and store.get("front"):
        return {"front": store["front"], "time": store["time"]}
    return {}
