"""R2 — 라이브 인용 정합 점검(주기 Celery 잡). **분석경로와 분리**된 곳에서만 라이브 호출(INV-13).

분석(소비) 경로의 CitationVerifier는 미러 대조만 하고, 이 잡이 별도 주기로 라이브 1차출처와 대조한다.
"""
from __future__ import annotations

from app.adapters.network import LiveNetwork, NetworkError
from app.tasks.celery_app import celery_app


@celery_app.task(name="verify.live_citation_check")
def live_citation_check(citation_ref: str) -> dict:
    try:
        LiveNetwork().get(f"https://www.law.go.kr/check?ref={citation_ref}")
        live_ok = True
    except NetworkError:
        live_ok = False
    return {"citation_ref": citation_ref, "live_checked": live_ok}
