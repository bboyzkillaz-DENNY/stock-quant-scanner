from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel, Field
import json
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("QuantEngine")


# ==========================================
# 1. Pydantic Data Schemas (Strict Typing)
# ==========================================

class RecommendationEnum(str, Enum):
    SCALE_IN_BUY = "SCALE-IN BUY"
    HOLD = "HOLD"
    SCALE_OUT_SELL = "SCALE-OUT SELL"


class MarketDataInput(BaseModel):
    ticker: str = Field(..., description="주식 티커")
    current_price: float = Field(..., gt=0, description="현재 주가 ($)")
    market_cap_m: float = Field(..., gt=0, description="시가총액 ($M)")
    fwd_revenue_m: float = Field(..., gt=0, description="향후 12개월 예상 매출 ($M)")
    total_cash_m: float = Field(..., ge=0, description="현금 및 단기투자자산 ($M)")
    total_debt_m: float = Field(..., ge=0, description="총부채 ($M)")
    annual_burn_rate_m: float = Field(..., gt=0, description="연간 순현금 소진율 ($M)")
    bps: float = Field(..., gt=0, description="주당순자산가치 (BPS, $)")
    short_float_pct: float = Field(..., ge=0, le=100, description="공매도 잔고 비율 (%)")
    days_to_cover: float = Field(..., ge=0, description="Days to Cover (DTC)")
    dma_200: float = Field(..., gt=0, description="200일 이동평균선 ($)")
    pbr: float = Field(..., gt=0, description="현재 PBR (주가/BPS)")
    sector: str = Field(..., description="GICS 섹터 (표시용)")
    sector_avg_pbr: float = Field(..., gt=0, description="동종업계 peer 종목들의 실시간 평균 PBR")
    stochastic_k: float = Field(..., ge=0, le=100, description="주봉 스토캐스틱 %K (14주 기준)")


class FactorScoreBreakdown(BaseModel):
    valuation_score: float = Field(..., ge=0, le=30)
    short_interest_score: float = Field(..., ge=0, le=25)
    technical_score: float = Field(..., ge=0, le=25)
    balance_sheet_score: float = Field(..., ge=0, le=20)
    total_score: float = Field(..., ge=0, le=100)


class PortfolioAllocation(BaseModel):
    max_portfolio_cap_percent: str = "5.0%"
    initial_entry_percent: str
    target_price_1st: str
    stop_loss_price: str


class QuantAnalysisReport(BaseModel):
    ticker: str
    current_price: str
    calculated_fwd_psr: float
    score_breakdown: FactorScoreBreakdown
    recommendation: RecommendationEnum
    portfolio_allocation: PortfolioAllocation
    executive_summary: str


# ==========================================
# 2. Deterministic Quant Engine
# ==========================================
# 섹터 평균 PBR(data.sector_avg_pbr)은 실시간 peer 조회로 계산되어 입력되며,
# 이 엔진 자체는 순수 계산만 수행한다 (네트워크 호출 없음 — data_fetcher.py 담당).


