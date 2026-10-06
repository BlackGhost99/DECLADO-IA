import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.hs_classifier.model import load_model, predict_topk, top_keywords_for_label
from app.hs_classifier.preprocess import prepare_corpus

router = APIRouter()


class HSSuggestRequest(BaseModel):
    text: str
    k: int | None = 3


class HSSuggestion(BaseModel):
    code: str
    score: float
    keywords: list[str]


class HSSuggestResponse(BaseModel):
    suggestions: list[HSSuggestion]


MODEL_FILE = os.path.join(os.path.dirname(__file__), "../../models/hs_classifier.joblib")


@router.post("/hs/suggest", response_model=HSSuggestResponse)
def suggest(payload: HSSuggestRequest):
    if not payload.text:
        raise HTTPException(status_code=400, detail="text is required")

    # load model lazily
    try:
        model = load_model(MODEL_FILE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model load error: {e}") from e

    text_clean = prepare_corpus([payload.text])[0]
    topk = predict_topk(model, [text_clean], k=payload.k)[0]
    suggestions = []
    for code, score in topk:
        keywords = top_keywords_for_label(model, code, top_n=5)
        suggestions.append({"code": code, "score": score, "keywords": keywords})

    return {"suggestions": suggestions}
