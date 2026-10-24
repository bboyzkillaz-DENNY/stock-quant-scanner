import html
import os
import sys
import time

import requests

from quant_engine import RecommendationEnum
from data_fetcher import fetch_and_evaluate
from watchlist_scanner import WATCHLIST

# PSR이 이 값보다 낮으면 "고성장 적자 성장주"용으로 설계된 이 모델의 대상이 아닐
# 가능성이 높음 (이미 흑자·정상 배수인 성숙 기업) → 목표가 신뢰도 낮음을 함께 표기.
LOW_PSR_CAVEAT_THRESHOLD = 20


def format_telegram_alert(report) -> str:
    # parse_mode=HTML: 종목명·요약·에러 문구의 _ * [ 같은 문자가 서식으로 해석되지 않도록 전부 이스케이프
    e = html.escape
    alloc = report.portfolio_allocation
    caveat = ""
    if report.calculated_fwd_psr < LOW_PSR_CAVEAT_THRESHOLD:
        caveat = "\n<i>(주: 저PSR 성숙 기업 — 목표가는 참고용이며 부정확할 수 있음)</i>"

    return (
        f"🚨 <b>[QUANT SIGNAL: {e(report.ticker)}]</b>\n"
        f"신호: <b>{e(report.recommendation.value)}</b> ({report.score_breakdown.total_score}점)\n"
        f"현재가 {e(str(report.current_price))} | FWD PSR {report.calculated_fwd_psr}배\n"
        f"목표가 {e(str(alloc.target_price_1st))} | 손절가 {e(str(alloc.stop_loss_price))}\n"
        f"{e(report.executive_summary)}"
        f"{caveat}"
    )


def format_error_summary(errors: list[str]) -> str:
    body = "\n".join(html.escape(err) for err in errors)
    return f"⚠️ <b>데이터 조회 실패</b>\n{body}"[:TELEGRAM_MAX_LEN]


TELEGRAM_TIMEOUT = 15
TELEGRAM_MAX_LEN = 4000  # 텔레그램 메시지 한도 4096자
TELEGRAM_MAX_ATTEMPTS = 4  # 최초 1회 + 재시도 3회 (대기 2s, 4s, 8s)


def send_telegram(token: str, chat_id: str, text: str) -> bool:
    """타임아웃·연결 오류·429·5xx는 지수 백오프로 재시도. 성공 여부를 반환."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}

    for attempt in range(1, TELEGRAM_MAX_ATTEMPTS + 1):
        delay = 2 ** attempt
        try:
            resp = requests.post(url, json=payload, timeout=TELEGRAM_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError) as e:
            print(f"텔레그램 통신 에러 ({attempt}/{TELEGRAM_MAX_ATTEMPTS}): {e}", file=sys.stderr)
        else:
            if resp.status_code == 200:
                return True
            print(f"텔레그램 전송 실패 ({attempt}/{TELEGRAM_MAX_ATTEMPTS}): {resp.status_code} {resp.text}", file=sys.stderr)
            if resp.status_code == 429:
                try:
                    delay = max(delay, int(resp.json()["parameters"]["retry_after"]))
                except (ValueError, KeyError, TypeError):
                    pass
            elif resp.status_code == 400 and "parse_mode" in payload and "parse entities" in resp.text:
                # 서식 해석 실패 → 서식 없이 원문 그대로 한 번 더 보낸다 (알림 유실 방지)
                payload.pop("parse_mode")
                continue
            elif resp.status_code < 500:
                return False  # 400/401/403 등은 재시도해도 같은 결과

        if attempt < TELEGRAM_MAX_ATTEMPTS:
            time.sleep(delay)
    return False


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    errors = []
    for ticker in WATCHLIST:
        try:
            report = fetch_and_evaluate(ticker)
        except Exception as e:
            print(f"{ticker} 조회 실패: {e}", file=sys.stderr)
            errors.append(f"{ticker}: {e}")
            continue
        finally:
            time.sleep(1)  # Yahoo Finance 레이트리밋 완화

        if report.recommendation in (RecommendationEnum.SCALE_IN_BUY, RecommendationEnum.SCALE_OUT_SELL):
            send_telegram(token, chat_id, format_telegram_alert(report))

    if errors:
        send_telegram(token, chat_id, format_error_summary(errors))


if __name__ == "__main__":
    main()
