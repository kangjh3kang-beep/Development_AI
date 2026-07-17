"""등기 권리분석 잡 — 소유권 스코프·병합 semantics 회귀 앵커(R1).

무엇을 고정하나:
1. 완료 잡을 **소유자**가 폴링하면 200 + result (과거 결함: `_run_registry_job` 이 엔트리를
   통째 replace 해 user_id 가 탈락 → 소유자 폴링이 404. 병합 semantics 로 교정됨 —
   `_set_registry_job` 을 replace 로 되돌리면 이 테스트가 실패한다.)
2. **타인**이 같은 job_id 를 폴링하면 404 (IDOR fail-closed — 존재 여부 비노출).

DB·외부 비의존: 잡 상태만 스토어에 직접 굴리고(GET 경로 실검증), 분석 실행은 발화하지 않는다.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt_handler import CurrentUser, get_current_user
from apps.api.routers import registry as reg_module
from apps.api.routers.registry import router

OWNER_ID = uuid.uuid4()
OTHER_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _client(user_id) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=user_id, tenant_id=TENANT_ID, role="user",
    )
    return TestClient(app)


@pytest.mark.asyncio
async def test_owner_polls_done_job_200_other_user_404():
    job_id = uuid.uuid4().hex
    # 제출 시점 상태(소유권 기록) 재현 — 제출 엔드포인트와 동일 shape.
    import time as _t

    reg_module._JOBS[job_id] = {
        "status": "pending", "ts": _t.time(), "user_id": str(OWNER_ID),
    }
    # 완료 전이는 실제 코드 경로(_set_registry_job — 병합 semantics)로 수행.
    await reg_module._set_registry_job(job_id, status="done", result={"ok": True, "v": 1})

    # ★병합 semantics 앵커: 전이 후에도 user_id 가 보존돼야 한다(replace 회귀 시 여기서 탈락).
    assert reg_module._JOBS[job_id].get("user_id") == str(OWNER_ID)

    owner = _client(OWNER_ID)
    r = owner.get(f"/api/v1/registry/analyze/jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done" and body["result"] == {"ok": True, "v": 1}

    other = _client(OTHER_ID)
    r2 = other.get(f"/api/v1/registry/analyze/jobs/{job_id}")
    assert r2.status_code == 404  # IDOR fail-closed(존재 비노출)

    # 정리(전역 dict 오염 방지 — 타 테스트 격리).
    reg_module._JOBS.pop(job_id, None)
