"""
내부자 거래 추적 (스마트머니 추적 2단계 — SEC EDGAR Form 4)

Form 4 = 임원·이사·10%주주의 보유 변동 공시. 그 중 '공개시장 매수(P)'는
가장 강한 내부자 확신 신호다(보상성 부여 A/옵션행사 M과 구분). 최근 90일
순매수(매수 − 매도)를 집계해 시그널에 반영한다.

설계:
  - EDGAR 호출은 느리고 rate-limit이 있어 **수집 cron이 미리 긁어 캐시**하고
    시그널/페이지는 캐시만 읽는다(allow_live=False → 콜드면 중립 반환, 느려지지 않음).
  - 캐시: data/cache/insider/{ticker}.json (요약본 + as_of)
  - 집계 대상 거래코드: P(매수)·S(매도) 만. A/M/G/F(보상·옵션·증여·세금)는 제외.

SEC 정책: User-Agent에 연락처 필수, 초당 10건 이하. 종목 간 sleep으로 준수.
"""
import os
import re
import time
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import requests

logger = logging.getLogger(__name__)

_UA = {"User-Agent": "StockAgent/1.0 (personal research; contact: user@example.com)"}
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSIDER_DIR = os.path.join(_BASE_DIR, "data", "cache", "insider")

_SEC_SLEEP = 0.15  # SEC rate-limit 준수


def _safe_name(ticker: str) -> str:
    return ticker.replace("^", "_idx_").replace("=", "_eq_").replace("/", "_")


def _cache_path(ticker: str) -> str:
    return os.path.join(INSIDER_DIR, f"{_safe_name(ticker)}.json")


def _is_fresh(ticker: str, max_age_h: float = 18) -> bool:
    path = _cache_path(ticker)
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        as_of = datetime.fromisoformat(data["as_of"])
        return (datetime.now() - as_of) < timedelta(hours=max_age_h)
    except Exception:
        return False


def _load_cache(ticker: str) -> Optional[Dict]:
    try:
        with open(_cache_path(ticker), "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_cache(ticker: str, summary: Dict):
    try:
        os.makedirs(INSIDER_DIR, exist_ok=True)
        tmp = _cache_path(ticker) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _cache_path(ticker))
    except Exception as e:
        logger.warning(f"insider 캐시 저장 실패 ({ticker}): {e}")


def _neutral(ticker: str) -> Dict[str, Any]:
    return {"ticker": ticker, "available": False, "net_shares": 0, "net_value": 0.0,
            "buy_value": 0.0, "sell_value": 0.0, "buyers": 0, "sellers": 0,
            "window_days": 90, "filings": 0, "as_of": datetime.now().isoformat()}


