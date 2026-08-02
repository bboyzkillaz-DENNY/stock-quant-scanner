import os
import json
import logging
import httpx
from fastapi import FastAPI, BackgroundTasks
from quant_engine import MarketDataInput, QuantFactorEngine, RecommendationEnum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("QuantMessengerApp")


# ==========================================
# 메신저 알림 모듈
# ==========================================

class TelegramNotifier:
    """텔레그램 봇 API 알림 모듈"""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    async def send_alert(self, message: str):
        if not self.bot_token or not self.chat_id:
            logger.warning("텔레그램 토큰 또는 Chat ID가 설정되지 않았습니다.")
            return

        payload = {"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(self.api_url, json=payload, timeout=5.0)
                if res.status_code == 200:
                    logger.info("텔레그램 알림 전송 성공")
                else:
                    logger.error(f"텔레그램 전송 실패: {res.text}")
            except Exception as e:
                logger.error(f"텔레그램 통신 에러: {e}")


class KakaoNotifier:
    """카카오톡 '나에게 보내기' REST API 모듈"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.api_url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

    async def send_alert(self, message: str):
        if not self.access_token:
            logger.warning("카카오톡 Access Token이 설정되지 않았습니다.")
            return

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        template_object = {
            "object_type": "text",
            "text": message,
            "link": {
                "web_url": "https://finance.yahoo.com",
                "mobile_web_url": "https://finance.yahoo.com",
            },
            "button_title": "증권사 앱 열기",
        }
        data = {"template_object": json.dumps(template_object)}

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(self.api_url, headers=headers, data=data, timeout=5.0)
                if res.status_code == 200:
                    logger.info("카카오톡 알림 전송 성공")
                else:
                    logger.error(f"카카오톡 전송 실패: {res.text}")
            except Exception as e:
                logger.error(f"카카오톡 통신 에러: {e}")


# ==========================================
# FastAPI 애플리케이션
# ==========================================

app = FastAPI(title="Quant Engine with Messenger Alerts")

# 미설정 시 확실히 falsy가 되도록 빈 문자열을 기본값으로 사용 (플레이스홀더 텍스트 금지)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
KAKAO_ACCESS_TOKEN = os.getenv("KAKAO_ACCESS_TOKEN", "")

telegram_notifier = TelegramNotifier(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
kakao_notifier = KakaoNotifier(KAKAO_ACCESS_TOKEN)


def format_alert_message(report) -> str:
    alloc = report.portfolio_allocation
    return (
        f"🚨 [QUANT SIGNAL ALERT: {report.ticker}]\n\n"
        f"• 최종 신호: *{report.recommendation.value}*\n"
        f"• 종합 스코어: *{report.score_breakdown.total_score:.1f} / 100점*\n"
        f"• 현재가: {report.current_price}\n"
        f"• FWD PSR: {report.calculated_fwd_psr:.1f}배\n"
        f"• 목표가: {alloc.target_price_1st} | 손절가: {alloc.stop_loss_price}\n\n"
        f"💡 {report.executive_summary}"
    )


@app.post("/api/v1/evaluate")
async def evaluate_stock(data: MarketDataInput, background_tasks: BackgroundTasks):
    # quant_engine.py의 검증된 엔진을 그대로 재사용 (스코어링 로직 중복 금지)
    report = QuantFactorEngine.evaluate(data)

    alert_triggered = report.recommendation in (
        RecommendationEnum.SCALE_IN_BUY,
        RecommendationEnum.SCALE_OUT_SELL,
    )
    if alert_triggered:
        alert_msg = format_alert_message(report)
        # 알림 전송 때문에 API 응답이 지연되지 않도록 백그라운드로 비동기 처리
        background_tasks.add_task(telegram_notifier.send_alert, alert_msg)
        background_tasks.add_task(kakao_notifier.send_alert, alert_msg)

    return {
        "ticker": report.ticker,
        "total_score": report.score_breakdown.total_score,
        "recommendation": report.recommendation.value,
        "alert_triggered": alert_triggered,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
