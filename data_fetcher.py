import yfinance as yf
from quant_engine import MarketDataInput, QuantFactorEngine


def fetch_and_evaluate(ticker_symbol: str):
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    history = ticker.history(period="1y")

    if not info.get("marketCap"):
        raise ValueError(f"Yahoo Finance에 '{ticker_symbol}'의 펀더멘털 데이터가 없습니다.")

    # 1. API 데이터 추출
    current_price = info.get("currentPrice", history["Close"].iloc[-1])
    market_cap_m = info.get("marketCap", 0) / 1e6

    # 애널리스트 컨센서스 forward 매출 추정치: yfinance의 revenue_estimate에서
    # 현재 회계연도("0y") 평균 추정치를 사용. 커버리지가 없는 종목이면 TTM 매출로 대체.
    try:
        fwd_revenue = ticker.revenue_estimate.loc["0y", "avg"]
    except (KeyError, AttributeError):
        fwd_revenue = None
    if fwd_revenue and fwd_revenue > 0:
        fwd_revenue_m = fwd_revenue / 1e6
    else:
        fwd_revenue_m = info.get("totalRevenue", 0) / 1e6

    total_cash_m = info.get("totalCash", 0) / 1e6
    total_debt_m = info.get("totalDebt", 0) / 1e6
    bps = info.get("bookValue", 1.0)
    short_float_pct = info.get("shortPercentOfFloat", 0.0) * 100
    days_to_cover = info.get("shortRatio", 2.0)

    # 연간 현금소진율: 영업현금흐름이 음수(적자)면 그 절대값을, 흑자 기업이면
    # 모델의 gt=0 제약을 만족시키기 위한 최소값(1.0)을 사용해 러너웨이가
    # 사실상 매우 길게(=재무 안전) 계산되도록 한다.
    operating_cashflow = info.get("operatingCashflow", 0)
    annual_burn_rate_m = abs(operating_cashflow) / 1e6 if operating_cashflow < 0 else 1.0

    # 200일 이동평균선 계산
    dma_200 = history["Close"].rolling(window=200).mean().iloc[-1]

    # 2. Pydantic 모델로 변환
    input_data = MarketDataInput(
        ticker=ticker_symbol,
        current_price=current_price,
        market_cap_m=market_cap_m,
        fwd_revenue_m=fwd_revenue_m,
        total_cash_m=total_cash_m,
        total_debt_m=total_debt_m,
        annual_burn_rate_m=annual_burn_rate_m,
        bps=bps,
        short_float_pct=short_float_pct,
        days_to_cover=days_to_cover,
        dma_200=dma_200,
    )

    # 3. 퀀트 평가 실행
    return QuantFactorEngine.evaluate(input_data)


if __name__ == "__main__":
    report = fetch_and_evaluate("IONQ")
    print(report.model_dump_json(indent=2))
