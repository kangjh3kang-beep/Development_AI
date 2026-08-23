"""zone_source 계측 — keyword_inference 빈도를 **잴 수 있게** 한다(2026-08-22 감사 후속).

★왜 필요했나(실측 2026-08-22, 168 propai-api-8001):
  `zone_source` 는 **어디에도 로깅되지 않았다**. 라이브 로그에서 'zone_source' grep 은 0건인데
  그건 부재가 아니라 **계측 부재**였다(양성 대조군도 0). 그래서 "VWorld 실패로 용도지역을
  지어낸 응답이 몇 건 나갔나"를 **원리적으로 잴 수 없었다**.

  지어내기는 주소가 나빠서가 아니라 VWorld 가 실패해서 난다:
      try:  geocode = await self.vworld.geocode_address(address)
      except Exception:  pass            # ← 장애·키미설정·레이트리밋을 **조용히** 삼킨다
      if not result["pnu"]:  zone_source = "keyword_inference"   # 주소 문자열에서 **지어냄**

  라이브 확증: `없는동 99999` → pnu=None·land_area=None 인데
  evidence 가 **국토계획법 시행령 제85조로 250%** 를 인용했다.

★픽스처는 두 모집단을 가른다(CLAUDE.md 검증규율 2):
  A) VWorld 지오코딩 실패 → keyword_inference 가 **계측에 찍혀야** 한다
  B) VWorld 실조회 성공   → 실출처가 찍히고 keyword_inference 가 **아니어야** 한다
  두 경우가 같은 값을 내면 배선을 끊어도 통과한다 — 그래서 둘을 갈라 단언한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402
import structlog  # noqa: E402

from app.services.zoning.auto_zoning_service import AutoZoningService  # noqa: E402


class _FailingVWorld:
    """지오코딩이 터진다 = VWorld 장애/키미설정 구간(A 모집단)."""

    async def geocode_address(self, address):  # noqa: ANN001
        raise RuntimeError("VWorld 502")


class _WorkingVWorld:
    """실조회가 되는 정상 구간(B 모집단)."""

    async def geocode_address(self, address):  # noqa: ANN001
        return {"pnu": "4137010800105690000", "lat": 37.1, "lon": 127.0}

    async def get_land_info(self, pnu):  # noqa: ANN001
        return {"properties": {"area": 1015.0, "jimok": "대", "use_zone": "제3종일반주거지역",
                               "official_price": 1234567}}

    async def get_land_characteristics(self, pnu):  # noqa: ANN001
        return None

    async def get_land_use_plan(self, pnu):  # noqa: ANN001
        return None


#: 프로덕션 로그를 이 문자열로 조회한다 — 이름이 바뀌면 대시보드/쿼리가 조용히 빈다.
TELEMETRY_EVENT = "용도지역 출처 계측"


def _zone_source_events(logs: list[dict]) -> list[dict]:
    """계측 이벤트만 추린다 — **이벤트 이름으로** 고른다(이름이 계약이다)."""
    return [e for e in logs if e.get("event") == TELEMETRY_EVENT]


@pytest.mark.asyncio
async def test_A_vworld_실패시_keyword_inference가_계측된다():
    svc = AutoZoningService()
    svc.vworld = _FailingVWorld()

    with structlog.testing.capture_logs() as logs:
        result = await svc.analyze_by_address("경기도 오산시 없는동 99999")

    # 전제 확인(공허한 진리 차단): 정말 추론 경로를 탔는가.
    assert result["zone_source"] == "keyword_inference"
    assert result["pnu"] is None

    events = _zone_source_events(logs)
    assert events, "zone_source 계측 이벤트가 없다 — 빈도를 잴 수 없다"
    ev = next(e for e in events if e["zone_source"] == "keyword_inference")
    assert ev["inferred"] is True
    # ★원인 추적 3종 — 코드 주석이 "남겨야 한다"고 **선언한** 필드를 실제로 잠근다.
    #   (선언만 하고 안 잠그면 지워져도 초록이다 — 변이 5건이 여기서 생존했다.)
    assert ev["zone_type"] == "제2종일반주거지역", "지어낸 값이 무엇이었는지"
    assert ev["has_pnu"] is False, "실조회가 안 됐다는 사실"
    assert ev["address"] == "경기도 오산시 없는동 99999", "어느 주소에서 났는지"


@pytest.mark.asyncio
async def test_B_실조회_성공시엔_실출처가_계측되고_추론이_아니다():
    svc = AutoZoningService()
    svc.vworld = _WorkingVWorld()

    with structlog.testing.capture_logs() as logs:
        result = await svc.analyze_by_address("경기도 오산시 수청동 569")

    assert result["zone_source"] == "vworld_land_info"
    assert result["pnu"] == "4137010800105690000"

    events = _zone_source_events(logs)
    assert events, "성공 경로에도 계측이 있어야 분모(전체 호출)를 알 수 있다"
    # ★두 모집단이 실제로 다른 값을 낸다 — 이게 없으면 배선을 끊어도 A가 통과한다.
    assert all(e["zone_source"] != "keyword_inference" for e in events)
    ev = events[0]
    assert ev["inferred"] is False
    assert ev["zone_type"] == "제3종일반주거지역"
    assert ev["has_pnu"] is True, "실조회 경로는 pnu 를 갖는다 — 두 모집단의 실제 차이"
    assert ev["address"] == "경기도 오산시 수청동 569"
