"""마이페이지(코인 주문·원장·프로필·동의이력) 회귀가드 — 무 DB 결정적 검증.

- 순수 로직: 주문 금액 서버결정(resolve_order_amount), CSV 포뮬러 인젝션 방어(_csv_safe),
  원장 해시체인 캐스케이드(_chain_hash).
- 계약: 인증 필수(401/403), 패키지 공개, 검증 실패 400/404, 시뮬레이션 결제 게이트(기본 501).
- 멱등: confirm/cancel의 pending 원자 전이(FakeSession).

실 DB append/조회/UNION 타임라인은 통합 환경에서 검증(그레이스풀 폴백은 여기서 고정).
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from apps.api.auth.jwt_handler import create_access_token  # noqa: E402


def _auth_headers() -> dict[str, str]:
    """무 DB 인증 헤더 — get_current_user는 JWT 서명 검증만 하므로 실 DB 불필요."""
    token = create_access_token(uuid.uuid4(), uuid.uuid4(), "admin")
    return {"Authorization": f"Bearer {token}"}


# ── 순수: 주문 금액은 서버가 결정 ──
class TestResolveOrderAmount:
    def test_preset_ignores_client_amount(self):
        from app.services.billing.coin_orders_service import resolve_order_amount

        # 프리셋 키면 클라이언트 금액(1원 조작 시도)은 무시되고 서버 금액이 확정된다.
        assert resolve_order_amount("starter", 1.0) == 10_000.0
        assert resolve_order_amount("max", None) == 300_000.0

    def test_custom_range_and_unit(self):
        from app.services.billing.coin_orders_service import resolve_order_amount

        assert resolve_order_amount("custom", 5_000) == 5_000.0
        with pytest.raises(ValueError):
            resolve_order_amount("custom", 999)  # 최소 미만
        with pytest.raises(ValueError):
            resolve_order_amount("custom", 1_000_001)  # 최대 초과
        with pytest.raises(ValueError):
            resolve_order_amount("custom", 5_050.5)  # 단위 위반
        with pytest.raises(ValueError):
            resolve_order_amount("custom", None)  # 금액 누락

    def test_unknown_package_rejected(self):
        from app.services.billing.coin_orders_service import resolve_order_amount

        with pytest.raises(ValueError):
            resolve_order_amount("free_money", 10)


# ── 순수: CSV 포뮬러 인젝션 방어 ──
class TestCsvSafe:
    def test_formula_prefixes_escaped(self):
        from routers.billing import _csv_safe

        assert _csv_safe("=SUM(A1:A9)").startswith("'=")
        assert _csv_safe("+cmd").startswith("'+")
        assert _csv_safe("@import").startswith("'@")
        assert _csv_safe("-rf /").startswith("'-")  # 숫자가 아닌 하이픈 텍스트는 이스케이프

    def test_negative_numbers_not_corrupted(self):
        from routers.billing import _csv_safe

        # 음수 금액(차감)은 데이터 — 이스케이프하면 안 된다.
        assert _csv_safe(-1500.0) == "-1500.0"
        assert _csv_safe("-42") == "-42"

    def test_rfc4180_quoting(self):
        from routers.billing import _csv_safe

        assert _csv_safe('충전, "테스트"') == '"충전, ""테스트"""'


