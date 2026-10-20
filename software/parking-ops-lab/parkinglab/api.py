"""Local application, authoritative server-side experiment records."""
from collections import OrderedDict
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .domain import ExperimentRequest, parse_csv, sample_reservations, to_csv
from .simulation import run_experiment, deterministic_report
from . import ollama

app = FastAPI(title="ParkingOps Lab", version="0.1.0")
static = Path(__file__).parent / "static"
runs = OrderedDict()
lock = Lock()


@app.middleware("http")
async def local_security(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin != str(request.base_url).rstrip("/"):
        return Response("Only same-origin requests are accepted", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'"
    if request.url.path in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; frame-ancestors 'none'"
    return response


@app.get("/api/health")
def health():
    import scipy
    return {"status":"ok", "solver":"SciPy / HiGHS", "scipy":scipy.__version__}


@app.get("/api/sample")
def sample(count: int = Query(48, ge=1, le=300), seed: int = Query(20261020, ge=0, le=2**32-1)):
    return {"reservations":[r.model_dump() for r in sample_reservations(count, seed)]}


@app.get("/api/sample.csv")
def sample_csv():
    return Response(to_csv(sample_reservations()), media_type="text/csv", headers={"Content-Disposition":"attachment; filename=reservations.csv"})


class CsvInput(BaseModel):
    csv_text: str = Field(max_length=1_000_000)


@app.post("/api/import")
def import_csv(body: CsvInput):
    try:
        return {"reservations":[r.model_dump() for r in parse_csv(body.csv_text)]}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.post("/api/solve")
def solve(body: ExperimentRequest):
    result = run_experiment(body)
    run_id = str(uuid4())
    with lock:
        runs[run_id] = result
        while len(runs) > 20:
            runs.popitem(last=False)
    return {"run_id":run_id, **result}


class ReportInput(BaseModel):
    run_id: str = Field(max_length=40)
    use_ollama: bool = False
    model: str = Field(default="", max_length=100, pattern=r"^[A-Za-z0-9_.:/-]*$")


@app.post("/api/report")
def report(body: ReportInput):
    with lock:
        result = runs.get(body.run_id)
    if result is None:
        raise HTTPException(404, "实验记录不存在或已过期，请重新运行")
    text = deterministic_report(result)
    if body.use_ollama:
        if not body.model:
            raise HTTPException(422, "请选择本地已有模型")
        try:
            return {"report":text, "interpretation":ollama.explain(result, body.model)}
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(503, "本地模型暂时无法响应，计算结果与标准报告仍可使用") from error
    return {"report":text}


@app.get("/api/models")
def get_models():
    return ollama.models()


@app.get("/")
def index():
    return FileResponse(static / "index.html")


app.mount("/static", StaticFiles(directory=static), name="static")
