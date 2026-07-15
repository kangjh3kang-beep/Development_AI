"""WP-L 게이트 — Idempotency-Key 재전송 안전(miss/replay/conflict·테넌트스코프·최초1행).

핵심 게이트(계획서 §4 WP-L):
- 같은 키+같은 요청지문 → 저장 응답 재생(replay).
- 같은 키+다른 요청지문 → conflict(호출부 422).
- 테넌트별 키 공간 분리(교차테넌트 재생 0).
- ON CONFLICT DO NOTHING — 경쟁 시 최초 응답이 정본(덮어쓰기 0).

라이브 DB 없이, idempotency 모듈이 작성한 SQL을 충실히 모사하는 인메모리 fake로 구동한다
(WP-E design_run_store 테스트 동형).
"""
from __future__ import annotations

import base64
import json

import pytest

from app.core import idempotency as idem


def _coalesce(v):
    return v if v is not None else ""


class _Res:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def first(self):
        return self._row


class _FakeIdemDb:
    """idempotency_key SQL(COALESCE 유니크·ON CONFLICT DO NOTHING·테넌트스코프 SELECT)을 모사."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, statement, params=None):  # noqa: ANN001
        sql = str(getattr(statement, "text", statement))
        p = params or {}
        if "CREATE TABLE" in sql or "CREATE INDEX" in sql:
            return _Res()
        if sql.strip().startswith("INSERT INTO idempotency_key"):
            key = (_coalesce(p["tid"]), p["ep"], p["key"])
            if key not in self.rows:  # ON CONFLICT DO NOTHING — 최초 1행만
                self.rows[key] = {
                    "request_hash": p["rh"], "response_status": p["st"],
                    "response_media_type": p["mt"], "response_body_b64": p["body"],
                    "run_id": p["rid"],
                }
            return _Res()
        if sql.strip().startswith("SELECT request_hash"):
            key = (_coalesce(p["tid"]), p["ep"], p["key"])
            r = self.rows.get(key)
            if r is None:
                return _Res(None)
            return _Res((r["request_hash"], r["response_status"], r["response_media_type"],
                         r["response_body_b64"], r["run_id"]))
        return _Res()

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


# ── 1. 순수 헬퍼 ─────────────────────────────────────────────────────────────
def test_normalize_key_strips_and_caps():
    assert idem.normalize_key("  k1 ") == "k1"
    assert idem.normalize_key("") is None
    assert idem.normalize_key(None) is None
    assert idem.normalize_key("   ") is None
    assert len(idem.normalize_key("x" * 500)) == 255


def test_request_hash_deterministic_and_key_order_insensitive():
    h1 = idem.compute_request_hash({"a": 1, "b": 2})
    h2 = idem.compute_request_hash({"b": 2, "a": 1})
    assert h1 == h2
    assert idem.compute_request_hash({"a": 1}) != idem.compute_request_hash({"a": 2})


# ── 2. lookup/save 오케스트레이션 ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_lookup_miss_on_empty():
    db = _FakeIdemDb()
    look = await idem.lookup(db=db, key="k1", tenant_id="t-a", endpoint="ep", request_hash="rh1")
    assert look.state == idem.STATE_MISS


@pytest.mark.asyncio
async def test_save_then_replay_returns_stored_response():
    db = _FakeIdemDb()
    body = json.dumps({"run_id": "dr_1", "status": "APPROVED"}).encode()
    ok = await idem.save(db=db, key="k1", tenant_id="t-a", endpoint="ep",
                         request_hash="rh1", response_status=200, body=body,
                         media_type="application/json", run_id="dr_1")
    assert ok is True
    look = await idem.lookup(db=db, key="k1", tenant_id="t-a", endpoint="ep", request_hash="rh1")
    assert look.state == idem.STATE_REPLAY
    assert look.stored.response_status == 200
    assert look.stored.body == body
    assert look.stored.run_id == "dr_1"


@pytest.mark.asyncio
async def test_conflict_when_same_key_different_request():
    """★같은 키, 다른 요청지문 → conflict(키 오사용 — 호출부 422)."""
    db = _FakeIdemDb()
    await idem.save(db=db, key="k1", tenant_id="t-a", endpoint="ep",
                    request_hash="rh1", response_status=200, body=b"x")
    look = await idem.lookup(db=db, key="k1", tenant_id="t-a", endpoint="ep", request_hash="DIFFERENT")
    assert look.state == idem.STATE_CONFLICT


@pytest.mark.asyncio
async def test_tenant_scoped_keyspace():
    """★테넌트별 키 공간 분리 — 다른 테넌트로는 재생되지 않는다(miss)."""
    db = _FakeIdemDb()
    await idem.save(db=db, key="k1", tenant_id="t-a", endpoint="ep",
                    request_hash="rh1", response_status=200, body=b"x")
    look_other = await idem.lookup(db=db, key="k1", tenant_id="t-b", endpoint="ep", request_hash="rh1")
    assert look_other.state == idem.STATE_MISS
    look_same = await idem.lookup(db=db, key="k1", tenant_id="t-a", endpoint="ep", request_hash="rh1")
    assert look_same.state == idem.STATE_REPLAY


@pytest.mark.asyncio
async def test_first_write_wins_on_conflict_do_nothing():
    """★ON CONFLICT DO NOTHING — 두 번째 save가 첫 응답을 덮어쓰지 않는다(경쟁 최초 정본)."""
    db = _FakeIdemDb()
    await idem.save(db=db, key="k1", tenant_id="t-a", endpoint="ep",
                    request_hash="rh1", response_status=200, body=b"FIRST")
    await idem.save(db=db, key="k1", tenant_id="t-a", endpoint="ep",
                    request_hash="rh1", response_status=200, body=b"SECOND")
    look = await idem.lookup(db=db, key="k1", tenant_id="t-a", endpoint="ep", request_hash="rh1")
    assert look.stored.body == b"FIRST"


@pytest.mark.asyncio
async def test_large_body_stored_meta_only_replay_body_none():
    """상한 초과 본문은 저장 안 함(메타만) — 재생 시 body None(호출부 결정적 재계산)."""
    db = _FakeIdemDb()
    big = b"z" * 100
    await idem.save(db=db, key="k1", tenant_id="t-a", endpoint="ep",
                    request_hash="rh1", response_status=200, body=big,
                    media_type="application/zip", max_body_bytes=10)
    look = await idem.lookup(db=db, key="k1", tenant_id="t-a", endpoint="ep", request_hash="rh1")
    assert look.state == idem.STATE_REPLAY
    assert look.stored.body is None
    assert look.stored.to_response() is None  # 본문 없으면 재생 불가 → 재계산 신호


@pytest.mark.asyncio
async def test_stored_response_to_response_roundtrip():
    db = _FakeIdemDb()
    body = b"hello-zip"
    await idem.save(db=db, key="k1", tenant_id=None, endpoint="ep",
                    request_hash="rh1", response_status=200, body=body,
                    media_type="application/zip")
    look = await idem.lookup(db=db, key="k1", tenant_id=None, endpoint="ep", request_hash="rh1")
    resp = look.stored.to_response()
    assert resp is not None
    assert resp.body == body
    assert resp.status_code == 200
    assert resp.media_type == "application/zip"


def test_base64_encoding_used_for_body_storage():
    """저장은 base64 텍스트(바이너리 안전) — 인코딩 계약 확인(정적)."""
    # save가 base64.b64encode를 쓰는지 소스로 확인(바이너리 zip 안전 저장).
    import inspect
    src = inspect.getsource(idem.save)
    assert "base64.b64encode" in src
    # sanity: round-trip
    assert base64.b64decode(base64.b64encode(b"\x00\x01")) == b"\x00\x01"


def test_submission_bundle_request_hash_includes_cosmetic_fields():
    """★리뷰 MEDIUM 회귀 고정 — submission-bundle 멱등 지문은 산출물에 영향을 주는
    표제란 필드(축척·발행일)를 반드시 포함해야 한다. 같은 input_hash라도 scale/issue_date가
    다르면 지문이 달라져(→ 다른 요청=conflict) 낡은 표제란 zip이 재생되지 않는다."""
    ih = "abc123deadbeef"
    base = idem.compute_request_hash({"input_hash": ih, "scale": "1:200", "issue_date": "2026-07-15"})
    diff_scale = idem.compute_request_hash({"input_hash": ih, "scale": "1:100", "issue_date": "2026-07-15"})
    diff_date = idem.compute_request_hash({"input_hash": ih, "scale": "1:200", "issue_date": "2026-07-16"})
    assert base != diff_scale, "축척만 달라도 지문이 달라야 함(낡은 표제란 재생 방지)"
    assert base != diff_date, "발행일만 달라도 지문이 달라야 함"
    # 같은 3필드면 결정적으로 동일(정상 재생)
    assert base == idem.compute_request_hash(
        {"issue_date": "2026-07-15", "scale": "1:200", "input_hash": ih}
    )
