"""#9 해촉·전매·MH — 머니패스/개인정보/발송 silent-fail 순수로직 회귀 안전망(Wave2 P1).

DB·라이브 발송·공공API 는 sandbox 미가용(deploy-pending) — 여기선 순수로직과 가짜 async 세션으로
다음 회귀를 영구 차단한다.

- resale 전매 상태머신:
    · request_transfer  : site_id 격리(타현장 계약 차단)·중복 PENDING 요청 멱등(중복 행 금지).
    · decide_transfer   : 이미 결정된 요청 재결정 차단(이중 명의변경 차단)·승인 1회만 명의변경.
    · create_realtx_report : 중복 PENDING 신고 멱등·신고기한(파라미터) 산정.
- cert 개인정보·SSRF:
    · mask_rrn          : 'YYMMDD-1******' 표준 마스킹(뒤 6자리 가림)·형식불명 견고.
    · _is_blocked_ip    : 사설/루프백/링크로컬(메타데이터)/해석불가 차단(SSRF).
    · _fetch_stamp_flowable : file://·내부망 호스트는 fetch 전 차단(네트워크 미접촉) → None 폴백.
- mh 동의 게이트:
    · has_required_consent : 필수동의(REQUIRED) 미동의 시 등록 차단(개인정보보호법 제15조).
    · marketing_allowed    : MARKETING 동의 행이 agreed=True 일 때만 True(미동의 발송 차단).
    · enrich_consent       : 고지문 메타(이용목적·보유기간) 결합.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid as uuid_mod
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.sales.cert.termination_cert_pdf import (  # noqa: E402
    _fetch_stamp_flowable,
    _is_blocked_ip,
    mask_rrn,
)
from app.services.sales.mh.consent import (  # noqa: E402
    REQUIRED_TYPES,
    enrich_consent,
    has_required_consent,
)
from app.services.sales.resale import service as resale  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ── 가짜 ORM 행/세션(순수로직 — DB 미접촉) ──────────────────────────────────────
class _Row:
    """필드를 자유롭게 받는 가짜 ORM 행."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


class _ScalarResult:
    """execute() 결과 — scalar_one_or_none()/scalars().first()/scalars() 를 흉내낸다."""

    def __init__(self, items):
        self._items = list(items)

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return _Scalars(self._items)


class _Scalars:
    def __init__(self, items):
        self._items = list(items)

    def first(self):
        return self._items[0] if self._items else None

    def __iter__(self):
        return iter(self._items)

    def all(self):
        return list(self._items)


