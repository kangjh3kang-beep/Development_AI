"""커넥터 검증 — platform_secrets 복호화→env 오버레이. 합성 시크릿으로만 검증(실 자격증명 미접근).

마스터키 일치 시 복호화→os.environ 설정, 위험키 차단(DENYLIST), 마스터키 불일치 시 failed(무음 단정 금지).
"""
import os

from app.services.secrets.platform_secret_loader import (
    _fernet,
    is_allowed,
    overlay_secrets,
)


def _enc(master: str, value: str) -> str:
    os.environ["SECRET_STORE_KEY"] = master
    return _fernet().encrypt(value.encode()).decode()


def test_overlay_decrypts_and_sets_env(monkeypatch):
    monkeypatch.setenv("SECRET_STORE_KEY", "test-master-key-xyz")
    enc = _fernet().encrypt(b"sk-ant-SYNTHETIC").decode()
    res = overlay_secrets([("ANTHROPIC_API_KEY", enc)])
    try:
        assert "ANTHROPIC_API_KEY" in res["applied"]
        assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-SYNTHETIC"
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_overlay_blocks_denylist(monkeypatch):
    monkeypatch.setenv("SECRET_STORE_KEY", "k")
    enc = _fernet().encrypt(b"postgresql://danger").decode()
    res = overlay_secrets([("DATABASE_URL", enc)])
    assert "DATABASE_URL" not in res["applied"]
    assert res["denied"] == 1
    assert os.getenv("DATABASE_URL") != "postgresql://danger"


def test_overlay_wrong_master_key_fails(monkeypatch):
    enc = _enc("MASTER-A", "secret-value")
    monkeypatch.setenv("SECRET_STORE_KEY", "MASTER-B")  # 다른 키 → 복호화 실패
    res = overlay_secrets([("VWORLD_API_KEY", enc)])
    assert res["failed"] == 1
    assert res["applied"] == []


def test_is_allowed():
    assert is_allowed("ANTHROPIC_API_KEY") is True
    assert is_allowed("DATABASE_URL") is False
    assert is_allowed("bad-name") is False


def test_platform_env_file_reference(monkeypatch, tmp_path):
    # 플랫폼 .env(합성)에서 마스터키를 런타임 참조 — 복사 없이 단일 출처.
    from app.services.secrets.platform_secret_loader import has_master_key, master_key_material

    pe = tmp_path / "platform.env"
    pe.write_text("# platform\nJWT_SECRET_KEY=synthetic-master-123\nOTHER=x\n", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_ENV_FILE", str(pe))
    assert has_master_key() is True
    assert master_key_material() == "synthetic-master-123"


def test_platform_env_file_priority(monkeypatch, tmp_path):
    pe = tmp_path / "p.env"
    pe.write_text("JWT_SECRET_KEY=jwt-v\nSECRET_STORE_KEY=sss-v\n", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_ENV_FILE", str(pe))
    from app.services.secrets.platform_secret_loader import master_key_material
    assert master_key_material() == "sss-v"  # SECRET_STORE_KEY 우선
