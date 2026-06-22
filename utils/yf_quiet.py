"""yfinance 로그 노이즈 억제.

ETF처럼 펀더멘털이 없는 종목을 조회하면 yfinance가
  HTTP Error 404: {"quoteSummary": ... "No fundamentals data found for symbol: SOXL"}
같은 메시지를 자체 로거로 찍는다. 호출부(get_earnings_events, refresh_alerts 등)는
빈 결과를 정상 처리하므로 기능에는 영향이 없고 로그만 더러워진다.

yfinance 전용 로거("yfinance")만 올리므로 우리 앱 로그에는 영향이 없다.
cron 진입점에서 한 번 호출하면 그 프로세스 전체에 적용된다.
"""
import logging


def silence_yfinance() -> None:
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
