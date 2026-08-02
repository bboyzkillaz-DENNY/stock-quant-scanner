import os
import sys

import requests

from quant_engine import RecommendationEnum
from data_fetcher import fetch_and_evaluate
from watchlist_scanner import WATCHLIST

# PSR이 이 값보다 낮으면 "고성장 적자 성장주"용으로 설계된 이 모델의 대상이 아닐
# 가능성이 높음 (이미 흑자·정상 배수인 성숙 기업) → 목표가 신뢰도 낮음을 함께 표기.
LOW_PSR_CAVEAT_THRESHOLD = 20


def format_telegram_alert(report) -> str:
    alloc = report.portfolio_allocation
    caveat = ""
    if report.calculated_fwd_psr < LOW_PSR_CAVEAT_THRESHOLD:
        caveat = "\n_(주: 저PSR 성숙 기업 — 목표가는 참고용이며 부정확할 수 있음)_"

    return (
        f"🚨 *[QUANT SIGNAL: {report.ticker}]*\n"
        f"신호: *{report.recommendation.value}* ({report.score_breakdown.total_score}점)\n"
        f"현재가 {report.current_price} | FWD PSR {report.calculated_fwd_psr}배\n"
        f"목표가 {alloc.target_price_1st} | 손절가 {alloc.stop_loss_price}\n"
        f"{report.executive_summary}"
        f"{caveat}"
    )


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"텔레그램 전송 실패: {resp.status_code} {resp.text}", file=sys.stderr)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    errors = []
    for ticker in WATCHLIST:
        try:
            report = fetch_and_evaluate(ticker)
        except Exception as e:
            errors.append(f"{ticker}: {e}")
            continue

        if report.recommendation in (RecommendationEnum.SCALE_IN_BUY, RecommendationEnum.SCALE_OUT_SELL):
            send_telegram(token, chat_id, format_telegram_alert(report))

    if errors:
        send_telegram(token, chat_id, "⚠️ *데이터 조회 실패*\n" + "\n".join(errors))


if __name__ == "__main__":
    main()
