"""라우터 커버리지 — '만들어놓고 배선 안 함(정의됐으나 미마운트)' 재발을 구조적으로 차단.

정찰 F1: rates 라우터가 미마운트라 BimCostDashboard 의 /api/v1/rates/current 호출이 런타임 404.
이 테스트는 (1) rates 라우트가 실제로 동작함(회귀 가드), (2) app/routers 의 모든 라우터 모듈이
main.py 에서 참조되거나 '의도적 미마운트'로 명시됐는지(정적 검사)를 확인한다.
"""

from __future__ import annotations

import pathlib
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

API_ROOT = pathlib.Path(__file__).resolve().parents[1]

# 의도적으로 마운트하지 않는 라우터(표면 확대 방지). 새로 미마운트하려면 여기 명시(사유와 함께).
KNOWN_UNMOUNTED = {
    "agents",   # 프론트 호출 없음 — 표면 확대 방지
    # v2_tax 삭제됨(2026-07-12 정리 — v1 tax와 기능 중복 死모듈, 전용 테스트도 함께 제거)
    "__init__",
}


def test_rates_route_lives():
    """rates 라우터를 마운트하면 /api/v1/rates/current 가 200(회귀 가드)."""
    from app.routers.rates import router

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.get("/api/v1/rates/current")
    assert res.status_code == 200, f"rates/current 가 {res.status_code} (라우터 미배선 재발?)"
    body = res.json()
    assert isinstance(body, (dict, list)) and body, "rates/current 응답이 비어있음"


def test_rates_mounted_in_main():
    """main.py 가 rates 라우터를 실제로 등록하는지 소스 확인(정찰 F1 회귀 가드)."""
    main_src = (API_ROOT / "main.py").read_text(encoding="utf-8")
    assert "app.routers.rates" in main_src, "main.py 가 rates 라우터를 등록하지 않음(F1 재발)"


def test_all_app_routers_mounted_or_declared():
    """app/routers 의 모든 router 정의 모듈이 main.py 에 참조되거나 KNOWN_UNMOUNTED 에 명시됐는가."""
    routers_dir = API_ROOT / "app" / "routers"
    main_src = (API_ROOT / "main.py").read_text(encoding="utf-8")

    defines_router = re.compile(r"^\s*router\s*(:\s*APIRouter\s*)?=", re.MULTILINE)
    missing = []
    for py in sorted(routers_dir.glob("*.py")):
        name = py.stem
        if name in KNOWN_UNMOUNTED:
            continue
        if not defines_router.search(py.read_text(encoding="utf-8")):
            continue  # router 를 정의하지 않는 헬퍼 모듈은 대상 아님
        # main.py 에서 모듈명이 어떤 형태로든 참조되면 통과(import 또는 importlib 문자열)
        if name not in main_src:
            missing.append(name)

    assert not missing, (
        f"정의됐으나 main.py 미참조 라우터: {missing}. "
        f"마운트하거나 KNOWN_UNMOUNTED 에 사유와 함께 추가하라('만들어놓고 배선안함' 방지)."
    )
