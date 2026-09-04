"""SourceSnapshot 계약 테스트 (W2-1, R1 R2 봉합 포함).

순수 헬퍼(마스킹·checksum·지문·절단·error_message 스크러빙)는 DB 없이, 기록/조회
(safe_record_*·get_by_*)는 app/services/ai/base_interpreter fewshot 테스트와 동형의
인메모리 fake session으로 실 Postgres 없이 검증한다(analysis_ledger_service._ensure
동형 DDL 경로 포함).
"""
from __future__ import annotations

import hashlib
import json
import uuid

import httpx
import pytest

from app.services.provenance import source_snapshot as ss


@pytest.fixture(autouse=True)
def _reset_schema_ready_flag(monkeypatch):
    """_SCHEMA_READY 모듈 전역을 매 테스트 시작 전 False로 되돌린다(R1 MEDIUM-3 1회화
    플래그를 테스트했을 때, 어떤 테스트가 먼저 실행되든 _ensure의 to_regclass 왕복 여부가
    결정론적이도록 — 순서 의존 플레이키 방지)."""
    monkeypatch.setattr(ss, "_SCHEMA_READY", False)


# ══════════════════════════════════════════════════════════════════════════
# 1) 순수 헬퍼 — 마스킹·지문·checksum·절단·error_message 스크러빙(DB 불요)
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


# ── error_message 스크러빙(★R1 HIGH 회귀 수정) ──────────────────────────────


def test_scrub_error_message_strips_url_query_string_and_key():
    msg = ("Client error '404 Not Found' for url "
           "'https://api.vworld.kr/req/data?service=data&key=SECRET123&pnu=1'")
    scrubbed = ss.scrub_error_message(msg)
    assert "SECRET123" not in scrubbed
    assert "?***" in scrubbed


def test_scrub_error_message_none_passthrough():
    assert ss.scrub_error_message(None) is None


def test_scrub_error_message_empty_string_passthrough():
    assert ss.scrub_error_message("") == ""


def test_scrub_error_message_no_url_left_unchanged():
    assert ss.scrub_error_message("plain error, no url") == "plain error, no url"


def test_scrub_error_message_second_url_without_query_untouched():
    # 쿼리스트링이 없는 URL(예: 안내 링크)은 건드리지 않는다 — 과다삭제 방지.
    msg = "for url 'https://x.example/path?key=SECRET' more info: https://docs.example.com/404"
    scrubbed = ss.scrub_error_message(msg)
    assert "SECRET" not in scrubbed
    assert "https://docs.example.com/404" in scrubbed


def test_scrub_error_message_reuses_logging_config_pii_patterns():
    # 쿼리스트링 형태가 아닌 위치(예: 헤더/바디 로그)의 serviceKey=... 도 logging_config의
    # 마스킹 규칙 재사용으로 잡혀야 한다(계약 정합 — 로그와 저장소가 같은 규칙 공유).
    msg = "auth failed serviceKey=ABCDEFG in header"
    scrubbed = ss.scrub_error_message(msg)
    assert "ABCDEFG" not in scrubbed


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
    # ★교훈(R1): 이 테스트는 원래 error_message="boom"처럼 "이미 안전한" 문자열만 검증했다.
    #   스크러빙 로직이 아예 없어도(또는 고장나도) 이 테스트는 그대로 통과하므로, 실제
    #   비밀유출(str(httpx.HTTPStatusError)에 담긴 쿼리스트링 키)을 잡지 못하고 은폐했다 —
    #   기본 저장 동작(상태·에러문구 보존)만 확인하는 용도로 남기고, 진짜 스크러빙 검증은
    #   아래 test_dead_letter_scrubs_secret_from_real_httpx_error_message가 담당한다.
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