class _Savepoint:
    """db.begin_nested() 가 돌려주는 async 컨텍스트 매니저 흉내(SAVEPOINT)."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False  # 예외를 삼키지 않음(서비스가 IntegrityError 를 잡도록)


class _FakeDB:
    """resale 서비스용 가짜 async 세션. execute() 는 미리 넣어둔 결과를 순서대로 돌려준다.

    with_for_update()/where() 등은 select 객체에서 호출되므로 세션은 관여하지 않는다.
    flush_raises=[횟수목록] 을 주면 해당 순번 flush 에서 IntegrityError 를 던져 TOCTOU 경합을 흉내낸다.
    """

    def __init__(self, results, flush_raises=None):
        self._results = list(results)
        self._i = 0
        self.added = []
        self.flushed = 0
        self._flush_raises = set(flush_raises or [])

    async def execute(self, _stmt):
        res = self._results[self._i]
        self._i += 1
        return _ScalarResult(res)

    def add(self, obj):
        self.added.append(obj)

    def begin_nested(self):
        return _Savepoint()

    async def flush(self):
        self.flushed += 1
        if self.flushed in self._flush_raises:
            from sqlalchemy.exc import IntegrityError
            raise IntegrityError("stmt", {}, Exception("duplicate key (23505)"))


SID = uuid_mod.uuid4()
OTHER_SID = uuid_mod.uuid4()
CONTRACT = uuid_mod.uuid4()
CUST_A = uuid_mod.uuid4()
CUST_B = uuid_mod.uuid4()


# ── 1) mask_rrn — 개인정보 표준 마스킹 ─────────────────────────────────────────
class TestMaskRrn:
    def test_standard_13_digits(self):
        """13자리 주민번호 → 앞 6 + 성별 1자리만 노출, 나머지 6자리 '*'."""
        assert mask_rrn("9001011234567") == "900101-1******"

    def test_with_hyphen(self):
        """하이픈 포함 입력도 숫자만 추출해 동일 마스킹."""
        assert mask_rrn("900101-2345678") == "900101-2******"

    def test_none_and_empty(self):
        assert mask_rrn(None) == "-"
        assert mask_rrn("") == "-"

    def test_no_full_rrn_leak(self):
        """★핵심: 출력에 뒤 6자리(고유식별번호)가 평문으로 남으면 안 된다."""
        out = mask_rrn("9001011234567")
        assert "234567" not in out  # 뒤 6자리 평문 노출 금지
        assert out.count("*") == 6

    def test_unknown_format_partial(self):
        """형식 불명(자릿수 부족)도 앞 일부만 노출하고 나머지는 가린다."""
        out = mask_rrn("12345678")
        assert out.startswith("123456")
        assert "78" not in out  # 6자리 초과분은 마스킹


# ── 2) SSRF 차단 — 직인 fetch ──────────────────────────────────────────────────
class TestStampSsrf:
    def test_blocks_loopback(self):
        assert _is_blocked_ip("127.0.0.1") is True

    def test_blocks_private(self):
        assert _is_blocked_ip("10.0.0.5") is True
        assert _is_blocked_ip("192.168.1.1") is True
        assert _is_blocked_ip("172.16.0.1") is True

    def test_blocks_link_local_metadata(self):
        """클라우드 메타데이터(169.254.169.254) 차단 — SSRF 핵심 표적."""
        assert _is_blocked_ip("169.254.169.254") is True

    def test_blocks_cgnat(self):
        """★CGNAT(100.64.0.0/10) 차단 — is_private/is_link_local 에 안 잡히던 비공인 대역(allowlist 화)."""
        assert _is_blocked_ip("100.64.0.1") is True
        assert _is_blocked_ip("100.127.255.254") is True

    def test_allows_public_ip(self):
        """공인 라우팅 주소는 차단하지 않는다(allowlist=is_global True 통과) — 무회귀."""
        assert _is_blocked_ip("8.8.8.8") is False
        assert _is_blocked_ip("1.1.1.1") is False

    def test_blocks_unresolvable_host(self):
        """해석 불가 호스트는 '안전 우선'으로 차단(True)."""
        assert _is_blocked_ip("this-host-does-not-exist.invalid") is True

    def test_fetch_blocks_file_scheme(self):
        """file:// 스킴은 fetch 전에 차단 → None(네트워크/로컬자원 미접촉)."""
        assert _fetch_stamp_flowable("file:///etc/passwd", 1) is None

    def test_fetch_blocks_internal_host(self):
        """내부 IP 직접 지정 URL 은 fetch 전 차단 → None."""
        assert _fetch_stamp_flowable("http://169.254.169.254/latest/meta-data/", 1) is None
        assert _fetch_stamp_flowable("http://127.0.0.1:8000/secret", 1) is None

    def test_fetch_none_url(self):
        assert _fetch_stamp_flowable(None, 1) is None


