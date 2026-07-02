"""이중 Settings 환경판별 정합 계약(3단계-a).

배경: apps/api/config.py(Settings A, `environment`←ENVIRONMENT)와 app/core/config.py
(Settings B, `APP_ENV`←APP_ENV)가 서로 다른 env var 를 읽어, 한쪽만 설정된 배포에서
두 클래스가 다른 환경으로 판별됐다 — 프로덕션 가드(P1-4 secret_store)·시크릿 검증이
B 기준이라 ENVIRONMENT=production 만 설정한 배포에선 우회되는 실위험.

계약: 두 클래스 모두 `ENVIRONMENT → APP_ENV` 동일 우선순위로 환경을 해석한다(어느 var 를
설정해도, 둘 다 설정돼도 항상 동일 판별). 전면 단일 클래스 통합은 별도 트랙(119 소비처).
"""
from __future__ import annotations

import pytest

# 모듈 레벨(dev 환경)에서 선로드 — app.core.config 는 임포트 시 module-level get_settings()가
# 돌아 production+무시크릿이면 정당 fail-fast 하므로, 테스트 내부(monkeypatch 후) 최초 임포트 금지.
from app.core.config import Settings as CoreSettings  # noqa: E402
from apps.api.config import Settings as ApiSettings  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for k in ("ENVIRONMENT", "APP_ENV"):
        monkeypatch.delenv(k, raising=False)
    # production 케이스에서 A 의 jwt_secret 기본값 fail-fast(정당 가드)가 환경판별 계약
    # 검증을 가리지 않도록 유효 시크릿 주입(본 테스트의 관심사는 환경 해석 일관성뿐).
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-jwt-secret-for-env-consistency-40ch")
    yield


def _envs():
    # lru_cache 우회 + .env 파일 격리(_env_file=None) — 순수 env var 만으로 판별.
    a = ApiSettings(_env_file=None).environment
    b = CoreSettings(_env_file=None).APP_ENV
    return a, b


def test_both_default_development():
    a, b = _envs()
    assert (a, b) == ("development", "development")


def test_environment_var_reaches_both(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    a, b = _envs()
    assert (a, b) == ("production", "production")  # ★핵심: B 도 ENVIRONMENT 를 인식


def test_app_env_var_reaches_both(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    a, b = _envs()
    assert (a, b) == ("production", "production")  # ★핵심: A 도 APP_ENV 를 인식


def test_conflict_resolves_identically(monkeypatch):
    # 둘 다 설정·상충 시에도 동일 우선순위(ENVIRONMENT 우선)로 '같은' 판별 — 드리프트 0.
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APP_ENV", "development")
    a, b = _envs()
    assert a == b == "production"
