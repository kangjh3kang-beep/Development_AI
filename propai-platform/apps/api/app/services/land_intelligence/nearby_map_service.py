"""주변 실거래 지도 데이터 서비스.

대상 지번 중심좌표 + 반경 + 카테고리별(매매6·전월세4) 실거래를 건물단위로
그룹핑·집계하고, 각 건물을 카카오 로컬 지오코딩으로 좌표화하여 지도에 표시할
페이로드를 만든다.

- 실거래: 검증된 MolitClient(apis.data.go.kr/1613000) 재사용
- 지오코딩: 카카오 로컬 API(주소→좌표, 지번·도로명·키워드 모두 처리), Redis 캐시
- 성능: 카테고리별 그룹 상한 + 고유 쿼리 dedupe + 병렬(semaphore) + 7일 캐시
"""

import asyncio
import json
import math
import time
from datetime import datetime
from typing import Any

import httpx
import structlog

from app.core.db_utils import PostGISHelper
from app.services.data_validation.deal_date import parse_deal_date
from app.services.data_validation.price_stats import robust_price_stats
from apps.api.config import get_settings
from apps.api.integrations.molit_client import MolitClient

logger = structlog.get_logger(__name__)

PYEONG_SQM = 3.305785  # 1평 = 3.305785㎡ (프론트 lib/formatters.ts PYEONG_SQM 상수 미러)

_TRADE_TYPES = [
    ("apt", "아파트"),
    ("villa", "연립다세대"),
    ("house", "단독다가구"),
    ("officetel", "오피스텔"),
    ("land", "토지"),
    ("commercial", "상업업무용"),
]
_RENT_TYPES = [
    ("apt", "아파트"),
    ("villa", "연립다세대"),
    ("house", "단독다가구"),
    ("officetel", "오피스텔"),
]

_MAX_GROUPS_PER_CAT = 28  # 카테고리별 마커 상한(건물 수) — 지오코딩 부하·페이로드 축소(40→28)
# 지오코딩 '사전 컷' 상한 — 반경 필터가 캡(28)보다 먼저 돌게 되면서(순서: 지오코딩→필터→캡)
# 지오코딩 대상이 시군구 전체로 커지는 것을 막는 콜드로드 안전판. 최종 캡(28)보다 충분히 넓게.
_MAX_GEOCODE_GROUPS_PER_CAT = 80
_GEOCODE_CONCURRENCY = 12  # 지오코딩 병렬도(6→12) — 첫 로딩 시간 단축

# ── 결과 캐시(프로세스 메모리, TTL) ──
# 같은 지역(주소·lawd_cd·기간)을 재조회하면 MOLIT 수집+지오코딩(수 초)을 건너뛰고 즉시 반환.
# Redis가 degraded여도 동작(인프로세스). 단일 워커 운영이라 적중률 높음.
_BUILD_CACHE: dict[tuple, tuple[float, "dict[str, Any]"]] = {}
_BUILD_CACHE_TTL = 1800.0  # 30분
_BUILD_CACHE_MAX = 128     # 메모리 상한(초과 시 가장 오래된 항목부터 제거)
# VWorld 지오코딩(서버에 키 설정·운영중). 지번주소=PARCEL, 도로명=ROAD.
_VWORLD_GEOCODE_URL = "https://api.vworld.kr/req/address"
# 지오코딩 캐시 TTL(초):
#   - 성공(좌표 확보): 7일 — 좌표는 사실상 불변이라 길게 캐시해 재조회 비용 절감.
#   - 실패/미해결(빈 결과): 5분 — ★일시적 VWorld 무응답·키 누락을 7일간 "빈 좌표"로 고착시키면
#     복구 후에도 지도가 계속 서울 폴백에 갇힌다. 짧게만 캐시해 곧 재시도되게 한다.
_GEOCODE_CACHE_TTL_OK = 604800  # 7일
_GEOCODE_CACHE_TTL_MISS = 300   # 5분


