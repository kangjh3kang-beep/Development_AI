"""심의분석 콘솔 UI — 정적 단일 페이지(엔진 자체 서빙). GET / → 입력 폼 + 결과 렌더.

self-contained 풀스택: 같은 FastAPI가 백엔드(/api/v1/analyze)와 프런트(/)를 함께 제공.
"""
from __future__ import annotations

import pathlib

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_INDEX = pathlib.Path(__file__).resolve().parents[2] / "ui" / "index.html"


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX.read_text(encoding="utf-8")
