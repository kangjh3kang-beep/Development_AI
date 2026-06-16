"""구역 입력(BatchInput) → 대상 PNU 집합 정규화.

핵심 규칙:
- pnu_list: 그대로 사용(검증만).
- bbox: VWorldService.get_parcels_in_bbox 로 필지를 받아 pnu 추출.
- polygon: 폴리곤의 bbox로 필지를 받은 뒤 shapely 로 폴리곤과 교차하는 것만 남김.
- admin_code(bcode)/district_code: 직접 필지목록 API가 없으므로 가짜 생성 금지,
  정직하게 degrade 플래그를 반환한다(향후 확장 TODO).

무목업 원칙: 외부 데이터가 없으면(키 미설정·미적재) 빈 결과 + degrade 플래그를 주고,
가짜 좌표/가짜 PNU를 절대 만들지 않는다. 외부 미가용이면 라이브콜 0으로 끝난다.
"""

from __future__ import annotations

from typing import Any, Optional

from app.foundation.parcel.contracts.batch import BatchInput


class NormalizeResult:
    """정규화 결과 — 대상 PNU 목록 + degrade(지원불가/부분) 플래그 + 사유."""

    def __init__(
        self,
        pnus: list[str],
        degraded: bool = False,
        reason: Optional[str] = None,
    ) -> None:
        # PNU 중복 제거(순서 보존). VWorld bbox는 다부분 필지를 같은 PNU로 여러 번
        # 반환할 수 있어, 중복이 남으면 len(items)<len(target)로 완결성이 영원히 PARTIAL에
        # 갇힌다(state RUNNING 고착). 여기서 1회 정규화한다.
        seen: set[str] = set()
        deduped: list[str] = []
        for p in pnus:
            if p and p not in seen:
                seen.add(p)
                deduped.append(p)
        self.pnus = deduped
        self.degraded = degraded
        self.reason = reason


def _lazy_vworld() -> Any:
    """실제 VWorldService 를 지연 임포트한다(테스트 시 import 비용/의존성 회피).

    테스트에서는 BatchService/Runner 에 fake vworld 를 주입하므로 이 경로를 타지 않는다.
    """
    from app.services.external_api.vworld_service import VWorldService

    return VWorldService()


async def normalize(inp: BatchInput, vworld: Any = None) -> NormalizeResult:
    """BatchInput 을 대상 PNU 목록으로 정규화한다.

    Args:
        inp: 배치 입력.
        vworld: VWorldService 호환 객체(미지정 시 실제 서비스 지연 생성).
    """
    if vworld is None:
        vworld = _lazy_vworld()

    # ── 1) PNU 직접 지정 ──
    if inp.pnu_list is not None:
        pnus = [str(p).strip() for p in inp.pnu_list if str(p).strip()]
        return NormalizeResult(pnus=pnus)

    # ── 2) bbox ──
    if inp.bbox is not None:
        min_lon, min_lat, max_lon, max_lat = inp.bbox
        parcels = await vworld.get_parcels_in_bbox(
            min_lon, min_lat, max_lon, max_lat, max_count=1000
        )
        pnus = [p.get("pnu", "") for p in (parcels or []) if p.get("pnu")]
        if not pnus:
            # 외부 미가용/미적재 → 정직 degrade(가짜 생성 금지)
            return NormalizeResult(
                pnus=[], degraded=True,
                reason="bbox 영역에서 필지를 찾지 못했습니다(외부 데이터 미가용 또는 빈 영역).",
            )
        return NormalizeResult(pnus=pnus)

    # ── 3) polygon ──
    if inp.polygon is not None:
        # 폴리곤의 bounding box로 후보 필지를 받은 뒤, shapely 로 실제 교차만 필터.
        # ※공간색인 가정: get_parcels_in_bbox 가 bbox 후보를 좁게 반환한다고 보고,
        #   교차(intersect) 정확성으로 폴리곤 필터를 보장한다(EXPLAIN 대체).
        try:
            from shapely.geometry import shape
        except Exception:  # noqa: BLE001 - shapely 미설치 환경 방어
            return NormalizeResult(
                pnus=[], degraded=True,
                reason="shapely 미설치로 폴리곤 필터 불가.",
            )

        poly = shape(inp.polygon)
        minx, miny, maxx, maxy = poly.bounds
        candidates = await vworld.get_parcels_in_bbox(
            minx, miny, maxx, maxy, max_count=1000
        )
        if not candidates:
            return NormalizeResult(
                pnus=[], degraded=True,
                reason="폴리곤 bbox 영역에서 필지를 찾지 못했습니다(외부 데이터 미가용).",
            )
        pnus: list[str] = []
        for cand in candidates:
            geom = cand.get("geometry")
            pnu = cand.get("pnu", "")
            if not geom or not pnu:
                continue
            try:
                if poly.intersects(shape(geom)):
                    pnus.append(pnu)
            except Exception:  # noqa: BLE001 - 잘못된 geometry는 건너뛴다
                continue
        return NormalizeResult(pnus=pnus)

    # ── 3.5) center_address + radius → 지오코딩 후 반경 bbox 필지 ──
    if inp.center_address is not None:
        import math

        geo = await vworld.geocode_address(inp.center_address)
        lat = (geo or {}).get("lat")
        lon = (geo or {}).get("lon")
        if lat is None or lon is None:
            return NormalizeResult(
                pnus=[], degraded=True,
                reason=f"중심 주소 '{inp.center_address}' 지오코딩 실패(좌표 미확보).",
            )
        radius = int(inp.radius_m or 500)
        # 위경도 1도 ≈ 111,320m. 경도는 위도 코사인 보정.
        dlat = radius / 111_320.0
        dlon = radius / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
        parcels = await vworld.get_parcels_in_bbox(
            lon - dlon, lat - dlat, lon + dlon, lat + dlat, max_count=1000
        )
        pnus = [p.get("pnu", "") for p in (parcels or []) if p.get("pnu")]
        if not pnus:
            return NormalizeResult(
                pnus=[], degraded=True,
                reason=f"'{inp.center_address}' 반경 {radius}m 내 필지를 찾지 못했습니다(외부 데이터 미가용 또는 빈 영역).",
            )
        return NormalizeResult(pnus=pnus)

    # ── 4) admin_code / district_code → 정직 degrade ──
    if inp.admin_code is not None:
        # TODO: 행정구역(bcode) → 필지목록 직접 API 확보 시 구현(현재 미지원).
        return NormalizeResult(
            pnus=[], degraded=True,
            reason="행정구역코드(admin_code) 기반 필지목록 직접 조회 API 미지원 — "
                   "현재는 가짜 생성 없이 미지원으로 정직 표기합니다.",
        )
    if inp.district_code is not None:
        # TODO: 지구단위계획 구역코드 → 필지목록 API 확보 시 구현(현재 미지원).
        return NormalizeResult(
            pnus=[], degraded=True,
            reason="지구단위 구역코드(district_code) 기반 필지목록 직접 조회 API 미지원.",
        )

    return NormalizeResult(pnus=[], degraded=True, reason="알 수 없는 입력.")