"""SourceSnapshot 계약 테스트 (W2-1).

순수 헬퍼(마스킹·checksum·지문·절단)는 DB 없이, 기록/조회(safe_record_*·get_by_*)는
app/services/ai/base_interpreter fewshot 테스트와 동형의 인메모리 fake session으로
실 Postgres 없이 검증한다(analysis_ledger_service._ensure 동형 DDL 경로 포함).
"""
from __future__ import annotations

import hashlib
import json
import uuid

from app.services.provenance import source_snapshot as ss

# ══════════════════════════════════════════════════════════════════════════
# 1) 순수 헬퍼 — 마스킹·지문·checksum·절단(DB 불요)
# ══════════════════════════════════════════════════════════════════════════


def test_mask_secret_params_masks_service_key():
    masked = ss.mask_secret_params({"serviceKey": "SECRET123", "pageNo": "1"})
    assert masked["serviceKey"] == ss._MASK
    assert masked["pageNo"] == "1"


def test_mask_secret_params_masks_plain_key_vworld_style():
    # VWorld는 서비스 접두 없는 평문 'key' 파라미터를 쓴다 — 로그 정규식(serviceKey/apiKey)보다
    # 넓게 "키 이름에 토큰 포함" 규칙으로 잡아야 한다.
    masked = ss.mask_secret_params({"key": "ABCDEF", "pnu": "12345"})
    assert masked["key"] == ss._MASK
    assert masked["pnu"] == "12345"


def test_mask_secret_params_case_insensitive_and_other_tokens():
    masked = ss.mask_secret_params({"AuthToken": "t", "Client_Secret": "s", "password": "p", "x": "y"})
    assert masked["AuthToken"] == ss._MASK
    assert masked["Client_Secret"] == ss._MASK
    assert masked["password"] == ss._MASK
    assert masked["x"] == "y"


def test_mask_secret_params_none_or_empty_returns_empty_dict():
    assert ss.mask_secret_params(None) == {}
    assert ss.mask_secret_params({}) == {}


def test_mask_secret_params_does_not_mutate_original():
    original = {"key": "SECRET"}
    ss.mask_secret_params(original)
    assert original["key"] == "SECRET"  # 원본 dict 불변


def test_build_request_fingerprint_masks_before_hashing():
    fp1 = ss.build_request_fingerprint("GET", "https://api.vworld.kr/req/data", {"key": "SECRET_A", "pnu": "1"})
    fp2 = ss.build_request_fingerprint("GET", "https://api.vworld.kr/req/data", {"key": "SECRET_B", "pnu": "1"})
    # 비밀 값만 다르면 지문이 같아야 한다 — 비밀이 마스킹 후 해시되어 지문에 영향을 주지 않는다.
    assert fp1 == fp2


def test_build_request_fingerprint_differs_by_non_secret_param():
    fp1 = ss.build_request_fingerprint("GET", "url", {"pnu": "1"})
    fp2 = ss.build_request_fingerprint("GET", "url", {"pnu": "2"})
    assert fp1 != fp2


def test_build_request_fingerprint_differs_by_url():
    fp1 = ss.build_request_fingerprint("GET", "url-a", {"pnu": "1"})
    fp2 = ss.build_request_fingerprint("GET", "url-b", {"pnu": "1"})
    assert fp1 != fp2


def test_build_request_fingerprint_key_order_independent():
    fp1 = ss.build_request_fingerprint("GET", "url", {"a": "1", "b": "2"})
    fp2 = ss.build_request_fingerprint("GET", "url", {"b": "2", "a": "1"})
    assert fp1 == fp2


def test_build_request_fingerprint_no_secret_leaks_in_output():
    fp = ss.build_request_fingerprint("GET", "url", {"serviceKey": "TOPSECRETVALUE"})
    assert "TOPSECRETVALUE" not in fp


def test_compute_checksum_deterministic_and_distinct():
    assert ss.compute_checksum(b"hello") == ss.compute_checksum(b"hello")
    assert ss.compute_checksum(b"hello") != ss.compute_checksum(b"world")


