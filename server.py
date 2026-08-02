# server.py
from fastapi import FastAPI, HTTPException
from quant_engine import MarketDataInput, QuantFactorEngine, QuantAnalysisReport

app = FastAPI(title="Non-Profitable Growth Stock Quant Engine", version="1.0.0")

@app.post("/api/v1/evaluate", response_model=QuantAnalysisReport)
def evaluate_stock(data: MarketDataInput):
    try:
        report = QuantFactorEngine.evaluate(data)
        return report
    except Exception as e:
        # pydantic이 요청 단계에서 이미 입력을 검증하므로, 여기 도달하는 예외는
        # 클라이언트 오류(400)가 아니라 예상 못한 서버 내부 오류(500)다.
        raise HTTPException(status_code=500, detail=str(e))

# 서버 실행 명령: uvicorn server:app --reload --port 8000
