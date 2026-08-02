from quant_engine import RecommendationEnum
from data_fetcher import fetch_and_evaluate

WATCHLIST = [
    "IONQ", "RXRX", "INOD", "TWST", "MU", "MRVL", "RKLB", "GLW", "CRDO",
    "OKLO", "SMR", "JOBY", "ACHR", "HOOD", "CCJ", "TEM", "CRWD",
    "TSLA", "NVDA", "META", "AMZN",
]


def format_alert(report) -> str:
    alloc = report.portfolio_allocation
    return (
        f"[QUANT SIGNAL ALERT: {report.ticker}]\n\n"
        f"* 신호: `{report.recommendation.value}` (매집 진입 승인)\n"
        f"* 종합 점수: `{report.score_breakdown.total_score} / 100점`\n"
        f"* 추천 비중: {alloc.initial_entry_percent}\n"
        f"* 진입가: {report.current_price} 부근 | 목표가: {alloc.target_price_1st} | 손절가: {alloc.stop_loss_price}\n"
        f"* 사유: {report.executive_summary}"
    )


def format_kakao_alert(report) -> str:
    """카카오톡 '나에게 보내기' 200자 제한에 맞춘 축약 포맷."""
    alloc = report.portfolio_allocation
    return (
        f"[퀀트 알림] {report.ticker}\n"
        f"신호: {report.recommendation.value} ({report.score_breakdown.total_score}점)\n"
        f"현재가 {report.current_price} | PSR {report.calculated_fwd_psr}배\n"
        f"목표가 {alloc.target_price_1st.split(' ')[0]} | 손절가 {alloc.stop_loss_price.split(' ')[0]}"
    )[:200]


def scan_watchlist(tickers=WATCHLIST):
    """관심 종목을 평가해 (매수신호 알림 목록, 관망 목록, 오류 목록)을 반환한다."""
    alerts, watch, errors = [], [], []
    for tk in tickers:
        try:
            report = fetch_and_evaluate(tk)
        except Exception as e:
            errors.append((tk, str(e)))
            continue

        if report.recommendation == RecommendationEnum.SCALE_IN_BUY:
            alerts.append(format_alert(report))
        else:
            watch.append((tk, report.recommendation.value, report.score_breakdown.total_score))

    return alerts, watch, errors


if __name__ == "__main__":
    alerts, watch, errors = scan_watchlist()

    for alert in alerts:
        print(alert)
        print("-" * 60)

    if watch:
        print("[HOLD/WATCHLIST]", watch)
    if errors:
        print("[ERRORS]", errors)