class NearbyMapService:
    """주변 실거래 지도 페이로드 생성기."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.molit = MolitClient()
        self._geo_key = getattr(self.settings, "vworld_api_key", "") or ""

    # ── 공개 진입점 ──
    async def build(
        self,
        address: str,
        lawd_cd: str,
        months: int = 3,
        radius_m: int = 1000,
        sigungu_hint: str = "",
        center_hint: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        # center_hint: 라우터가 PNU/좌표 확보 과정(주소 지오코딩·point→parcel)에서 이미 얻은
        #   중심좌표. 여기서 다시 주소 지오코딩이 실패해도 이 힌트로 center를 채워, 지도가
        #   선택 필지 위치로 이동한다(백엔드 지오코딩 실패와 무관하게 서울 폴백 제거).
        hint_lat = (center_hint or {}).get("lat")
        hint_lon = (center_hint or {}).get("lon")
        has_hint = bool(hint_lat and hint_lon)

        # 0) 결과 캐시 조회 — 동일 조건 재조회는 즉시 반환(수 초 → 수 ms)
        cache_key = ((address or "").strip(), f"{lawd_cd}", months, radius_m)
        hit = _BUILD_CACHE.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _BUILD_CACHE_TTL:
            cached = hit[1]
            # 캐시된 결과에 center가 비어 있고(과거 지오코딩 실패분) 지금은 힌트가 있으면 보강.
            if has_hint and not (cached.get("center") or {}).get("lat"):
                cached = {**cached, "center": {"lat": hint_lat, "lon": hint_lon, "address": address}}
            return cached

        ym_list = self._recent_months(months)

        # 1) 카테고리별 실거래 수집(병렬) + 시도/실패 집계
        trade_res, rent_res = await asyncio.gather(
            self._collect(self.molit.get_transactions, _TRADE_TYPES, lawd_cd, ym_list),
            self._collect(self.molit.get_rent_transactions, _RENT_TYPES, lawd_cd, ym_list),
        )
        trade_raw, t_fail, t_att = trade_res
        rent_raw, r_fail, r_att = rent_res

        # 2) 건물단위 그룹핑
        categories: dict[str, dict[str, Any]] = {}
        for tkey, tlabel in _TRADE_TYPES:
            categories[f"{tkey}_trade"] = self._group_trade(
                tkey, f"{tlabel} 매매", trade_raw.get(tkey, []), sigungu_hint
            )
        for tkey, tlabel in _RENT_TYPES:
            categories[f"{tkey}_rent"] = self._group_rent(
                tkey, f"{tlabel} 전월세", rent_raw.get(tkey, []), sigungu_hint
            )

        # 3) 고유 지오코딩 쿼리 수집 → dedupe → 병렬 지오코딩
        # ★지오코딩 사전 컷(R1 P2): 캡(28)을 반경 필터 뒤로 옮기면서 지오코딩 대상이 시군구
        #   전체 건물로 확대될 수 있다(대형 시군구 콜드로드에서 수백~천 건 → 수십 초 지연·쿼터
        #   소모). 카테고리별 거래건수 상위 _MAX_GEOCODE_GROUPS_PER_CAT 건만 지오코딩 대상으로
        #   사전 컷해 콜드 비용을 상수로 묶는다. 반경 내 상위 28건 정합성은 사전 컷 폭(80)이
        #   최종 캡(28)보다 충분히 넓어 실용상 유지된다. 컷된 그룹 수는 정직 카운트로 노출.
        geocode_precut = 0
        for cat in categories.values():
            if len(cat["groups"]) > _MAX_GEOCODE_GROUPS_PER_CAT:
                cat["groups"].sort(key=lambda x: x["count"], reverse=True)
                geocode_precut += len(cat["groups"]) - _MAX_GEOCODE_GROUPS_PER_CAT
                cat["groups"] = cat["groups"][:_MAX_GEOCODE_GROUPS_PER_CAT]
        queries: set[str] = set()
        for cat in categories.values():
            for grp in cat["groups"]:
                queries.add(grp["_query"])
        coords = await self._geocode_many(sorted(queries))

        # 4) 중심좌표 확보: (1) 이미 지오코딩된 주소 좌표 → (2) 주소 재지오코딩 → (3) 라우터 힌트.
        #   ★(3) 힌트가 있으면 자체 지오코딩이 실패해도 center가 null로 남지 않는다(서울 폴백 방지).
        center = coords.get(address.strip()) or await self._geocode_one(address.strip())
        if not center and has_hint:
            center = {"lat": hint_lat, "lon": hint_lon, "address": address}
        center_lat = (center or {}).get("lat")
        center_lon = (center or {}).get("lon")
        # 반경 필터는 중심좌표와 radius_m 이 모두 있어야 의미가 있다. 중심좌표가 없으면
        # (지오코딩 전면 실패 + 힌트도 없음) radius_m 은 여전히 "요청값"으로만 에코되고
        # 실제 필터링은 하지 않는다 — 그 사실을 radius_applied=False 로 정직 표기한다.
        radius_applied = bool(center_lat and center_lon and radius_m)

        # 5) 좌표 주입 + 반경 필터(★실구현 — 종전엔 radius_m 을 필터에 전혀 쓰지 않고
        #    result["radius_m"]에 요청값을 에코만 해 라벨이 거짓이었다) + 좌표 미확보 그룹 보존
        #    (반경 밖으로 단정하지 않는다 — 무날조) + 상한(_MAX_GROUPS_PER_CAT)은 반경 필터
        #    이후에 적용한다(순서: 지오코딩 → 반경 필터 → 캡).
        groups_evaluated = 0   # 좌표 확보 후 반경 판정 대상이 된 그룹 수(필터 "전")
        filtered_out = 0       # 반경 밖으로 제외된 그룹 수
        coords_unresolved = 0  # 좌표 미확보로 반경 판정 자체가 불가능했던 그룹 수(보존)
        for cat in categories.values():
            resolved: list[dict] = []
            unresolved: list[dict] = []
            for grp in cat["groups"]:
                c = coords.get(grp.pop("_query"))
                if not c:
                    # 좌표 미확보 — 제외하지 않고 보존한다(반경 밖 단정 금지). 지도 마커로는
                    # 못 찍지만(lat/lon 없음), 실거래 데이터 자체는 응답에 남는다.
                    unresolved.append(grp)
                    continue
                grp["lat"], grp["lon"] = c["lat"], c["lon"]
                resolved.append(grp)
            coords_unresolved += len(unresolved)

            if radius_applied:
                groups_evaluated += len(resolved)
                in_radius = []
                for grp in resolved:
                    dist_km = PostGISHelper.st_distance(center_lat, center_lon, grp["lat"], grp["lon"])
                    if dist_km * 1000.0 <= radius_m:
                        in_radius.append(grp)
                filtered_out += len(resolved) - len(in_radius)
                resolved = in_radius

            # 거래 많은 순 정렬 후 상한 — ★반경 필터 이후에 캡을 적용해야 "반경 내 상위 N건"이
            # 된다(캡을 필터보다 먼저 적용하면 시군구 전체 상위 N건이 되어 radius_m 이 무의미).
            resolved.sort(key=lambda x: x["count"], reverse=True)
            capped = resolved[:_MAX_GROUPS_PER_CAT]
            # ★절단 정직 고지: 캡(28)에 걸려 응답에서 빠진 그룹 수를 카테고리별로 센다.
            #   종전엔 이 절단을 아무도 세지 않아 프론트가 "다 보여준다"고 오인할 여지가 있었다
            #   (geocode_precut_count·radius_filtered_out_count와 동일한 정직 원칙 — #459 계보).
            cat["capped_count"] = max(0, len(resolved) - _MAX_GROUPS_PER_CAT)
            cat["groups"] = capped + unresolved
            cat["count"] = sum(g["count"] for g in cat["groups"])
            # ★근본수정(P0) — 반경을 **실제로 통과한** 그룹을 따로 보관한다.
            #   종전엔 `capped + unresolved`를 한 리스트로만 내보내 소비처가 둘을 구분할 수
            #   없었고, 그 결과 AVM이 **반경 판정을 받은 적도 없는** 그룹으로 계산됐다
            #   (호미곶 실측: 반경 통과 0건인데 AVM 표본 32건 — 전부 좌표미확보분).
            cat["_in_radius_groups"] = capped
            # 카운트도 분리 노출한다. 하나로 합치면 프론트가 "반경 내 N건"으로 오독한다.
            cat["count_in_radius"] = sum(g["count"] for g in capped)
            cat["count_unresolved"] = sum(g["count"] for g in unresolved)

        # ★내부 전용 필드 정리 — `_in_radius_groups`는 AVM 계산용이고 그대로 두면 응답
        #   페이로드가 그룹만큼 중복된다(대형 시군구에서 수 MB). 소비 후 제거한다.
        avm_summary = self._compute_avm_summary(
            categories.get("apt_trade"), radius_applied=radius_applied, radius_m=radius_m,
        )
        avm_caveat = self._avm_caveat(
            categories.get("apt_trade"), radius_applied=radius_applied, radius_m=radius_m,
        )
        # ★계약 불변식(R3-MED-2) — **거래가 있는데 시세도 없고 사유도 없는** 상태를 봉인한다.
        #   `_compute_avm_summary`와 `_avm_caveat`은 서로를 모른 채 독립 계산하므로,
        #   예컨대 반경 통과 그룹은 있는데 그 그룹의 가격·면적이 전부 결측이면
        #   전자는 None, 후자도 None이 되어 화면이 다시 "실거래가 없어 추정 불가"라는
        #   **거짓 문장**을 낸다(거래는 있는데). 이 모순은 R1→R2→R3에서 **세 번 다른 경로로**
        #   나왔다 — 개별 분기를 땜질하지 말고 여기서 한 번에 막는다.
        _apt = categories.get("apt_trade") or {}
        if avm_summary is None and (_apt.get("groups") or []) and not avm_caveat:
            avm_caveat = (
                "수집된 아파트 실거래는 있으나 가격·면적 정보가 부족해 시세를 산정하지 "
                "못했습니다(거래가 없는 것이 아닙니다)."
            )
        for _cat in categories.values():
            _cat.pop("_in_radius_groups", None)

        result: dict[str, Any] = {
            "center": center or {"lat": None, "lon": None, "address": address},
            "radius_m": radius_m,
            # ★프론트 라벨 연동용 additive 필드 — 반경 필터가 실제로 적용됐는지와 그 전/후 카운트.
            "radius_applied": radius_applied,
            "groups_evaluated_count": groups_evaluated,
            "radius_filtered_out_count": filtered_out,
            "coords_unresolved_count": coords_unresolved,
            "geocode_precut_count": geocode_precut,
            "lawd_cd": lawd_cd,
            "months": ym_list,
            "categories": categories,
            # ★AVM SSOT 일원화(PropAI#3): 아파트 매매 실거래 그룹(반경 필터·캡 적용 후,
            #   위 categories와 동일 객체) 통계로 AI 시세를 계산해 함께 싣는다 — 프론트가
            #   같은 payload를 재가공(평당가 가중평균+CV)하던 것을 여기로 이동(SSOT).
            # ★근본수정(P0): AVM은 **반경을 통과한 그룹만**으로 계산한다. 통과분이 없으면
            #   시세를 만들지 않고 사유를 말한다(무날조 — 기존 "표본 0건이면 None" 원칙을
            #   반경 기준으로 확장). 종전엔 위치를 모르는 원거리 아파트로 임야 시세를 냈다.
            "avm": avm_summary,
            # ★AVM **신뢰성 단서**(additive) — 없으면 None.
            #   ★R2 HIGH-1 교훈: 종전 이름 `avm_unavailable_reason`은 "AVM이 **없을** 때의
            #   사유"라는 **잘못된 멘탈모델을 인코딩**했고, 그 탓에 프론트 배선이 자연스럽게
            #   빈 상태 가지로만 갔다. 그런데 가장 위험한 단서(반경 필터 미적용)는 **AVM이
            #   존재할 때** 붙는다 — 즉 경고가 구조적으로 도달 불가능해졌다.
            #   이름이 곧 계약이다: 이 필드는 **AVM 유무와 무관하게** 붙을 수 있고,
            #   소비처는 **두 경우 모두** 표시해야 한다.
            "avm_caveat": avm_caveat,
            # 구 이름 호환(같은 값) — 외부 소비처가 있을 수 있어 한 릴리스 유지.
            "avm_unavailable_reason": avm_caveat,
        }

        # ★정직 표기: 공공데이터 조회 실패와 "거래 0건(실제 없음)"을 구분한다.
        #   - 전건 실패 = 국토부 실거래 API 무응답/서킷OPEN → data_source=unavailable(빈 표시는 거짓).
        #   - 일부 실패 = 표시 건수가 일부일 수 있음.
        total_att = t_att + r_att
        total_fail = t_fail + r_fail
        fetch_failed = total_att > 0 and total_fail >= total_att
        if fetch_failed:
            result["data_source"] = "unavailable"
            result["fetch_failed"] = True
            result["note"] = (
                "국토부 실거래 공공데이터가 응답하지 않습니다(데이터포털 지연·점검 추정). "
                "거래가 없는 것이 아니라 일시적 조회 실패이며, 잠시 후 다시 시도해 주세요."
            )
        else:
            result["data_source"] = "molit_live"
            if total_fail > 0:
                result["partial_failed"] = True
                result["note"] = (
                    "일부 유형의 실거래 데이터를 불러오지 못했습니다(공공데이터 응답 지연). "
                    "표시된 건수는 일부일 수 있습니다."
                )

        # 결과 캐시 저장(+ 상한 초과 시 가장 오래된 항목 제거).
        # ★실패 결과는 캐싱하지 않는다 — 복구 후에도 TTL 동안 거짓 빈값이 고정되는 것 방지.
        if not fetch_failed:
            _BUILD_CACHE[cache_key] = (time.monotonic(), result)
            if len(_BUILD_CACHE) > _BUILD_CACHE_MAX:
                oldest = min(_BUILD_CACHE, key=lambda k: _BUILD_CACHE[k][0])
                _BUILD_CACHE.pop(oldest, None)
        return result

    # ── 수집 ──
    @staticmethod
    def _recent_months(months: int) -> list[str]:
        # 현재월은 신고지연으로 데이터가 거의 없음 → 직전월부터 수집
        now = datetime.now()
        y, m = now.year, now.month
        m -= 1
        if m == 0:
            m = 12
            y -= 1
        out = []
        for _ in range(months):
            out.append(f"{y}{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return out

    async def _collect(self, fetch, types, lawd_cd, ym_list) -> tuple[dict[str, list], int, int]:
        # 호출 시도/실패 수를 함께 집계한다. MOLIT 클라이언트는 타임아웃·서킷OPEN 시
        # ExternalServiceError 를 던지므로(그것이 여기 except 로 옴), 이를 세어
        # "거래 0건(실제 없음)" 과 "공공데이터 조회 실패(빈 표시는 거짓)" 를 구분한다.
        stats = {"fail": 0, "attempt": 0}

        async def one(pt: str) -> tuple[str, list]:
            rows: list = []
            for ym in ym_list:
                stats["attempt"] += 1
                try:
                    rows.extend(await fetch(lawd_cd, ym, prop_type=pt, num_rows=1000))
                except Exception as e:  # noqa: BLE001
                    stats["fail"] += 1
                    logger.debug("실거래 수집 실패", pt=pt, ym=ym, err=str(e)[:60])
            return pt, rows

        results = await asyncio.gather(*[one(pt) for pt, _ in types])
        return dict(results), stats["fail"], stats["attempt"]

    # ── 그룹핑 ──
    def _query_for(self, sigungu: str, dong: str, jibun: str, name: str) -> str:
        sgg = (sigungu or "").strip()
        if jibun:
            return f"{sgg} {dong} {jibun}".strip()
        if name:
            return f"{dong} {name}".strip()
        return f"{sgg} {dong}".strip()

    def _group_trade(self, type_key, label, rows, sigungu_hint) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = (r.get("building_name") or "").strip()
            jibun = (r.get("jibun") or "").strip()
            dong = (r.get("dong") or "").strip()
            sigungu = (r.get("sigungu") or sigungu_hint or "").strip()
            key = name or jibun or dong
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": name or (f"{dong} {jibun}".strip() or "물건"),
                "dong": dong, "jibun": jibun,
                "_query": self._query_for(sigungu, dong, jibun, name),
                # ★실무 판단정보(그룹 대표값) — molit_client가 이미 파싱해 넘기는 build_year/
                #   jimok/land_use(토지 매매 전용)를 종전엔 여기서 폐기했다. 관측된 고유값을
                #   집합으로 모아두고(대표값 확정은 _finalize에서 — 혼재 검출을 위해), 원천에
                #   없으면 빈 채로 남는다(무날조).
                "_build_years": set(), "_jimoks": set(), "_land_uses": set(),
                "deals": [], "_prices": [], "_areas": [],
            })
            price = int(r.get("price_10k_won") or 0)
            area = float(r.get("area_m2") or 0)
            if price > 0:
                g["_prices"].append(price)
            if area > 0:
                g["_areas"].append(area)
            if r.get("build_year"):
                g["_build_years"].add(r.get("build_year"))
            jimok_v = (r.get("jimok") or "").strip()
            if jimok_v:
                g["_jimoks"].add(jimok_v)
            land_use_v = (r.get("land_use") or "").strip()
            if land_use_v:
                g["_land_uses"].add(land_use_v)
            g["deals"].append({
                "price_10k_won": price, "area_m2": area,
                "floor": r.get("floor"), "deal_date": r.get("deal_date"),
            })
        return self._finalize(type_key, label, "trade", groups)

    def _group_rent(self, type_key, label, rows, sigungu_hint) -> dict[str, Any]:
        groups: dict[str, dict[str, Any]] = {}
        for r in rows:
            name = (r.get("building_name") or "").strip()
            jibun = (r.get("jibun") or "").strip()
            dong = (r.get("dong") or "").strip()
            sigungu = (r.get("sigungu") or sigungu_hint or "").strip()
            key = name or jibun or dong
            if not key:
                continue
            g = groups.setdefault(key, {
                "name": name or (f"{dong} {jibun}".strip() or "물건"),
                "dong": dong, "jibun": jibun,
                "_query": self._query_for(sigungu, dong, jibun, name),
                "deals": [], "_deposits": [], "_monthlies": [], "_areas": [],
            })
            dep = int(r.get("deposit_10k_won") or 0)
            mon = int(r.get("monthly_rent_10k_won") or 0)
            area = float(r.get("area_m2") or 0)
            if dep > 0:
                g["_deposits"].append(dep)
            if mon > 0:
                g["_monthlies"].append(mon)
            if area > 0:
                g["_areas"].append(area)
            g["deals"].append({
                "deposit_10k_won": dep, "monthly_rent_10k_won": mon,
                "area_m2": area, "floor": r.get("floor"), "deal_date": r.get("deal_date"),
            })
        return self._finalize(type_key, label, "rent", groups)

    def _finalize(self, type_key, label, kind, groups) -> dict[str, Any]:
        out = []
        for g in groups.values():
            cnt = len(g["deals"])
            areas = g.pop("_areas", [])
            g["count"] = cnt
            g["avg_area_m2"] = round(sum(areas) / len(areas), 1) if areas else 0
            # ★대표값 혼재 완화(R1 후속 — 레인G R2 항목3): 그룹 키가 건물명·지번 없이 법정동
            #   (dong)으로만 폴백되면 서로 다른 필지의 거래가 한 그룹에 섞일 수 있다(주로 토지
            #   매매에서 건물명이 없는 행). 이 경우 build_year/jimok/land_use "첫 값"만 대표로
            #   보이면 실제로는 여러 필지가 섞였는데 그중 하나의 속성만 그룹 전체인 것처럼
            #   오도한다 — 지목·용도지역은 개발 판단에 직결되는 정보라 피해가 크다.
            #   무음 위험 비교: (a)혼재 시 미표기(None)는 "정보 없음"으로만 보이는 결측 —
            #   기존 age_status 무자료 패턴과 동일한 안전한 실패 모드. (b)"대표 필지 기준"
            #   캡션 부기는 사용자가 캡션을 놓치면 그룹 전체 속성으로 오인하는 정보 왜곡
            #   실패 모드라 더 위험하다. 따라서 (a) 미표기를 채택 — 고유값이 정확히 1개일
            #   때만 대표값을 확정하고, 0개(무자료) 또는 2개 이상(혼재)이면 None.
            build_years = g.pop("_build_years", set())
            jimoks = g.pop("_jimoks", set())
            land_uses = g.pop("_land_uses", set())
            g["build_year"] = next(iter(build_years)) if len(build_years) == 1 else None
            g["jimok"] = next(iter(jimoks)) if len(jimoks) == 1 else None
            g["land_use"] = next(iter(land_uses)) if len(land_uses) == 1 else None
            if kind == "trade":
                p = g.pop("_prices", [])
                # ★대표통계(이상치 제거) — 지분·정정 등 미미거래·초고가 왜곡 방지(공용 헬퍼).
                _s = robust_price_stats(p)
                g["avg_price_10k"] = _s["avg"]
                g["min_price_10k"] = _s["min"]
                g["max_price_10k"] = _s["max"]
                g["excluded_outliers"] = _s["excluded"]
            else:
                d = g.pop("_deposits", [])
                m = g.pop("_monthlies", [])
                g["avg_deposit_10k"] = round(sum(d) / len(d)) if d else 0
                g["avg_monthly_10k"] = round(sum(m) / len(m)) if m else 0
            # ★최신순 정렬 후 절단 — 무정렬 [:10]은 최신 거래를 잘라낼 수 있다(수집 순서는
            #   MOLIT 응답 순서일 뿐 날짜순이 아님). 파싱 실패분(날짜 없음)은 최하위로 보존.
            g["deals"].sort(key=lambda d: parse_deal_date(d.get("deal_date")) or (0, 0, 0), reverse=True)
            g["deals"] = g["deals"][:10]
            out.append(g)
        # 거래 많은 순 정렬. ★상한(_MAX_GROUPS_PER_CAT)은 여기서 적용하지 않는다 — build()가
        #   지오코딩·반경 필터 이후에 적용한다. 여기서 캡을 걸면 "반경 내 상위 N건"이 아니라
        #   "시군구 전체 상위 N건"이 되어 radius_m 라벨이 실제 필터와 무관한 거짓 표기가 된다.
        out.sort(key=lambda x: x["count"], reverse=True)
        return {"label": label, "type": type_key, "kind": kind,
                "count": sum(x["count"] for x in out), "groups": out}

    # ── AI 시세(AVM) 요약 ──
    @staticmethod
    def _js_round(x: float) -> int:
        """JS `Math.round` 방식(0.5는 항상 올림)으로 반올림한다.

        Python 내장 `round()`는 banker's rounding(가장 가까운 짝수로 반올림)이라 종전
        프론트 계산(Math.round)과 .5 경계에서 값이 어긋날 수 있다 — 이 함수는 값 동일성
        (프론트 재구현 이전과 이후 산출값이 정확히 같아야 함)을 보장하기 위한 것.
        본 서비스에서 다루는 값(가격·면적·CV%)은 항상 0 이상이라 이 구현으로 충분하다.
        """
        return math.floor(x + 0.5)

    @staticmethod
    def _avm_caveat(
        apt_trade_category: dict[str, Any] | None,
        *,
        radius_applied: bool,
        radius_m: int | None,
    ) -> str | None:
        """AVM의 **신뢰성 단서**를 말한다(무날조 — 침묵 대신 사유).

        ★AVM이 **없을 때**(사유)와 **있지만 반경 보증이 없을 때**(경고)를 모두 반환한다.
          후자가 더 위험하다 — 확신에 찬 숫자에 아무 표시가 없으면 사용자는 그대로 믿는다.

        ★"거래가 아예 없다"와 "거래는 있는데 반경 안에서 위치가 확인된 게 없다"는 전혀 다른
          상태다. 종전엔 둘 다 조용히 null이라 사용자는 구분할 수 없었고, 그 사이 화면은
          **위치를 모르는 원거리 거래로 만든 시세**를 보여주고 있었다.
        """
        cat = apt_trade_category or {}
        all_groups = cat.get("groups") or []
        if not all_groups:
            return None  # 진짜로 거래가 없다 — 기존 "무자료" 표기로 충분
        if radius_applied:
            if not (cat.get("_in_radius_groups") or []):
                return (
                    f"반경 {radius_m}m 안에서 위치가 확인된 아파트 실거래를 찾지 못했습니다"
                    f"(위치 미확인 {len(all_groups)}곳은 시세 산정에 쓰지 않습니다)."
                )
            return None
        # ★반경 미적용(중심좌표 확보 실패) — 좌표가 있는 그룹만 쓰되, **반경 보증이 없다는
        #   사실**을 반드시 말한다. 종전엔 이 경로에서 사유가 None이라 사용자에게 아무
        #   경고도 없이 시군구 전역 거래로 만든 시세가 나갔다.
        resolved = [g for g in all_groups if g.get("lat") is not None]
        if not resolved:
            return (
                f"위치가 확인된 아파트 실거래가 없어 시세를 산정하지 않았습니다"
                f"(수집 {len(all_groups)}곳 전부 위치 미확인)."
            )
        return (
            "대상지 중심좌표를 확보하지 못해 반경 필터를 적용하지 못했습니다 — "
            f"아래 시세는 시군구 범위의 위치 확인분 {len(resolved)}곳 기준이며 "
            "대상지 인근이라는 보증이 없습니다."
        )

    def _compute_avm_summary(
        self,
        apt_trade_category: dict[str, Any] | None,
        *,
        radius_applied: bool = False,
        radius_m: int | None = None,
    ) -> dict[str, Any] | None:
        """아파트 매매 실거래 그룹(**반경 통과분만**) 통계로 AI 시세(AVM) 요약을 계산한다.

        ★근본수정(P0) — 종전 도크스트링은 "반경 필터·캡 적용 후"라고 적혀 있었으나 실제
          입력은 `capped + unresolved`였다(주석과 코드 불일치). 그래서 **반경 판정을 받은
          적조차 없는** 좌표미확보 그룹이 시세를 만들었다. 호미곶 임야 실측: 반경 통과 0건인데
          AVM 1,490,069원/㎡ — 근거는 20km 밖 아파트였다. 이제 `_in_radius_groups`만 쓴다.

        SSOT 일원화(PropAI 아이디어#3): 종전엔 프론트(MarketInsightsWorkspaceClient.tsx
        deriveResults :196-238)가 이 서비스의 apt_trade 응답을 다시 순회해 재계산했다 —
        그 로직을 그대로(재구현 아님) 이 메서드로 이식했을 뿐 계산방식은 불변이다.

        - 시세: 그룹별 평당가(avg_price_10k / (avg_area_m2/평)) 를 그룹 거래건수(count)로
          가중평균 → 84㎡ 환산 총액·㎡당 시세.
        - 신뢰도: 개별 거래가(price_10k_won) 표본의 변동계수(CV=표준편차/평균) 기반 —
          표본이 많고(count 항) 가격이 고르게 형성될수록(CV 항, 낮을수록 가산) 신뢰도가
          높다. 두 항을 절반씩 반영해 0.3~0.98로 클램프.
        - 표본(비교 가능한 그룹) 0건이면 None — 무날조.
        """
        cat = apt_trade_category or {}
        # ★반경 필터가 적용된 경우에만 통과분으로 한정한다. 미적용(중심좌표 없음 등)이면
        #   반경 개념 자체가 없으므로 종전처럼 전체를 쓰되, 아래 basis가 그 사실을 밝힌다.
        if radius_applied:
            groups = cat.get("_in_radius_groups") or []
            if not groups:
                # ★반경 안에 비교 대상이 없다 → **None**(기존 계약 유지 — 소비처가
                #   `payload.avm ?? null`로 읽어 "미제공"으로 graceful 처리한다).
                #   사유는 응답 최상위 `avm_unavailable_reason`으로 **additive** 제공한다.
                #   여기서 truthy 객체를 돌려주면 기존 소비처가 0원·NaN을 그린다.
                return None
        else:
            # ★R1 HIGH-2 봉합 — 종전 `else` 가지는 **좌표 미확인 그룹을 포함한 전체**를 썼다.
            #   즉 봉합 대상 결함(위치를 모르는 거래로 시세를 만든다)이 이 가지에 그대로
            #   살아 있었고, 게다가 이 경로는 **생산에서 도달 가능**하다:
            #   라우터의 `center_hint`는 `lawd_cd`가 없을 때만 계산되므로, 프론트가 pnu/bcode를
            #   정상 공급하는 주경로(사통맵 필지 선택)에서는 힌트가 없고, 내부 주소 지오코딩이
            #   실패하면 `radius_applied=False`가 된다 — 지오코딩이 잘 실패하는 모집단이
            #   바로 산 지번·농어촌 주소(호미곶이 속한 그 모집단)다.
            #   반경 판정은 못 해도 **좌표조차 없는 그룹은 배제**한다(무날조는 반경 적용
            #   여부에 따라 켜졌다 꺼졌다 하면 안 된다).
            groups = [g for g in (cat.get("groups") or []) if g.get("lat") is not None]
        if not groups:
            return None

        pp_sum = 0.0
        pp_n = 0
        for g in groups:
            avg_price_10k = g.get("avg_price_10k")
            avg_area_m2 = g.get("avg_area_m2") or 0
            if avg_price_10k and avg_area_m2 > 0:
                per_pyeong = avg_price_10k / (avg_area_m2 / PYEONG_SQM)
                cnt = g.get("count") or 1
                pp_sum += per_pyeong * cnt
                pp_n += cnt
        if pp_n <= 0:
            return None

        per_pyeong = pp_sum / pp_n          # 만원/평
        per_m2_man = per_pyeong / PYEONG_SQM  # 만원/㎡

        deal_prices = [
            d.get("price_10k_won")
            for g in groups
            for d in (g.get("deals") or [])
            if isinstance(d.get("price_10k_won"), (int, float)) and d.get("price_10k_won") > 0
        ]

        confidence = 0.5  # 개별 거래가 표본이 없는 비정상 케이스 폴백(프론트와 동일)
        cv_percent = 0.0
        if deal_prices:
            n = len(deal_prices)
            mean = sum(deal_prices) / n
            variance = sum((p - mean) ** 2 for p in deal_prices) / n
            cv = (math.sqrt(variance) / mean) if mean > 0 else 0.0
            cv_percent = cv * 100
            count_factor = min(1.0, math.log10(n + 1) / 2)  # 표본 ~100건에서 포화
            dispersion_factor = max(0.0, 1 - cv / 0.5)  # CV 0~50% 구간을 1→0으로 선형 감산
            confidence = 0.4 + 0.3 * count_factor + 0.3 * dispersion_factor

        return {
            "estimated_price": self._js_round(per_m2_man * 84 * 10000),
            "price_per_sqm": self._js_round(per_m2_man * 10000),
            "confidence_score": min(0.98, max(0.3, confidence)),
            # ★`comparable_count`는 이름과 달리 "비교 **거래** 건수"였다(그룹 수 아님).
            #   기존 소비처 무회귀를 위해 값은 유지하되, 이제 **반경 통과분 기준**이고
            #   의미가 분명한 별칭을 함께 낸다.
            "comparable_count": sum(g.get("count") or 0 for g in groups),
            "comparable_deal_count": sum(g.get("count") or 0 for g in groups),
            "comparable_group_count": len(groups),
            "sample_count": len(deal_prices),
            "price_cv_percent": self._js_round(cv_percent),
            # ★근거 표기 — 이 시세가 **무엇으로부터** 나왔는지 소비처가 알 수 있어야 한다.
            "basis": {
                "radius_applied": radius_applied,
                "radius_m": radius_m,
                "in_radius_group_count": len(groups) if radius_applied else None,
                "scope": "in_radius" if radius_applied else "all_groups_radius_not_applied",
            },
        }

    # ── 공개 지오코딩(다른 서비스 재사용·캐시 공유) ──
    async def geocode_addresses(self, queries: list[str]) -> dict[str, dict]:
        """주소 리스트 → {주소: {lat, lon}} (VWorld, 7일 캐시 공유). 분양정보 등에서 재사용."""
        return await self._geocode_many(queries)

    async def geocode_one(self, query: str) -> dict | None:
        return await self._geocode_one(query)

    # ── 지오코딩(카카오 로컬 + Redis 캐시) ──
    async def _redis(self):
        try:
            import redis.asyncio as aioredis
            return aioredis.from_url(self.settings.redis_url)
        except Exception:
            return None

    async def _geocode_many(self, queries: list[str]) -> dict[str, dict]:
        if not queries or not self._geo_key:
            return {}
        sem = asyncio.Semaphore(_GEOCODE_CONCURRENCY)
        async with httpx.AsyncClient(timeout=12.0) as client:
            async def run(q):
                async with sem:
                    return q, await self._geocode_one(q, client)
            pairs = await asyncio.gather(*[run(q) for q in queries])
        return {q: c for q, c in pairs if c}

    async def _geocode_one(self, query: str, client: httpx.AsyncClient | None = None) -> dict | None:
        if not query or not self._geo_key:
            return None
        cache_key = f"geo:vworld:{query}"
        r = await self._redis()
        if r is not None:
            try:
                cached = await r.get(cache_key)
                if cached:
                    await r.aclose()
                    val = json.loads(cached)
                    return val or None
            except Exception:
                pass
        own = client is None
        if own:
            client = httpx.AsyncClient(timeout=12.0)
        coord = None
        try:
            base = {
                "key": self._geo_key, "service": "address",
                "request": "getcoord", "format": "json",
            }
            # 지번주소=PARCEL 우선, 도로명=ROAD 폴백
            for addr_type in ("PARCEL", "ROAD"):
                try:
                    resp = await client.get(
                        _VWORLD_GEOCODE_URL, params={**base, "address": query, "type": addr_type}
                    )
                    if resp.status_code != 200:
                        continue
                    j = resp.json()
                    if j.get("response", {}).get("status") == "OK":
                        pt = j["response"]["result"]["point"]
                        coord = {"lat": float(pt["y"]), "lon": float(pt["x"])}
                        break
                except Exception:
                    continue
        finally:
            if own:
                await client.aclose()
        if r is not None:
            try:
                # ★성공은 7일, 실패/미해결은 5분만 캐시 — 일시 실패가 장기 고착되지 않게 한다.
                ttl = _GEOCODE_CACHE_TTL_OK if coord else _GEOCODE_CACHE_TTL_MISS
                await r.setex(cache_key, ttl, json.dumps(coord or {}))
                await r.aclose()
            except Exception:
                pass
        return coord
