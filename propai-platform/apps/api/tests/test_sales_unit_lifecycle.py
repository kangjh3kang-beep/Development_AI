"""#6 세대 라이프사이클·추첨 — 순수로직 단위 테스트(라이브 DB 불요).

검증 대상(외부 연결 없이 결정적으로 확인 가능한 로직만):
  · 해시체인 결정론: 같은 입력 → 같은 content_hash, 한 글자만 바뀌어도 다른 해시.
  · 변조탐지 범위: content_hash 변조 / prev_hash 단절 / seq 누락·재정렬·중복은 적발한다.
    단, 끝잘림 tail-truncation 은 앵커 없이 self-탐지 불가 → {valid:True} 가 '의도된 현 한계'임을 단언.
  · IDOR 스코프: verify_chain/unit_timeline 에 site_id 를 주면 WHERE 에 site_id=:s 가 더해진다.
  · 상태머신: 허용 전이만 통과, 불가 전이·미정의 액션 거부.
  · 마스킹: held_by(직원 UUID)는 본인/관리자만 노출, 일반 멤버는 마스킹.

라이브 DB 동시성(advisory-lock seq 직렬화·041 적용)·Redis·tsc 는 deploy-pending(샌드박스 미적용)이라
여기선 코드평가 가능한 순수로직만 다룬다. 동시 append 의 체인 fork 는 UNIQUE(unit_id, seq) +
pg_advisory_xact_lock(append 의 unit 키·트랜잭션 종료 시 자동해제)으로 막으며 이는 통합/라이브 검증 영역이다.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import app.services.sales.units.event_ledger as ledger
from app.api.endpoints.sales.units_live import _mask_held_by
from app.services.sales.units.event_ledger import _hash, unit_timeline, verify_chain
from app.services.sales.units.lifecycle_actions import _TRANSITIONS


@pytest.fixture(autouse=True)
def _ledger_ready(monkeypatch):
    """순수로직 검증이므로 _ensure 의 DDL(별도 단명 세션·실 DB)을 타지 않게 게이트를 미리 닫는다.

    본 iter 부터 _ensure 는 호출자 세션(db)이 아니라 async_session_factory(실 DB)로 DDL 을 수행한다.
    샌드박스엔 라이브 DB 가 없으므로 _READY=True 로 두어 verify_chain/unit_timeline 이 곧장 SELECT 만
    하도록 한다(_ensure 의 실 DB 접속은 deploy-pending 통합/라이브 검증 영역).
    """
    monkeypatch.setattr(ledger, "_READY", True)


# ── 해시체인 결정론 ───────────────────────────────────────────────────────────
class TestHashDeterminism:
    """_hash 는 같은 입력에 항상 같은 결과(결정론), 입력 1바이트 변화에도 전혀 다른 해시."""

    def _h(self, **over):
        base = dict(prev_hash=None, unit_id="u-1", seq=1, event_type="HOLD_REQUEST",
                    to_status="HOLD", message="msg", occurred_at="2026-06-19T00:00:00+00:00",
                    meta={"k": "v"})
        base.update(over)
        return _hash(base["prev_hash"], base["unit_id"], base["seq"], base["event_type"],
                     base["to_status"], base["message"], base["occurred_at"], base["meta"])

    def test_같은_입력_같은_해시(self):
        assert self._h() == self._h()

    def test_sha256_64자_hex(self):
        h = self._h()
        assert len(h) == 64
        int(h, 16)  # hex 파싱 가능(예외 없으면 통과)

    def test_message_한글자_변화로_해시변경(self):
        assert self._h(message="msg") != self._h(message="msh")

    def test_prev_hash_변화로_해시변경(self):
        assert self._h(prev_hash=None) != self._h(prev_hash="a" * 64)

    def test_seq_변화로_해시변경(self):
        assert self._h(seq=1) != self._h(seq=2)

    def test_meta_키순서_무관_정규화(self):
        # sort_keys=True 라 dict 키 입력순서가 달라도 같은 해시(정규화).
        a = self._h(meta={"a": 1, "b": 2})
        b = self._h(meta={"b": 2, "a": 1})
        assert a == b

    def test_None_과_빈값_정규화(self):
        # message=None 과 message='' 는 페이로드에서 '' 로 정규화되어 같은 해시.
        assert self._h(message=None) == self._h(message="")


# ── verify_chain 변조탐지(가짜 세션으로 결정적 검증) ──────────────────────────
class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """verify_chain/unit_timeline 이 요구하는 execute(...).all() 만 흉내내는 최소 가짜 세션.

    verify_chain 은 _ensure(db) 를 먼저 호출하지만, 본 iter 부터 _ensure 는 인자 db 를 쓰지 않고
    별도 단명 세션(async_session_factory)에서 DDL 을 수행하므로 본 가짜 세션은 SELECT 만 응대한다.
    last_select_(sql|params) 에 마지막 SELECT 의 SQL/파라미터를 기록해 site_id 스코프 주입을 검증한다.
    """

    def __init__(self, rows):
        self._rows = rows
        self.last_select_sql: str = ""             # 마지막 SELECT SQL(대문자) — site_id 스코프 검증용
        self.last_select_params: dict = {}         # 마지막 SELECT 파라미터({u, [s]})

    async def execute(self, stmt, params=None):
        sql = str(stmt).upper()
        if sql.startswith("SELECT SEQ"):
            self.last_select_sql = sql
            self.last_select_params = params or {}
            return _FakeResult(self._rows)
        return _FakeResult([])  # 그 외(없음)는 무시

    async def commit(self):
        return None


def _build_chain(events):
    """events=[(event_type,to_status,message,meta_dict)] → verify_chain 행 형식으로 정상 체인 생성.

    행 형식(verify_chain SELECT 순서): (seq, event_type, to_status, message, meta, occurred_iso,
    content_hash, prev_hash). meta 는 dict 그대로(verify_chain 이 dict/문자열 모두 처리).
    """
    rows = []
    prev = None
    for i, (et, ts, msg, meta) in enumerate(events, start=1):
        at_iso = f"2026-06-19T00:00:{i:02d}+00:00"
        chash = _hash(prev, "u-1", i, et, ts, msg, at_iso, meta)
        rows.append((i, et, ts, msg, meta, at_iso, chash, prev))
        prev = chash
    return rows


@pytest.fixture
def good_rows():
    return _build_chain([
        ("HOLD_REQUEST", "HOLD", "선점", None),
        ("CONTRACT_WAIT", "APPLIED", "계약대기", None),
        ("CONTRACT_SIGN", "CONTRACTED", "체결", None),
    ])


class TestVerifyChain:
    # pyproject asyncio_mode='auto' 라 async def test_ 는 마커 없이 자동 수집된다.
    async def test_정상체인_valid(self, good_rows):
        res = await verify_chain(_FakeSession(good_rows), "u-1")
        assert res["valid"] is True
        assert res["events"] == 3

    async def test_content_hash_변조_탐지(self, good_rows):
        rows = list(good_rows)
        # 2번째 행 메시지를 바꾸되 stored content_hash 는 그대로 → 재계산 불일치(변조).
        seq, et, ts, _msg, meta, at_iso, chash, ph = rows[1]
        rows[1] = (seq, et, ts, "변조된메시지", meta, at_iso, chash, ph)
        res = await verify_chain(_FakeSession(rows), "u-1")
        assert res["valid"] is False
        assert res["broken_at"] == 2
        assert "content_hash" in res["reason"]

    async def test_prev_hash_단절_탐지(self, good_rows):
        rows = list(good_rows)
        seq, et, ts, msg, meta, at_iso, chash, _ph = rows[2]
        rows[2] = (seq, et, ts, msg, meta, at_iso, chash, "f" * 64)  # 끊긴 prev_hash
        res = await verify_chain(_FakeSession(rows), "u-1")
        assert res["valid"] is False
        assert res["broken_at"] == 3
        assert "prev_hash" in res["reason"]

    async def test_중간행_삭제_누락_탐지(self, good_rows):
        # 2번 행 삭제 → 남은 행 seq=1,3(단조성 위반) 으로 즉시 적발.
        rows = [good_rows[0], good_rows[2]]
        res = await verify_chain(_FakeSession(rows), "u-1")
        assert res["valid"] is False
        assert res["broken_at"] == 3
        assert "seq" in res["reason"]

    async def test_재정렬_단조성_위반_탐지(self, good_rows):
        # seq 가 1,3,2 처럼 순서가 어긋나면(재정렬) 단조성 검사가 적발.
        rows = [good_rows[0], good_rows[2], good_rows[1]]
        res = await verify_chain(_FakeSession(rows), "u-1")
        assert res["valid"] is False
        assert "seq" in res["reason"]

    async def test_중복seq_단조성_위반_탐지(self, good_rows):
        # seq 가 1,2,2 처럼 중복되면(같은 seq 2행) 단조성 검사가 적발(체인 fork 흔적).
        rows = [good_rows[0], good_rows[1], good_rows[1]]
        res = await verify_chain(_FakeSession(rows), "u-1")
        assert res["valid"] is False
        assert "seq" in res["reason"]

    async def test_빈체인_valid(self):
        res = await verify_chain(_FakeSession([]), "u-1")
        assert res["valid"] is True
        assert res["events"] == 0

    async def test_끝잘림_tail_truncation_은_현재_미탐지(self, good_rows):
        # ★[정직·현 한계 문서화] 가장 최근 이벤트(seq=3)를 통째로 삭제한 tail-truncation 은
        #   남은 1,2 행이 여전히 정합이라 앵커 없이 self-탐지가 불가능하다 → {valid:True} 가 '의도된
        #   현 한계'. 이를 단언해 docstring('truncation 실탐지=앵커 필요·backlog')과 커버리지를 일치시킨다.
        #   (앵커 기반 실탐지가 구현되면 본 테스트는 valid:False 로 뒤집혀 회귀를 알린다.)
        truncated = [good_rows[0], good_rows[1]]  # seq=3 끝잘림
        res = await verify_chain(_FakeSession(truncated), "u-1")
        assert res["valid"] is True  # 현재는 미탐지(앵커 미구현). 실탐지는 backlog.
        assert res["events"] == 2

    async def test_site_id_스코프_WHERE_주입(self, good_rows):
        # ★[security·IDOR] site_id 를 주면 SELECT WHERE 에 site_id=:s 가 더해지고 파라미터로 전달된다.
        sess = _FakeSession(good_rows)
        await verify_chain(sess, "u-1", site_id="site-A")
        assert "SITE_ID=:S" in sess.last_select_sql
        assert sess.last_select_params.get("s") == "site-A"
        assert sess.last_select_params.get("u") == "u-1"

    async def test_site_id_미지정시_세대단위_조회(self, good_rows):
        # site_id 가 None(내부 호출·테스트)이면 WHERE 에 site_id 조건을 넣지 않는다(하위호환).
        sess = _FakeSession(good_rows)
        await verify_chain(sess, "u-1")
        assert "SITE_ID=:S" not in sess.last_select_sql
        assert "s" not in (sess.last_select_params or {})


class TestUnitTimelineScope:
    """unit_timeline 도 site_id 스코프 시 WHERE 에 site_id=:s 를 더한다(교차테넌트 IDOR 차단).

    unit_timeline 의 SELECT 컬럼 형식(9개)은 verify_chain(8개)과 다르므로, 여기선 행 파싱이 아니라
    WHERE 스코프 주입만 검증한다(빈 rows 로 루프를 건너뛰고 last_select_* 만 확인).
    """

    async def test_timeline_site_id_스코프_주입(self):
        sess = _FakeSession([])
        await unit_timeline(sess, "u-1", site_id="site-A")
        assert "SITE_ID=:S" in sess.last_select_sql
        assert sess.last_select_params.get("s") == "site-A"
        assert sess.last_select_params.get("u") == "u-1"

    async def test_timeline_site_id_미지정_하위호환(self):
        sess = _FakeSession([])
        await unit_timeline(sess, "u-1")
        assert "SITE_ID=:S" not in sess.last_select_sql
        assert "s" not in sess.last_select_params


# ── 상태머신(_TRANSITIONS) ────────────────────────────────────────────────────
class TestStateMachine:
    def test_허용전이_정의(self):
        assert _TRANSITIONS["HOLD_REQUEST"] == ({"AVAILABLE"}, "HOLD")
        assert _TRANSITIONS["HOLD_CANCEL"] == ({"HOLD"}, "AVAILABLE")
        assert _TRANSITIONS["CONTRACT_SIGN"][1] == "CONTRACTED"
        assert _TRANSITIONS["CONTRACT_TERMINATE"] == ({"CONTRACTED"}, "CANCELLED")

    def test_HOLD_REQUEST_는_AVAILABLE에서만(self):
        allowed_from, _to = _TRANSITIONS["HOLD_REQUEST"]
        assert "AVAILABLE" in allowed_from
        assert "CONTRACTED" not in allowed_from  # 계약된 세대는 재선점 불가

    def test_계약취소_는_APPLIED에서만(self):
        allowed_from, to = _TRANSITIONS["CONTRACT_CANCEL"]
        assert allowed_from == {"APPLIED"}
        assert to == "AVAILABLE"

    def test_미정의_액션은_매핑에_없음(self):
        # unit_action 이 _TRANSITIONS 미포함 액션을 거부하는 근거(NOTE 제외).
        assert "FOO_BAR" not in _TRANSITIONS
        assert "NOTE" not in _TRANSITIONS  # NOTE 는 상태변화 없는 특수경로(별도 처리)


# ── held_by 마스킹(개인정보) ──────────────────────────────────────────────────
class TestMaskHeldBy:
    def test_미점유_노출없음(self):
        assert _mask_held_by(None, "me", "MEMBER") == {
            "held": False, "held_by_me": False, "held_by": None}

    def test_본인점유_본인에게_노출(self):
        m = _mask_held_by("me", "me", "MEMBER")
        assert m["held"] is True and m["held_by_me"] is True and m["held_by"] == "me"

    def test_타인점유_일반멤버는_마스킹(self):
        m = _mask_held_by("staff-x", "me", "MEMBER")
        assert m["held"] is True
        assert m["held_by_me"] is False
        assert m["held_by"] is None  # 일반 멤버에겐 직원 신원 숨김

    @pytest.mark.parametrize("role", ["DEVELOPER", "AGENCY", "SUPERADMIN", "DIRECTOR", "GM_DIRECTOR"])
    def test_관리자군은_타인점유도_노출(self, role):
        m = _mask_held_by("staff-x", "me", role)
        assert m["held_by"] == "staff-x"  # 관리자군은 점유자 신원 확인 가능

    def test_권한없는_역할은_타인_마스킹(self):
        for role in ("MEMBER", "VIEWER", "", None):
            assert _mask_held_by("staff-x", "me", role)["held_by"] is None
