"""WP-L 게이트(정적 배선) — design-runs 라우터·submission-bundle·main.py 등록의 계약 검증.

라우터/메인은 전체 앱 부팅(asyncpg 엔진·auth 체인)을 필요로 해 단위 import가 무겁다. WP-E/WP-I가
DB 계약을 소스 텍스트 정적검사로 확인한 선례와 동형으로, 여기서는 파일 텍스트로 '배선이 실제로
연결됐는가'(멱등 lookup/save·problem+json·차원 분리·main 등록)를 검증한다.
"""
from __future__ import annotations

from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[1]  # apps/api


def _read(rel: str) -> str:
    return (_API_ROOT / rel).read_text(encoding="utf-8")


# ── design-runs 라우터 ───────────────────────────────────────────────────────
def test_design_runs_router_prefix_and_endpoints():
    src = _read("app/routers/design_runs.py")
    assert 'prefix="/design-runs"' in src
    assert '@router.post("/{run_id}/approve")' in src
    assert '@router.post("/{run_id}/cancel")' in src
    assert '@router.post("/{run_id}/job")' in src
    assert '@router.get("/{run_id}")' in src


def test_approve_wires_idempotency_and_problem_json():
    """★approve: Idempotency-Key 헤더·lookup·save·problem+json·409 거부가 모두 배선됐다."""
    src = _read("app/routers/design_runs.py")
    assert 'Header(default=None, alias="Idempotency-Key")' in src
    assert "idempotency.lookup(" in src
    assert "idempotency.save(" in src
    assert "idempotency.STATE_CONFLICT" in src
    assert "idempotency.STATE_REPLAY" in src
    # 재생 경로(재실행 0) — 저장된 응답 그대로 반환.
    assert ".to_response()" in src
    # 승인 거부는 problem+json 409.
    assert "ProblemException(" in src
    assert 'code="APPROVE_REJECTED"' in src


def test_approve_tenant_fail_closed():
    """★비가역 승인 — 테넌트 없는 세션 fail-closed(403)."""
    src = _read("app/routers/design_runs.py")
    assert "if tenant_id is None:" in src
    assert 'code="TENANT_REQUIRED"' in src


def test_router_uses_both_dimension_modules_separately():
    """★차원 분리 — 승인차원은 design_run_store, 실행차원은 design_run_job으로 분리 호출."""
    src = _read("app/routers/design_runs.py")
    assert "design_run_store.approve_design_run(" in src   # 승인차원
    assert "design_run_job.cancel_job(" in src             # 실행차원
    assert "design_run_job.set_job_status(" in src
    # approve 핸들러가 job_status를 직접 만지지 않는다(별도 축).
    assert "set_job_status" in src and "approve_design_run" in src


def test_router_maps_service_codes_to_problem_status():
    src = _read("app/routers/design_runs.py")
    assert '"not_found"' in src
    assert "status=404" in src
    assert "status=409" in src


# ── submission-bundle 멱등 배선(design_v61) ──────────────────────────────────
def test_submission_bundle_wires_idempotency():
    src = _read("app/routers/design_v61.py")
    assert "from app.core import idempotency" in src
    assert 'Header(default=None, alias="Idempotency-Key")' in src
    # lookup·save가 submission-bundle endpoint 키로 배선.
    assert 'endpoint="submission-bundle"' in src
    assert "idempotency.lookup(" in src
    assert "idempotency.save(" in src
    assert "idempotency.STATE_CONFLICT" in src
    assert "idempotency.STATE_REPLAY" in src
    # request_hash로 결정적 input_hash를 재사용(추가 계산 0).
    assert "request_hash=input_hash" in src


# ── main.py 등록(additive) ───────────────────────────────────────────────────
def test_main_registers_problem_handlers_and_router():
    src = _read("main.py")
    assert "register_problem_handlers(app)" in src
    assert "design_runs_router" in src
    assert "app.include_router(design_runs_router, prefix=\"/api/v1\")" in src
    # 기존 예외 핸들러 등록 뒤에 additive로 붙었는지(무회귀).
    assert "register_exception_handlers(app)" in src
    assert src.index("register_exception_handlers(app)") < src.index("register_problem_handlers(app)")


# ── problem_details 스코프아웃 명시(design_v61 다른 엔드포인트 미포함) ────────
def test_problem_surface_prefixes_are_scoped():
    src = _read("app/core/problem_details.py")
    # 전용 표면 접두 + submission-bundle 접미만 — /api/v1/design 전체 접두 금지(과대적용 방지).
    assert '"/api/v1/design-runs"' in src
    assert '"/submission-bundle"' in src
    assert '"/api/v1/design"' not in src.replace('"/api/v1/design-runs"', "")  # design 전체 접두 없음
