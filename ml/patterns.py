"""규칙 기반 차트 패턴 탐지 — ML 없음.

각 탐지 함수는 OHLCV DataFrame(일봉)을 받아 **이벤트 확정일** 리스트를 반환한다.

⚠ 누수 금지 원칙 (제일 중요):
    이벤트 확정일은 "그 날 종가까지 알 수 있었던 정보만으로" 판정해야 한다.
    - 피벗(고점/저점)은 좌우 N봉이 지나야 확정 → 확정일은 피벗보다 N봉 이상 뒤여야 함
    - 미래 봉을 보고 패턴을 소급 판정하면 승률이 가짜로 부풀어 오른다

패턴 추가하려면: 같은 시그니처(df → list[Timestamp])로 함수를 만들고
event_study.PATTERNS 에 등록하면 끝.
"""

import numpy as np
import pandas as pd


def _dedupe(dates: list, index: pd.Index, min_gap: int) -> list:
    """같은 에피소드에서 연달아 잡힌 이벤트를 첫 발생만 남김 (min_gap 거래일 간격)."""
    out, last_pos = [], None
    for dt in dates:
        pos = index.get_loc(dt)
        if last_pos is None or pos - last_pos >= min_gap:
            out.append(dt)
            last_pos = pos
    return out


def ma50_touch_bounce(df: pd.DataFrame, period: int = 50, tol: float = 0.005,
                      min_gap: int = 10) -> list:
    """상승 추세 중 50일선 터치 후 반등 — 확정일 = 반등 마감한 그 날.

    조건 (전부 당일까지 정보만 사용):
    1. MA50이 우상향       (당일 MA > 20거래일 전 MA)
    2. 추세 위에서 주행 중  (20거래일 전 종가가 당시 MA 위)
    3. 당일 저가가 MA50 근처(±tol)까지 하락 — '터치'
    4. 당일 종가는 MA50 위에서 마감 — '반등 확인'
    """
    close, low = df["Close"], df["Low"]
    ma = close.rolling(period).mean()

    cond = (
        (ma > ma.shift(20))                      # 1. MA 우상향
        & (close.shift(20) > ma.shift(20))       # 2. 추세 위 주행
        & (low <= ma * (1 + tol))                # 3. 당일 터치
        & (close > ma)                           # 4. 반등 마감
    )
    dates = list(df.index[cond.fillna(False)])
    return _dedupe(dates, df.index, min_gap)


def sharp_drop(df: pd.DataFrame, drop: float = -0.10, lookback: int = 10,
               min_gap: int = 10) -> list:
    """급락: 최근 lookback거래일 수익률 ≤ drop(−10%). 확정일 = 조건 최초 충족일.

    '보유 종목이 확 빠졌다 — 버텨도 되나?' 질문의 이벤트 정의.
    에피소드 첫날만 잡는다 (전날은 조건 미충족이었던 날).
    """
    close = df["Close"]
    ret = close / close.shift(lookback) - 1
    cond = ret <= drop
    first = cond & ~cond.shift(1, fill_value=False)   # 에피소드 진입일만
    dates = list(df.index[first.fillna(False)])
    return _dedupe(dates, df.index, min_gap)


def _ma200_filter(df: pd.DataFrame, dates: list, above: bool) -> list:
    """이벤트일 종가가 200일선 위/아래인 것만. MA 미형성 구간(NaN)은 제외."""
    close = df["Close"]
    ma200 = close.rolling(200).mean()
    out = []
    for d in dates:
        m = ma200.loc[d]
        if pd.isna(m):
            continue
        if (close.loc[d] > m) == above:
            out.append(d)
    return out


def sharp_drop_above_ma200(df: pd.DataFrame, **kw) -> list:
    """급락인데 아직 200일선 위 — '상승 추세 중의 흔들기' 후보."""
    return _ma200_filter(df, sharp_drop(df, **kw), above=True)


def sharp_drop_below_ma200(df: pd.DataFrame, **kw) -> list:
    """급락 + 200일선 아래 — '추세 붕괴' 후보."""
    return _ma200_filter(df, sharp_drop(df, **kw), above=False)


def high_52w_breakout(df: pd.DataFrame, lookback: int = 252, min_gap: int = 20) -> list:
    """52주 신고가 돌파: 종가가 직전 252거래일 최고 종가를 넘어선 날 (에피소드 첫날만).

    '신고가는 사는 자리다 vs 꼭지다' 논쟁의 이벤트 정의. 강한 추세에서 연일
    신고가가 나오므로 min_gap을 크게(20일) 잡아 같은 랠리 중복 계상을 줄인다.
    """
    close = df["Close"]
    prior_max = close.shift(1).rolling(lookback).max()   # 어제까지의 52주 최고
    cond = close > prior_max
    first = cond & ~cond.shift(1, fill_value=False)      # 돌파 진입일만
    dates = list(df.index[first.fillna(False)])
    return _dedupe(dates, df.index, min_gap)


def _pivot_highs(high: pd.Series, window: int) -> list:
    """좌우 window봉보다 높은 국소 고점의 위치(iloc) 리스트."""
    v = high.to_numpy()
    n = len(v)
    out = []
    for i in range(window, n - window):
        seg = v[i - window: i + window + 1]
        if v[i] == seg.max() and (seg == v[i]).sum() == 1:
            out.append(i)
    return out


