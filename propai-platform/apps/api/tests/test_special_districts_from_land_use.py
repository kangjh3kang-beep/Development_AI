"""`special_districts` 는 **주소 문자열 휴리스틱**이라 사실상 항상 비어 있었다 (원 인계서 P2).

【무엇이 죽어 있었나 — 2026-08-21 라이브 실측】
종전 생산자는 `AutoZoningService._detect_special_districts(zone_type, address)` 하나였고,
주소나 용도지역명에 **"지구단위" 라는 글자**가 있어야 채워진다. 실제 주소엔 없다.

    오산 수청동 569  : get_land_use_plan **20건** · status=ok → special_districts **0건**
    오산 내삼미동 741: get_land_use_plan **11건** · status=ok → special_districts **0건**

【그래서 조례 캠페인 계약 셋이 통째로 발화 불가였다】
`special_districts` 는 셋의 **공통 입력**이다:
  · `plan_limit_unknown`(#705) · `conditional_ceiling`(#704) · `ordinance_conditional`(#711)
입력이 비면 셋 다 화면 경로에서 한 번도 발화하지 못한다.

【수정 후 라이브】
    수청동 569  : 20건 → `plan_limit_unknown` **발화** ['지구단위계획구역']
    내삼미동 741: 11건 → 발화 **없음**(지구단위 아님 — 음성 대조군)
    ★실효값은 전후 동일(300/50 · 80/20) — 무회귀
    ★두 필지 모두 `성장관리권역` 을 갖지만 `conditional_ceiling` 은 발화하지 않는다
      (#703 판별자가 실데이터를 처음 만나 정확히 배제 — 수도권 권역 ≠ 성장관리계획구역)
"""

from app.services.land_intelligence import far_tier_service
from app.services.zoning.district_regime import (
    is_detailed_urban_plan,
    is_growth_management_plan,
)

# ── 라이브 실측 designation 최소 재현(모양 그대로 — 소비처는 district_name 을 읽는다) ──
_REAL_SUCHEONG = [   # 수청동 569: 지구단위계획구역 포함
    {"district_name": "비행안전제2구역(전술)"}, {"district_name": "공익용산지"},
    {"district_name": "성장관리권역"},          # ★수도권정비계획법 — 완화 근거 아님(#703)
    {"district_name": "제3종일반주거지역"}, {"district_name": "토지거래계약에관한허가구역"},
    {"district_name": "지구단위계획구역"},
]
_REAL_NAESAMMI = [   # 내삼미동 741: 지구단위 없음(음성 모집단)
    {"district_name": "비행안전제2구역(전술)"}, {"district_name": "공익용산지"},
    {"district_name": "성장관리권역"}, {"district_name": "도로구역"},
    {"district_name": "교통광장"}, {"district_name": "토지거래계약에관한허가구역"},
]


def test_premise_two_populations_actually_differ():
    """전제 — 한쪽에만 지구단위계획구역이 있어야 이 파일의 검증이 성립한다(공허 방지)."""
    assert any(is_detailed_urban_plan(d) for d in _REAL_SUCHEONG)
    assert not any(is_detailed_urban_plan(d) for d in _REAL_NAESAMMI)
    # ★그리고 **둘 다** 성장관리권역을 갖는다 — 아래 #703 검증이 공허하지 않다.
    assert any(d["district_name"] == "성장관리권역" for d in _REAL_SUCHEONG)
    assert any(d["district_name"] == "성장관리권역" for d in _REAL_NAESAMMI)


def _calc(districts):
    return far_tier_service.calc_effective_far(
        {"local_ordinance": {"source": "법제처API", "effective_bcr": 50, "effective_far": 300},
         "zone_limits": {"max_bcr_pct": 50, "max_far_pct": 300},
         "special_districts": districts},
        "제3종일반주거지역", 1000.0,
    )


def test_real_designations_make_plan_limit_unknown_fire():
    """★★실측 designation 이 들어오면 #705 가 **발화한다** — 종전엔 입력이 비어 불가능했다."""
    out = _calc(_REAL_SUCHEONG)
    plu = out["plan_limit_unknown"]
    assert plu is not None, "지구단위계획구역이 있는데 고지가 안 나온다"
    assert plu["districts"] == ["지구단위계획구역"]
    # 계획이 지배하는 범위 — 수치만이 아니다(용도 추천도 미검증이라는 것이 이 고지의 핵심).
    assert "건축물 용도제한" in plu["governs"]
    assert plu["applied"] is False