def test_compute_checksum_none_is_empty_bytes_hash():
    assert ss.compute_checksum(None) == hashlib.sha256(b"").hexdigest()


def test_truncate_payload_under_limit_unchanged():
    data = b"x" * 100
    out, truncated = ss.truncate_payload(data, limit=1000)
    assert out == data
    assert truncated is False


def test_truncate_payload_over_limit_flags_truncated():
    data = b"x" * 2000
    out, truncated = ss.truncate_payload(data, limit=1000)
    assert len(out) == 1000
    assert truncated is True


def test_truncate_payload_exactly_at_limit_not_truncated():
    data = b"x" * 1000
    out, truncated = ss.truncate_payload(data, limit=1000)
    assert len(out) == 1000
    assert truncated is False


def test_truncate_payload_none_passthrough():
    out, truncated = ss.truncate_payload(None)
    assert out is None
    assert truncated is False


def test_default_payload_limit_is_512kb():
    assert ss.PAYLOAD_LIMIT_BYTES == 512 * 1024


# ══════════════════════════════════════════════════════════════════════════
# 2) 인메모리 fake DB — 기록(성공/dead-letter)·조회·예외흡수
#    (app/services/ai/base_interpreter fewshot 테스트 동형 패턴)
# ══════════════════════════════════════════════════════════════════════════
_SELECT_ROW_COLS = (
    "id", "source_id", "status", "http_status", "fetched_at", "observed_at",
    "payload_truncated", "checksum", "request_fingerprint",
)


class _Result:
    def __init__(self, scalar_val=None, first_val=None, all_val=None):
        self._scalar = scalar_val
        self._first = first_val
        self._all = all_val or []

    def scalar(self):
        return self._scalar

    def first(self):
        return self._first

    def all(self):
        return self._all


class _FakeDB:
    """source_snapshots SQL을 모사하는 인메모리 fake(analysis_ledger 계열 fake 패턴 동형)."""

    def __init__(self, *, table_exists: bool = True, insert_row=None, select_rows=None):
        self.table_exists = table_exists
        self.insert_row = insert_row or (str(uuid.uuid4()), "2026-07-22T00:00:00+00:00")
        self.select_rows = select_rows or []
        self.executed: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt)).strip()
        self.executed.append((sql, params or {}))
        if "to_regclass" in sql:
            return _Result(scalar_val=self.table_exists)
        if sql.startswith("SELECT pg_advisory_xact_lock") or sql.startswith("CREATE TABLE") or sql.startswith("CREATE INDEX"):
            return _Result()
        if sql.startswith("INSERT INTO source_snapshots"):
            return _Result(first_val=self.insert_row)
        if sql.startswith("SELECT") and "FROM source_snapshots" in sql:
            return _Result(all_val=self.select_rows)
        return _Result()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


class _FakeSessionCtx:
    def __init__(self, db: _FakeDB):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_a):
        return False


def _patch_session(monkeypatch, db: _FakeDB) -> _FakeDB:
    import app.core.database as dbm
    monkeypatch.setattr(dbm, "async_session_factory", lambda: _FakeSessionCtx(db))
    return db


def _insert_params(db: _FakeDB) -> dict:
    calls = [p for sql, p in db.executed if sql.startswith("INSERT INTO source_snapshots")]
    assert len(calls) == 1, "INSERT는 정확히 1회 호출되어야 한다"
    return calls[0]


async def test_safe_record_success_persists_and_returns_checksum(monkeypatch):
    db = _FakeDB(table_exists=True)
    _patch_session(monkeypatch, db)
    payload = b'{"ok":true}'
    result = await ss.safe_record_success(
        source_id="vworld", method="GET", url="https://api.vworld.kr/req/data",
        params={"key": "SECRET", "pnu": "111"}, payload_bytes=payload, http_status=200,
    )
    assert result is not None
    assert result["status"] == ss.STATUS_OK
    assert result["checksum"] == ss.compute_checksum(payload)
    assert result["payload_truncated"] is False
    assert db.committed is True

    p = _insert_params(db)
    assert p["st"] == ss.STATUS_OK
    assert p["hs"] == 200
    assert p["pb"] == payload
    # ★비밀 마스킹 — INSERT 바인드 파라미터 어디에도 원문 'SECRET'이 남지 않아야 한다.
    assert "SECRET" not in json.dumps(p, default=str)