# ── 순수: 원장 해시체인 캐스케이드 ──
class TestCoinLedgerChain:
    def test_chain_hash_folds_prev_and_seq(self):
        from app.services.billing.coin_ledger_service import _chain_hash, _event_payload

        p = _event_payload("u1", "order_paid", 10_000, "충전", "coin_order", "o1")
        genesis = _chain_hash(p, None, 1)
        chained = _chain_hash(p, "abc", 2)
        assert genesis != chained                       # prev/seq가 해시에 접힘
        assert _chain_hash(p, "abc", 2) != _chain_hash(p, "xyz", 2)  # 캐스케이드
        p2 = _event_payload("u1", "order_paid", 10_001, "충전", "coin_order", "o1")
        assert _chain_hash(p, None, 1) != _chain_hash(p2, None, 1)   # 금액 변조 탐지

    def test_chain_hash_folds_actor_and_tenant(self):
        # ★감사 무결성: created_by(행위자)·tenant_id(스코프) 위조 시 해시가 깨져 verify가 탐지.
        from app.services.billing.coin_ledger_service import _chain_hash, _event_payload

        a = _event_payload("u1", "admin_adjust", 100, "조정", "admin", "a1", created_by="admin-A", tenant_id="t1")
        b = _event_payload("u1", "admin_adjust", 100, "조정", "admin", "a1", created_by="admin-B", tenant_id="t1")
        c = _event_payload("u1", "admin_adjust", 100, "조정", "admin", "a1", created_by="admin-A", tenant_id="t2")
        assert _chain_hash(a, None, 1) != _chain_hash(b, None, 1)  # 행위자 재귀속 탐지
        assert _chain_hash(a, None, 1) != _chain_hash(c, None, 1)  # 테넌트 이동 탐지

    def test_amount_encoding_deterministic(self):
        from app.services.billing.coin_ledger_service import _event_payload

        # 금액은 고정 소수점 문자열 — float 재해석(DB 왕복)에도 해시 결정성 유지.
        assert _event_payload("u", "topup", 1234.56, None, None, None)["amount_krw"] == "1234.56"
        assert _event_payload("u", "topup", 10_000, None, None, None)["amount_krw"] == "10000.00"

    def test_unknown_entry_type_rejected(self):
        import asyncio

        from app.services.billing.coin_ledger_service import append_event

        out = asyncio.run(append_event(user_id="u1", entry_type="hack", amount_krw=1))
        assert out["persisted"] is False

    def test_filter_groups_are_subset_of_entry_types(self):
        # ★SQL 안전 불변식: 그룹 멤버가 리터럴로 SQL에 삽입되므로 반드시 코드 상수(ENTRY_TYPES)여야 한다.
        from app.services.billing.coin_ledger_service import ENTRY_TYPES, FILTER_GROUPS

        for members in FILTER_GROUPS.values():
            for m in members:
                assert m in ENTRY_TYPES
                assert m.replace("_", "").isalnum()  # 따옴표·세미콜론 등 주입 문자 부재

    def test_legal_retention_is_five_years(self):
        from app.services.billing.coin_orders_service import LEGAL_RETENTION_DAYS

        assert LEGAL_RETENTION_DAYS >= 5 * 365  # 전상법 §6 대금결제 기록 5년


# ── FakeSession — 멱등 전이 검증(pending 원자 UPDATE) ──
class _FakeMappingResult:
    def __init__(self, mapping=None, mappings_list=None):
        self._m = mapping
        self._list = mappings_list or ([] if mapping is None else [mapping])

    def first(self):
        return self._m

    def all(self):
        return self._list


class _FakeResult:
    def __init__(self, row=None, mapping=None, scalar=None):
        self._row = row
        self._mapping = mapping
        self._scalar = scalar

    def first(self):
        return self._row

    def scalar(self):
        return self._scalar

    def mappings(self):
        return _FakeMappingResult(self._mapping)


