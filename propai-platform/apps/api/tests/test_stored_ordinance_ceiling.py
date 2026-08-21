"""저장된 조례 해석이 **법정상한 가드를 우회**한다 — 가드보다 위에서 return 하기 때문이다.

【라이브 실측 2026-08-21 · 168 propai-api-8000 / propai-v002674-e06b7aad】
`ordinance_resolutions` 저장 **62행** 중 **6행이 법정상한 초과**였고, 오늘도 그대로
화면에 나간다(전부 가드 도입 2026-08-19 **이전** 저장분):

    포항시   제2종일반주거지역  far 500 (법정 250) · bcr 70 (60)   2026-07-29
    의정부시 자연녹지지역      bcr 40  (법정 20)                    2026-07-22
    평택시   자연녹지지역      bcr 40  (법정 20)                    2026-08-05
    포항시   자연녹지지역      bcr 30  (법정 20)                    2026-07-30
    원주시   계획관리지역      bcr 50  (법정 40)                    2026-08-12
    포항시   계획관리지역      bcr 50  (법정 40)                    2026-07-24

【왜 가드가 안 잡았나】`enforce_national_ceiling` 은 **파싱 경로**에만 걸려 있다.
`get_ordinance_limits` 의 0차 저장본 조회는 그 가드보다 **위에서 곧장 return** 한다
— 처방이 환자에게 닿지 않는 그 형태다.

【확증 — 신선 파싱은 옳다】같은 실행에서 `_fetch_from_moleg_api("의정부시", 자연녹지)`
→ `bcr: 20`(가드 통과). 저장본만 40 이다. 즉 **기각하면 자가치유된다.**

【★왜 실효값만 보면 놓치나】`effective_*` 는 `min(법정, 조례)` 로 이미 깎여 정상이다
(라이브 6행 **전부** 그렇다). 그런데 화면 "② 조례 적용" 칸은 **조례값을 그대로 표시**한다
— 실효값만 검사하면 위반 0으로 보인다.
"""

import asyncio
import json

from app.services.land_intelligence import ordinance_service as M

# ── 두 모집단 — **다른 판정**을 받아야 한다(같으면 판별을 끊어도 초록) ──────────────
_VIOLATING = {
    "sigungu": "의정부시", "zone_type": "자연녹지지역", "source": "법제처API",
    "ordinance_bcr": 40, "ordinance_far": 80,      # ★법정 bcr 20 초과
    "effective_bcr": 20.0, "effective_far": 80,    # 실효는 min() 으로 이미 정상
}
_CLEAN = {
    "sigungu": "오산시", "zone_type": "자연녹지지역", "source": "법제처API",
    "ordinance_bcr": 20, "ordinance_far": 100,
    "effective_bcr": 20.0, "effective_far": 100.0,
}


def test_premise_two_payloads_actually_differ():
    """전제 — 한쪽만 법정을 넘어야 판별이 성립한다(공허 방지)."""
    ceil = M.NATIONAL_LIMITS["자연녹지지역"]["bcr"]
    assert _VIOLATING["ordinance_bcr"] > ceil
    assert _CLEAN["ordinance_bcr"] <= ceil
    # ★그리고 **실효값은 둘 다 정상**이다 — 실효만 보는 검사는 이 차이를 못 본다.
    assert _VIOLATING["effective_bcr"] <= ceil and _CLEAN["effective_bcr"] <= ceil


def test_detects_ordinance_value_above_ceiling():
    v = M._stored_violates_national_ceiling(_VIOLATING, "자연녹지지역")
    assert v, "법정 초과 저장본을 못 잡는다"
    assert any("ordinance_bcr" in x and "40" in x for x in v)


def test_clean_payload_is_not_flagged():
    """★대조군(음성) — 정상 저장본은 통과한다(가드 위양성이 곧 결함이다)."""
    # ★양성 짝 — **같은 실행에서** 반대 결과가 나올 수 있음을 함께 단언한다.
    assert M._stored_violates_national_ceiling(_VIOLATING, "자연녹지지역")
    assert M._stored_violates_national_ceiling(_CLEAN, "자연녹지지역") == []


def test_effective_value_above_ceiling_is_also_caught():
    """실효값이 넘는 경우도 잡는다 — 두 필드를 **둘 다** 본다."""
    p = dict(_CLEAN, effective_far=250.0)   # 자연녹지 법정 far 100
    v = M._stored_violates_national_ceiling(p, "자연녹지지역")
    assert any("effective_far" in x for x in v)


def test_unknown_zone_type_is_not_flagged():
    """법정 표에 없는 용도지역은 판정하지 않는다(날조 금지 — 모르면 비운다)."""
    assert M._stored_violates_national_ceiling(_VIOLATING, "개발제한구역") == []


# ── ★배선 락 — `_load_stored` 본체를 실제로 태운다(외부 경계 DB 만 대역) ────────────
class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, *a, **k):
        return _FakeResult(self._row)

    async def commit(self):
        return None