# ── 3) resale 전매 상태머신 — 격리·멱등 ────────────────────────────────────────
class TestResaleTransfer:
    def test_request_isolation_blocks_cross_site_contract(self):
        """타현장 계약 id 를 넘기면 _load_contract_scoped 가 '찾을 수 없음'으로 거부(IDOR 차단)."""
        # 첫 execute(계약 로드)가 빈 결과 → ValueError.
        db = _FakeDB(results=[[]])
        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            _run(resale.request_transfer(db, SID, CONTRACT, CUST_B, "RESALE"))

    def test_request_idempotent_returns_existing_pending(self):
        """같은 계약에 이미 PENDING 전매요청이 있으면 새 행을 만들지 않고 기존 건 반환(중복 차단)."""
        contract = _Row(id=CONTRACT, site_id=SID, customer_id=CUST_A,
                        unit_id=uuid_mod.uuid4(), round_id=uuid_mod.uuid4())
        existing = _Row(id=uuid_mod.uuid4(), allowed=True, reason=None, decided_at=None,
                        transfer_type="RESALE")
        # execute 순서(중복 즉시반환): ①계약 ②기존 PENDING
        db = _FakeDB(results=[[contract], [existing]])
        res = _run(resale.request_transfer(db, SID, CONTRACT, CUST_B, "RESALE"))
        assert res["duplicate"] is True
        assert res["transfer_id"] == str(existing.id)
        assert db.added == []  # 새 transfer 행 생성 안 됨(멱등)

    def test_request_duplicate_surfaces_existing_transfer_type(self):
        """★과대매칭 해소: RESALE 대기 중 NAME_CHANGE 요청해도 기존 종류(RESALE)를 응답에 노출(silent-swallow 방지)."""
        contract = _Row(id=CONTRACT, site_id=SID, customer_id=CUST_A,
                        unit_id=uuid_mod.uuid4(), round_id=uuid_mod.uuid4())
        existing = _Row(id=uuid_mod.uuid4(), allowed=True, reason=None, decided_at=None,
                        transfer_type="RESALE")
        db = _FakeDB(results=[[contract], [existing]])
        res = _run(resale.request_transfer(db, SID, CONTRACT, CUST_B, "NAME_CHANGE"))
        assert res["duplicate"] is True
        assert res["transfer_type"] == "RESALE"  # 기존 종류 노출(NAME_CHANGE 가 RESALE 로 위장되지 않음)
        assert db.added == []

    def test_request_toctou_integrity_error_relooks_up(self):
        """★TOCTOU 봉합: SELECT 직후 동시 INSERT 가 들어와 부분유니크 위반(IntegrityError)이 나면
        기존 PENDING 을 재조회해 graceful 반환(미가공 500 금지·중복행 0)."""
        contract = _Row(id=CONTRACT, site_id=SID, customer_id=CUST_A,
                        unit_id=uuid_mod.uuid4(), round_id=uuid_mod.uuid4())
        winner = _Row(id=uuid_mod.uuid4(), allowed=True, reason=None, decided_at=None,
                      transfer_type="RESALE")
        # execute 순서: ①계약 ②기존없음 ③제한없음 ④(flush 실패 후)재조회=winner. flush #1 에서 IntegrityError.
        db = _FakeDB(results=[[contract], [], [], [winner]], flush_raises=[1])
        res = _run(resale.request_transfer(db, SID, CONTRACT, CUST_B, "RESALE"))
        assert res["duplicate"] is True
        assert res["transfer_id"] == str(winner.id)  # 경합 승자 행 반환

    def test_request_creates_when_no_pending(self):
        """PENDING 없고 제한기간도 없으면 allowed=True 로 새 요청 생성."""
        contract = _Row(id=CONTRACT, site_id=SID, customer_id=CUST_A,
                        unit_id=uuid_mod.uuid4(), round_id=uuid_mod.uuid4())
        db = _FakeDB(results=[[contract], [], []])  # 계약·기존없음·제한없음
        res = _run(resale.request_transfer(db, SID, CONTRACT, CUST_B, "RESALE"))
        assert res["allowed"] is True
        assert len(db.added) == 1  # 새 transfer 1건 생성

    def test_decide_blocks_already_decided(self):
        """★이중 명의변경 차단: 이미 결정된 요청은 재결정하지 않는다(상태머신 종결)."""
        decided = _Row(id=uuid_mod.uuid4(), site_id=SID, allowed=True, reason="ok",
                       decided_at=datetime.now(UTC), contract_ext_id=CONTRACT, to_customer=CUST_B)
        db = _FakeDB(results=[[decided]])  # transfer 로드만(계약 재로드로 안 감)
        res = _run(resale.decide_transfer(db, decided.id, allowed=False, reason="flip", site_id=SID))
        assert res["already_decided"] is True
        assert res["allowed"] is True  # 기존 결정 유지(반려로 뒤집히지 않음)
        assert db.flushed == 0  # 아무 것도 쓰지 않음

    def test_decide_not_found(self):
        db = _FakeDB(results=[[]])
        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            _run(resale.decide_transfer(db, uuid_mod.uuid4(), allowed=True, site_id=SID))

    def test_decide_approve_changes_owner_once(self):
        """승인 시 계약 customer_id 를 to_customer 로 1회만 변경."""
        pending = _Row(id=uuid_mod.uuid4(), site_id=SID, allowed=False, reason=None,
                       decided_at=None, contract_ext_id=CONTRACT, to_customer=CUST_B)
        contract = _Row(id=CONTRACT, site_id=SID, customer_id=CUST_A)
        db = _FakeDB(results=[[pending], [contract]])  # transfer·계약
        res = _run(resale.decide_transfer(db, pending.id, allowed=True, reason="승인", site_id=SID))
        assert res["allowed"] is True
        assert contract.customer_id == CUST_B  # 명의변경 반영
        assert pending.decided_at is not None  # 결정 확정


