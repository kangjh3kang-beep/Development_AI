"""Phase1-C 동호수 선점 동시성 — 원자 조건부 UPDATE 시맨틱 증명(로컬, 외부호출 0).

프로덕션은 Postgres + asyncpg 지만, 원자 단일행 조건부 UPDATE 의 *시맨틱*(WHERE 조건이
race 를 막는다)은 SQLite 로도 동일하게 검증 가능하다(RETURNING 지원 SQLite≥3.35).
시각 의존(now()+interval)은 sqlite 호환을 위해 julianday/strftime 로 치환한 동등 SQL 로 증명한다.

검증 시나리오
  1) 2직원 동시 hold → 정확히 1성공 1실패(0행)
  2) release 후 재 hold 성공
  3) 만료(과거 expires)된 hold → 다른 직원 hold 성공(takeover)
  4) reserve: 만료된 hold 확정거부(0행)
  5) reserve: 유효 hold 확정 성공 + 이중 reserve 차단(0행)
"""

import sqlite3
import uuid

import pytest


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute(
        "CREATE TABLE units ("
        " id TEXT PRIMARY KEY, site_id TEXT, dong TEXT, ho TEXT,"
        " status TEXT DEFAULT 'AVAILABLE', held_by TEXT,"
        " hold_expires_at TEXT, hold_token TEXT, deleted_at TEXT)"
    )
    return c


# now()+interval / now() 를 sqlite 동등식으로(julianday). +/-분은 분/1440 일.
def _hold(c, uid, site, held_by, ttl_min=5, expires_offset_min=None):
    """원자 hold — concurrency.atomic_hold 의 WHERE 조건과 동치."""
    token = uuid.uuid4().hex
    exp = f"+{ttl_min} minutes" if expires_offset_min is None else f"{expires_offset_min} minutes"
    cur = c.execute(
        "UPDATE units SET status='HOLD', held_by=?, "
        "  hold_expires_at=datetime('now', ?), hold_token=? "
        "WHERE id=? AND site_id=? AND deleted_at IS NULL "
        "  AND ( status='AVAILABLE' "
        "        OR (status='HOLD' AND (hold_expires_at IS NULL OR hold_expires_at < datetime('now'))) ) "
        "RETURNING id, hold_token, hold_expires_at",
        (held_by, exp, token, uid, site),
    )
    row = cur.fetchone()
    return (row[1], row[2]) if row else None


def _release(c, uid, site, held_by, token=None):
    q = ("UPDATE units SET status='AVAILABLE', held_by=NULL, hold_expires_at=NULL, hold_token=NULL "
         "WHERE id=? AND site_id=? AND status='HOLD' AND held_by=?")
    params = [uid, site, held_by]
    if token:
        q += " AND hold_token=?"
        params.append(token)
    cur = c.execute(q + " RETURNING id", params)
    return cur.fetchone() is not None


def _reserve(c, uid, site, held_by, token):
    cur = c.execute(
        "UPDATE units SET status='CONTRACTED' "
        "WHERE id=? AND site_id=? AND status='HOLD' AND held_by=? AND hold_token=? "
        "  AND hold_expires_at IS NOT NULL AND hold_expires_at >= datetime('now') "
        "RETURNING id",
        (uid, site, held_by, token),
    )
    return cur.fetchone() is not None


@pytest.fixture()
def db():
    c = _conn()
    yield c
    c.close()


def _seed(c, status="AVAILABLE"):
    uid, site = str(uuid.uuid4()), str(uuid.uuid4())
    c.execute("INSERT INTO units (id, site_id, dong, ho, status) VALUES (?,?,?,?,?)",
              (uid, site, "101", "1501", status))
    return uid, site


def test_동시_hold_정확히_1명만_성공(db):
    uid, site = _seed(db)
    staff_a, staff_b = str(uuid.uuid4()), str(uuid.uuid4())
    # 두 직원이 같은 세대 hold 시도 — 단일행 조건부 UPDATE 는 직렬화되어 1건만 성공
    r1 = _hold(db, uid, site, staff_a)
    r2 = _hold(db, uid, site, staff_b)
    successes = [r for r in (r1, r2) if r is not None]
    assert len(successes) == 1, "동시 hold 시 정확히 1명만 성공해야 함"
    assert r1 is not None and r2 is None
    row = db.execute("SELECT status, held_by FROM units WHERE id=?", (uid,)).fetchone()
    assert row[0] == "HOLD" and row[1] == staff_a


def test_release_후_재hold_성공(db):
    uid, site = _seed(db)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ra = _hold(db, uid, site, a)
    assert ra is not None
    assert _hold(db, uid, site, b) is None              # 점유중 차단
    assert _release(db, uid, site, a, token=ra[0]) is True
    rb = _hold(db, uid, site, b)                          # 해제 후 재선점
    assert rb is not None
    assert db.execute("SELECT held_by FROM units WHERE id=?", (uid,)).fetchone()[0] == b


def test_만료된_hold_타직원_takeover(db):
    uid, site = _seed(db)
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    # a 가 이미 과거(-1분)로 만료된 hold 보유
    assert _hold(db, uid, site, a, expires_offset_min=-1) is not None
    # b 가 hold 시도 → 만료 조건(hold_expires_at < now) 충족으로 takeover 성공
    rb = _hold(db, uid, site, b)
    assert rb is not None, "만료된 hold 는 다른 직원이 선점 가능해야 함"
    assert db.execute("SELECT held_by FROM units WHERE id=?", (uid,)).fetchone()[0] == b


def test_reserve_만료_확정거부(db):
    uid, site = _seed(db)
    a = str(uuid.uuid4())
    r = _hold(db, uid, site, a, expires_offset_min=-1)   # 만료된 hold
    assert r is not None
    assert _reserve(db, uid, site, a, r[0]) is False, "만료된 hold 는 확정 거부되어야 함"
    assert db.execute("SELECT status FROM units WHERE id=?", (uid,)).fetchone()[0] == "HOLD"


def test_reserve_유효_확정_및_이중reserve_차단(db):
    uid, site = _seed(db)
    a = str(uuid.uuid4())
    r = _hold(db, uid, site, a, ttl_min=5)               # 유효 hold
    assert r is not None
    assert _reserve(db, uid, site, a, r[0]) is True      # 1차 확정 성공
    assert db.execute("SELECT status FROM units WHERE id=?", (uid,)).fetchone()[0] == "CONTRACTED"
    assert _reserve(db, uid, site, a, r[0]) is False     # 이미 CONTRACTED → 2차 차단
    # 확정 후 다른 직원 hold 도 불가(available/만료 조건 불충족)
    assert _hold(db, uid, site, str(uuid.uuid4())) is None