def _load(monkeypatch, payload, zone_type="자연녹지지역"):
    """외부 경계(DB)만 끊고 `_load_stored` 본체를 그대로 실행한다."""
    import app.core.database as dbmod

    row = (json.dumps(payload), "2026-07-22 01:29:30")
    monkeypatch.setattr(dbmod, "async_session_factory", lambda: _FakeSession(row))

    async def _noop(db):
        return None

    monkeypatch.setattr(M, "_ensure_ord_table", _noop)
    return asyncio.run(M._load_stored("의정부시", zone_type))


def test_load_stored_rejects_violating_row(monkeypatch):
    """★법정 초과 저장본은 재사용하지 않는다 — None 이면 파이프라인이 재조회해 자가치유."""
    assert _load(monkeypatch, _VIOLATING) is None


def test_load_stored_still_returns_clean_row(monkeypatch):
    """★★양성 짝 — 정상 저장본은 **여전히 재사용된다**.

    이게 없으면 `_load_stored` 가 통째로 고장 나 항상 None 을 내도 위 테스트가 통과한다
    (부재 단언은 그 자체로 잠금이 아니다). 저장본 재사용이 죽으면 매 요청이 법제처 API 를
    때려 조회비용·지연이 폭증한다 — 무해한 회귀가 아니다.
    """
    got = _load(monkeypatch, _CLEAN)
    assert got is not None, "정상 저장본까지 기각한다(가드 위양성 — 캐시가 죽는다)"
    assert got["ordinance_bcr"] == 20
    assert got["provenance"]["reused"] is True


def test_load_stored_still_drops_legacy_statutory_rows(monkeypatch):
    """무회귀 — 기존 레거시(법정상한) 기각 규칙이 살아 있다."""
    assert _load(monkeypatch, dict(_CLEAN, source="법정상한")) is None


# ── ★정적캐시 전수 불변식 — 목록이 아니라 **파생**시킨다(새 항목이 자동 편입) ─────────
def test_static_cache_never_exceeds_national_ceiling():
    """정적캐시(ORDINANCE_CACHE)는 2차 폴백이라 **가드를 타지 않는다** — 여기서 잠근다.

    ★2026-08-21 실측 84엔트리 위반 0. 지금 깨끗하다는 것이 앞으로도 깨끗하다는 뜻은 아니다
    — 손으로 추가하는 표라 이 테스트가 없으면 다음 편집이 조용히 넘어간다.
    """
    checked = 0
    for region, zones in M.ORDINANCE_CACHE.items():
        for zt, vals in zones.items():
            nat = M.NATIONAL_LIMITS.get(zt)
            if not nat:
                continue
            for key in ("bcr", "far"):
                ceiling, val = nat.get(key), vals.get(key)
                if ceiling is None or val is None:
                    continue
                checked += 1
                assert float(val) <= float(ceiling), (
                    f"{region} {zt} {key}={val} > 법정상한 {ceiling} — "
                    "조건부 완화값을 기본값으로 잘못 적었을 가능성"
                )
    # ★공허 진리 가드 — "위반 0"이 참인 이유가 "대상이 0개"이면 무의미하다.
    assert checked >= 100, f"검사 대상이 너무 적다({checked}) — 캐시 파생이 끊겼다"


def test_rejection_is_logged_with_jurisdiction_and_reason(monkeypatch, caplog):
    """★기각을 **관할·용도지역·사유와 함께** 남긴다 — 운영자가 영향 지자체를 찾는 경로다.

    변이감사(2026-08-21)에서 이 로그 문자열만 생존했다. 로그는 '있으면 좋은 것'이 아니라
    이 수정의 **관측 수단**이다: 기각이 조용하면 값이 왜 바뀌었는지 아무도 설명하지 못한다.
    """
    import logging

    with caplog.at_level(logging.WARNING, logger=M.logger.name):
        assert _load(monkeypatch, _VIOLATING) is None
    msgs = [r.getMessage() for r in caplog.records]
    assert any("법정상한 초과" in m for m in msgs), f"기각 사유가 로그에 없다: {msgs}"
    hit = next(m for m in msgs if "법정상한 초과" in m)
    assert "의정부시" in hit and "자연녹지지역" in hit, f"관할/용도지역이 없다: {hit}"
    assert "ordinance_bcr" in hit and "40" in hit, f"어떤 값이 문제인지 없다: {hit}"


def test_clean_row_is_not_logged_as_rejected(monkeypatch, caplog):
    """★대조군(음성) — 정상 행은 기각 로그를 남기지 않는다(로그 위양성 방지)."""
    import logging

    with caplog.at_level(logging.WARNING, logger=M.logger.name):
        assert _load(monkeypatch, _CLEAN) is not None
    assert not any("법정상한 초과" in r.getMessage() for r in caplog.records)
