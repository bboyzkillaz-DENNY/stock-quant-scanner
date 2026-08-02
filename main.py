from fastapi import FastAPI

from quant_engine import MarketDataInput, QuantAnalysisReport, QuantFactorEngine

app = FastAPI(title="Quant Factor Engine")


@app.post("/api/v1/quant-evaluate", response_model=QuantAnalysisReport)
def quant_evaluate(data: MarketDataInput) -> QuantAnalysisReport:
    return QuantFactorEngine.evaluate(data)