def head_shoulders(df: pd.DataFrame, pivot_window: int = 5, shoulder_tol: float = 0.05,
                   head_min: float = 0.03, max_span: int = 120,
                   confirm_within: int = 40, min_gap: int = 10) -> list:
    """헤드앤숄더(약세 반전) — 확정일 = 넥라인 하향 이탈 마감일.

    정의:
    - 연속 피벗 고점 3개 (왼어깨 P1, 머리 P2, 오른어깨 P3): P2가 양쪽보다 head_min 이상 높고,
      어깨 둘은 높이 차이 ≤ shoulder_tol
    - 넥라인 = 두 골(P1~P2 최저가, P2~P3 최저가) 중 낮은 쪽 (보수적)
    - P3 피벗이 확정된(pivot_window 경과) 후 confirm_within일 내 종가가 넥라인 아래로
      마감하면 확정. 그 전에 머리 위로 신고가 나면 패턴 무효.
    """
    high, low, close = df["High"], df["Low"], df["Close"]
    piv = _pivot_highs(high, pivot_window)
    highs, lows, closes = high.to_numpy(), low.to_numpy(), close.to_numpy()
    n = len(df)

    dates = []
    for k in range(len(piv) - 2):
        p1, p2, p3 = piv[k], piv[k + 1], piv[k + 2]     # 인접한 피벗 고점 3개
        if p3 - p1 > max_span:
            continue
        s1, h, s2 = highs[p1], highs[p2], highs[p3]
        if h < max(s1, s2) * (1 + head_min):             # 머리가 충분히 높아야
            continue
        if abs(s2 / s1 - 1) > shoulder_tol:              # 어깨 대칭
            continue
        neckline = min(lows[p1:p2 + 1].min(), lows[p2:p3 + 1].min())
        start = p3 + pivot_window                        # 오른어깨 피벗 확정 이후만
        end = min(start + confirm_within, n)
        for j in range(start, end):
            if highs[j] > h:                             # 머리 돌파 → 패턴 무효
                break
            if closes[j] < neckline:                     # 넥라인 이탈 마감 → 확정
                dates.append(df.index[j])
                break

    dates = sorted(set(dates))
    return _dedupe(dates, df.index, min_gap)


def _pivot_lows(low: pd.Series, window: int) -> list:
    """좌우 window봉보다 낮은 국소 저점의 위치(iloc) 리스트.
    피벗은 우측 window봉이 지나야 확정된다는 점을 호출부에서 지켜야 함."""
    v = low.to_numpy()
    n = len(v)
    out = []
    for i in range(window, n - window):
        seg = v[i - window: i + window + 1]
        if v[i] == seg.min() and (seg == v[i]).sum() == 1:  # 유일한 최저
            out.append(i)
    return out


def double_bottom(df: pd.DataFrame, pivot_window: int = 5, bottom_tol: float = 0.03,
                  depth_min: float = 0.05, min_span: int = 15, max_span: int = 60,
                  confirm_within: int = 40, min_gap: int = 10) -> list:
    """이중바닥(쌍바닥) — 확정일 = 넥라인(두 저점 사이 고점) 상향 돌파 마감일.

    정의:
    - 피벗 저점 2개: 가격 차이 ≤ bottom_tol(3%), 간격 min_span~max_span 거래일
    - 사이 반등 고점(넥라인)이 저점 대비 depth_min(5%) 이상 → 진짜 'W' 모양
    - 두 번째 저점 피벗이 '확정'(pivot_window봉 경과)된 이후에,
      종가가 넥라인 위로 마감하는 첫날이 이벤트 확정일 (confirm_within일 내)
    """
    low, high, close = df["Low"], df["High"], df["Close"]
    piv = _pivot_lows(low, pivot_window)
    lows = low.to_numpy()
    highs = high.to_numpy()
    closes = close.to_numpy()
    n = len(df)

    dates = []
    for a in range(len(piv) - 1):
        for b in range(a + 1, len(piv)):
            p1, p2 = piv[a], piv[b]
            span = p2 - p1
            if span < min_span:
                continue
            if span > max_span:
                break  # p2가 더 멀어지기만 하므로 중단
            b1, b2 = lows[p1], lows[p2]
            if abs(b2 / b1 - 1) > bottom_tol:          # 두 저점 높이 유사
                continue
            neckline = highs[p1:p2 + 1].max()          # 사이 반등 고점
            if neckline / min(b1, b2) - 1 < depth_min:  # 충분히 깊은 W
                continue
            # 돌파 탐색: 두 번째 저점 피벗이 확정된 시점부터
            start = p2 + pivot_window
            end = min(start + confirm_within, n)
            for j in range(start, end):
                if lows[j] < b2 * (1 - bottom_tol):    # 저점 붕괴 → 패턴 무효
                    break
                if closes[j] > neckline:               # 넥라인 돌파 마감 → 확정
                    dates.append(df.index[j])
                    break

    dates = sorted(set(dates))
    return _dedupe(dates, df.index, min_gap)