class QuantFactorEngine:
    """금융 수학 알고리즘 기반 정량 스코어링 엔진"""

    @staticmethod
    def evaluate(data: MarketDataInput) -> QuantAnalysisReport:
        logger.info(f"Evaluating ticker: {data.ticker}")

        # 1. 지표 산출
        fwd_psr = data.market_cap_m / data.fwd_revenue_m
        net_cash_m = data.total_cash_m - data.total_debt_m
        runway_years = net_cash_m / data.annual_burn_rate_m if data.annual_burn_rate_m > 0 else 0
        disparity_200dma = ((data.current_price - data.dma_200) / data.dma_200) * 100

        # Factor 1: Valuation Score (Max 30)
        if fwd_psr <= 30:
            val_score = 30.0
        elif fwd_psr <= 60:
            val_score = 30.0 - ((fwd_psr - 30) / 30) * 12.0  # 30~18점 선형 감점
        elif fwd_psr <= 100:
            val_score = 18.0 - ((fwd_psr - 60) / 40) * 10.0  # 18~8점 선형 감점
        else:
            val_score = 0.0

        # Factor 2: Short Interest Exhaustion (Max 25)
        if data.short_float_pct < 15.0 and data.days_to_cover < 3.0:
            short_score = 25.0
        elif data.short_float_pct <= 25.0:
            short_score = 15.0
        else:
            short_score = 5.0

        # Factor 3: Technical (Max 25) = 200일선 이격도(15) + 주봉 스토캐스틱(10)
        if disparity_200dma < -20.0:
            disparity_score = 15.0
        elif disparity_200dma <= 0.0:
            disparity_score = 9.0
        elif disparity_200dma <= 50.0:
            disparity_score = 3.0
        else:
            disparity_score = 0.0

        if data.stochastic_k < 20.0:
            stochastic_score = 10.0
        elif data.stochastic_k <= 50.0:
            stochastic_score = 6.0
        elif data.stochastic_k <= 80.0:
            stochastic_score = 3.0
        else:
            stochastic_score = 0.0

        tech_score = disparity_score + stochastic_score

        # Factor 4: Balance Sheet (Max 20) = 순현금/런웨이(12) + 섹터 대비 PBR(8)
        if net_cash_m >= 1000 and runway_years >= 3.0:
            cash_score = 12.0
        elif net_cash_m >= 500 and runway_years >= 2.0:
            cash_score = 7.0
        elif net_cash_m > 0:
            cash_score = 3.0
        else:
            cash_score = 0.0

        sector_avg_pbr = data.sector_avg_pbr
        pbr_ratio = data.pbr / sector_avg_pbr
        if pbr_ratio <= 0.7:
            pbr_score = 8.0
        elif pbr_ratio <= 1.0:
            pbr_score = 5.0
        elif pbr_ratio <= 1.3:
            pbr_score = 2.0
        else:
            pbr_score = 0.0

        bs_score = cash_score + pbr_score

        total_score = round(val_score + short_score + tech_score + bs_score, 2)

        # 2. Decision Matrix & Portfolio Risk Control
        if total_score >= 75.0 and fwd_psr <= 100.0:
            recommendation = RecommendationEnum.SCALE_IN_BUY
            initial_entry = "1.5% (Max 5.0% 대비 30% 분할 진입)"
            target_price = f"${round((data.fwd_revenue_m * 80) / (data.market_cap_m / data.current_price), 2)} (PSR 80x 환산)"
            stop_loss = f"${round(max(data.bps * 1.1, data.current_price * 0.75), 2)} (순현금/장부가선)"
            summary = (
                f"{data.ticker}는 FWD PSR {fwd_psr:.1f}배 수준으로 과열 구간을 벗어났으며, "
                f"순현금 ${net_cash_m:.0f}M 및 {runway_years:.1f}년의 캐시 런웨이를 확보하여 재무 리스크가 낮습니다. "
                f"PBR {data.pbr:.2f}배는 {data.sector} 섹터 평균({sector_avg_pbr:.1f}배) 대비 "
                f"{'저평가' if pbr_ratio <= 1.0 else '고평가'} 구간이고, 주봉 스토캐스틱 %K {data.stochastic_k:.1f}는 "
                f"{'바닥권' if data.stochastic_k < 20 else '중립~과열' if data.stochastic_k <= 80 else '과열권'}입니다. "
                f"공매도 비율({data.short_float_pct:.2f}%) 하향 안정화로 하방 경직성이 확보되어 분할 매수를 추천합니다."
            )
        elif total_score >= 50.0 and fwd_psr <= 100.0:
            recommendation = RecommendationEnum.HOLD
            initial_entry = "0.0% (관망)"
            target_price = "N/A"
            stop_loss = f"${round(data.current_price * 0.85, 2)}"
            summary = (
                f"{data.ticker}는 밸류에이션 점수가 중간 수준(Total {total_score}점)으로 주요 지지선 형성 여부를 추가 관망해야 합니다. "
                f"PBR {data.pbr:.2f}배({data.sector} 평균 {sector_avg_pbr:.1f}배 대비 {pbr_ratio:.2f}배율), "
                f"주봉 스토캐스틱 %K {data.stochastic_k:.1f} 기준입니다."
            )
        else:
            recommendation = RecommendationEnum.SCALE_OUT_SELL
            initial_entry = "0.0% (매도/비중 축소)"
            target_price = "N/A"
            stop_loss = "N/A"
            summary = (
                f"{data.ticker}는 PSR 과열 및 기술적 이격도 부담으로 리스크 관리 차원의 비중 축소가 필요합니다. "
                f"PBR {data.pbr:.2f}배({data.sector} 평균 대비 {pbr_ratio:.2f}배율), "
                f"주봉 스토캐스틱 %K {data.stochastic_k:.1f}."
            )

        scores = FactorScoreBreakdown(
            valuation_score=round(val_score, 2),
            short_interest_score=round(short_score, 2),
            technical_score=round(tech_score, 2),
            balance_sheet_score=round(bs_score, 2),
            total_score=total_score,
        )

        allocation = PortfolioAllocation(
            max_portfolio_cap_percent="5.0%",
            initial_entry_percent=initial_entry,
            target_price_1st=target_price,
            stop_loss_price=stop_loss,
        )

        return QuantAnalysisReport(
            ticker=data.ticker,
            current_price=f"${data.current_price:.2f}",
            calculated_fwd_psr=round(fwd_psr, 2),
            score_breakdown=scores,
            recommendation=recommendation,
            portfolio_allocation=allocation,
            executive_summary=summary,
        )


# ==========================================
# 3. Execution Pipeline Driver Example
# ==========================================

if __name__ == "__main__":
    # 아이온큐(IONQ) 실전 데이터 입력 예시 [확실]
    ionq_input = MarketDataInput(
        ticker="IONQ",
        current_price=35.77,
        market_cap_m=13350.0,
        fwd_revenue_m=270.0,
        total_cash_m=2030.0,
        total_debt_m=30.4,
        annual_burn_rate_m=220.0,
        bps=15.48,
        short_float_pct=12.7,
        days_to_cover=2.87,
        dma_200=42.50,
        pbr=35.77 / 15.48,
        sector="Technology",
        sector_avg_pbr=8.0,
        stochastic_k=35.0,
    )

    # 파이프라인 실행
    report = QuantFactorEngine.evaluate(ionq_input)

    # 상용 API 응답용 JSON 출력
    print(json.dumps(report.model_dump(), indent=2, ensure_ascii=False))
