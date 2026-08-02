import yfinance as yf
from quant_engine import MarketDataInput, QuantFactorEngine

# 섹터별 대표 peer 종목 (실시간 평균 PBR 계산용). GICS 섹터 분류 기준.
SECTOR_PEER_TICKERS = {
    "Technology": ["MSFT", "AAPL", "NVDA", "ORCL", "CSCO"],
    "Healthcare": ["JNJ", "UNH", "PFE", "ABBV", "MRK"],
    "Communication Services": ["GOOGL", "META", "VZ", "T", "DIS"],
    "Consumer Cyclical": ["AMZN", "HD", "MCD", "NKE", "TJX"],
    "Consumer Defensive": ["PG", "KO", "PEP", "WMT", "COST"],
    "Financial Services": ["JPM", "BAC", "WFC", "GS", "MS"],
    "Energy": ["XOM", "CVX", "COP", "SLB", "EOG"],
    "Industrials": ["HON", "UNP", "CAT", "GE", "RTX"],
    "Basic Materials": ["LIN", "APD", "ECL", "NEM", "FCX"],
    "Real Estate": ["PLD", "AMT", "EQIX", "PSA", "O"],
    "Utilities": ["NEE", "DUK", "SO", "D", "AEP"],
}
DEFAULT_SECTOR_PBR = 3.0  # peer 조회가 아예 실패할 때만 쓰는 최종 폴백

_sector_pbr_cache: dict[str, float] = {}


def get_sector_avg_pbr(sector: str) -> float:
    """섹터 내 대표 peer 종목들의 실시간 PBR 평균. 같은 실행 내에서는 섹터별로 한 번만 조회(캐시)."""
    if sector in _sector_pbr_cache:
        return _sector_pbr_cache[sector]

    peers = SECTOR_PEER_TICKERS.get(sector, [])
    pbrs = []
    for peer in peers:
        try:
            peer_pbr = yf.Ticker(peer).info.get("priceToBook")
            if peer_pbr and peer_pbr > 0:
                pbrs.append(peer_pbr)
        except Exception:
            continue

    avg_pbr = sum(pbrs) / len(pbrs) if pbrs else DEFAULT_SECTOR_PBR
    _sector_pbr_cache[sector] = avg_pbr
    return avg_pbr


def compute_rsi(close, period: int = 14) -> float:
    """Wilder's smoothing 방식의 RSI (14일 기준)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    last_avg_loss = avg_loss.iloc[-1]
    if last_avg_loss == 0:
        return 100.0
    rs = avg_gain.iloc[-1] / last_avg_loss
    return 100 - (100 / (1 + rs))


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

    sector = info.get("sector", "Unknown")
    sector_avg_pbr = get_sector_avg_pbr(sector)

    pbr = info.get("priceToBook")
    if not pbr or pbr <= 0:
        pbr = current_price / bps if bps > 0 else 1.0

    # 주봉 스토캐스틱 %K (14주 기준): 최근 14주 고가/저가 대비 현재 종가 위치
    weekly = ticker.history(period="2y", interval="1wk")
    stochastic_k = 50.0
    if not weekly.empty:
        recent = weekly.tail(14)
        lowest_low = recent["Low"].min()
        highest_high = recent["High"].max()
        last_close = weekly["Close"].iloc[-1]
        if highest_high > lowest_low:
            stochastic_k = 100 * (last_close - lowest_low) / (highest_high - lowest_low)

    # 연간 현금소진율: 영업현금흐름이 음수(적자)면 그 절대값을, 흑자 기업이면
    # 모델의 gt=0 제약을 만족시키기 위한 최소값(1.0)을 사용해 러너웨이가
    # 사실상 매우 길게(=재무 안전) 계산되도록 한다.
    operating_cashflow = info.get("operatingCashflow", 0)
    annual_burn_rate_m = abs(operating_cashflow) / 1e6 if operating_cashflow < 0 else 1.0

    # 200일 이동평균선 계산
    dma_200 = history["Close"].rolling(window=200).mean().iloc[-1]

    rsi = compute_rsi(history["Close"])

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
        pbr=pbr,
        sector=sector,
        sector_avg_pbr=sector_avg_pbr,
        stochastic_k=stochastic_k,
        rsi=rsi,
    )

    # 3. 퀀트 평가 실행
    return QuantFactorEngine.evaluate(input_data)


if __name__ == "__main__":
    report = fetch_and_evaluate("IONQ")
    print(report.model_dump_json(indent=2))
