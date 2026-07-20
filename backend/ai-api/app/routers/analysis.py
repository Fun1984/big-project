import json
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/analysis", tags=["analysis"])

_CONTRACT = Path(__file__).parents[4] / "contracts" / "ai_analysis_mock.json"
SAMPLE = json.loads(_CONTRACT.read_text(encoding="utf-8"))


@router.get("/{consultation_id}")
def get_analysis(consultation_id: str):
    return {**SAMPLE, "consultation_id": consultation_id}


@router.post("")
def create_analysis(payload: dict):
    # TODO: services/analysis_service.py 의 실제 파이프라인으로 교체
    return SAMPLE