def _fetch_form4_xml(cik: int, acc_clean: str) -> Optional[str]:
    """공시 폴더에서 Form 4 본문 XML을 찾아 텍스트 반환."""
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}"
    try:
        r = requests.get(f"{base}/index.json", headers=_UA, timeout=15)
        r.raise_for_status()
        items = r.json().get("directory", {}).get("item", [])
    except Exception:
        return None
    xmls = [it["name"] for it in items if it.get("name", "").lower().endswith(".xml")]
    # 보고서 조각(R1.xml 등) 제외, form/ownership 우선
    xmls = [x for x in xmls if not re.match(r"^R\d+\.xml$", x, re.IGNORECASE)]
    cand = [x for x in xmls if "form" in x.lower() or "ownership" in x.lower()] or xmls
    if not cand:
        return None
    try:
        time.sleep(_SEC_SLEEP)
        r = requests.get(f"{base}/{cand[0]}", headers=_UA, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _parse_form4(xml_text: str) -> List[Dict[str, Any]]:
    """Form 4 XML → 비파생 거래 리스트 [{code, ad, shares, price, owner}]."""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    owner = (root.findtext(".//reportingOwner/reportingOwnerId/rptOwnerName") or "").strip()
    for tx in root.findall(".//nonDerivativeTransaction"):
        code = (tx.findtext(".//transactionCoding/transactionCode") or "").strip()
        ad = (tx.findtext(".//transactionAmounts/transactionAcquiredDisposedCode/value") or "").strip()
        try:
            shares = float(tx.findtext(".//transactionAmounts/transactionShares/value") or 0)
        except ValueError:
            shares = 0.0
        try:
            price = float(tx.findtext(".//transactionAmounts/transactionPricePerShare/value") or 0)
        except ValueError:
            price = 0.0
        out.append({"code": code, "ad": ad, "shares": shares, "price": price, "owner": owner})
    return out


def _compute_summary(ticker: str, cik: str, days: int = 90) -> Dict[str, Any]:
    """EDGAR에서 최근 days일 Form 4를 긁어 순매수 요약 계산."""
    summary = _neutral(ticker)
    summary["window_days"] = days
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                         headers=_UA, timeout=15)
        r.raise_for_status()
        recent = r.json().get("filings", {}).get("recent", {})
    except Exception as e:
        logger.warning(f"insider submissions 조회 실패 ({ticker}): {e}")
        return summary

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    cutoff = datetime.now() - timedelta(days=days)

    buy_val = sell_val = buy_sh = sell_sh = 0.0
    buyers, sellers = set(), set()
    n_filings = 0

    for form, fdate, acc in zip(forms, dates, accs):
        if form != "4":
            continue
        try:
            fd = datetime.strptime(fdate, "%Y-%m-%d")
        except ValueError:
            continue
        if fd < cutoff:
            break  # 최신순 → 윈도우 벗어나면 중단
        acc_clean = acc.replace("-", "")
        time.sleep(_SEC_SLEEP)
        xml = _fetch_form4_xml(int(cik), acc_clean)
        if not xml:
            continue
        n_filings += 1
        for t in _parse_form4(xml):
            val = t["shares"] * t["price"]
            if t["code"] == "P" and t["ad"] == "A":      # 공개시장 매수
                buy_sh += t["shares"]; buy_val += val
                if t["owner"]:
                    buyers.add(t["owner"])
            elif t["code"] == "S" and t["ad"] == "D":    # 공개시장 매도
                sell_sh += t["shares"]; sell_val += val
                if t["owner"]:
                    sellers.add(t["owner"])

    summary.update({
        "available": True,
        "net_shares": round(buy_sh - sell_sh),
        "net_value": round(buy_val - sell_val, 2),
        "buy_value": round(buy_val, 2), "sell_value": round(sell_val, 2),
        "buyers": len(buyers), "sellers": len(sellers),
        "filings": n_filings, "as_of": datetime.now().isoformat(),
    })
    return summary


def get_insider_activity(ticker: str, days: int = 90,
                         allow_live: bool = False) -> Dict[str, Any]:
    """최근 days일 내부자 순매수 요약. 캐시 우선.
    allow_live=False(기본, 시그널/페이지용): 콜드면 중립 반환(느려지지 않음).
    allow_live=True(수집 cron용): 콜드/stale면 EDGAR에서 긁어 캐시 갱신."""
    if _is_fresh(ticker):
        cached = _load_cache(ticker)
        if cached:
            return cached
    if not allow_live:
        cached = _load_cache(ticker)  # stale라도 있으면 마지막 값 사용
        return cached or _neutral(ticker)

    # 라이브 수집 경로
    try:
        from modules.daily_paper import _load_cik_map
        cik = _load_cik_map().get(ticker.upper())
    except Exception:
        cik = None
    if not cik:
        summary = _neutral(ticker)
        summary["note"] = "CIK 없음(미국 상장 아님?)"
        _save_cache(ticker, summary)
        return summary

    summary = _compute_summary(ticker, cik, days)
    _save_cache(ticker, summary)
    return summary


def insider_score(activity: Dict[str, Any]) -> Dict[str, Any]:
    """순매수 요약 → 시그널 가산 점수 + 설명.
    내부자 '매수'는 강한 강세 신호(확신), '매도'는 약한 신호(분산·세금 등 사유 다양)."""
    if not activity or not activity.get("available"):
        return {"points": 0, "note": None, "buying": False}
    net = activity.get("net_value", 0.0)
    buyers = activity.get("buyers", 0)
    sellers = activity.get("sellers", 0)
    pts, note, buying = 0, None, False

    if net > 0 and buyers > 0:
        buying = True
        if net >= 5_000_000 or buyers >= 3:
            pts = 10; note = f"내부자 순매수 ${net/1e6:.1f}M ({buyers}명) — 강한 확신 신호"
        elif net >= 1_000_000:
            pts = 6; note = f"내부자 순매수 ${net/1e6:.1f}M ({buyers}명)"
        else:
            pts = 3; note = f"내부자 소폭 순매수 (${net/1e3:.0f}K, {buyers}명)"
    elif net < 0 and sellers > 0:
        # 내부자 매도는 사유가 다양(분산·세금·부여분 처분)해 예측력이 약함 →
        # 거의 모든 대형주가 순매도라 감점하면 좋은 종목까지 깎인다. 점수 0, 참고만.
        note = f"내부자 순매도 ${abs(net)/1e6:.1f}M ({sellers}명) — 매도는 약한 신호(참고)"

    return {"points": pts, "note": note, "buying": buying}
