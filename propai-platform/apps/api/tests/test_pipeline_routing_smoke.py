"""파이프라인 라우터 배선 스모크 — 데코레이터가 올바른 핸들러에 붙는지 검증.

왜 필요한가: @router.post 데코레이터와 핸들러 함수 사이에 다른 함수를 끼워 넣으면
데코레이터가 그 함수에 붙어 실제 엔드포인트가 등록되지 않는 실수를 할 수 있다(라우팅 침묵 파괴).
기존 파이프라인 테스트는 ProjectPipeline().run()을 직접 불러 FastAPI 라우팅 테이블을 안 거쳐
이 결함을 못 잡았다. 이 테스트는 라우트 테이블에서 (메서드,경로)→핸들러 매핑을 직접 확인한다.
"""
from __future__ import annotations

from app.routers import pipeline as pipeline_router


def _route_map() -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for r in pipeline_router.router.routes:
        if not hasattr(r, "endpoint"):
            continue
        for m in sorted(getattr(r, "methods", []) or []):
            out[(m, r.path)] = r.endpoint.__name__
    return out


def test_pipeline_run_binds_to_run_pipeline():
    """POST /api/v2/pipeline/run 이 실제 실행 핸들러(run_pipeline)에 바인딩돼야 한다."""
    routes = _route_map()
    assert routes.get(("POST", "/api/v2/pipeline/run")) == "run_pipeline"


def test_pipeline_rerun_binds_to_rerun_stage():
    routes = _route_map()
    assert routes.get(("POST", "/api/v2/pipeline/rerun-stage")) == "rerun_stage"


def test_no_helper_leaked_as_endpoint():
    """내부 헬퍼(_merge_parcels_into_options)가 엔드포인트로 새어 등록되면 안 된다."""
    bound = set(_route_map().values())
    assert "_merge_parcels_into_options" not in bound
