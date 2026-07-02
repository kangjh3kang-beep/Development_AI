"""config-divergence 전역 공용화 회귀 테스트 — app.core.env SSOT + 4개 보안게이트.

근본 버그(적대적 전역스윕 확정, M1 동일 패턴):
- 런타임 권위 소스는 ENVIRONMENT(apps.api.config, main.py 기동 기준)인데 여러 보안게이트가
  app/core/config.APP_ENV(또는 국소 os.getenv('APP_ENV'))를 읽었다.
- 배포 관례상 ENVIRONMENT=production 만 설정되고 APP_ENV 는 development 로 남아 →
  프로덕션을 개발로 오판 → 보안 우회(폴백키·SQL echo·deploy_pending 과소표기).

검증 핵심: ENVIRONMENT=production + APP_ENV=development '발산'을 실증적으로 재현하고,
공용 헬퍼가 fail-secure 하게 프로덕션으로 판정하는지 각 사이트에서 확인한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.core import env  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """각 테스트는 환경/키 관련 env 를 통제하고, 두 config lru_cache 를 비워 격리한다."""
    for k in ("ENVIRONMENT", "APP_ENV", "APP_DEBUG", "DEBUG",
              "APP_SECRET_KEY", "JWT_SECRET_KEY", "SALES_ENC_KEY",
              "SECRET_STORE_KEY"):
        monkeypatch.delenv(k, raising=False)
    # 루트/코어 config 캐시 초기화(env 변경이 즉시 반영되게).
    from apps.api.config import get_settings as _root_gs
    from app.core.config import get_settings as _core_gs
    _root_gs.cache_clear()
    _core_gs.cache_clear()
    yield
    _root_gs.cache_clear()
    _core_gs.cache_clear()


# ───────────────────────── env.is_production ─────────────────────────

class TestIsProduction:
    def test_우회핵심_ENVIRONMENT프로덕션_APP_ENV개발_True(self, monkeypatch):
        """★M1 우회 패턴: 두 소스 발산 시 fail-secure 로 프로덕션(True)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("APP_ENV", "development")
        assert env.is_production() is True

    def test_순수개발_둘다development_False(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        assert env.is_production() is False

    def test_staging도_프로덕션취급_True(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "staging")
        assert env.is_production() is True

    def test_test환경_False(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        monkeypatch.setenv("APP_ENV", "test")
        assert env.is_production() is False

    def test_힌트로_production전달_True(self, monkeypatch):
        # os.environ 은 비어도(루트 config 기본 development) 힌트가 production 이면 True.
        assert env.is_production("production") is True

    def test_힌트development여도_ENVIRONMENT프로덕션이면_True(self, monkeypatch):
        # config.py 가 s.APP_ENV=development 를 힌트로 넘겨도 ENVIRONMENT=production 이면 차단.
        monkeypatch.setenv("ENVIRONMENT", "production")
        assert env.is_production("development") is True


# ───────────────────────── env.is_debug ─────────────────────────

class TestIsDebug:
    def test_프로덕션이면_APP_DEBUG참여도_False(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("APP_DEBUG", "true")
        assert env.is_debug() is False

    def test_개발_APP_DEBUG참이면_True(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("APP_DEBUG", "true")
        assert env.is_debug() is True

    def test_개발_플래그없으면_False(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        assert env.is_debug() is False

    def test_개발_DEBUG별칭도_인식(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("DEBUG", "1")
        assert env.is_debug() is True


# ───────────────────────── config.py get_settings 게이트 ─────────────────────────

class TestConfigSecretGate:
    def test_우회발산_약한키_validate_secret발화(self, monkeypatch):
        """ENVIRONMENT=production + APP_ENV=development, 약한 APP_SECRET_KEY → RuntimeError."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("APP_SECRET_KEY", "short")  # len<32 → _validate_secret 거부
        monkeypatch.setenv("JWT_SECRET_KEY", "x" * 40)
        from app.core.config import get_settings
        get_settings.cache_clear()
        with pytest.raises(RuntimeError):
            get_settings()

    def test_우회발산_빈키_validate_secret발화(self, monkeypatch):
        """ENVIRONMENT=production + APP_ENV=development, 빈 APP_SECRET_KEY → RuntimeError(fail-fast)."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("APP_ENV", "development")
        # APP_SECRET_KEY 미설정(빈값) → 프로덕션 판정 시 _validate_secret 이 먼저 raise.
        from app.core.config import get_settings
        get_settings.cache_clear()
        with pytest.raises(RuntimeError):
            get_settings()

    def test_순수개발_빈키_자동생성_통과(self, monkeypatch):
        """둘 다 development 면 프로덕션 아님 → 빈키 자동생성 분기(예외 없이 통과)."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        from app.core.config import get_settings
        get_settings.cache_clear()
        s = get_settings()
        assert s.APP_SECRET_KEY  # 자동 생성됨
        assert s.JWT_SECRET_KEY


# ───────────────────────── sales_crypto._key 게이트 ─────────────────────────

class TestSalesCryptoGate:
    def test_우회발산_키미설정_RuntimeError(self, monkeypatch):
        """ENVIRONMENT=production + APP_ENV=development, SALES_ENC_KEY/APP_SECRET_KEY 미설정 → 차단."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("APP_ENV", "development")
        from app.core import sales_crypto
        with pytest.raises(RuntimeError):
            sales_crypto._key()

    def test_개발_폴백키_허용(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        from app.core import sales_crypto
        # dev 는 폴백키 허용(예외 없이 bytes 반환).
        assert isinstance(sales_crypto._key(), bytes)


# ───────────────────────── database echo(is_debug 갈음) ─────────────────────────

class TestDatabaseEcho:
    def test_프로덕션이면_echo_off(self, monkeypatch):
        """DB echo 는 is_debug 로 결정 — 프로덕션이면 APP_DEBUG=true 여도 off."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("APP_DEBUG", "true")
        assert env.is_debug() is False  # database.create_async_engine(echo=is_debug())

    def test_개발이면_APP_DEBUG따름(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("APP_DEBUG", "true")
        assert env.is_debug() is True
