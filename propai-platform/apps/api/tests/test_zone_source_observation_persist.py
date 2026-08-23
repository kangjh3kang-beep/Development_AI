"""zone_source 관측을 **영속 저장**한다 — 계측을 넣고도 읽지 못하던 문제 (2026-08-23).

★왜(라이브 실측): `#751` 로 structlog 계측을 넣었는데, 하루 뒤 읽어 보니 **총 1건**이었다.
  `docker logs` 는 배포마다 컨테이너가 바뀌면 사라지고(로그 드라이버 json-file),
  이 저장소는 하루에도 여러 번 배포한다 — 25분치 창만 남아 **빈도를 잴 수 없었다**.
  반면 `platform_events` 는 살아 있다(실측: api_call 169,326건 · 최신 2026-08-23).
  ★"계측 부재"를 고치고 다시 "판독 불가"로 방치할 뻔했다.

★F4a 거버넌스(최중요) — 이 플랫폼엔 **인간 개입 없는 자동 변이 루프**가 있다:
    verify_result → analyzer._analyze_quality_drop → down_pct
    → growth.feature_flags 가 llm_narrative 를 **자동 비활성화**
  관측을 잘못된 event_type 으로 흘리면 **기능이 저절로 꺼진다**.
  `field_audit_observation` 선례를 그대로 따라 **구별된 event_type** 으로만 emit 하고,
  severity/recommended_action 을 담지 않아 조치신호로 소비될 수 없게 한다.

★두 모집단(CLAUDE.md 검증규율 2): 지어낸 경로 / 실조회 경로가 **다른 값**을 실어야 한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.zoning import auto_zoning_service as azs  # noqa: E402


class _FailingVWorld:
    async def geocode_address(self, address):  # noqa: ANN001
        raise RuntimeError("VWorld 502")


class _WorkingVWorld:
    async def geocode_address(self, address):  # noqa: ANN001
        return {"pnu": "4137010800105690000", "lat": 37.1, "lon": 127.0}

    async def get_land_info(self, pnu):  # noqa: ANN001
        return {"properties": {"area": 1015.0, "jimok": "대",
                               "use_zone": "제3종일반주거지역", "official_price": 1234567}}

    async def get_land_characteristics(self, pnu, year=None):  # noqa: ANN001
        return None

    async def get_land_use_plan(self, pnu):  # noqa: ANN001
        return None


@pytest.fixture
def captured(monkeypatch):
    """capture_service.record_event 를 가로채 emit 을 관찰한다(외부 경계 대역)."""
    events: list[tuple[str, dict]] = []

    def _spy(event_type, props=None):
        events.append((event_type, props or {}))

    from app.services.growth import capture_service

    monkeypatch.setattr(capture_service, "record_event", _spy)
    return events


async def _run(vworld, address):
    svc = azs.AutoZoningService()
    svc.vworld = vworld
    return await svc.analyze_by_address(address)


@pytest.mark.asyncio
async def test_A_지어낸_경로가_영속_관측으로_남는다(captured):
    r = await _run(_FailingVWorld(), "경기도 오산시 없는동 99999")
    assert r["zone_source"] == "keyword_inference"          # 전제 가드

    obs = [e for e in captured if e[0] == azs.ZONE_SOURCE_OBSERVATION_EVENT]
    assert obs, "영속 관측이 emit 되지 않았다 — docker logs 만으로는 빈도를 못 잰다"
    event_type, props = obs[0]
    # ★상수값 자체를 잠근다 — 프로덕션 조회 키다(이름이 바뀌면 대시보드·쿼리가 조용히 빈다).
    assert event_type == "zone_source_observation"
    # ★analyzer 가 COALESCE(route, service) 로 **실제 읽는** 컬럼이다 — 빠지면 집계에서 샌다.
    assert props["service"] == "auto_zoning"
    assert props["surface"] == "api"
    payload = props["payload"]
    assert payload["zone_source"] == "keyword_inference"
    assert payload["inferred"] is True
    assert payload["has_pnu"] is False
    # ★주석이 "상관분석용"이라 **선언한** 필드를 실제로 잠근다(선언만 하면 지워져도 초록이다).
    assert payload["zone_type"] == "제2종일반주거지역"


@pytest.mark.asyncio
async def test_B_실조회_경로도_남는다_분모확보(captured):
    """성공 경로가 없으면 '몇 건 중 몇 건'을 못 센다 — 분모가 사라진다."""
    r = await _run(_WorkingVWorld(), "경기도 오산시 수청동 569")
    assert r["zone_source"] == "vworld_land_info"            # 전제 가드

    obs = [e for e in captured if e[0] == azs.ZONE_SOURCE_OBSERVATION_EVENT]
    assert obs
    payload = obs[0][1]["payload"]
    assert payload["inferred"] is False                      # ★A와 갈리는 지점
    assert payload["has_pnu"] is True


@pytest.mark.asyncio
async def test_C_F4a_거버넌스_자동토글_신호를_만들지_않는다(captured):
    """★event_type 이 verify_result 계열이면 quality_drop 자동토글이 기능을 끈다.

    구별된 타입 + severity/recommended_action 부재를 **함께** 잠근다.
    """
    await _run(_FailingVWorld(), "경기도 오산시 없는동 99999")

    for event_type, props in captured:
        assert event_type != "verify_result", "자동 변이 루프에 걸리는 타입이다"
        assert "severity" not in props, "severity 는 verdict 신호로 소비된다"
        assert "recommended_action" not in props, "L1 자가수정 루프가 조치신호로 읽는다"
    assert azs.ZONE_SOURCE_OBSERVATION_EVENT != "verify_result"


@pytest.mark.asyncio
async def test_D_주소는_관측에_담지_않는다_PII(captured):
    """★주소는 개인정보 성격이다 — 선례(field_audit)도 zone_type 같은 차원 힌트만 담는다."""
    await _run(_FailingVWorld(), "경기도 오산시 없는동 99999")

    obs = [e for e in captured if e[0] == azs.ZONE_SOURCE_OBSERVATION_EVENT]
    flat = str(obs[0][1])
    assert "없는동" not in flat, "주소가 관측 payload 에 실렸다"
