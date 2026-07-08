"""캔들 차트 이미지 렌더링 — 학습(build_dataset)과 추론(predict)이 공유.

학습 때와 추론 때 이미지가 픽셀 단위로 동일해야 모델이 제대로 동작하므로,
스타일과 렌더링 로직을 여기 한 곳에만 둔다.
"""

import io

import matplotlib

matplotlib.use("Agg")  # 창 없이 파일/버퍼로만 렌더링

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

_MC = mpf.make_marketcolors(up="red", down="blue", edge="inherit",
                            wick="inherit", volume="inherit")
STYLE = mpf.make_mpf_style(marketcolors=_MC, facecolor="white",
                           figcolor="white", gridstyle="")


def render_fig(win_df: pd.DataFrame, img_size: int):
    """축·격자·여백 없는 순수 캔들+거래량 Figure 반환 (호출자가 close 해야 함)."""
    fig, _ = mpf.plot(win_df, type="candle", style=STYLE, volume=True,
                      axisoff=True, returnfig=True, scale_padding=0,
                      figsize=(img_size / 100, img_size / 100))
    return fig


def save_png(win_df: pd.DataFrame, path, img_size: int) -> None:
    fig = render_fig(win_df, img_size)
    fig.savefig(path, dpi=100)
    plt.close(fig)


def to_png_bytes(win_df: pd.DataFrame, img_size: int) -> bytes:
    fig = render_fig(win_df, img_size)
    buf = io.BytesIO()
    fig.savefig(buf, dpi=100, format="png")
    plt.close(fig)
    return buf.getvalue()
