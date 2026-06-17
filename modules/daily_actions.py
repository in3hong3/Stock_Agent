"""
오늘의 액션 체크리스트
보유 종목 스냅샷 + 이벤트 + 알림 + 발행 상태를 규칙 기반으로 점검해
"오늘 뭘 해야 하는지"를 투자 성향에 맞는 문구로 알려준다. (LLM 호출 없음)
"""
import os
from datetime import datetime
from typing import Dict, List, Any

import pandas as pd

# 성향별 권고 문구 (situation → stance → text)
_STANCE_TEXT = {
    "rsi_oversold": {
        "aggressive": "과매도권 진입 — 분할매수 1차 검토 구간입니다",
        "neutral": "과매도권 — 낙폭 원인 확인 후 소량 분할매수 검토",
        "conservative": "과매도권 — 낙폭 원인 파악 전 진입 금지, 관망하세요",
    },
    "rsi_overbought": {
        "aggressive": "과매수권 — 추세 유지 시 홀드, 단 신규 추격매수는 자제",
        "neutral": "과매수권 — 일부 차익실현 검토 구간입니다",
        "conservative": "과매수권 — 차익실현으로 비중 축소를 검토하세요",
    },
    "surge": {
        "aggressive": "뉴스 확인 후 모멘텀 지속 여부 판단하세요",
        "neutral": "원인 뉴스를 확인하고 목표가 도달 시 일부 실현 검토",
        "conservative": "차익실현 기회인지 뉴스로 확인하세요",
    },
    "plunge": {
        "aggressive": "원인 확인 후 펀더멘탈 이상 없으면 매수 기회 검토",
        "neutral": "원인 뉴스 확인 필수, 일시적 악재인지 판단하세요",
        "conservative": "손절 라인 점검, 추가 하락 리스크부터 확인하세요",
    },
    "earnings_near": {
        "aggressive": "실적 임박 — 서프라이즈 베팅 여부 결정, 변동성 대비",
        "neutral": "실적 임박 — 비중 점검, 발표 후 대응 시나리오 준비",
        "conservative": "실적 임박 — 변동성 구간, 비중 축소 또는 헤지 검토",
    },
}


def _stance_msg(situation: str, stance: str) -> str:
    return _STANCE_TEXT.get(situation, {}).get(stance, _STANCE_TEXT.get(situation, {}).get("neutral", ""))


def _holding_str(s: Dict, fx: float) -> str:
    """시그널 dict에서 보유 평가금액을 달러 기준 문자열로. 미보유면 빈 문자열."""
    qty = s.get("quantity") or 0
    price = s.get("price") or 0
    if qty <= 0 or price <= 0:
        return ""
    is_kr = str(s.get("ticker", "")).endswith((".KS", ".KQ"))
    eval_usd = (price * qty / fx) if (is_kr and fx) else (price * qty)
    return f"보유 {qty:,.0f}주 (${eval_usd:,.0f})"


