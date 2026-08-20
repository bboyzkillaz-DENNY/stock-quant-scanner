# stock-quant-scanner

적자 성장주(IONQ, RKLB 등) 중심의 정량 스코어링 엔진. 매일 평일 자동으로 워치리스트를 평가해서 매수/매도 신호가 뜬 종목만 텔레그램으로 보내준다.

- 스코어링 로직: [`quant_engine.py`](quant_engine.py)
- 실시간 데이터 수집: [`data_fetcher.py`](data_fetcher.py) (yfinance, 실패 시 FMP 폴백)
- 워치리스트/신호 필터: [`watchlist_scanner.py`](watchlist_scanner.py)
- 매일 실행되는 알림 스크립트: [`daily_scan_notify.py`](daily_scan_notify.py)
- 자동 스케줄: [`.github/workflows/daily_scan.yml`](.github/workflows/daily_scan.yml)

## A. 알림 확인하기 (컴퓨터 필요 없음)

매일 평일 20:30 UTC(서머타임 기준 한국시간 새벽 5:30경)에 자동으로 텔레그램으로 알림이 옵니다. **어떤 컴퓨터도 켜져 있을 필요 없습니다** — GitHub 클라우드에서 알아서 돌아갑니다. 그냥 텔레그램 앱만 확인하면 됩니다.

## B. 실행 기록/로그 보기 (브라우저만 있으면 어디서든)

https://github.com/bboyzkillaz-DENNY/stock-quant-scanner/actions

여기서 매일 실행이 성공했는지, 어떤 종목이 몇 개 처리됐는지 로그로 직접 볼 수 있습니다. 로그인 없이도 볼 수 있습니다(저장소가 public).

## C. 지금 바로 수동으로 한 번 돌려보기

1. 위 Actions 페이지 접속 (GitHub 로그인 필요)
2. 왼쪽에서 "Daily Stock Quant Scan" 클릭
3. 오른쪽 "Run workflow" 버튼 클릭 → 다시 "Run workflow" 확인
4. 1~2분 후 텔레그램 확인

컴퓨터/터미널 없이 브라우저에서 클릭만으로 됩니다.

## D. 워치리스트(종목) 바꾸기

가장 쉬운 방법은 아무 컴퓨터에서나 GitHub 웹으로 직접 수정하는 것입니다.

1. https://github.com/bboyzkillaz-DENNY/stock-quant-scanner/blob/main/watchlist_scanner.py 접속
2. 연필 아이콘(Edit) 클릭
3. `WATCHLIST = [...]` 목록 수정
4. 하단에서 "Commit changes" (바로 main에 커밋)

다음 실행부터 자동 반영됩니다. (또는 이 대화에서처럼 저에게 종목 리스트를 알려주셔도 됩니다.)

## E. 새 컴퓨터에서 코드 개발/로컬 실행하려면

```bash
git clone https://github.com/bboyzkillaz-DENNY/stock-quant-scanner.git
cd stock-quant-scanner
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python watchlist_scanner.py   # 콘솔에 결과만 출력, 텔레그램 전송 안 함
```

텔레그램까지 실제로 보내보려면:
```bash
TELEGRAM_BOT_TOKEN=<봇토큰> TELEGRAM_CHAT_ID=<챗ID> ./venv/bin/python daily_scan_notify.py
```

## F. 크리덴셜/시크릿

텔레그램 봇 토큰, Chat ID, FMP API 키는 이미 **GitHub 저장소의 Settings → Secrets and variables → Actions**에 등록되어 있어서, 자동 실행 시엔 아무것도 새로 입력할 필요가 없습니다. 로컬에서 직접 돌릴 때만 위 E처럼 환경변수로 넣어주면 됩니다.

- 시크릿 확인/변경: https://github.com/bboyzkillaz-DENNY/stock-quant-scanner/settings/secrets/actions (본인 GitHub 계정 로그인 필요)

## G. 스케줄(시간) 바꾸기

[`.github/workflows/daily_scan.yml`](.github/workflows/daily_scan.yml)의 `cron: "30 20 * * 1-5"` 부분을 수정합니다. **UTC 기준**이며, 미국 서머타임(EDT)이 끝나는 11월경엔 1시간 조정이 필요합니다 (지금은 UTC 20:30 = 미국 동부 16:30, 서머타임 종료 후엔 UTC 21:30으로 바꿔야 같은 시각이 유지됩니다).

## H. 문제가 생겼을 때

1. 먼저 B의 Actions 로그를 확인 — 어느 단계에서 실패했는지 바로 보입니다.
2. 특정 종목만 계속 실패하면(Yahoo Finance 데이터 문제) 워치리스트에서 빼거나(D), 그대로 둬도 나머지 종목은 정상 처리되고 실패 종목만 텔레그램 오류 요약으로 옵니다.
3. 그래도 안 풀리면 이 저장소 링크와 함께 다시 물어보시면 됩니다.

## 알아두면 좋은 점

- 이 모델은 원래 **적자 성장주** 전용으로 설계됐습니다. NVDA/META/AMZN/TSLA처럼 이미 흑자인 초대형주는 PSR·목표가 계산이 실제 상황과 안 맞을 수 있어 참고용으로만 보세요.
- 섹터 평균 PBR은 섹터별 대표 종목 5개의 실시간 평균이며, 매 실행마다 다시 계산됩니다(고정값 아님).
