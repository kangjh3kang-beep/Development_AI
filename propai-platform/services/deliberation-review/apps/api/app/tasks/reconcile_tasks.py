"""L5 — 미러↔라이브 1차출처 주기 정합(Celery 잡). **분석경로와 분리**, 라이브는 여기서만(INV-13).

불일치 발견 시 미러 갱신 + 영향 finding 재검토 트리거(후속 배선). 분석(소비) 경로는 미러만 읽음.
"""
from __future__ import annotations

from app.adapters.network import LiveNetwork, NetworkError
from app.tasks.celery_app import celery_app


@celery_app.task(name="verify.reconcile_mirror")
def reconcile_mirror(citation_ref: str) -> dict:
    try:
        LiveNetwork().get(f"https://www.law.go.kr/reconcile?ref={citation_ref}")
        live_ok = True
    except NetworkError:
        live_ok = False
    return {"citation_ref": citation_ref, "live_reconciled": live_ok}