def test_non_district_parcel_stays_silent():
    """★음성 대조군 — designation 이 11건 있어도 지구단위가 아니면 발화하지 않는다.

    '무엇이든 넣으면 울리는' 고지가 되면 경보가 배경이 된다.
    """
    assert _calc(_REAL_NAESAMMI)["plan_limit_unknown"] is None
    # ★양성 짝 — 같은 실행에서 지구단위 모집단은 발화한다.
    assert _calc(_REAL_SUCHEONG)["plan_limit_unknown"] is not None


def test_metro_regime_does_not_open_conditional_ceiling():
    """★★#703 규율이 **실데이터에서** 유지된다 — 두 필지 모두 `성장관리권역` 을 갖는다.

    이 판별자는 종전까지 실데이터를 본 적이 없다(입력이 항상 비어 있었으므로).
    부분일치로 읽었다면 경기 전역에 건폐율 +10%p 가 붙는다.
    """
    for districts in (_REAL_SUCHEONG, _REAL_NAESAMMI):
        assert _calc(districts)["conditional_ceiling"] is None
    # ★양성 짝 — 진짜 성장관리계획구역이면 열린다(판별자가 통째로 죽은 게 아니다).
    opened = far_tier_service.calc_effective_far(
        {"local_ordinance": {"source": "법제처API", "effective_bcr": 20, "effective_far": 100},
         "zone_limits": {"max_bcr_pct": 20, "max_far_pct": 100},
         "special_districts": [{"district_name": "성장관리계획구역"}]},
        "자연녹지지역", 1000.0,
    )
    assert opened["conditional_ceiling"] is not None
    assert is_growth_management_plan({"district_name": "성장관리계획구역"})
    assert not is_growth_management_plan({"district_name": "성장관리권역"})


def test_effective_values_are_unchanged_by_the_fix():
    """★★무회귀 — designation 이 실려도 **실효값은 그대로다**.

    이 수정은 '모른다는 사실'을 흐르게 할 뿐 수치를 건드리지 않는다
    (라이브 전후 300/50 · 80/20 동일).
    """
    empty = _calc([])
    filled = _calc(_REAL_SUCHEONG)
    assert filled["effective_far_pct"] == empty["effective_far_pct"]
    assert filled["effective_bcr_pct"] == empty["effective_bcr_pct"]
    # 공허 진리 가드 — 값 자체가 None 이면 위 비교가 무의미하다.
    assert empty["effective_far_pct"] is not None
    # 그런데 **고지는 달라야** 한다(같으면 이 수정이 아무것도 안 한 것이다).
    assert (filled["plan_limit_unknown"] is not None) != (empty["plan_limit_unknown"] is not None)


# ── ★배선 층 — `collect_comprehensive` 본체를 태운다(외부 경계만 대역) ─────────────
#   변이감사가 잡았다: 위 테스트들은 순수함수(`calc_effective_far`)만 태워서
#   **실제 대입 지점이 무잠금**이었다(변이 4/4 생존). 이 세션에서 네 번째 같은 실수다.

import asyncio


def _svc_with(monkeypatch, *, land_use, zoning_districts=None):
    """외부 경계(AutoZoning·VWorld 조회)만 끊고 `collect_comprehensive` 본체를 실행한다."""
    from app.services.land_intelligence.land_info_service import LandInfoService

    svc = LandInfoService()

    async def fake_zoning(address):
        return {
            "pnu": "4137010800105690000", "coordinates": {"lat": 37.1, "lon": 127.0},
            "zone_type": "제3종일반주거지역", "zone_source": "vworld_ned",
            "zone_limits": {"max_bcr_pct": 50, "max_far_pct": 300},
            # ★종전 생산자(주소 키워드 휴리스틱)의 산출 — 기본은 빈 목록이다.
            "special_districts": zoning_districts if zoning_districts is not None else [],
            "warnings": [], "land_area_sqm": 1000.0,
        }

    async def fake_lup(pnu):
        return land_use

    async def none_(*a, **k):
        return None

    monkeypatch.setattr(svc.zoning, "analyze_by_address", fake_zoning)
    monkeypatch.setattr(svc, "_fetch_land_use_plan", fake_lup)
    for m in ("_fetch_land_register", "_fetch_official_price", "_fetch_building_info",
              "_fetch_land_characteristics"):
        monkeypatch.setattr(svc, m, none_)
    return svc


def test_wiring_puts_real_designations_into_special_districts(monkeypatch):
    """★★실제 대입 지점 — 실측 designation 이 `special_districts` 로 들어간다.

    이 테스트는 **구 코드에서 반드시 실패한다**(0건이었다).
    """
    svc = _svc_with(monkeypatch, land_use=_REAL_SUCHEONG)
    r = asyncio.run(svc.collect_comprehensive("경기도 오산시 수청동 569"))
    sd = r.get("special_districts") or []
    assert len(sd) == len(_REAL_SUCHEONG), f"{len(sd)}건 — 실측이 안 실렸다"
    assert any((d.get("district_name") == "지구단위계획구역") for d in sd)
    assert r["special_districts_source"] == "vworld_ned_land_use"


