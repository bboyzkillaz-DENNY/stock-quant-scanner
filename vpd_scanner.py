"""거래량-가격 괴리(Volume-Price Divergence) 매집 탐지 스크리너.

조건: 최근 거래일 거래량이 직전 20거래일 평균의 3배 이상 AND 당일 등락률이 ±3% 이내.
종목을 예측하지 않고 '거래량은 터졌는데 가격은 안 움직인' 종목만 걸러낸다.

유니버스: vpd_universe.txt(한 줄에 티커 1개)가 있으면 그것, 없으면 watchlist_scanner.WATCHLIST.
텔레그램 환경변수(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)가 없으면 콘솔에만 출력한다.
"""
import os
import sys

import requests
import yfinance as yf

VOL_MULT = float(os.environ.get("VPD_VOL_MULT", 3.0))
MAX_MOVE_PCT = float(os.environ.get("VPD_MAX_MOVE_PCT", 3.0))
LOOKBACK = 20


def load_universe() -> list[str]:
    if os.path.exists("vpd_universe.txt"):
        with open("vpd_universe.txt") as f:
            return [t.strip().upper() for t in f if t.strip() and not t.startswith("#")]
    from watchlist_scanner import WATCHLIST
    return list(WATCHLIST)


def scan(tickers: list[str]) -> tuple[list[dict], list[str]]:
    data = yf.download(tickers, period="3mo", group_by="ticker", auto_adjust=False,
                       progress=False, threads=True)
    hits, errors = [], []
    for t in tickers:
        try:
            df = data[t].dropna(subset=["Close", "Volume"]) if len(tickers) > 1 else data.dropna(subset=["Close", "Volume"])
            if len(df) < LOOKBACK + 2:
                raise ValueError("데이터 부족")
            last, prev = df.iloc[-1], df.iloc[-2]
            avg_vol = df["Volume"].iloc[-LOOKBACK - 1:-1].mean()
            ratio = last["Volume"] / avg_vol if avg_vol else 0
            move = (last["Close"] / prev["Close"] - 1) * 100
            if ratio >= VOL_MULT and abs(move) <= MAX_MOVE_PCT:
                hits.append({"ticker": t, "ratio": ratio, "move": move,
                             "close": last["Close"], "date": df.index[-1].date()})
        except Exception as e:
            errors.append(f"{t}: {e}")
    return sorted(hits, key=lambda h: -h["ratio"]), errors


def format_message(hits: list[dict], total: int) -> str:
    if not hits:
        return f"[VPD 스캔] {total}개 중 조건 충족 종목 없음 (거래량 {VOL_MULT:g}배↑ & 등락 ±{MAX_MOVE_PCT:g}%)"
    lines = [f"[VPD 스캔] 거래량 {VOL_MULT:g}배↑ & 등락 ±{MAX_MOVE_PCT:g}% : {len(hits)}/{total}개"]
    for h in hits:
        lines.append(f"{h['ticker']} 거래량 {h['ratio']:.1f}배 | 등락 {h['move']:+.1f}% | 종가 {h['close']:.2f} ({h['date']})")
    lines.append("※ 매집 '가능성' 신호일 뿐, 매수 추천이 아닙니다.")
    return "\n".join(lines)


def send_telegram(text: str) -> None:
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    resp = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": chat_id, "text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"텔레그램 전송 실패: {resp.status_code} {resp.text}", file=sys.stderr)


def main() -> None:
    tickers = load_universe()
    hits, errors = scan(tickers)
    if len(errors) == len(tickers):
        msg = f"⚠️ VPD 스캔 실패: {len(tickers)}개 전부 데이터 조회 실패 (데이터 소스 확인 필요)"
        print(msg, file=sys.stderr)
        send_telegram(msg)
        sys.exit(1)
    msg = format_message(hits, len(tickers) - len(errors))
    print(msg)
    send_telegram(msg)
    if errors:
        print("[ERRORS]", errors, file=sys.stderr)
        send_telegram("⚠️ VPD 데이터 조회 실패\n" + "\n".join(errors[:10]))


if __name__ == "__main__":
    main()
