"""
QuantAnalyst DCF/SOTP 테스트 스크립트
"""
from dotenv import load_dotenv
load_dotenv()

from modules.quant_analyst import QuantAnalyst

print("=" * 80)
print("QuantAnalyst DCF/SOTP 테스트")
print("=" * 80)

analyst = QuantAnalyst()

# 테스트 1: DCF 모델 (성장주 - Palantir)
print("\n\n[테스트 1: DCF 모델 - Palantir (PLTR)]")
print("-" * 80)

dcf_analysis = analyst.generate_analysis(
    ticker="PLTR",
    price=85.0,
    valuation_method="dcf",
    fcf_current=500,  # $500M FCF
    growth_rate=25,  # 25% 성장률
    terminal_growth=3,  # 3% 영구 성장률
    wacc=10,  # 10% 할인율
    shares_outstanding=2200  # 2.2B shares
)

print(dcf_analysis)

# 테스트 2: SOTP 모델 (복합 기업 - Alphabet)
print("\n\n[테스트 2: SOTP 모델 - Alphabet (GOOGL)]")
print("-" * 80)

sotp_analysis = analyst.generate_analysis(
    ticker="GOOGL",
    price=175.0,
    valuation_method="sotp",
    segments=[
        {"name": "Google Search", "revenue": 200000, "multiple": 6},
        {"name": "YouTube", "revenue": 35000, "multiple": 8},
        {"name": "Google Cloud", "revenue": 35000, "multiple": 10},
        {"name": "Other Bets", "revenue": 1500, "multiple": 2}
    ],
    net_debt=-100000,  # Net cash position
    shares_outstanding=12500  # 12.5B shares
)

print(sotp_analysis)

# 테스트 3: 기존 P/E 모델 (안정적 기업)
print("\n\n[테스트 3: P/E 모델 - Apple (AAPL)]")
print("-" * 80)

pe_analysis = analyst.generate_analysis(
    ticker="AAPL",
    price=230.0,
    valuation_method="pe",
    eps_ttm=6.50,
    eps_fy1=7.00,
    theme="Big Tech",
    theme_pe=28,
    pe_low=22,
    pe_base=26,
    pe_high=30
)

print(pe_analysis)

print("\n" + "=" * 80)
print("테스트 완료!")
print("=" * 80)
