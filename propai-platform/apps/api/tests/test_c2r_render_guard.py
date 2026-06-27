"""C2R 렌더 가드 테스트 — 검증 안 된/위조 브리프 차단 판정·브리프 지문 부착·shadow 무회귀.

외부 키/네트워크 없이 전부 통과해야 한다(가드 판정·지문 부착은 순수 결정론).
shadow/enforce 무회귀는 라우터의 분기 로직을 미러로 재현해 check 단위로 검증한다
(라우터 모듈 임포트가 DB 드라이버를 끌어와 이 venv에서 불가하므로 — 플랜이 허용한 'check 단위').
"""

import app.services.c2r.c2r_service as svc
from app.services.c2r.c2r_service import build_foundation
from app.services.c2r.render_guard import check_render_allowed
from app.services.cad.provenance import compute_geometry_hash

# ── 1) check_render_allowed 단위 판정 ──────────────────────────────────────────

def test_guard_blocks_when_geometry_hash_missing():
    """geometry_hash 없는 브리프 → 검증 안 됨으로 차단."""
    out = check_render_allowed({"role": "임의 브리프"})
    assert out["allowed"] is False
    assert out["status"] == "blocked_by_unverified_geometry"
    assert out["reason"]  # 정직한 사유 문자열 존재


def test_guard_allows_when_hash_matches_fingerprint():
    """geometry_hash + 일치 fingerprint → 우리 브리프로 보고 허용."""
    fp = {"far_pct": 250.0, "bcr_pct": 60.0, "max_floors": 7}
    brief = {"geometry_fingerprint": fp, "geometry_hash": compute_geometry_hash(fp)}
    out = check_render_allowed(brief)
    assert out["allowed"] is True
    assert out["status"] == "allowed"
    assert out["reason"] is None


def test_guard_blocks_when_hash_mismatches_fingerprint():
    """geometry_hash + 변조된(불일치) fingerprint → 위조/변조 의심 차단."""
    fp = {"far_pct": 250.0, "bcr_pct": 60.0}
    brief = {"geometry_fingerprint": fp, "geometry_hash": compute_geometry_hash(fp)}
    # fingerprint 를 몰래 바꿔치기(해시는 옛 값 그대로) → 불일치.
    brief["geometry_fingerprint"] = {"far_pct": 999.0, "bcr_pct": 60.0}
    out = check_render_allowed(brief)
    assert out["allowed"] is False
    assert out["status"] == "blocked_by_geometry_mismatch"
    assert out["reason"]


def test_guard_allows_when_hash_only_no_fingerprint():
    """geometry_hash 만 있고 fingerprint 없음 → 외부 검증 해시로 간주해 허용(현 단계)."""
    out = check_render_allowed({"geometry_hash": "abc123"})
    assert out["allowed"] is True
    assert out["status"] == "allowed"


# ── 2) build_foundation 이 브리프에 지문을 부착하는지(통합·결정론) ─────────────

def _fake_parcel() -> dict:
    return {
        "address": "서울특별시 강남구 역삼동 123-45",
        "pnu": "1168010100101230045",
        "zone_type": "제2종일반주거지역",
        "zone_source": "vworld_land_info",
        "zone_limits": {"max_bcr_pct": 60, "max_far_pct": 250, "max_height_m": None,
                        "max_floors": None},
        "land_area_sqm": 660.0,
        "coordinates": {"lat": 37.5, "lon": 127.03},
        "warnings": [],
    }


def _patch_resolve(monkeypatch, parcel: dict, geometry=None):
    async def _fake_resolve(_key):
        return parcel

    async def _fake_geom(_parcel):
        return geometry

    monkeypatch.setattr(svc, "_resolve_parcel", _fake_resolve)
    monkeypatch.setattr(svc, "_fetch_geometry", _fake_geom)


async def test_build_foundation_attaches_geometry_hash(monkeypatch):
    """build_foundation 산출 브리프에 geometry_hash·geometry_fingerprint 가 부착된다."""
    _patch_resolve(monkeypatch, _fake_parcel())
    out = await build_foundation("서울특별시 강남구 역삼동 123-45", {"building_use": "공동주택"})
    brief = out["brief"]
    assert "geometry_hash" in brief
    assert "geometry_fingerprint" in brief
    # 인벨로프 결정적 수치가 지문에 담겨야 한다(가짜 아님 — 실제 인벨로프값).
    fp = brief["geometry_fingerprint"]
    assert fp.get("bcr_pct") == 60.0
    assert fp.get("far_pct") == 250.0
    assert fp.get("land_area_sqm") == 660.0
    # 부착된 해시는 fingerprint 재계산과 정확히 일치해야 한다(가드가 통과시킬 수 있어야 함).
    assert brief["geometry_hash"] == compute_geometry_hash(fp)
    assert check_render_allowed(brief)["allowed"] is True