class FakeSession:
    """SQL 본문 부분일치 → 응답 매핑. 그 외 INSERT/DDL은 캡처만."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.executed = []
        self.committed = 0

    async def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.executed.append((sql, params or {}))
        for needle, result in self.responses:
            if needle in sql:
                return result
        return _FakeResult()

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass


class TestConfirmIdempotency:
    async def test_confirm_already_processed_raises(self):
        from app.services.billing import coin_orders_service as svc

        # UPDATE … WHERE status='pending' 미적중(이미 paid/취소) → 지급·원장 기록 없이 예외.
        sess = FakeSession(responses=[("UPDATE coin_orders SET status='paid'", _FakeResult(mapping=None))])
        with pytest.raises(svc.OrderNotConfirmableError):
            await svc.confirm_order(
                sess, order_id=str(uuid.uuid4()), owner_user_id="u1", provider="manual"
            )
        assert sess.committed == 0  # 커밋 없음(부작용 없음)
        assert not any("UPDATE public.users" in s for s, _ in sess.executed)

    async def test_confirm_pending_grants_and_ledgers_in_one_txn(self):
        from app.services.billing import coin_orders_service as svc

        oid = str(uuid.uuid4())
        paid_row = {"id": oid, "order_no": "CO20260717-ABCD", "coin_krw": 50_000, "tenant_id": None}
        sess = FakeSession(responses=[
            ("UPDATE coin_orders SET status='paid'", _FakeResult(mapping=paid_row)),
        ])
        out = await svc.confirm_order(sess, order_id=oid, owner_user_id="u1", provider="manual")
        assert out["status"] == "paid" and out["coin_krw"] == 50_000.0
        joined = [s for s, _ in sess.executed]
        assert any("UPDATE public.users SET topup_krw" in s for s in joined)  # 잔액 증액
        assert any("INSERT INTO coin_ledger_events" in s for s in joined)      # 원장 동반
        assert sess.committed == 1  # 단일 트랜잭션 커밋

    async def test_cancel_only_pending(self):
        from app.services.billing import coin_orders_service as svc

        sess = FakeSession(responses=[("UPDATE coin_orders SET status='canceled'", _FakeResult(mapping=None))])
        with pytest.raises(svc.OrderNotConfirmableError):
            await svc.cancel_order(sess, order_id=str(uuid.uuid4()), user_id="u1")


# ── HTTP 계약(무 DB) ──
class TestHttpContracts:
    async def test_packages_public_and_server_priced(self, client):
        r = await client.get("/api/v1/billing/packages")
        assert r.status_code == 200
        body = r.json()
        amounts = {p["key"]: p["amount_krw"] for p in body["packages"]}
        assert amounts["starter"] == 10_000 and amounts["max"] == 300_000
        assert body["custom"]["min_krw"] == 1_000 and body["custom"]["max_krw"] == 1_000_000

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/v1/billing/orders"),
        ("post", "/api/v1/billing/orders"),
        ("post", "/api/v1/billing/orders/x/confirm"),
        ("post", "/api/v1/billing/orders/x/cancel"),
        ("get", "/api/v1/billing/ledger"),
        ("get", "/api/v1/billing/ledger/verify"),
        ("get", "/api/v1/billing/ledger/export"),
        ("patch", "/api/v1/auth/me"),
        ("get", "/api/v1/auth/me/consents"),
        ("post", "/api/v1/auth/me/consents/marketing"),
    ])
    async def test_requires_authentication(self, client, method, path):
        if method in ("post", "patch"):
            r = await getattr(client, method)(path, json={})
        else:
            r = await getattr(client, method)(path)
        assert r.status_code in (401, 403)

    async def test_create_order_rejects_unknown_package(self, client):
        r = await client.post(
            "/api/v1/billing/orders",
            json={"package_key": "free_money"},
            headers=_auth_headers(),
        )
        assert r.status_code == 400

    async def test_create_order_rejects_bad_custom_amount(self, client):
        r = await client.post(
            "/api/v1/billing/orders",
            json={"package_key": "custom", "amount_krw": 999},
            headers=_auth_headers(),
        )
        assert r.status_code == 400

    async def test_self_confirm_gated_off_by_default(self, client):
        # ★프로덕션 기본: 시뮬레이션 결제 꺼짐 → 501 정직 응답(사용자 자가지급 불가).
        r = await client.post(
            f"/api/v1/billing/orders/{uuid.uuid4()}/confirm",
            headers=_auth_headers(),
        )
        assert r.status_code == 501

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "0", "-100"])
    async def test_topup_rejects_non_finite_or_nonpositive(self, client, bad):
        # ★성장루프 LOW 수렴: NaN/Infinity/음수/0 금액은 422로 차단(예산 오염 방지).
        #   NaN/Infinity는 JSON 리터럴(따옴표 없음)로 보내야 실제 취약점 재현 — 원시 바디 구성.
        #   (스키마 검증이 활성계정 가드·시뮬레이션 게이트보다 앞서므로 무 DB로 422 확인 가능.)
        r = await client.post(
            "/api/v1/billing/topup",
            content=f'{{"amount_krw": {bad}}}',
            headers={**_auth_headers(), "Content-Type": "application/json"},
        )
        # 400(본문 isfinite/양수 하드가드) 또는 422(pydantic gt=0/allow_inf_nan) — 어느 쪽이든 차단.
        assert r.status_code in (400, 422)

    async def test_legacy_topup_gated_off_by_default(self, client):
        # ★성장루프 HIGH 수렴: 레거시 /topup 무결제 자가충전이 프로덕션(플래그 off)에서
        #   403으로 차단되는지 — 신규 결제 게이트를 우회하지 못하게 한다.
        r = await client.post(
            "/api/v1/billing/topup",
            json={"amount_krw": 1000000},
            headers=_auth_headers(),
        )
        assert r.status_code == 403

    async def test_packages_expose_payment_mode(self, client):
        # 프론트가 결제 확정 버튼을 정직하게 게이트하도록 payment_mode 노출(기본 manual_only).
        r = await client.get("/api/v1/billing/packages")
        assert r.status_code == 200
        assert r.json()["payment_mode"] == "manual_only"

    async def test_cancel_invalid_uuid_is_404_not_500(self, client):
        r = await client.post(
            "/api/v1/billing/orders/not-a-uuid/cancel",
            headers=_auth_headers(),
        )
        assert r.status_code == 404

    async def test_patch_me_validates_phone(self, client):
        r = await client.patch(
            "/api/v1/auth/me",
            json={"phone": "abc-def"},
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    async def test_patch_me_rejects_blank_name(self, client):
        r = await client.patch(
            "/api/v1/auth/me",
            json={"name": "   "},
            headers=_auth_headers(),
        )
        assert r.status_code == 422

    async def test_marketing_consent_requires_agreed_field(self, client):
        # 스키마 검증(무 DB): agreed 필수 — 누락 시 활성계정 가드(DB) 이전에 422.
        r = await client.post(
            "/api/v1/auth/me/consents/marketing",
            json={},
            headers=_auth_headers(),
        )
        assert r.status_code == 422
