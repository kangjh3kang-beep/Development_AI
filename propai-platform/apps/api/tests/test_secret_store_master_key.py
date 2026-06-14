"""시크릿 스토어 마스터키 강건화 회귀 테스트.

근본문제: 마스터키가 SECRET_STORE_KEY 미설정 시 APP_SECRET_KEY(로테이션 대상)에서 파생 →
배포/로테이션 시 키가 바뀌어 기존 시크릿 복호화 실패(22/24). 강건화 검증:
- SECRET_STORE_KEY(임의 문자열·정식 Fernet 키 모두) → 안정 라운드트립.
- master_key_status: SECRET_STORE_KEY만 stable=True, 그 외 unstable 경고.
- 키 회전 시 복호화 실패 재현 + 옛 키로 복구 가능.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from app.services.secrets import secret_store as ss  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_key_env(monkeypatch):
    # 각 테스트는 마스터키 관련 env 를 깨끗이 통제한다.
    for k in ("SECRET_STORE_KEY", "APP_SECRET_KEY", "JWT_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield


class TestMasterKey:
    def test_임의문자열_SECRET_STORE_KEY_라운드트립_stable(self, monkeypatch):
        monkeypatch.setenv("SECRET_STORE_KEY", "any-arbitrary-admin-string")
        tok = ss._encrypt("hello")
        assert ss._decrypt(tok) == "hello"
        assert ss.master_key_status() == {"source": "SECRET_STORE_KEY", "stable": True}

    def test_정식_Fernet_키_하위호환(self, monkeypatch):
        monkeypatch.setenv("SECRET_STORE_KEY", Fernet.generate_key().decode())
        tok = ss._encrypt("payload")
        assert ss._decrypt(tok) == "payload"

    def test_APP_SECRET_KEY_파생은_unstable(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET_KEY", "appkey-X")
        st = ss.master_key_status()
        assert st["source"] == "APP_SECRET_KEY" and st["stable"] is False and "warning" in st

    def test_무설정_하드코딩폴백_unstable(self):
        st = ss.master_key_status()
        assert st["source"] == "hardcoded-fallback" and st["stable"] is False

    def test_키회전_복호화실패_재현_및_옛키복구(self, monkeypatch):
        monkeypatch.setenv("APP_SECRET_KEY", "appkey-X")
        tok = ss._encrypt("payload")            # 옛 키로 암호화
        monkeypatch.setenv("APP_SECRET_KEY", "appkey-Y")  # 키 회전
        assert ss._decrypt(tok) is None         # 현재 키로는 복호화 실패(불일치 재현)
        old = Fernet(ss._fernet_key_from_material("appkey-X"))
        assert old.decrypt(tok.encode()).decode() == "payload"  # 옛 재질로 복구 가능
