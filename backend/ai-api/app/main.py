from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import analysis

from pydantic import BaseModel
from app.agents.case_analysis.graph import run_case_analysis
from app.agents.case_analysis.multimodal import get_whisper_model
from app.agents.rescue_check.graph import eligibility_graph
from app.agents.rescue_check.modal import EligibilityCheckRequest, EligibilityCheckResponse
from app.agents.missing_check.graph import missing_data_graph
from app.agents.missing_check.modal import MissingDataCheckRequest, MissingDataCheckResponse

app = FastAPI(title="AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite 개발 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)


@app.get("/health")
def health():
    return {"status": "ok"}



@app.on_event("startup")
def preload_models():
    """Whisper 모델을 서버 시작 시점에 미리 로드해서,
    첫 요청에서 모델 로딩 때문에 지연되는 것을 방지."""
    get_whisper_model()

class ConsultRequest(BaseModel):
    content: dict

@app.post("/case-analysis")
def analyze(req: ConsultRequest):
    # HITL 원칙: 이 응답은 항상 "검토 대기" 상태로 프론트/DB에 저장되어야 하며,
    # 상담원/변호사/공익법무관의 최종 확정 액션을 거쳐야 함.
    result = run_case_analysis({"content": req.content})
    # return result["case_analysis"]
    return result

#
@app.post("/eligibility/analyze", response_model=EligibilityCheckResponse)
async def analyze_eligibility(payload: EligibilityCheckRequest) -> EligibilityCheckResponse:
    initial_state = payload.to_consult_fields()
    result_state = await eligibility_graph.ainvoke(initial_state)
    return EligibilityCheckResponse(relief_review_checklist=result_state["relief_review_checklist"])

@app.post("/missing-data/analyze", response_model=MissingDataCheckResponse)
async def analyze_missing_data(payload: MissingDataCheckRequest) -> MissingDataCheckResponse:
    initial_state = payload.to_consult_fields()
    result_state = await missing_data_graph.ainvoke(initial_state)
    return MissingDataCheckResponse(missing_items=result_state["missing_items"])