def test_wiring_keeps_heuristic_when_no_real_data(monkeypatch):
    """★무회귀 — 실조회가 없으면 **종전 휴리스틱 값을 유지**한다(덮어쓰지 않는다)."""
    legacy = [{"name": "지구단위계획구역", "bonus_far": 300}]
    svc = _svc_with(monkeypatch, land_use=None, zoning_districts=legacy)
    r = asyncio.run(svc.collect_comprehensive("경기도 오산시 지구단위 어딘가"))
    assert r.get("special_districts") == legacy
    assert r["special_districts_source"] == "keyword_inference"
    # ★양성 짝 — 같은 실행에서 실조회가 있으면 실측으로 덮인다.
    svc2 = _svc_with(monkeypatch, land_use=_REAL_SUCHEONG, zoning_districts=legacy)
    r2 = asyncio.run(svc2.collect_comprehensive("x"))
    assert r2["special_districts_source"] == "vworld_ned_land_use"
    assert len(r2["special_districts"]) == len(_REAL_SUCHEONG)


def test_wiring_reaches_plan_limit_unknown_end_to_end(monkeypatch):
    """★★종단 — 배선이 실제로 #705 발화까지 도달한다(대입만 하고 안 흐르면 소용없다)."""
    svc = _svc_with(monkeypatch, land_use=_REAL_SUCHEONG)
    r = asyncio.run(svc.collect_comprehensive("경기도 오산시 수청동 569"))
    plu = (r.get("effective_far") or {}).get("plan_limit_unknown")
    assert plu is not None and plu["districts"] == ["지구단위계획구역"]
    # ★음성 대조군 — 지구단위 없는 필지는 종단에서도 조용하다.
    svc2 = _svc_with(monkeypatch, land_use=_REAL_NAESAMMI)
    r2 = asyncio.run(svc2.collect_comprehensive("경기도 오산시 내삼미동 741"))
    assert (r2.get("effective_far") or {}).get("plan_limit_unknown") is None


def test_rows_carry_both_name_keys(monkeypatch):
    """★★행이 `district_name` 과 `name` 을 **둘 다** 갖는다 — 소비처가 두 키를 쓴다.

    #742 직후 전역 스윕에서 적발: 프론트 일부가 `name` **만** 읽는다.
        LandIntelligencePanel:666  specialDistricts.map(d => d.name)   ← 폴백 없음
        SiteAnalysisDetail:1989    obj(d).name || d                    ← 객체가 그대로 출력
    종전 휴리스틱 행이 `{name, bonus_far}` 모양이라 그렇게 굳어 있었다.
    두 키를 다 실으면 **어느 소비처가 어느 키를 읽는지 감사할 필요가 없다**.
    """
    svc = _svc_with(monkeypatch, land_use=_REAL_SUCHEONG)
    r = asyncio.run(svc.collect_comprehensive("경기도 오산시 수청동 569"))
    sd = r["special_districts"]
    assert sd, "행이 비었다 — 아래 단언이 공허해진다"
    for d in sd:
        assert d.get("name"), f"name 이 없다: {d}"
        assert d.get("district_name"), f"district_name 이 사라졌다: {d}"
        assert d["name"] == d["district_name"]
    # ★프론트가 하던 것을 그대로 재현 — `undefined` 나 `[object Object]` 가 나오면 안 된다.
    joined = ", ".join(str(d.get("name")) for d in sd)
    assert "None" not in joined and "undefined" not in joined, joined
    assert "지구단위계획구역" in joined


def test_original_rows_are_not_mutated(monkeypatch):
    """★원본 designation 리스트를 **건드리지 않는다**(같은 객체를 다른 소비처도 쓴다).

    `land_use_plan.districts` 는 같은 리스트를 싣는다 — 원본을 변형하면 그쪽까지 바뀐다.
    """
    src = [dict(d) for d in _REAL_SUCHEONG]
    before = [dict(d) for d in src]
    svc = _svc_with(monkeypatch, land_use=src)
    asyncio.run(svc.collect_comprehensive("x"))
    assert src == before, "원본 행이 변형됐다"
    # ★양성 짝 — 그래도 결과 행에는 name 이 붙어 있다(복사가 실제로 일어났다).
    r = asyncio.run(_svc_with(monkeypatch, land_use=src).collect_comprehensive("x"))
    assert all(d.get("name") for d in r["special_districts"])