async def test_dead_letter_scrubs_secret_from_real_httpx_error_message(monkeypatch):
    """★R1 HIGH 회귀(리뷰어 실증 벡터) — str(httpx.HTTPStatusError)는 요청 URL 전체를
    쿼리스트링(인증키 포함)까지 그대로 문자열화한다. "boom" 같은 안전한 문자열이 아니라,
    실제 httpx 예외가 만드는 진짜 문자열을 그대로 error_message에 흘려보내 저장값에
    비밀이 남지 않는지 검증한다(위 test_safe_record_dead_letter_persists_with_status_and_error
    가 은폐했던 바로 그 유출 경로).
    """
    db = _FakeDB(table_exists=True)
    _patch_session(monkeypatch, db)

    req = httpx.Request("GET", "https://api.vworld.kr/req/data",
                         params={"service": "data", "key": "SECRET123ABC", "pnu": "1111"})
    resp = httpx.Response(404, request=req, content=b"not found")
    try:
        resp.raise_for_status()
        raise AssertionError("raise_for_status가 예외를 던지지 않음(테스트 셋업 오류)")
    except httpx.HTTPStatusError as exc:
        real_error_message = str(exc)

    # 원본 문자열에는 비밀이 그대로 있다는 것부터 재확인(그렇지 않으면 이 테스트가 무의미).
    assert "SECRET123ABC" in real_error_message

    await ss.safe_record_dead_letter(
        source_id="vworld", method="GET", url="https://api.vworld.kr/req/data",
        params={"key": "SECRET123ABC", "pnu": "1111"}, http_status=404,
        error_message=real_error_message,
    )
    p = _insert_params(db)
    assert "SECRET123ABC" not in p["err"]
    assert "?***" in p["err"]


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


# ══════════════════════════════════════════════════════════════════════════
# 3) _ensure 1회화(★R1 MEDIUM-3) — 모듈 플래그로 to_regclass 왕복 생략 + 생성 직후 commit
# ══════════════════════════════════════════════════════════════════════════


async def test_ensure_sets_ready_flag_and_queries_to_regclass_once(monkeypatch):
    monkeypatch.setattr(ss, "_SCHEMA_READY", False)
    db1 = _FakeDB(table_exists=True)
    await ss._ensure(db1)
    assert any("to_regclass" in sql for sql, _ in db1.executed)
    assert ss._SCHEMA_READY is True

    # 두 번째 호출은 플래그가 이미 True라 DB 왕복 자체가 없어야 한다(1회화 핵심).
    db2 = _FakeDB(table_exists=True)
    await ss._ensure(db2)
    assert db2.executed == []


async def test_ensure_creates_table_when_missing_and_commits_before_flag(monkeypatch):
    """생성 분기에서는 반드시 즉시 commit한 뒤 플래그를 세운다 — 그렇지 않으면 읽기전용
    호출부(get_by_*)가 커밋하지 않아 세션 종료 시 방금 만든 테이블이 롤백되는데도
    _SCHEMA_READY만 True로 남아 이후 모든 호출이 "존재한다고 착각"하는 위험한 상태가
    된다(1회화 리팩토링이 새로 만들 뻔한 회귀 — 여기서 직접 검증)."""
    monkeypatch.setattr(ss, "_SCHEMA_READY", False)
    db = _FakeDB(table_exists=False)
    await ss._ensure(db)
    sqls = [sql for sql, _ in db.executed]
    assert any("to_regclass" in s for s in sqls)
    assert any(s.startswith("CREATE TABLE") for s in sqls)
    assert any("pg_advisory_xact_lock" in s for s in sqls)
    assert db.committed is True  # ★핵심 회귀 가드
    assert ss._SCHEMA_READY is True


# ══════════════════════════════════════════════════════════════════════════
# 4) 무음 실패 해소(★R1 MEDIUM-1) — 기록 실패 로그가 debug가 아니라 warning으로 남는지
# ══════════════════════════════════════════════════════════════════════════


class _CapturingLogger:
    def __init__(self):
        self.warnings: list[tuple] = []
        self.debugs: list[tuple] = []

    def warning(self, *a, **k):
        self.warnings.append((a, k))

    def debug(self, *a, **k):
        self.debugs.append((a, k))

    def __getattr__(self, _name):
        return lambda *a, **k: None


async def test_safe_record_success_db_failure_logs_warning_not_debug(monkeypatch):
    fake_logger = _CapturingLogger()
    monkeypatch.setattr(ss, "logger", fake_logger)

    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    await ss.safe_record_success(
        source_id="vworld", method="GET", url="url", params=None,
        payload_bytes=b"{}", http_status=200,
    )
    assert len(fake_logger.warnings) == 1
    assert fake_logger.debugs == []  # ★역전 해소 확인 — 더 이상 debug로 무음 처리하지 않는다.


async def test_safe_record_dead_letter_db_failure_logs_warning_not_debug(monkeypatch):
    fake_logger = _CapturingLogger()
    monkeypatch.setattr(ss, "logger", fake_logger)

    import app.core.database as dbm

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbm, "async_session_factory", _boom)
    await ss.safe_record_dead_letter(
        source_id="g2b", method="GET", url="url", params=None, error_message="x",
    )
    assert len(fake_logger.warnings) == 1
    assert fake_logger.debugs == []