def build_actions(snap_df: pd.DataFrame, tickers: List[str],
                  stance: str = "aggressive", signals: List[Dict] = None,
                  fx: float = 1400.0) -> List[Dict[str, Any]]:
    """
    오늘의 액션 리스트 생성.
    snap_df: get_snapshot() 결과 (티커/1일/RSI 컬럼 사용)
    signals: trade_signal.generate_signals()의 signals — 있으면 정밀 시그널 사용
    fx: 원/달러 환율 (한국주 보유액 달러 환산용)
    Returns: [{priority(낮을수록 중요), icon, text}]
    """
    actions = []

    # ── 1. 임박 이벤트 (3일 이내) ──
    try:
        from modules.event_calendar import get_all_events, get_upcoming_events
        events = get_all_events(tickers)
        for ev in get_upcoming_events(events, days=3):
            d_day = "오늘" if ev["d_day"] == 0 else f"D-{ev['d_day']}"
            title = ev["title"]
            if "실적발표" in title:
                ticker = title.split(" ")[1] if " " in title else ""
                actions.append({
                    "priority": 1, "icon": "📅",
                    "text": f"**{d_day} {title}** — {_stance_msg('earnings_near', stance)}",
                })
            elif "FOMC" in title or "CPI" in title:
                actions.append({
                    "priority": 1, "icon": "🏛️",
                    "text": f"**{d_day} {title}** — 발표 전후 변동성 주의, 신규 진입은 발표 이후 권장",
                })
            elif "휴장" in title:
                actions.append({
                    "priority": 3, "icon": "🏖️",
                    "text": f"{d_day} {title} — 거래 일정 참고하세요",
                })
    except Exception as e:
        print(f"이벤트 액션 실패: {e}")

    # ── 2. 종목 시그널 ──
    if signals is not None:
        # 정밀 시그널 엔진 결과 사용 (셋업 + 진입/손절/목표 기반)
        holds = []
        for s in signals:
            hold_str = _holding_str(s, fx)
            pr = s.get("profit_rate")
            pr_str = f" {pr:+.1f}%" if pr is not None else ""
            if s["action"] == "관망":
                # 관망 종목도 보유액·수익률은 요약줄에 함께 노출
                tag = f"{s['ticker']}({s['adj_score']:+.0f}"
                tag += f", {hold_str.replace('보유 ', '')}{pr_str})" if hold_str else f"{pr_str})"
                holds.append(tag)
                for ex in s.get("extra", []):
                    actions.append({"priority": 1, "icon": "⚠️", "text": f"**{s['ticker']}** {ex}"})
                continue
            is_strong = "🟢🟢" in s["icon"] or "🔴🔴" in s["icon"]
            # 진입/손절/목표가 있으면 구체적 가격으로, 없으면 플랜 문구
            if s.get("entry"):
                detail = (f"진입 {s['entry']:,.2f} / 손절 {s['stop']:,.2f} / 목표 {s['target']:,.2f} "
                          f"(손익비 1:{s['rr']})")
            else:
                detail = s["plan"]
            # 보유 평가액 + 수익률을 액션 문구 앞부분에 노출 (직관적 포지션 파악)
            hold_prefix = f" · {hold_str}{pr_str}" if hold_str else ""
            actions.append({
                "priority": 1 if is_strong else 2,
                "icon": s["icon"],
                "text": f"**{s['ticker']} → {s['action']}**{hold_prefix} · {s.get('setup','')} — {detail}",
            })
            for ex in s.get("extra", []):
                actions.append({"priority": 1, "icon": "⚠️", "text": f"**{s['ticker']}** {ex}"})

        if holds:
            actions.append({
                "priority": 5, "icon": "⚪",
                "text": f"나머지 {len(holds)}종목은 **홀드** — {', '.join(holds)} · 특별한 행동 불필요 (상세는 아래 매매 시그널 참고)",
            })
    else:
        # 폴백: 단순 RSI/급등락 규칙
        try:
            for _, row in snap_df.iterrows():
                ticker = row.get("티커", "")
                rsi = row.get("RSI")
                chg = row.get("1일")

                if isinstance(chg, (int, float)):
                    if chg <= -4:
                        actions.append({
                            "priority": 1, "icon": "📉",
                            "text": f"**{ticker} {chg:+.1f}% 급락** — {_stance_msg('plunge', stance)}",
                        })
                    elif chg >= 4:
                        actions.append({
                            "priority": 2, "icon": "🚀",
                            "text": f"**{ticker} {chg:+.1f}% 급등** — {_stance_msg('surge', stance)}",
                        })

                if isinstance(rsi, (int, float)):
                    if rsi <= 30:
                        actions.append({
                            "priority": 2, "icon": "🟢",
                            "text": f"**{ticker} RSI {rsi:.0f}** — {_stance_msg('rsi_oversold', stance)}",
                        })
                    elif rsi >= 70:
                        actions.append({
                            "priority": 2, "icon": "🔴",
                            "text": f"**{ticker} RSI {rsi:.0f}** — {_stance_msg('rsi_overbought', stance)}",
                        })
        except Exception as e:
            print(f"시그널 액션 실패: {e}")

    # ── 3. 알림 상태 ──
    try:
        from modules.price_alert import load_alerts
        alerts = load_alerts()
        active = [a for a in alerts if a.get("enabled")]
        fired = [a for a in alerts if not a.get("enabled") and a.get("last_triggered")]
        if fired:
            actions.append({
                "priority": 2, "icon": "🔔",
                "text": f"충족된 알림 {len(fired)}건이 비활성 상태 — '가격 알림' 탭에서 재설정하거나 정리하세요",
            })
        if not active and not fired:
            actions.append({
                "priority": 4, "icon": "🔕",
                "text": "설정된 가격 알림이 없습니다 — 주요 종목 목표가/RSI 알림을 걸어두면 놓치지 않아요",
            })
    except Exception as e:
        print(f"알림 액션 실패: {e}")

    # ── 4. 오늘 발행물 체크 ──
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        from modules.daily_paper import _load_paper_store
        if _load_paper_store().get("date") != today:
            actions.append({
                "priority": 3, "icon": "🗞️",
                "text": "오늘 신문이 아직 발행 전 — '데일리' 탭에서 발행하면 시장 흐름을 한눈에",
            })
    except Exception:
        pass
    try:
        from modules.portfolio_advisor import _load_evals
        if not any(k.startswith(today) for k in _load_evals()):
            actions.append({
                "priority": 3, "icon": "🤖",
                "text": "오늘 AI 평가서 미생성 — 아래에서 성향 선택 후 생성해보세요",
            })
    except Exception:
        pass

    actions.sort(key=lambda a: a["priority"])
    return actions