# ── 4) create_realtx_report — 멱등·기한 ────────────────────────────────────────
class TestRealtxReport:
    def test_idempotent_returns_existing_pending(self):
        """같은 계약의 PENDING 신고가 있으면 새로 만들지 않고 기존 건 반환."""
        contract = _Row(id=CONTRACT, site_id=SID, signed_at=None, unit_id=uuid_mod.uuid4(),
                        total_price=100000000)
        existing = _Row(id=uuid_mod.uuid4(), status="PENDING")
        db = _FakeDB(results=[[contract], [existing]])  # 계약·기존 PENDING
        res = _run(resale.create_realtx_report(db, SID, CONTRACT))
        assert res is existing
        assert db.added == []  # 중복 신고 생성 안 됨

    def test_creates_with_due_date(self):
        """PENDING 없으면 신고기한(기본 30일) 산정해 새 신고 생성."""
        signed = datetime(2026, 1, 1, tzinfo=UTC)
        contract = _Row(id=CONTRACT, site_id=SID, signed_at=signed, unit_id=uuid_mod.uuid4(),
                        total_price=100000000)
        cfg = _Row(site_id=SID, stage_def={})  # realtx_report_days 미설정 → 기본 30
        db = _FakeDB(results=[[contract], [], [cfg]])  # 계약·기존없음·cfg
        _run(resale.create_realtx_report(db, SID, CONTRACT))
        assert len(db.added) == 1
        created = db.added[0]
        # 2026-01-01 + 30일 = 2026-01-31
        assert created.due_date.isoformat() == "2026-01-31"

    def test_isolation_blocks_cross_site(self):
        db = _FakeDB(results=[[]])  # 계약 로드 실패(타현장)
        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            _run(resale.create_realtx_report(db, SID, CONTRACT))

    def test_toctou_integrity_error_relooks_up(self):
        """★TOCTOU 봉합: 신고 INSERT 가 부분유니크 위반(IntegrityError)나면 기존 PENDING 재조회·반환."""
        contract = _Row(id=CONTRACT, site_id=SID, signed_at=None, unit_id=uuid_mod.uuid4(),
                        total_price=100000000)
        cfg = _Row(site_id=SID, stage_def={})
        winner = _Row(id=uuid_mod.uuid4(), status="PENDING")
        # 순서: ①계약 ②기존없음 ③cfg ④(flush 실패 후)재조회=winner. flush #1 에서 IntegrityError.
        db = _FakeDB(results=[[contract], [], [cfg], [winner]], flush_raises=[1])
        res = _run(resale.create_realtx_report(db, SID, CONTRACT))
        assert res is winner  # 경합 승자 기존 PENDING 반환(미가공 예외 전파 안 함)


# ── 4b) submit_realtx — 종결가드(머니패스 서류 보호) ───────────────────────────
class TestSubmitRealtx:
    def test_overwrites_when_pending(self):
        """PENDING 신고는 제출 처리로 status/report_no 가 정상 기록된다."""
        rpt = _Row(id=uuid_mod.uuid4(), site_id=SID, status="PENDING",
                   report_no=None, reported_at=None)
        db = _FakeDB(results=[[rpt]])
        res = _run(resale.submit_realtx(db, SID, rpt.id, {"status": "SUBMITTED", "report_no": "R-1"}))
        assert res.status == "SUBMITTED"
        assert res.report_no == "R-1"
        assert db.flushed == 1

    def test_idempotent_skip_when_already_submitted(self):
        """★종결가드: 이미 SUBMITTED 신고를 재제출(report_no 없이)해도 기존 접수번호가 소실되지 않는다."""
        rpt = _Row(id=uuid_mod.uuid4(), site_id=SID, status="SUBMITTED",
                   report_no="R-EXISTING", reported_at=datetime.now(UTC))
        db = _FakeDB(results=[[rpt]])
        res = _run(resale.submit_realtx(db, SID, rpt.id, {}))  # report_no 없는 재제출
        assert res.report_no == "R-EXISTING"  # 덮어쓰지 않음(None 으로 소실 안 됨)
        assert res.status == "SUBMITTED"
        assert db.flushed == 0  # 쓰기 없음(멱등 반환)

    def test_not_found_cross_site(self):
        db = _FakeDB(results=[[]])
        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            _run(resale.submit_realtx(db, SID, uuid_mod.uuid4(), {"status": "SUBMITTED"}))


# ── 5) mh 동의 게이트 ──────────────────────────────────────────────────────────
class TestConsentGate:
    def test_required_missing_blocks(self):
        """필수동의 미동의(또는 누락) → False(등록 차단)."""
        assert has_required_consent([]) is False
        assert has_required_consent([{"type": "MARKETING", "agreed": True}]) is False

    def test_required_present_allows(self):
        consents = [{"type": t, "agreed": True} for t in REQUIRED_TYPES]
        assert has_required_consent(consents) is True

    def test_required_not_agreed_blocks(self):
        """필수 type 이 있어도 agreed=False 면 차단."""
        consents = [{"type": t, "agreed": False} for t in REQUIRED_TYPES]
        assert has_required_consent(consents) is False

    def test_enrich_attaches_template_meta(self):
        """저장용 보강 — 고지문의 이용목적·보유기간이 결합된다."""
        e = enrich_consent({"type": "MARKETING", "agreed": True})
        assert e["agreed"] is True
        assert e["purpose"]  # 고지문 메타 결합
        assert e["retention"]
        assert e["version"]