async def test_safe_record_dead_letter_persists_with_status_and_error(monkeypatch):
    db = _FakeDB(table_exists=True)
    _patch_session(monkeypatch, db)
    result = await ss.safe_record_dead_letter(
        source_id="g2b", method="GET", url="http://apis.data.go.kr/x",
        params={"serviceKey": "SECRET"}, http_status=500, error_message="boom",
    )
    assert result is not None
    assert result["status"] == ss.STATUS_DEAD_LETTER

    p = _insert_params(db)
    assert p["st"] == ss.STATUS_DEAD_LETTER
    assert p["hs"] == 500
    assert p["err"] == "boom"
    assert "SECRET" not in json.dumps(p, default=str)


async def test_safe_record_success_flags_payload_truncated_over_limit(monkeypatch):
    db = _FakeDB(table_exists=True)
    _patch_session(monkeypatch, db)
    big_payload = b"a" * (ss.PAYLOAD_LIMIT_BYTES + 100)
    result = await ss.safe_record_success(
        source_id="vworld", method="GET", url="url", params=None,
        payload_bytes=big_payload, http_status=200,
    )
    assert result["payload_truncated"] is True
    # ★무결성 계약: checksum은 절단 "전" 원문 전체 기준이어야 한다.
    assert result["checksum"] == ss.compute_checksum(big_payload)

    p = _insert_params(db)
    assert p["trunc"] is True
    assert len(p["pb"]) == ss.PAYLOAD_LIMIT_BYTES


async def test_safe_record_success_swallows_db_exceptions(monkeypatch):
    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    # ★계약 핵심: 기록 실패가 예외로 전파되지 않고 None만 반환한다(수집 호출경로 무영향).
    result = await ss.safe_record_success(
        source_id="vworld", method="GET", url="url", params=None,
        payload_bytes=b"{}", http_status=200,
    )
    assert result is None


async def test_safe_record_dead_letter_swallows_db_exceptions(monkeypatch):
    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    result = await ss.safe_record_dead_letter(
        source_id="g2b", method="GET", url="url", params=None, error_message="x",
    )
    assert result is None


async def test_get_by_checksum_returns_mapped_rows(monkeypatch):
    row = (str(uuid.uuid4()), "vworld", ss.STATUS_OK, 200,
           "2026-07-22 00:00:00+00", None, False, "abc123", "fp-1")
    db = _FakeDB(select_rows=[row])
    _patch_session(monkeypatch, db)
    out = await ss.get_by_checksum("abc123")
    assert len(out) == 1
    assert out[0]["checksum"] == "abc123"
    assert out[0]["status"] == ss.STATUS_OK
    assert out[0]["request_fingerprint"] == "fp-1"


async def test_get_by_checksum_failure_returns_empty_list(monkeypatch):
    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    assert await ss.get_by_checksum("whatever") == []


async def test_get_by_request_fingerprint_returns_mapped_rows(monkeypatch):
    row = (str(uuid.uuid4()), "g2b", ss.STATUS_DEAD_LETTER, 500,
           "2026-07-22 00:00:00+00", None, False, "chk-1", "fp-1")
    db = _FakeDB(select_rows=[row])
    _patch_session(monkeypatch, db)
    out = await ss.get_by_request_fingerprint("fp-1")
    assert len(out) == 1
    assert out[0]["request_fingerprint"] == "fp-1"
    assert out[0]["status"] == ss.STATUS_DEAD_LETTER


async def test_get_by_request_fingerprint_failure_returns_empty_list(monkeypatch):
    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    assert await ss.get_by_request_fingerprint("whatever") == []
