"""
캔들스틱 차트 빌더
yfinance 데이터로 캔들차트 + 이동평균선 + 볼린저밴드 + RSI/MACD 서브플롯 생성
"""
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def fetch_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame:
    """OHLCV 데이터 + 보조지표 계산"""
    df = yf.Ticker(ticker).history(period=period)
    if df.empty:
        return df

    # 이동평균선
    df["MA20"] = df["Close"].rolling(20).mean()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()

    # 볼린저 밴드
    df["BB_Middle"] = df["Close"].rolling(20).mean()
    bb_std = df["Close"].rolling(20).std()
    df["BB_Upper"] = df["BB_Middle"] + bb_std * 2
    df["BB_Lower"] = df["BB_Middle"] - bb_std * 2

    # RSI
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))

    # MACD
    exp1 = df["Close"].ewm(span=12, adjust=False).mean()
    exp2 = df["Close"].ewm(span=26, adjust=False).mean()
    df["MACD"] = exp1 - exp2
    df["Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["Signal"]

    return df


def build_candlestick_chart(ticker: str, period: str = "6mo",
                            show_bb: bool = True, show_ma: bool = True) -> go.Figure:
    """
    캔들차트 + 거래량 + RSI + MACD 4단 차트 생성

    Returns:
        plotly Figure (데이터 없으면 None)
    """
    df = fetch_ohlcv(ticker, period)
    if df.empty:
        return None

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.55, 0.15, 0.15, 0.15],
        vertical_spacing=0.02,
        subplot_titles=(f"{ticker} 가격", "거래량", "RSI (14)", "MACD"),
    )

    # 1단: 캔들스틱
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"],
        low=df["Low"], close=df["Close"],
        increasing_line_color="#FF4B4B", decreasing_line_color="#4B7BFF",
        name="가격",
    ), row=1, col=1)

    if show_ma:
        for col, color in (("MA20", "#FFD700"), ("MA50", "#FF8C00"), ("MA200", "#9370DB")):
            if df[col].notna().any():
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[col], name=col,
                    line=dict(color=color, width=1),
                ), row=1, col=1)

    if show_bb:
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Upper"], name="BB 상단",
            line=dict(color="rgba(150,150,150,0.5)", width=1, dash="dot"),
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df.index, y=df["BB_Lower"], name="BB 하단",
            line=dict(color="rgba(150,150,150,0.5)", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(150,150,150,0.08)",
        ), row=1, col=1)

    # 2단: 거래량 (상승/하락 색 구분)
    volume_colors = [
        "#FF4B4B" if c >= o else "#4B7BFF"
        for c, o in zip(df["Close"], df["Open"])
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df["Volume"], marker_color=volume_colors,
        name="거래량", showlegend=False,
    ), row=2, col=1)

    # 3단: RSI
    fig.add_trace(go.Scatter(
        x=df.index, y=df["RSI"], name="RSI",
        line=dict(color="#00FFA3", width=1.5), showlegend=False,
    ), row=3, col=1)
    fig.add_hline(y=70, line=dict(color="red", width=1, dash="dash"), row=3, col=1)
    fig.add_hline(y=30, line=dict(color="green", width=1, dash="dash"), row=3, col=1)

    # 4단: MACD
    hist_colors = ["#FF4B4B" if v >= 0 else "#4B7BFF" for v in df["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(
        x=df.index, y=df["MACD_Hist"], marker_color=hist_colors,
        name="Histogram", showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["MACD"], name="MACD",
        line=dict(color="#FFD700", width=1), showlegend=False,
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df["Signal"], name="Signal",
        line=dict(color="#FF8C00", width=1), showlegend=False,
    ), row=4, col=1)

    fig.update_layout(
        height=800,
        xaxis_rangeslider_visible=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E2E8F0"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=40, r=20, t=60, b=20),
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")

    return fig