async def test_build_foundation_geometry_hash_deterministic(monkeypatch):
    """같은 입력이면 두 번 돌려도 geometry_hash 가 같다(결정론·멱등)."""
    _patch_resolve(monkeypatch, _fake_parcel())
    a = await build_foundation("서울특별시 강남구 역삼동 123-45", {"building_use": "공동주택"})
    _patch_resolve(monkeypatch, _fake_parcel())
    b = await build_foundation("서울특별시 강남구 역삼동 123-45", {"building_use": "공동주택"})
    assert a["brief"]["geometry_hash"] == b["brief"]["geometry_hash"]


# ── 3) /render shadow(기본) 무회귀 — geometry_hash 없어도 차단 안 함 ───────────
#  ★라우터 모듈(app.routers.c2r) 임포트는 DB 드라이버(asyncpg)를 끌어와 이 venv에서 불가하므로,
#    라우터의 shadow/enforce 분기 로직을 그대로 재현해 check 단위로 무회귀를 검증한다(플랜 허용).

def _simulate_render_decision(guard: dict, *, enforce: bool, rendered: dict) -> dict:
    """c2r.render_from_brief 의 가드 분기와 동일한 결정 로직(테스트용 미러).

    - allowed False + enforce  → render 미호출·정직 차단 응답.
    - allowed False + shadow    → render 호출·render_guard_warning 메타만 additive.
    - allowed True              → render 그대로.
    """
    if not guard["allowed"]:
        if enforce:
            return {
                "status": guard["status"],
                "reason": guard["reason"],
                "render_guard": "enforced",
            }
        result = dict(rendered)  # render_image 결과(여기선 provider_unconfigured 모사)
        result["render_guard_warning"] = {
            "status": guard["status"],
            "reason": guard["reason"],
        }
        return result
    return dict(rendered)


# render_image 가 키 없을 때 돌려주는 정직 상태(가짜 이미지 없음) 모사.
_PROVIDER_UNCONFIGURED = {"status": "provider_unconfigured", "provider": "openai", "image": None}


def test_render_shadow_does_not_block_unverified_brief():
    """ENFORCE False(shadow): geometry_hash 없는 브리프여도 렌더 경로로 진입(경고만)."""
    guard = check_render_allowed({"role": "검증 안 된 브리프"})
    out = _simulate_render_decision(guard, enforce=False, rendered=_PROVIDER_UNCONFIGURED)
    # 차단 상태가 아니라 렌더 경로로 진입했음(키 없으니 provider_unconfigured).
    assert out["status"] != "blocked_by_unverified_geometry"
    assert out["status"] == "provider_unconfigured"
    # shadow 경고 메타가 additive로 붙는다(렌더 결과 자체는 무변경).
    assert out["render_guard_warning"]["status"] == "blocked_by_unverified_geometry"


def test_render_enforce_blocks_unverified_brief():
    """ENFORCE True: geometry_hash 없는 브리프 → render 미호출·정직 차단(가짜 이미지 없음)."""
    guard = check_render_allowed({"role": "검증 안 된 브리프"})
    out = _simulate_render_decision(guard, enforce=True, rendered=_PROVIDER_UNCONFIGURED)
    assert out["status"] == "blocked_by_unverified_geometry"
    assert out["render_guard"] == "enforced"
    assert out.get("image") is None  # render 미호출 → 이미지 키 자체가 없음(가짜 이미지 없음)


def test_guard_blocks_empty_fingerprint():
    """★빈 geometry_fingerprint(인벨로프 산출 실패)는 hash가 있어도 차단 — '빈 일치' 우회 방지(MEDIUM)."""
    from app.services.cad.provenance import compute_geometry_hash
    brief = {"geometry_hash": compute_geometry_hash({}), "geometry_fingerprint": {}}
    res = check_render_allowed(brief)
    assert res["allowed"] is False
    assert res["status"] == "blocked_by_unverified_geometry"
